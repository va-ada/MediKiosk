import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, USE_FIXTURES, api } from '../api/client'
import type { Department, Outcome, OutcomeRequest, QueueItem } from '../api/types'

interface Props {
  sessionId: string
  /** Department of the session's token (from the summary) — the queue to look the token up in. */
  department: Department
  tokenDisplay: string
}

const DEPARTMENTS: { value: Department; label: string }[] = [
  { value: 'general', label: 'General OPD' },
  { value: 'ayurveda', label: 'Ayurveda OPD' },
]

const OUTCOMES: { value: Outcome; label: string; className: string }[] = [
  { value: 'out', label: 'Out', className: 'bg-brand-green text-white' },
  { value: 'recheck', label: 'Recheck', className: 'bg-brand-orange text-white' },
  { value: 'refer', label: 'Refer', className: 'bg-navy text-white' },
  { value: 'followup', label: 'Follow-up', className: 'bg-slate-700 text-white' },
]

/** Local YYYY-MM-DD, `days` from today. */
function localDate(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** What will happen, in words, for the confirm step (§10.3). */
function consequence(o: Outcome, display: string, form: FormState): string {
  switch (o) {
    case 'out':
      return `${display} is done: the visit closes and the record is queued for the hospital system.`
    case 'recheck':
      return form.resultsTomorrow
        ? `${display} closes today; a priority token for tomorrow is reserved for you.`
        : `${display} goes back to the queue as priority, reserved for you.`
    case 'refer':
      return `${display} is referred: a new priority token is issued in ${
        DEPARTMENTS.find((d) => d.value === form.referDepartment)?.label ?? form.referDepartment
      }.`
    case 'followup':
      return `${display} is done; follow-up on ${form.followupDate}${form.admit ? ', marked for admission' : ''}.`
  }
}

interface FormState {
  note: string
  resultsTomorrow: boolean
  referDepartment: Department
  followupDate: string
  admit: boolean
}

/** Sticky footer on the patient view: Out / Recheck / Refer / Follow-up → confirm → `POST /api/tokens/{id}/outcome`. */
export default function OutcomeBar({ sessionId, department, tokenDisplay }: Props) {
  const navigate = useNavigate()
  const [token, setToken] = useState<QueueItem | null>(null)
  const [lookup, setLookup] = useState<'loading' | 'found' | 'none' | 'error'>('loading')
  const [dialog, setDialog] = useState<Outcome | null>(null)
  const [form, setForm] = useState<FormState>(() => ({
    note: '',
    resultsTomorrow: false,
    referDepartment: department === 'ayurveda' ? 'general' : 'ayurveda',
    followupDate: localDate(7),
    admit: false,
  }))
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The summary has no token id: find this session's active (called / in) token in the queue.
  const findToken = useCallback(async (): Promise<void> => {
    try {
      const items = await api<QueueItem[]>('GET', `/api/queue?department=${department}`)
      const t = items.find((i) => i.session_id === sessionId && (i.status === 'in' || i.status === 'called')) ?? null
      setToken(t)
      setLookup(t ? 'found' : 'none')
    } catch {
      setLookup('error')
    }
  }, [department, sessionId])

  useEffect(() => {
    void findToken()
  }, [findToken])

  const open = (o: Outcome): void => {
    setError(null)
    setDialog(o)
    void findToken()
  }
  const close = (): void => {
    if (!sending) setDialog(null)
  }

  useEffect(() => {
    if (!dialog) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const confirm = async (): Promise<void> => {
    if (!dialog || !token) return
    if (USE_FIXTURES) {
      setError('Fixture mode — outcomes are not sent to the server.')
      return
    }
    const body: OutcomeRequest = { outcome: dialog }
    const note = form.note.trim()
    if (note) body.note = note
    if (dialog === 'recheck') body.results_tomorrow = form.resultsTomorrow
    if (dialog === 'refer') body.refer_department = form.referDepartment
    if (dialog === 'followup') {
      body.followup_date = form.followupDate
      body.admit = form.admit
    }
    setSending(true)
    setError(null)
    try {
      await api<QueueItem>('POST', `/api/tokens/${token.id}/outcome`, body)
      void navigate('/doctor')
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === 'invalid_state'
          ? 'This token is no longer with you (already closed or moved). Go back to the queue.'
          : e instanceof ApiError
            ? e.message
            : 'Could not record the outcome',
      )
      void findToken()
    } finally {
      setSending(false)
    }
  }

  const followupInvalid = dialog === 'followup' && !(form.followupDate >= localDate(1))
  const label = OUTCOMES.find((o) => o.value === dialog)?.label ?? ''
  const set = <K extends keyof FormState>(key: K, value: FormState[K]): void => setForm((f) => ({ ...f, [key]: value }))
  const inputCls = 'mt-1 w-full rounded-md border border-slate-300 px-3 py-2'

  return (
    <>
      <footer className="sticky bottom-0 z-10 flex flex-wrap items-center gap-2 border-t border-slate-200 bg-white px-4 py-2">
        <span className="mr-auto text-sm text-slate-600">
          {lookup === 'loading' && 'Finding token…'}
          {lookup === 'found' && token && (
            <>
              Outcome for <span className="font-mono font-semibold">{token.display}</span>
            </>
          )}
          {lookup === 'none' && `${tokenDisplay} is not called or in consultation — no outcome to record.`}
          {lookup === 'error' && (
            <button type="button" className="text-brand-red underline" onClick={() => void findToken()}>
              Could not load the token — retry
            </button>
          )}
        </span>
        {OUTCOMES.map((o) => (
          <button
            key={o.value}
            type="button"
            disabled={lookup !== 'found'}
            onClick={() => open(o.value)}
            className={`rounded-md px-4 py-2 font-semibold disabled:bg-slate-200 disabled:text-slate-500 ${o.className}`}
          >
            {o.label}
          </button>
        ))}
      </footer>

      {dialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={close}>
          <form
            role="dialog"
            aria-modal="true"
            aria-labelledby="outcome-title"
            onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => {
              e.preventDefault()
              void confirm()
            }}
            className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl"
          >
            <h2 id="outcome-title" className="text-xl font-semibold text-navy">
              {label} — {token?.display ?? tokenDisplay}
            </h2>

            <div className="mt-4 flex flex-col gap-3">
              {dialog === 'refer' && (
                <label className="block text-sm font-medium">
                  Refer to
                  <select
                    value={form.referDepartment}
                    onChange={(e) => set('referDepartment', e.target.value as Department)}
                    className={inputCls}
                  >
                    {DEPARTMENTS.map((d) => (
                      <option key={d.value} value={d.value}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {dialog === 'followup' && (
                <>
                  <label className="block text-sm font-medium">
                    Follow-up date
                    <input
                      type="date"
                      required
                      min={localDate(1)}
                      value={form.followupDate}
                      onChange={(e) => set('followupDate', e.target.value)}
                      className={inputCls}
                    />
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.admit} onChange={(e) => set('admit', e.target.checked)} />
                    Admit the patient
                  </label>
                </>
              )}
              {dialog === 'recheck' && (
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.resultsTomorrow}
                    onChange={(e) => set('resultsTomorrow', e.target.checked)}
                  />
                  Results come tomorrow (close today, priority token for tomorrow)
                </label>
              )}
              <label className="block text-sm font-medium">
                Note {dialog === 'out' ? '(optional)' : '(optional, for the record)'}
                <textarea
                  value={form.note}
                  maxLength={1000}
                  rows={2}
                  onChange={(e) => set('note', e.target.value)}
                  className={inputCls}
                />
              </label>
            </div>

            <p className="mt-4 rounded-md bg-slate-50 p-3 text-sm text-slate-700 ring-1 ring-slate-200">
              {consequence(dialog, token?.display ?? tokenDisplay, form)}
            </p>
            {error && (
              <p className="mt-3 text-sm font-medium text-brand-red" role="alert">
                {error}
              </p>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={close} className="rounded-md px-4 py-2 font-semibold ring-1 ring-slate-300">
                Cancel
              </button>
              <button
                type="submit"
                autoFocus
                disabled={sending || !token || followupInvalid}
                className="rounded-md bg-navy px-4 py-2 font-semibold text-white disabled:opacity-50"
              >
                {sending ? 'Saving…' : `Confirm ${label}`}
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  )
}
