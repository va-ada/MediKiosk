import { useState } from 'react'
import type { AlertLevel, AlertStatus, ReasonCode } from '../api/types'

/** One alert on the triage station: a server Alert, or a relay alarm the server has not confirmed. */
export interface AlertView {
  id: string
  kiosk_id: string
  level: AlertLevel
  reason: string
  status: AlertStatus
  escalated: boolean
  created_at: string
  acknowledged_by: string | null
  /** Seen only on the alarm relay — the API server does not know it (yet). */
  relayOnly: boolean
}

export const REASON_LABEL: Record<ReasonCode, string> = {
  chest_pain: 'Chest pain',
  breathing: 'Breathing difficulty',
  bleeding: 'Bleeding',
  unconscious: 'Unconscious',
  seizure: 'Seizure / fits',
  stroke_signs: 'Stroke signs',
  severe_pain: 'Severe pain',
  pregnancy: 'Pregnancy emergency',
  other: 'Other emergency',
}

export type AlertAction = 'ack' | 'confirmed' | 'downgraded' | 'dismiss'

interface Props {
  alert: AlertView
  /** Current time (ms) — ticks every second on the page for the live age. */
  now: number
  busy: boolean
  onAction: (alert: AlertView, action: AlertAction) => void
}

function age(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(s / 60)
  if (m >= 60) return `${Math.floor(m / 60)} h ${m % 60} min`
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

const CONFIRM_TEXT: Record<Exclude<AlertAction, 'ack'>, string> = {
  confirmed: 'Confirm emergency? The patient moves to the emergency lane.',
  downgraded: 'Downgrade? The patient goes back to the normal lane (same place).',
  dismiss: 'Hide this relay alarm on this screen? Only do this once it is handled.',
}

/** Large, distance-readable alert card (emergency red). */
export default function AlertCard({ alert, now, busy, onAction }: Props) {
  const [pending, setPending] = useState<Exclude<AlertAction, 'ack'> | null>(null)
  const emergency = alert.level === 'emergency'
  const open = alert.status === 'open'
  const ageMs = now - Date.parse(alert.created_at)

  const tone = emergency
    ? open
      ? 'bg-brand-red text-white ring-4 ring-red-300'
      : 'bg-red-700 text-white ring-2 ring-red-300'
    : open
      ? 'bg-orange-500 text-white ring-4 ring-orange-200'
      : 'bg-orange-100 text-orange-950 ring-2 ring-orange-300'
  const btn = 'rounded-lg px-5 py-3 text-xl font-bold shadow disabled:opacity-50'

  return (
    <article className={`rounded-2xl p-5 ${tone}`} aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-lg font-bold tracking-wide uppercase">
            {open && (
              <span aria-hidden className="relative flex h-4 w-4">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
                <span className="relative inline-flex h-4 w-4 rounded-full bg-white" />
              </span>
            )}
            <span>{emergency ? 'Emergency' : 'Urgent'}</span>
            <span className="opacity-80">·</span>
            <span>{alert.kiosk_id}</span>
            {alert.escalated && (
              <span className="rounded-full bg-black px-3 py-0.5 text-base text-yellow-300">Escalated</span>
            )}
            {alert.relayOnly && (
              <span className="rounded-full bg-yellow-300 px-3 py-0.5 text-base text-black normal-case">
                via relay — server not confirmed
              </span>
            )}
          </div>
          <h2 className="mt-1 text-4xl leading-tight font-extrabold">{alert.reason}</h2>
          <p className="mt-1 text-lg opacity-90">
            {open ? 'Nobody on the way yet' : `On the way: ${alert.acknowledged_by ?? 'staff'}`}
          </p>
        </div>
        <div className="text-right">
          <div className="font-mono text-5xl font-extrabold tabular-nums">{age(ageMs)}</div>
          <div className="text-sm opacity-80">since alert</div>
        </div>
      </div>

      {pending ? (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl bg-white/95 p-3 text-slate-900">
          <span className="text-lg font-semibold">{CONFIRM_TEXT[pending]}</span>
          <button
            type="button"
            autoFocus
            disabled={busy}
            onClick={() => {
              onAction(alert, pending)
              setPending(null)
            }}
            className={`${btn} bg-navy text-white`}
          >
            Yes
          </button>
          <button type="button" onClick={() => setPending(null)} className={`${btn} bg-slate-200 text-slate-900`}>
            No
          </button>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap gap-3">
          {alert.relayOnly ? (
            <button type="button" onClick={() => setPending('dismiss')} className={`${btn} bg-white/90 text-slate-900`}>
              Hide (handled)
            </button>
          ) : (
            <>
              {open && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onAction(alert, 'ack')}
                  className={`${btn} bg-white text-brand-red`}
                >
                  On my way
                </button>
              )}
              <button
                type="button"
                disabled={busy}
                onClick={() => setPending('confirmed')}
                className={`${btn} bg-black text-white`}
              >
                Confirm emergency
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setPending('downgraded')}
                className={`${btn} bg-white/80 text-slate-900`}
              >
                Downgrade
              </button>
            </>
          )}
        </div>
      )}
    </article>
  )
}
