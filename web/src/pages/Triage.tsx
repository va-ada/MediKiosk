import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, USE_FIXTURES, api } from '../api/client'
import type { Alert, ResolveRequest, WsMessage } from '../api/types'
import AlertCard, { REASON_LABEL, type AlertAction, type AlertView } from '../components/AlertCard'
import { useChannel } from '../ws/useChannel'
import { useRelay } from '../ws/useRelay'

const POLL_MS = 15_000
const BEEP_EVERY_MS = 1500
const MUTE_MS = 30_000
const DISMISSED_KEY = 'mk.triage.dismissedRelay'

function loadDismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY)
    const v: unknown = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [])
  } catch {
    return new Set()
  }
}

/** Short square-wave beeps: two for emergency, one for urgent. */
function beep(ctx: AudioContext, emergency: boolean): void {
  const tones = emergency ? [0, 0.25] : [0]
  tones.forEach((offset) => {
    const t = ctx.currentTime + offset
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'square'
    osc.frequency.value = emergency ? 1100 : 760
    gain.gain.setValueAtTime(0.0001, t)
    gain.gain.exponentialRampToValueAtTime(0.25, t + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.18)
    osc.connect(gain).connect(ctx.destination)
    osc.start(t)
    osc.stop(t + 0.2)
  })
}

/** `/triage`: nurse alert station — server alerts + alarm relay, merged by id; beeps while anything is open. */
export default function Triage() {
  // Every server alert we have seen (any status) — closed ones stay here so their relay copies stay hidden.
  const [known, setKnown] = useState<ReadonlyMap<string, Alert>>(new Map())
  const [serverError, setServerError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(loadDismissed)
  const [now, setNow] = useState(() => Date.now())
  const [muteUntil, setMuteUntil] = useState(0)

  const upsert = useCallback((alerts: Alert[]) => {
    setKnown((prev) => {
      const next = new Map(prev)
      alerts.forEach((a) => next.set(a.id, a))
      return next
    })
  }, [])

  const load = useCallback(async (): Promise<void> => {
    try {
      const [active, closed] = await Promise.all([
        api<Alert[]>('GET', '/api/alerts?status=open,acknowledged'),
        api<Alert[]>('GET', '/api/alerts?status=confirmed,downgraded&limit=200'),
      ])
      upsert([...closed, ...active])
      setServerError(null)
    } catch (e) {
      setServerError(e instanceof ApiError ? e.message : 'Cannot reach the MediKiosk server')
    }
  }, [upsert])

  useEffect(() => {
    void load()
    const t = setInterval(() => void load(), POLL_MS)
    return () => clearInterval(t)
  }, [load])

  const onMessage = useCallback(
    (msg: WsMessage) => {
      if (msg.type === 'alert.created' || msg.type === 'alert.updated') upsert([msg.data])
    },
    [upsert],
  )
  const server = useChannel('alerts', onMessage)
  const relay = useRelay()

  // Re-sync after the server socket comes back.
  const lastConnected = useRef<boolean | null>(null)
  useEffect(() => {
    if (server.connected && lastConnected.current === false) void load()
    if (server.connected || lastConnected.current !== null) lastConnected.current = server.connected
  }, [server.connected, load])

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const views = useMemo(() => {
    const out: AlertView[] = []
    known.forEach((a) => {
      if (a.status !== 'open' && a.status !== 'acknowledged') return
      out.push({
        id: a.id,
        kiosk_id: a.kiosk_id,
        level: a.level,
        reason: a.reason_text || (a.reason_code ? REASON_LABEL[a.reason_code] : 'Alert'),
        status: a.status,
        escalated: a.escalated,
        created_at: a.created_at,
        acknowledged_by: a.acknowledged_by,
        relayOnly: false,
      })
    })
    relay.alarms.forEach((r) => {
      if (known.has(r.id) || dismissed.has(r.id)) return
      out.push({
        id: r.id,
        kiosk_id: r.kiosk_id,
        level: 'emergency',
        reason: REASON_LABEL[r.reason_code] ?? r.reason_code,
        status: 'open',
        escalated: false,
        created_at: r.created_at,
        acknowledged_by: null,
        relayOnly: true,
      })
    })
    const rank = (v: AlertView): number => (v.level === 'emergency' ? 0 : 2) + (v.status === 'open' ? 0 : 1)
    return out.sort((a, b) => rank(a) - rank(b) || a.created_at.localeCompare(b.created_at))
  }, [known, relay.alarms, dismissed])

  const openViews = views.filter((v) => v.status === 'open')
  const anyOpen = openViews.length > 0
  const emergencyOpen = openViews.some((v) => v.level === 'emergency')
  const muted = now < muteUntil
  const shouldBeep = anyOpen && !muted

  // ---- sound (Web Audio; browsers keep it suspended until a user gesture) ----
  const audio = useRef<AudioContext | null>(null)
  const [soundBlocked, setSoundBlocked] = useState(false)
  useEffect(() => {
    const ctx = new AudioContext()
    audio.current = ctx
    const sync = (): void => setSoundBlocked(ctx.state !== 'running')
    ctx.onstatechange = sync
    void ctx.resume().catch(() => undefined).finally(sync)
    const unlock = (): void => void ctx.resume()
    window.addEventListener('pointerdown', unlock)
    window.addEventListener('keydown', unlock)
    return () => {
      window.removeEventListener('pointerdown', unlock)
      window.removeEventListener('keydown', unlock)
      void ctx.close()
    }
  }, [])

  const emergencyRef = useRef(emergencyOpen)
  useEffect(() => {
    emergencyRef.current = emergencyOpen
  }, [emergencyOpen])
  useEffect(() => {
    if (!shouldBeep) return
    const tick = (): void => {
      const ctx = audio.current
      if (ctx && ctx.state === 'running') beep(ctx, emergencyRef.current)
    }
    tick()
    const t = setInterval(tick, BEEP_EVERY_MS)
    return () => clearInterval(t)
  }, [shouldBeep])

  // ---- actions ----
  const onAction = async (view: AlertView, action: AlertAction): Promise<void> => {
    if (action === 'dismiss') {
      setDismissed((prev) => {
        const next = new Set(prev).add(view.id)
        try {
          localStorage.setItem(DISMISSED_KEY, JSON.stringify([...next].slice(-200)))
        } catch {
          // storage unavailable — dismissal lasts for this page only
        }
        return next
      })
      return
    }
    if (USE_FIXTURES) {
      setNotice('Fixture mode — actions are not sent to the server.')
      return
    }
    setBusyId(view.id)
    setNotice(null)
    try {
      const updated =
        action === 'ack'
          ? await api<Alert>('POST', `/api/alerts/${view.id}/ack`)
          : await api<Alert>('POST', `/api/alerts/${view.id}/resolve`, { outcome: action } satisfies ResolveRequest)
      upsert([updated])
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : 'Action failed')
      void load()
    } finally {
      setBusyId(null)
    }
  }

  const down = [!server.connected && 'MediKiosk server', !relay.connected && 'alarm relay'].filter(Boolean)

  return (
    <main className="mx-auto max-w-6xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold text-navy">Triage and alert station</h1>
          <p className="text-lg text-slate-600">
            {anyOpen ? `${openViews.length} open` : 'No open alerts'} · {views.length} active
          </p>
        </div>
        <button
          type="button"
          onClick={() => setMuteUntil(muted ? 0 : Date.now() + MUTE_MS)}
          className={`rounded-xl px-6 py-3 text-xl font-bold shadow ${
            muted ? 'bg-amber-400 text-black' : 'bg-slate-800 text-white'
          }`}
        >
          {muted ? `Muted ${Math.ceil((muteUntil - now) / 1000)} s — unmute` : 'Mute 30 s'}
        </button>
      </div>

      {!USE_FIXTURES && down.length > 0 && (
        <p className="mt-3 rounded-xl bg-yellow-300 px-4 py-3 text-xl font-bold text-black" role="alert">
          ⚠ Disconnected from the {down.join(' and the ')} — {down.length === 2 ? 'alerts may be missed' : 'reconnecting'}.
        </p>
      )}
      {soundBlocked && (
        <button
          type="button"
          onClick={() => void audio.current?.resume()}
          className="mt-3 w-full rounded-xl bg-navy px-4 py-3 text-xl font-bold text-white"
        >
          🔇 Sound is off — click here to enable alarm beeps
        </button>
      )}
      {serverError && server.connected === false && (
        <p className="mt-2 text-lg text-brand-red">{serverError}. Relay alarms still show below.</p>
      )}
      {notice && (
        <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-lg text-amber-900 ring-1 ring-amber-200" role="status">
          {notice}
        </p>
      )}

      <div className="mt-4 flex flex-col gap-4">
        {views.map((v) => (
          <AlertCard key={v.id} alert={v} now={now} busy={busyId !== null} onAction={(a, act) => void onAction(a, act)} />
        ))}
        {views.length === 0 && (
          <p className="rounded-2xl bg-emerald-50 p-10 text-center text-3xl font-semibold text-brand-green ring-1 ring-emerald-200">
            All clear
          </p>
        )}
      </div>
    </main>
  )
}
