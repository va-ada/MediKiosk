import { useState, type ReactNode } from 'react'
import { ApiError, USE_FIXTURES, api } from '../api/client'
import type { AyushExamRequest, Fact, SummarySection } from '../api/types'
import TrustChip from './TrustChip'

interface Props {
  sessionId: string
  /** The summary's `ayush` section (absent when nothing was recorded yet). */
  section?: SummarySection
  /** Called after a successful save so the page re-fetches the summary. */
  onSaved: () => void
}

type Option = { value: string; label: string }
const DOSHA: Option[] = [
  { value: 'vata', label: 'Vata' },
  { value: 'pitta', label: 'Pitta' },
  { value: 'kapha', label: 'Kapha' },
]
const NADI: Option[] = [...DOSHA, { value: 'mixed', label: 'Mixed (dvandvaja)' }]
const JIHVA: Option[] = [
  { value: 'clean', label: 'Clean (nirama)' },
  { value: 'coated', label: 'Coated (sama)' },
]
const GRADE: Option[] = [
  { value: 'pravara', label: 'Pravara (best)' },
  { value: 'madhyama', label: 'Madhyama (medium)' },
  { value: 'avara', label: 'Avara (poor)' },
]
const VIKRITI: Option[] = [
  ...DOSHA,
  { value: 'vata-pitta', label: 'Vata-Pitta' },
  { value: 'pitta-kapha', label: 'Pitta-Kapha' },
  { value: 'vata-kapha', label: 'Vata-Kapha' },
]

/** Doctor exam facts come back in the ayush section with these text prefixes (server `ayush_exam`). */
const EXAM_TEXT = /^(Nadi|Jihva|Pramana|Sara|Samhanana|Vikriti|Examination notes):/

interface Form {
  nadi: string
  nadiNote: string
  jihva: string
  jihvaNote: string
  height: string
  weight: string
  sara: string
  samhanana: string
  vikriti: string
  vikritiNote: string
  notes: string
}
const EMPTY: Form = {
  nadi: '',
  nadiNote: '',
  jihva: '',
  jihvaNote: '',
  height: '',
  weight: '',
  sara: '',
  samhanana: '',
  vikriti: '',
  vikritiNote: '',
  notes: '',
}

const finding = (value: string, note: string): { value: string; note?: string } =>
  note.trim() ? { value, note: note.trim() } : { value }

/** AYUSH tab (Ayurveda OPD): patient-reported Dashavidha items (read-only) + doctor examination form. */
export default function AyushTab({ sessionId, section, onSaved }: Props) {
  const items = section?.items ?? []
  const reported = items.filter((i) => !EXAM_TEXT.test(i.text))
  const exam = items.filter((i) => EXAM_TEXT.test(i.text))

  const [form, setForm] = useState<Form>(EMPTY)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const set = (key: keyof Form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const h = Number(form.height)
  const w = Number(form.weight)
  const pramanaGiven = form.height !== '' || form.weight !== ''
  const pramanaValid = h > 30 && h < 260 && w > 1 && w < 350
  const bmi = pramanaValid ? w / (h / 100) ** 2 : null

  const body: AyushExamRequest = {}
  if (form.nadi) body.nadi = finding(form.nadi, form.nadiNote)
  if (form.jihva) body.jihva = finding(form.jihva, form.jihvaNote)
  if (pramanaValid) body.pramana = { height_cm: h, weight_kg: w }
  if (form.sara) body.sara = form.sara
  if (form.samhanana) body.samhanana = form.samhanana
  if (form.vikriti) body.vikriti = finding(form.vikriti, form.vikritiNote)
  if (form.notes.trim()) body.notes = form.notes.trim()
  const canSave = Object.keys(body).length > 0 && (!pramanaGiven || pramanaValid)

  const save = async (): Promise<void> => {
    if (USE_FIXTURES) {
      setMessage({ ok: false, text: 'Fixture mode — the exam is not sent to the server.' })
      return
    }
    setSaving(true)
    setMessage(null)
    try {
      const res = await api<{ facts: Fact[] }>('POST', `/api/sessions/${sessionId}/ayush-exam`, body)
      setMessage({ ok: true, text: `Saved ${res.facts.length} finding${res.facts.length === 1 ? '' : 's'} as doctor-verified.` })
      setForm(EMPTY)
      onSaved()
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.message : 'Could not save the examination' })
    } finally {
      setSaving(false)
    }
  }

  const input = 'w-full rounded-md border border-slate-300 px-2 py-1.5'
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200">
        <h2 className="font-semibold text-navy">Patient-reported (Dashavidha Pariksha history)</h2>
        <p className="text-xs text-slate-500">Asked in plain words at the kiosk; clinical terms shown for the doctor only.</p>
        {reported.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No AYUSH answers recorded.</p>
        ) : (
          <ul className="mt-2 grid grid-cols-1 gap-x-6 divide-y divide-slate-100 xl:grid-cols-2 xl:divide-y-0">
            {reported.map((it) => (
              <li key={it.fact_id} className="flex items-start justify-between gap-2 py-1.5">
                <div className="min-w-0">
                  <p>{it.text}</p>
                  {it.doctor_note && <p className="text-xs font-medium text-slate-500">{it.doctor_note}</p>}
                </div>
                <TrustChip trust={it.trust} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {exam.length > 0 && (
        <section className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-emerald-200">
          <h2 className="font-semibold text-navy">Recorded examination</h2>
          <ul className="mt-1 divide-y divide-slate-100">
            {exam.map((it) => (
              <li key={it.fact_id} className="flex items-start justify-between gap-2 py-1.5">
                <span>{it.text}</span>
                <TrustChip trust={it.trust} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <form
        className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200"
        onSubmit={(e) => {
          e.preventDefault()
          if (canSave) void save()
        }}
      >
        <h2 className="font-semibold text-navy">Examination (doctor)</h2>
        <p className="text-xs font-medium text-amber-700">
          Option lists are a draft — clinician to confirm. Fill only what you examined; re-saving a field replaces it.
        </p>

        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label="Nadi (pulse)">
            <Select value={form.nadi} onChange={set('nadi')} options={NADI} />
            <input className={input} placeholder="Note (optional)" maxLength={300} value={form.nadiNote} onChange={set('nadiNote')} />
          </Field>
          <Field label="Jihva (tongue)">
            <Select value={form.jihva} onChange={set('jihva')} options={JIHVA} />
            <input className={input} placeholder="Note (optional)" maxLength={300} value={form.jihvaNote} onChange={set('jihvaNote')} />
          </Field>
          <Field label="Pramana (height, weight)">
            <div className="flex gap-2">
              <input
                className={input}
                type="number"
                inputMode="decimal"
                min={31}
                max={259}
                step="0.1"
                placeholder="Height cm"
                aria-label="Height in cm"
                value={form.height}
                onChange={set('height')}
              />
              <input
                className={input}
                type="number"
                inputMode="decimal"
                min={2}
                max={349}
                step="0.1"
                placeholder="Weight kg"
                aria-label="Weight in kg"
                value={form.weight}
                onChange={set('weight')}
              />
            </div>
            <p className={`text-sm ${pramanaGiven && !pramanaValid ? 'text-brand-red' : 'text-slate-600'}`} aria-live="polite">
              {bmi !== null ? `BMI ${bmi.toFixed(1)}` : pramanaGiven ? 'Enter both height and weight' : 'BMI —'}
            </p>
          </Field>
          <Field label="Vikriti (present dosha imbalance)">
            <Select value={form.vikriti} onChange={set('vikriti')} options={VIKRITI} />
            <input
              className={input}
              placeholder="Note (optional)"
              maxLength={300}
              value={form.vikritiNote}
              onChange={set('vikritiNote')}
            />
          </Field>
          <Field label="Sara (tissue excellence)">
            <Select value={form.sara} onChange={set('sara')} options={GRADE} />
          </Field>
          <Field label="Samhanana (body build)">
            <Select value={form.samhanana} onChange={set('samhanana')} options={GRADE} />
          </Field>
        </div>
        <label className="mt-3 block text-sm font-medium">
          Examination notes
          <textarea className={`${input} mt-1`} rows={2} maxLength={1000} value={form.notes} onChange={set('notes')} />
        </label>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={!canSave || saving}
            className="rounded-md bg-brand-green px-4 py-2 font-semibold text-white disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save examination'}
          </button>
          {message && (
            <span className={`text-sm font-medium ${message.ok ? 'text-brand-green' : 'text-brand-red'}`} role="status">
              {message.text}
            </span>
          )}
        </div>
      </form>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1 text-sm font-medium">{label}</legend>
      {children}
    </fieldset>
  )
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (e: { target: { value: string } }) => void
  options: Option[]
}) {
  return (
    <select value={value} onChange={onChange} className="w-full rounded-md border border-slate-300 px-2 py-1.5">
      <option value="">— not examined —</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}
