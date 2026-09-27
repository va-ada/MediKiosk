import type { ReactNode } from 'react'
import type { QueueFlag, QueueItem } from '../api/types'

const FLAG_STYLE: Record<QueueFlag, { label: string; className: string }> = {
  red_flag: { label: 'Red flag', className: 'bg-red-100 text-brand-red ring-red-300' },
  aged: { label: 'Waiting long', className: 'bg-amber-100 text-amber-800 ring-amber-300' },
  recheck: { label: 'Recheck', className: 'bg-orange-100 text-orange-800 ring-orange-300' },
  referred: { label: 'Referred', className: 'bg-blue-100 text-blue-800 ring-blue-300' },
}

const LANGUAGE: Record<string, string> = { hi: 'Hindi', en: 'English' }

export type QueueAction = 'call' | 'in' | 'no-show'

interface Props {
  item: QueueItem
  /** The logged-in doctor's staff id. */
  me: string
  busy: boolean
  onAction: (item: QueueItem, action: QueueAction) => void
  onOpen: (item: QueueItem) => void
}

/** One token on the doctor's queue board (§11.2 QueueItem). */
export default function QueueCard({ item, me, busy, onAction, onOpen }: Props) {
  const p = item.patient
  const mine = item.doctor_id === me
  const withOther = item.doctor_name && !mine
  const reservedForOther = item.preferred_doctor_id !== null && item.preferred_doctor_id !== me

  const actionable = item.status === 'waiting' || item.status === 'called'
  const btn = 'rounded-md px-3 py-1.5 text-sm font-semibold disabled:opacity-40'

  return (
    <article
      className={`rounded-lg bg-white p-3 shadow-sm ring-1 ${
        item.status === 'in' ? 'ring-2 ring-brand-green' : item.status === 'called' ? 'ring-2 ring-navy' : 'ring-slate-200'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xl font-bold text-navy">{item.display}</span>
            <span className="truncate font-semibold">{p?.name ?? 'Unknown patient'}</span>
          </div>
          <div className="text-sm text-slate-600">
            {p ? `${p.age} ${p.sex} · ${LANGUAGE[p.language] ?? p.language}` : '—'}
            {' · '}
            {item.complaint ?? 'No complaint recorded'}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-lg font-semibold tabular-nums">{item.wait_min} min</div>
          <div className="text-xs text-slate-500">waiting</div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {item.status === 'called' && (
          <Chip className="bg-navy text-white ring-navy">Called{item.called_count > 1 ? ` ×${item.called_count}` : ''}</Chip>
        )}
        {item.status === 'in' && <Chip className="bg-brand-green text-white ring-brand-green">In consult</Chip>}
        {item.flags.map((f) => (
          <Chip key={f} className={FLAG_STYLE[f].className}>
            {FLAG_STYLE[f].label}
          </Chip>
        ))}
        {withOther && <Chip className="bg-slate-100 text-slate-600 ring-slate-300">with {item.doctor_name}</Chip>}
        {reservedForOther && item.status === 'waiting' && (
          <Chip className="bg-slate-100 text-slate-600 ring-slate-300">reserved for another doctor</Chip>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {item.status === 'in' && mine ? (
          <button type="button" className={`${btn} bg-brand-green text-white`} onClick={() => onOpen(item)}>
            Open
          </button>
        ) : (
          <>
            <button
              type="button"
              disabled={busy || !actionable}
              className={`${btn} bg-navy text-white`}
              onClick={() => onAction(item, 'call')}
            >
              {item.status === 'called' ? 'Call again' : 'Call'}
            </button>
            <button
              type="button"
              disabled={busy || !actionable}
              className={`${btn} bg-brand-green text-white`}
              onClick={() => onAction(item, 'in')}
            >
              In
            </button>
            <button
              type="button"
              disabled={busy || !actionable}
              className={`${btn} bg-slate-200 text-slate-800`}
              onClick={() => onAction(item, 'no-show')}
            >
              No-show
            </button>
          </>
        )}
      </div>
    </article>
  )
}

function Chip({ className, children }: { className: string; children: ReactNode }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${className}`}>{children}</span>
}
