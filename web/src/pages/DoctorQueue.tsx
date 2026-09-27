import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, USE_FIXTURES, api } from '../api/client'
import type { Lane, NextRequest, QueueItem, TokenStatus, WsMessage } from '../api/types'
import { useAuth } from '../auth/store'
import QueueCard, { type QueueAction } from '../components/QueueCard'
import { laneStyle } from '../theme'
import { useChannel } from '../ws/useChannel'

const POLL_MS = 10_000
const LANES: Lane[] = ['emergency', 'priority', 'normal']
/** Within a lane: patients already in/called first, then the waiting preview order from the server. */
const STATUS_RANK: Partial<Record<TokenStatus, number>> = { in: 0, called: 1, waiting: 2 }

/** `/doctor`: the doctor's department queue, live via WebSocket + 10 s poll. */
export default function DoctorQueue() {
  const auth = useAuth()
  const navigate = useNavigate()
  const department = auth?.staff.department ?? null
  const me = auth?.staff.id ?? ''

  const [items, setItems] = useState<QueueItem[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const inFlight = useRef(false)

  const load = useCallback(async (): Promise<void> => {
    if (inFlight.current) return
    inFlight.current = true
    try {
      const query = department ? `?department=${department}` : ''
      setItems(await api<QueueItem[]>('GET', `/api/queue${query}`))
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the queue')
    } finally {
      inFlight.current = false
      setLoaded(true)
    }
  }, [department])

  useEffect(() => {
    void load()
    const t = setInterval(() => void load(), POLL_MS)
    return () => clearInterval(t)
  }, [load])

  const onMessage = useCallback(
    (msg: WsMessage) => {
      if (msg.type.startsWith('token.')) void load()
    },
    [load],
  )
  const { connected } = useChannel('queue', onMessage)

  const groups = useMemo(() => {
    const byLane: Record<Lane, QueueItem[]> = { emergency: [], priority: [], normal: [] }
    items.forEach((it) => byLane[it.lane].push(it))
    LANES.forEach((lane) =>
      byLane[lane].sort((a, b) => (STATUS_RANK[a.status] ?? 3) - (STATUS_RANK[b.status] ?? 3)),
    )
    return byLane
  }, [items])

  const openSession = (item: QueueItem): void => {
    void navigate(`/doctor/session/${item.session_id}`)
  }

  const fixtureOnly = (): boolean => {
    if (USE_FIXTURES) setNotice('Fixture mode — actions are not sent to the server.')
    return USE_FIXTURES
  }

  const onAction = async (item: QueueItem, action: QueueAction): Promise<void> => {
    if (fixtureOnly()) {
      if (action === 'in') openSession(item)
      return
    }
    setBusyId(item.id)
    setNotice(null)
    try {
      const updated = await api<QueueItem>('POST', `/api/tokens/${item.id}/${action}`)
      if (action === 'in') {
        openSession(updated)
        return
      }
      setNotice(
        action === 'call'
          ? `Called ${updated.display}${updated.patient ? ` — ${updated.patient.name}` : ''}`
          : updated.status === 'absent'
            ? `${updated.display} marked absent (not answered twice)`
            : `${updated.display} back to waiting`,
      )
      await load()
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : 'Action failed')
      await load()
    } finally {
      setBusyId(null)
    }
  }

  const onNext = async (): Promise<void> => {
    if (fixtureOnly() || !department) {
      if (!department) setNotice('Your staff profile has no department — ask the admin.')
      return
    }
    setBusyId('next')
    setNotice(null)
    try {
      const body: NextRequest = { department }
      const called = await api<QueueItem | null>('POST', '/api/queue/next', body)
      setNotice(
        called
          ? `Called ${called.display}${called.patient ? ` — ${called.patient.name}` : ''}`
          : 'No one is waiting.',
      )
      await load()
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : 'Could not call the next patient')
    } finally {
      setBusyId(null)
    }
  }

  const waitingCount = items.filter((i) => i.status === 'waiting').length

  return (
    <main className="mx-auto max-w-7xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-navy">
            Queue{department ? ` · ${department === 'ayurveda' ? 'Ayurveda' : 'General'} OPD` : ''}
          </h1>
          <p className="text-sm text-slate-600">
            {waitingCount} waiting ·{' '}
            <span className={connected ? 'text-brand-green' : 'text-slate-500'}>
              {USE_FIXTURES ? 'fixtures' : connected ? '● live' : '○ polling every 10 s'}
            </span>
          </p>
        </div>
        <button
          type="button"
          onClick={() => void onNext()}
          disabled={busyId !== null}
          className="rounded-xl bg-navy px-6 py-3 text-lg font-semibold text-white shadow disabled:opacity-50"
        >
          Next patient →
        </button>
      </div>

      {notice && (
        <p className="mt-3 rounded-md bg-blue-50 px-3 py-2 text-sm text-navy ring-1 ring-blue-200" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-brand-red ring-1 ring-red-200" role="alert">
          {error}
        </p>
      )}

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {LANES.map((lane) => (
          <section key={lane} aria-labelledby={`lane-${lane}`} className="min-w-0">
            <h2
              id={`lane-${lane}`}
              className={`mb-2 flex items-center justify-between rounded-md border-l-4 px-3 py-1.5 font-semibold ${laneStyle[lane].className}`}
            >
              {laneStyle[lane].label}
              <span className="text-sm font-normal">{groups[lane].length}</span>
            </h2>
            <div className="flex flex-col gap-2">
              {groups[lane].map((item) => (
                <QueueCard
                  key={item.id}
                  item={item}
                  me={me}
                  busy={busyId !== null}
                  onAction={(it, a) => void onAction(it, a)}
                  onOpen={openSession}
                />
              ))}
              {loaded && groups[lane].length === 0 && <p className="px-3 text-sm text-slate-500">No patients</p>}
            </div>
          </section>
        ))}
      </div>
    </main>
  )
}
