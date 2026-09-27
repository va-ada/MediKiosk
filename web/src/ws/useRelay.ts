import { useEffect, useState } from 'react'
import { RELAY_URL, RELAY_WS, USE_FIXTURES } from '../api/client'
import type { RelayAlarm } from '../api/types'

export interface RelayState {
  connected: boolean
  /** Alarms seen on the relay (initial `GET /alarms` + live WS), newest first. */
  alarms: RelayAlarm[]
}

const MIN_DELAY_MS = 1000
const MAX_DELAY_MS = 15000
const KEEP = 200

function isAlarm(v: unknown): v is RelayAlarm {
  if (typeof v !== 'object' || v === null) return false
  const a = v as Record<string, unknown>
  return typeof a.id === 'string' && typeof a.kiosk_id === 'string' && typeof a.created_at === 'string'
}

function merge(prev: RelayAlarm[], incoming: RelayAlarm[]): RelayAlarm[] {
  const byId = new Map(prev.map((a) => [a.id, a]))
  incoming.forEach((a) => byId.set(a.id, a))
  return [...byId.values()].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, KEEP)
}

/**
 * Alarm relay (§7, independent of the API server): `GET ${VITE_RELAY_URL}/alarms` on every (re)connect,
 * then live `{"type":"alarm","data":{…}}` messages from `VITE_RELAY_WS`. Reconnects with backoff (1 s → 15 s).
 */
export function useRelay(): RelayState {
  const [connected, setConnected] = useState(false)
  const [alarms, setAlarms] = useState<RelayAlarm[]>([])

  useEffect(() => {
    if (USE_FIXTURES) return
    let ws: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let delay = MIN_DELAY_MS
    let closed = false

    const loadList = async (): Promise<void> => {
      try {
        const res = await fetch(`${RELAY_URL}/alarms`)
        if (!res.ok) return
        const body: unknown = await res.json()
        if (!closed && Array.isArray(body)) setAlarms((prev) => merge(prev, body.filter(isAlarm)))
      } catch {
        // relay unreachable — the socket state already says so
      }
    }

    const connect = (): void => {
      ws = new WebSocket(RELAY_WS)
      ws.onopen = () => {
        delay = MIN_DELAY_MS
        setConnected(true)
        void loadList()
      }
      ws.onmessage = (ev: MessageEvent) => {
        if (typeof ev.data !== 'string') return
        try {
          const msg: unknown = JSON.parse(ev.data)
          if (typeof msg === 'object' && msg !== null && (msg as { type?: unknown }).type === 'alarm') {
            const data = (msg as { data?: unknown }).data
            if (isAlarm(data)) setAlarms((prev) => merge(prev, [data]))
          }
        } catch {
          // ignore malformed frames
        }
      }
      ws.onclose = () => {
        setConnected(false)
        if (closed) return
        timer = setTimeout(connect, delay)
        delay = Math.min(delay * 2, MAX_DELAY_MS)
      }
      ws.onerror = () => ws?.close()
    }
    connect()

    return () => {
      closed = true
      if (timer) clearTimeout(timer)
      ws?.close()
    }
  }, [])

  return { connected, alarms }
}
