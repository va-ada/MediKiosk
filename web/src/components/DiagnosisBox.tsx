import { useEffect, useState } from 'react'
import { ApiError, USE_FIXTURES, api } from '../api/client'
import type { DiagnosisRequest, OkResponse, TerminologyResult } from '../api/types'

type System = 'NAMASTE' | 'ICD11_TM2' | 'ICD10'
const SYSTEMS: { value: System; label: string }[] = [
  { value: 'NAMASTE', label: 'NAMASTE' },
  { value: 'ICD11_TM2', label: 'ICD-11 TM2' },
  { value: 'ICD10', label: 'ICD-10' },
]
const DEBOUNCE_MS = 300

interface Props {
  sessionId: string
  defaultSystem: System
}

function SampleBadge() {
  return (
    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-amber-800 uppercase ring-1 ring-amber-300">
      SAMPLE code
    </span>
  )
}

/** Diagnosis coding: debounced terminology search → chips → `POST /api/sessions/{id}/diagnosis`. */
export default function DiagnosisBox({ sessionId, defaultSystem }: Props) {
  const [system, setSystem] = useState<System>(defaultSystem)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<TerminologyResult[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)
  const [chosen, setChosen] = useState<TerminologyResult[]>([])
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    const query = q.trim()
    if (!query) {
      setResults([])
      return
    }
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      api<TerminologyResult[]>(
        'GET',
        `/api/terminology/search?q=${encodeURIComponent(query)}&system=${system}`,
        undefined,
        { signal: ctrl.signal },
      )
        .then((r) => {
          setResults(r)
          setSearchError(null)
        })
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === 'AbortError') return
          setSearchError(e instanceof ApiError ? e.message : 'Search failed')
        })
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(t)
      ctrl.abort()
    }
  }, [q, system])

  const key = (c: { system: string; code: string }): string => `${c.system}:${c.code}`
  const add = (r: TerminologyResult): void => {
    setChosen((prev) => (prev.some((c) => key(c) === key(r)) ? prev : [...prev, r]))
    setQ('')
    setMessage(null)
  }
  const remove = (r: TerminologyResult): void => setChosen((prev) => prev.filter((c) => key(c) !== key(r)))

  const canSave = chosen.length > 0 || text.trim().length > 0
  const save = async (): Promise<void> => {
    if (USE_FIXTURES) {
      setMessage({ ok: false, text: 'Fixture mode — the diagnosis is not sent to the server.' })
      return
    }
    const body: DiagnosisRequest = { codes: chosen.map(({ system: s, code, display }) => ({ system: s, code, display })) }
    if (text.trim()) body.text = text.trim()
    setSaving(true)
    setMessage(null)
    try {
      await api<OkResponse>('POST', `/api/sessions/${sessionId}/diagnosis`, body)
      setMessage({ ok: true, text: `Diagnosis saved at ${new Date().toLocaleTimeString()}.` })
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.message : 'Could not save the diagnosis' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200" aria-labelledby="dx-title">
      <h2 id="dx-title" className="font-semibold text-navy">
        Diagnosis (doctor)
      </h2>

      <div className="mt-2 flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="dx-system">
          Code system
        </label>
        <select
          id="dx-system"
          value={system}
          onChange={(e) => setSystem(e.target.value as System)}
          className="rounded-md border border-slate-300 px-2 py-1.5"
        >
          {SYSTEMS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="dx-q">
          Search terminology
        </label>
        <input
          id="dx-q"
          type="search"
          value={q}
          maxLength={100}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search a term, e.g. sandhigata, knee"
          autoComplete="off"
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5"
        />
      </div>

      {searchError && <p className="mt-1 text-sm text-brand-red">{searchError}</p>}
      {q.trim() && results.length > 0 && (
        <ul className="mt-1 max-h-60 overflow-auto rounded-md ring-1 ring-slate-200" role="listbox" aria-label="Matching codes">
          {results.map((r) => (
            <li key={key(r)}>
              <button
                type="button"
                onClick={() => add(r)}
                className="flex w-full flex-wrap items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-50"
              >
                <span className="font-mono text-xs text-slate-500">{r.code}</span>
                <span>{r.display}</span>
                {r.sample && <SampleBadge />}
              </button>
            </li>
          ))}
        </ul>
      )}
      {q.trim() && results.length === 0 && !searchError && <p className="mt-1 text-sm text-slate-500">No match yet.</p>}

      {chosen.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2" aria-label="Chosen codes">
          {chosen.map((c) => (
            <li key={key(c)} className="flex items-center gap-1.5 rounded-full bg-navy/10 py-1 pr-1 pl-3 text-sm">
              <span className="font-mono text-xs text-slate-600">{c.system}</span>
              <span>{c.display}</span>
              {c.sample && <SampleBadge />}
              <button
                type="button"
                onClick={() => remove(c)}
                aria-label={`Remove ${c.display}`}
                className="rounded-full px-2 text-slate-600 hover:bg-white"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <label className="mt-3 block text-sm font-medium">
        Diagnosis text (optional)
        <textarea
          value={text}
          maxLength={1000}
          rows={2}
          onChange={(e) => setText(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
        />
      </label>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void save()}
          disabled={!canSave || saving}
          className="rounded-md bg-navy px-4 py-2 font-semibold text-white disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save diagnosis'}
        </button>
        {message && (
          <span className={`text-sm font-medium ${message.ok ? 'text-brand-green' : 'text-brand-red'}`} role="status">
            {message.text}
          </span>
        )}
      </div>
    </section>
  )
}
