import { useEffect, useRef, useState } from 'react'
import { USE_FIXTURES, WS_URL } from '../api/client'
import type { WsChannel, WsMessage } from '../api/types'

export interface ChannelState {
  connected: boolean
  lastMessage: WsMessage | null
}

const MIN_DELAY_MS = 1000
const MAX_DELAY_MS = 30000

function parse(raw: unknown): WsMessage | null {
  if (typeof raw !== 'string') return null
  try {
    const msg: unknown = JSON.parse(raw)
    if (typeof msg === 'object' && msg !== null && 'type' in msg && 'data' in msg && typeof msg.type === 'string') {
      return msg as WsMessage
    }
  } catch {
    // ignore malformed frames
  }
  return null
}

/**
 * Subscribe to `${VITE_WS_URL}/ws?channel=<channel>` (§5). Reconnects with exponential backoff
 * (1 s → 30 s). Does not connect in fixture mode.
 */
export function useChannel(channel: WsChannel, onMessage?: (msg: WsMessage) => void): ChannelState {
  const [connected, setConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null)
  const handler = useRef(onMessage)

  useEffect(() => {
    handler.current = onMessage
  }, [onMessage])

  useEffect(() => {
    if (USE_FIXTURES) return
    let ws: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let delay = MIN_DELAY_MS
    let closed = false

    const connect = (): void => {
      ws = new WebSocket(`${WS_URL}/ws?channel=${encodeURIComponent(channel)}`)
      ws.onopen = () => {
        delay = MIN_DELAY_MS
        setConnected(true)
      }
      ws.onmessage = (ev: MessageEvent) => {
        const msg = parse(ev.data)
        if (!msg) return
        setLastMessage(msg)
        handler.current?.(msg)
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
  }, [channel])

  return { connected, lastMessage }
}
