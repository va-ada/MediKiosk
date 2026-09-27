import QRCode from 'qrcode'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { ApiError } from '../api/client'
import { registerWalkIn, type WalkInProgress } from '../api/kiosk'
import type {
  ComplaintCode,
  Department,
  Informant,
  Language,
  Lane,
  RedFlagSlot,
  ResumeQrPayload,
  Sex,
} from '../api/types'
import { laneStyle } from '../theme'

/** Labels mirror content/triage.yaml (en / hi). */
const COMPLAINTS: { code: ComplaintCode; en: string; hi: string }[] = [
  { code: 'joint_pain', en: 'Joint pain', hi: 'जोड़ों का दर्द' },
  { code: 'fever', en: 'Fever', hi: 'बुखार' },
  { code: 'cough', en: 'Cough or cold', hi: 'खाँसी या ज़ुकाम' },
  { code: 'stomach', en: 'Stomach problem', hi: 'पेट की तकलीफ़' },
  { code: 'headache', en: 'Headache', hi: 'सिर दर्द' },
  { code: 'chest_pain', en: 'Chest pain', hi: 'सीने में दर्द' },
  { code: 'breathing', en: 'Breathing problem', hi: 'साँस की तकलीफ़' },
  { code: 'skin', en: 'Skin problem', hi: 'त्वचा की तकलीफ़' },
  { code: 'other', en: 'Something else', hi: 'कुछ और' },
]

/** content/triage.yaml redflag_questions, in order. */
const RED_FLAGS: { slot: RedFlagSlot; en: string; hi: string }[] = [
  { slot: 'chest_pain', en: 'Do you have chest pain now?', hi: 'क्या अभी सीने में दर्द है?' },
  { slot: 'breathless', en: 'Are you finding it hard to breathe?', hi: 'क्या साँस लेने में तकलीफ़ है?' },
  { slot: 'stroke_signs', en: 'Sudden weakness, face drooping or slurred speech?', hi: 'क्या अचानक कमज़ोरी, चेहरा टेढ़ा या बोलने में दिक्कत है?' },
  { slot: 'heavy_bleeding', en: 'Are you bleeding heavily?', hi: 'क्या बहुत ज़्यादा खून बह रहा है?' },
  { slot: 'fainted', en: 'Did you faint today?', hi: 'क्या आज आप बेहोश हुए?' },
]

interface Form {
  name: string
  age: string
  sex: Sex | null
  language: Language
  complaint: ComplaintCode | null
  complaintText: string
  redflags: Partial<Record<RedFlagSlot, boolean>>
  informant: Informant
  relation: string
  consentExplained: boolean
}

const EMPTY: Form = {
  name: '',
  age: '',
  sex: null,
  language: 'hi',
  complaint: null,
  complaintText: '',
  redflags: {},
  informant: 'self',
  relation: '',
  consentExplained: false,
}

/** One issued token, kept for today's list (this browser tab only). */
interface Registration {
  token_id: string
  session_id: string
  display: string
  lane: Lane
  department: Department
  name: string
  complaint: string
  alerts: string[]
  at: string
}

const todayIst = (): string => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date())
const storageKey = (): string => `medikiosk.desk.${todayIst()}`

function loadRegistrations(): Registration[] {
  try {
    const raw = sessionStorage.getItem(storageKey())
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? (parsed as Registration[]) : []
  } catch {
    return []
  }
}

function saveRegistrations(list: Registration[]): void {
  try {
    sessionStorage.setItem(storageKey(), JSON.stringify(list))
  } catch {
    // storage unavailable: list lives in memory only
  }
}

function validate(f: Form): string | null {
  if (!f.name.trim()) return 'Enter the patient’s name'
  const age = Number(f.age)
  if (f.age.trim() === '' || !Number.isInteger(age) || age < 0 || age > 120) return 'Enter an age between 0 and 120'
  if (!f.sex) return 'Choose sex'
  if (!f.complaint) return 'Choose the main complaint'
  const missing = RED_FLAGS.filter((q) => f.redflags[q.slot] === undefined)
  if (missing.length) return `Answer all 5 danger-sign questions (${missing.length} left)`
  if (f.informant === 'proxy' && !f.relation.trim()) return 'Enter who is answering (relation)'
  if (!f.consentExplained) return 'Confirm consent was explained and agreed'
  return null
}

/** `/desk`: register a walk-in in under a minute and hand them a token with a resume QR. */
export default function Desk() {
  const [form, setForm] = useState<Form>(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [issued, setIssued] = useState<Registration | null>(null)
  const [registrations, setRegistrations] = useState<Registration[]>(loadRegistrations)
  const progress = useRef<WalkInProgress>({})
  const nameInput = useRef<HTMLInputElement>(null)

  const set = <K extends keyof Form>(key: K, value: Form[K]): void => {
    setForm((f) => ({ ...f, [key]: value }))
    // Details changed after a failed attempt: start a fresh registration instead of resuming the old one.
    if (!progress.current.result && key !== 'consentExplained') progress.current = {}
  }

  const onSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault()
    const problem = validate(form)
    if (problem) return setError(problem)
    if (!form.sex || !form.complaint) return
    setBusy(true)
    setError(null)
    try {
      const res = await registerWalkIn(
        {
          patient: { name: form.name.trim(), age: Number(form.age), sex: form.sex, language: form.language },
          session:
            form.informant === 'proxy'
              ? { informant: 'proxy', informant_relation: form.relation.trim() }
              : { informant: 'self' },
          triage: {
            complaint_code: form.complaint,
            ...(form.complaintText.trim() ? { complaint_text: form.complaintText.trim() } : {}),
            redflags: {
              chest_pain: form.redflags.chest_pain === true,
              breathless: form.redflags.breathless === true,
              stroke_signs: form.redflags.stroke_signs === true,
              heavy_bleeding: form.redflags.heavy_bleeding === true,
              fainted: form.redflags.fainted === true,
            },
          },
        },
        progress.current,
      )
      if (!res.token) throw new ApiError('no_token', 'The server did not issue a token — please retry')
      const reg: Registration = {
        token_id: res.token.id,
        session_id: res.session.id,
        display: res.token.display,
        lane: res.token.lane,
        department: res.token.department,
        name: progress.current.patient?.name ?? form.name.trim(),
        complaint: COMPLAINTS.find((c) => c.code === form.complaint)?.en ?? form.complaint,
        alerts: res.alerts.map((a) => `${a.level === 'emergency' ? 'EMERGENCY' : 'Urgent'}: ${a.reason_text}`),
        at: new Date().toISOString(),
      }
      const list = [reg, ...registrations.filter((r) => r.token_id !== reg.token_id)]
      setRegistrations(list)
      saveRegistrations(list)
      setIssued(reg)
      progress.current = {}
      setForm(EMPTY)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? `${err.message}${err.code === 'network_error' ? '' : ` (${err.code})`} — press Issue token again to retry`
          : 'Something went wrong — press Issue token again to retry',
      )
    } finally {
      setBusy(false)
    }
  }

  const nextWalkIn = (): void => {
    setIssued(null)
    setError(null)
    nameInput.current?.focus()
  }

  return (
    <main className="mx-auto max-w-6xl p-4">
      <h1 className="text-2xl font-semibold text-navy">Help desk · walk-in registration</h1>

      <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <form onSubmit={(e) => void onSubmit(e)} className="flex flex-col gap-5 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
          <Field label="Patient name">
            <input
              ref={nameInput}
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              autoFocus
              autoComplete="off"
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg"
            />
          </Field>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Age (years)">
              <input
                value={form.age}
                onChange={(e) => set('age', e.target.value.replace(/\D/g, '').slice(0, 3))}
                inputMode="numeric"
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-lg"
              />
            </Field>
            <Field label="Sex">
              <Segmented
                value={form.sex}
                options={[
                  { value: 'F', label: 'Female' },
                  { value: 'M', label: 'Male' },
                  { value: 'O', label: 'Other' },
                ]}
                onChange={(v) => set('sex', v)}
              />
            </Field>
            <Field label="Language">
              <Segmented
                value={form.language}
                options={[
                  { value: 'hi', label: 'हिंदी' },
                  { value: 'en', label: 'English' },
                ]}
                onChange={(v) => set('language', v)}
              />
            </Field>
          </div>

          <Field label="Main complaint">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {COMPLAINTS.map((c) => (
                <button
                  key={c.code}
                  type="button"
                  onClick={() => set('complaint', c.code)}
                  aria-pressed={form.complaint === c.code}
                  className={`rounded-lg px-3 py-2 text-left ring-1 ${
                    form.complaint === c.code ? 'bg-navy text-white ring-navy' : 'bg-white ring-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <span className="block font-semibold">{c.en}</span>
                  <span className="block text-sm opacity-80">{c.hi}</span>
                </button>
              ))}
            </div>
            <input
              value={form.complaintText}
              onChange={(e) => set('complaintText', e.target.value.slice(0, 500))}
              placeholder="Patient’s own words (optional)"
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2"
            />
          </Field>

          <fieldset>
            <div className="mb-2 flex items-center justify-between">
              <legend className="text-sm font-semibold text-slate-700">Danger signs — ask all five</legend>
              <button
                type="button"
                onClick={() =>
                  set('redflags', Object.fromEntries(RED_FLAGS.map((q) => [q.slot, false])) as Form['redflags'])
                }
                className="text-sm font-medium text-navy underline"
              >
                All no
              </button>
            </div>
            <ul className="divide-y divide-slate-100 rounded-lg ring-1 ring-slate-200">
              {RED_FLAGS.map((q) => (
                <li key={q.slot} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                  <div>
                    <p className="font-medium">{q.en}</p>
                    <p className="text-sm text-slate-500">{q.hi}</p>
                  </div>
                  <Segmented
                    value={form.redflags[q.slot] === undefined ? null : form.redflags[q.slot] ? 'yes' : 'no'}
                    options={[
                      { value: 'no', label: 'No' },
                      { value: 'yes', label: 'Yes', danger: true },
                    ]}
                    onChange={(v) => set('redflags', { ...form.redflags, [q.slot]: v === 'yes' })}
                  />
                </li>
              ))}
            </ul>
          </fieldset>

          <Field label="Who is answering?">
            <div className="flex flex-wrap items-center gap-3">
              <Segmented
                value={form.informant}
                options={[
                  { value: 'self', label: 'Patient' },
                  { value: 'proxy', label: 'Someone else' },
                ]}
                onChange={(v) => set('informant', v)}
              />
              {form.informant === 'proxy' && (
                <input
                  value={form.relation}
                  onChange={(e) => set('relation', e.target.value.slice(0, 40))}
                  placeholder="Relation, e.g. son"
                  className="min-w-40 flex-1 rounded-lg border border-slate-300 px-3 py-2"
                />
              )}
            </div>
          </Field>

          <label className="flex items-start gap-3 rounded-lg bg-slate-50 p-3">
            <input
              type="checkbox"
              checked={form.consentExplained}
              onChange={(e) => set('consentExplained', e.target.checked)}
              className="mt-1 h-5 w-5"
            />
            <span>
              I explained consent (history capture, document scan, sharing with this hospital, ABHA link) and the
              patient agreed.
            </span>
          </label>

          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm font-medium text-brand-red ring-1 ring-red-200" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="rounded-xl bg-brand-green py-3 text-lg font-semibold text-white shadow disabled:opacity-50"
          >
            {busy ? 'Issuing token…' : 'Issue token'}
          </button>
        </form>

        <aside className="flex flex-col gap-4">
          {issued ? (
            <TokenCard reg={issued} onNext={nextWalkIn} />
          ) : (
            <div className="rounded-xl border-2 border-dashed border-slate-300 p-6 text-center text-slate-500">
              The token and its QR appear here.
            </div>
          )}

          <section>
            <h2 className="mb-2 font-semibold text-navy">Today’s desk registrations ({registrations.length})</h2>
            {registrations.length === 0 && <p className="text-sm text-slate-500">None yet</p>}
            <ul className="space-y-1.5">
              {registrations.map((r) => (
                <li key={r.token_id}>
                  <button
                    type="button"
                    onClick={() => setIssued(r)}
                    className="flex w-full items-center gap-3 rounded-lg bg-white px-3 py-2 text-left text-sm shadow-sm ring-1 ring-slate-200 hover:ring-navy"
                  >
                    <span className="font-mono text-base font-bold text-navy">{r.display}</span>
                    <span className="min-w-0 flex-1 truncate">
                      {r.name} · {r.complaint}
                    </span>
                    {r.alerts.length > 0 && <span className="font-bold text-brand-red">⚠</span>}
                    <span className="text-slate-500">
                      {new Date(r.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </main>
  )
}

function TokenCard({ reg, onNext }: { reg: Registration; onNext: () => void }) {
  const [qr, setQr] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const payload: ResumeQrPayload = { session_id: reg.session_id, token_id: reg.token_id }
    QRCode.toDataURL(JSON.stringify(payload), { margin: 1, width: 240, errorCorrectionLevel: 'M' }).then(
      (url) => alive && setQr(url),
      () => alive && setQr(null),
    )
    return () => {
      alive = false
    }
  }, [reg.session_id, reg.token_id])

  return (
    <div className="rounded-xl bg-white p-5 text-center shadow ring-1 ring-slate-200">
      <p className="text-sm text-slate-500">Token for {reg.name}</p>
      <p className="font-mono text-7xl font-black tracking-wider text-navy">{reg.display}</p>
      <p className={`mt-2 inline-block rounded-full border px-3 py-0.5 text-sm font-semibold ${laneStyle[reg.lane].className}`}>
        {laneStyle[reg.lane].label} · {reg.department === 'ayurveda' ? 'Ayurveda OPD' : 'General OPD'}
      </p>
      {reg.alerts.length > 0 && (
        <div className="mt-3 rounded-md bg-brand-red px-3 py-2 text-left text-sm font-semibold text-white" role="alert">
          {reg.alerts.map((a) => (
            <p key={a}>{a}</p>
          ))}
          <p className="mt-1 font-normal">Alert sent to the triage station — take the patient there now.</p>
        </div>
      )}
      <div className="mt-4 flex justify-center">
        {qr ? (
          <img src={qr} alt={`QR code to continue history for token ${reg.display}`} className="h-60 w-60" />
        ) : (
          <div className="h-60 w-60 animate-pulse rounded bg-slate-100" />
        )}
      </div>
      <p className="mt-2 text-sm text-slate-600">Scan at a hall station to continue the history.</p>
      <button type="button" onClick={onNext} className="mt-4 w-full rounded-xl bg-navy py-2.5 font-semibold text-white">
        Next walk-in
      </button>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-sm font-semibold text-slate-700">{label}</p>
      {children}
    </div>
  )
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T | null
  options: { value: T; label: string; danger?: boolean }[]
  onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex overflow-hidden rounded-lg ring-1 ring-slate-300" role="group">
      {options.map((o) => {
        const active = value === o.value
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={`min-w-16 px-3 py-2 font-medium ${
              active ? (o.danger ? 'bg-brand-red text-white' : 'bg-navy text-white') : 'bg-white hover:bg-slate-50'
            }`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
