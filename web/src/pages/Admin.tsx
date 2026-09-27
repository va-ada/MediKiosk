import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'
import type { AdminHealth, AuditLog, AuditVerify, IslandState, Outbox, OutboxStatus, WsMessage } from '../api/types'
import { useChannel } from '../ws/useChannel'

const HEALTH_REFRESH_MS = 10_000
const TILES: { key: keyof Omit<AdminHealth, 'island_mode'>; label: string }[] = [
  { key: 'db', label: 'Database' },
  { key: 'nlp', label: 'NLP service' },
  { key: 'ollama', label: 'Language model' },
  { key: 'relay', label: 'Alarm relay' },
  { key: 'his', label: 'Hospital HIS' },
]
const OUTBOX_CHIP: Record<OutboxStatus, string> = {
  pending: 'bg-amber-100 text-amber-800',
  sent: 'bg-emerald-100 text-emerald-800',
  skipped_no_consent: 'bg-gray-200 text-gray-700',
  failed: 'bg-red-100 text-red-800',
}

function errText(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Something went wrong'
}

function time(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : '—'
}

/** `/admin`: island mode, service health, outbox, audit chain, two-person patient erasure. */
export default function Admin() {
  const [health, setHealth] = useState<AdminHealth | null>(null)
  const [island, setIsland] = useState<boolean | null>(null)
  const [confirmIsland, setConfirmIsland] = useState<boolean | null>(null)
  const [outbox, setOutbox] = useState<Outbox[]>([])
  const [audit, setAudit] = useState<AuditLog[]>([])
  const [verify, setVerify] = useState<AuditVerify | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadHealth = useCallback(async () => {
    try {
      const h = await api<AdminHealth>('GET', '/api/admin/health')
      setHealth(h)
      setIsland(h.island_mode)
    } catch (e) {
      setError(errText(e))
    }
  }, [])
  const loadTables = useCallback(async () => {
    try {
      const [o, a] = await Promise.all([
        api<Outbox[]>('GET', '/api/admin/outbox?limit=100'),
        api<AuditLog[]>('GET', '/api/admin/audit?limit=100'),
      ])
      setOutbox(o)
      setAudit(a)
    } catch (e) {
      setError(errText(e))
    }
  }, [])

  useEffect(() => {
    void loadHealth()
    void loadTables()
    const t = setInterval(() => {
      void loadHealth()
      void loadTables()
    }, HEALTH_REFRESH_MS)
    return () => clearInterval(t)
  }, [loadHealth, loadTables])

  const { connected } = useChannel('admin', (msg: WsMessage) => {
    if (msg.type === 'island.changed') setIsland(msg.data.enabled)
    if (msg.type === 'alert.created' || msg.type === 'alert.updated') void loadTables()
  })

  const applyIsland = async (enabled: boolean): Promise<void> => {
    setConfirmIsland(null)
    try {
      setIsland((await api<IslandState>('POST', '/api/admin/island', { enabled })).enabled)
      void loadHealth()
    } catch (e) {
      setError(errText(e))
    }
  }

  const runVerify = async (): Promise<void> => {
    try {
      setVerify(await api<AuditVerify>('GET', '/api/admin/audit/verify'))
    } catch (e) {
      setError(errText(e))
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4">
      {error && (
        <div role="alert" className="flex justify-between rounded-md bg-red-50 px-4 py-2 text-brand-red">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="font-semibold">
            Dismiss
          </button>
        </div>
      )}

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-navy">Island mode</h2>
            <p className="text-sm text-gray-600">
              {island
                ? 'ON — nothing leaves the hospital. The outbox holds records until island mode is turned off.'
                : 'OFF — records are sent to the hospital HIS through the outbox.'}
            </p>
            {!connected && <p className="text-xs text-amber-700">Live updates disconnected — refreshing every 10 s.</p>}
          </div>
          <button
            type="button"
            disabled={island === null}
            onClick={() => setConfirmIsland(!island)}
            className={`min-h-14 rounded-lg px-6 text-lg font-bold text-white shadow ${
              island ? 'bg-brand-red hover:bg-red-700' : 'bg-brand-green hover:bg-emerald-700'
            } disabled:opacity-50`}
          >
            {island === null ? '…' : island ? 'Island mode ON' : 'Island mode OFF'}
          </button>
        </div>
      </section>

      <section aria-label="Service health" className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {TILES.map((t) => {
          const up = health?.[t.key]
          return (
            <div
              key={t.key}
              className={`rounded-lg border p-3 text-center ${
                up === undefined ? 'bg-gray-50' : up ? 'border-emerald-300 bg-emerald-50' : 'border-red-300 bg-red-50'
              }`}
            >
              <div className="text-sm text-gray-600">{t.label}</div>
              <div className={`text-lg font-bold ${up ? 'text-brand-green' : 'text-brand-red'}`}>
                {up === undefined ? '…' : up ? 'Up' : 'Down'}
              </div>
            </div>
          )
        })}
      </section>

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-lg font-semibold text-navy">Outbox</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-gray-500">
              <tr>
                <th className="py-1 pr-3">Created</th>
                <th className="pr-3">Key</th>
                <th className="pr-3">Status</th>
                <th className="pr-3">Attempts</th>
                <th className="pr-3">Resources</th>
                <th className="pr-3">Sent</th>
                <th>Last error</th>
              </tr>
            </thead>
            <tbody>
              {outbox.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-3 text-gray-500">
                    Nothing queued.
                  </td>
                </tr>
              )}
              {outbox.map((o) => (
                <tr key={o.id} className="border-t">
                  <td className="py-1 pr-3 whitespace-nowrap">{time(o.created_at)}</td>
                  <td className="pr-3 font-mono text-xs">{o.idempotency_key}</td>
                  <td className="pr-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${OUTBOX_CHIP[o.status]}`}>
                      {o.status.replaceAll('_', ' ')}
                    </span>
                  </td>
                  <td className="pr-3">{o.attempts}</td>
                  <td className="pr-3">{o.resource_count}</td>
                  <td className="pr-3 whitespace-nowrap">{time(o.sent_at)}</td>
                  <td className="max-w-xs truncate text-xs text-brand-red" title={o.last_error ?? ''}>
                    {o.last_error ?? ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-navy">Audit log (latest 100)</h2>
          <div className="flex items-center gap-3">
            {verify &&
              (verify.valid ? (
                <span className="font-semibold text-brand-green">✓ Chain valid ({verify.checked} entries)</span>
              ) : (
                <span className="font-semibold text-brand-red">✗ Chain broken at id {verify.first_bad_id}</span>
              ))}
            <button
              type="button"
              onClick={() => void runVerify()}
              className="rounded-md bg-navy px-4 py-2 font-semibold text-white hover:opacity-90"
            >
              Verify chain
            </button>
          </div>
        </div>
        <div className="max-h-96 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-gray-500">
              <tr>
                <th className="py-1 pr-3">#</th>
                <th className="pr-3">Time</th>
                <th className="pr-3">Actor</th>
                <th className="pr-3">Action</th>
                <th>Entity</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id} className="border-t">
                  <td className="py-1 pr-3 text-gray-500">{a.id}</td>
                  <td className="pr-3 whitespace-nowrap">{time(a.ts)}</td>
                  <td className="pr-3 font-mono text-xs">{a.actor}</td>
                  <td className="pr-3">{a.action}</td>
                  <td className="font-mono text-xs text-gray-600">
                    {a.entity}
                    {a.entity_id ? `:${a.entity_id.slice(0, 8)}` : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <EraseForm onDone={() => void loadTables()} onError={setError} />

      {confirmIsland !== null && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-navy">
              {confirmIsland ? 'Turn island mode ON?' : 'Turn island mode OFF?'}
            </h3>
            <p className="mt-2 text-sm text-gray-700">
              {confirmIsland
                ? 'Nothing will be sent outside the hospital. Everything inside keeps working.'
                : 'Queued records will start going to the hospital HIS within seconds. In the real deployment only the physical key reconnects.'}
            </p>
            <div className="mt-4 flex justify-end gap-3">
              <button type="button" onClick={() => setConfirmIsland(null)} className="rounded-md px-4 py-2 hover:bg-gray-100">
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void applyIsland(confirmIsland)}
                className="rounded-md bg-navy px-4 py-2 font-semibold text-white"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function EraseForm({ onDone, onError }: { onDone: () => void; onError: (msg: string) => void }) {
  const [patientId, setPatientId] = useState('')
  const [approver, setApprover] = useState('')
  const [pin, setPin] = useState('')
  const [confirmText, setConfirmText] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const ready = patientId.trim() && approver.trim() && pin.length >= 4 && confirmText === 'ERASE'

  const submit = async (e: FormEvent): Promise<void> => {
    e.preventDefault()
    if (!ready) return
    setBusy(true)
    setResult(null)
    try {
      await api<{ destroyed: boolean }>('POST', `/api/admin/patients/${encodeURIComponent(patientId.trim())}/erase`, {
        approver_staff_id: approver.trim(),
        approver_pin: pin,
      })
      setResult('Erased: the patient’s files can no longer be decrypted.')
      setPatientId('')
      setConfirmText('')
      onDone()
    } catch (err) {
      onError(errText(err))
    } finally {
      setPin('')
      setBusy(false)
    }
  }

  return (
    <section className="rounded-lg border border-red-200 bg-white p-4 shadow-sm">
      <h2 className="text-lg font-semibold text-brand-red">Erase a patient’s files</h2>
      <p className="mb-3 text-sm text-gray-600">
        Destroys the patient’s encryption key — documents and voice recordings become permanently unreadable. Needs a
        second admin. Cannot be undone.
      </p>
      <form onSubmit={(e) => void submit(e)} className="grid gap-3 sm:grid-cols-4">
        <label className="text-sm">
          Patient ID
          <input value={patientId} onChange={(e) => setPatientId(e.target.value)} className="mt-1 w-full rounded border px-2 py-2 font-mono" />
        </label>
        <label className="text-sm">
          Second admin ID
          <input value={approver} onChange={(e) => setApprover(e.target.value)} className="mt-1 w-full rounded border px-2 py-2" />
        </label>
        <label className="text-sm">
          Second admin PIN
          <input
            type="password"
            inputMode="numeric"
            autoComplete="off"
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
            className="mt-1 w-full rounded border px-2 py-2"
          />
        </label>
        <label className="text-sm">
          Type ERASE to confirm
          <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} className="mt-1 w-full rounded border px-2 py-2" />
        </label>
        <div className="sm:col-span-4 flex items-center gap-4">
          <button
            type="submit"
            disabled={!ready || busy}
            className="min-h-12 rounded-md bg-brand-red px-6 font-semibold text-white disabled:opacity-40"
          >
            {busy ? 'Erasing…' : 'Erase patient files'}
          </button>
          {result && <span className="text-sm text-brand-green">{result}</span>}
        </div>
      </form>
    </section>
  )
}
