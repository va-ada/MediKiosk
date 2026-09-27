import { useState } from 'react'
import type { SummaryItem, VerifyFactRequest } from '../api/types'

interface Props {
  item: SummaryItem
  busy: boolean
  /** Sends `POST /api/facts/{id}/verify`; resolves true on success. */
  onVerify: (item: SummaryItem, body: VerifyFactRequest) => Promise<boolean>
}

const btn = 'rounded-md px-2 py-0.5 text-xs font-semibold ring-1 disabled:opacity-40'

/** Per-fact actions: Approve / Edit (inline) / Reject (with confirm). */
export default function FactMenu({ item, busy, onVerify }: Props) {
  const [mode, setMode] = useState<'idle' | 'edit' | 'reject'>('idle')
  const [text, setText] = useState(item.text)

  const verified = item.trust === 'doctor_verified'
  const run = async (body: VerifyFactRequest): Promise<void> => {
    if (await onVerify(item, body)) setMode('idle')
  }

  if (mode === 'edit') {
    const trimmed = text.trim()
    return (
      <form
        className="flex w-full basis-full flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (trimmed) void run({ action: 'edit', text_en: trimmed })
        }}
      >
        <label className="sr-only" htmlFor={`edit-${item.fact_id}`}>
          Corrected text
        </label>
        <input
          id={`edit-${item.fact_id}`}
          autoFocus
          value={text}
          maxLength={500}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setMode('idle')
          }}
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
        <button type="submit" disabled={busy || !trimmed} className={`${btn} bg-brand-green text-white ring-brand-green`}>
          Save as verified
        </button>
        <button type="button" onClick={() => setMode('idle')} className={`${btn} text-slate-700 ring-slate-300`}>
          Cancel
        </button>
      </form>
    )
  }

  if (mode === 'reject') {
    return (
      <span className="flex items-center gap-1.5" role="group" aria-label="Confirm reject">
        <span className="text-xs font-semibold text-brand-red">Reject this fact?</span>
        <button
          type="button"
          autoFocus
          disabled={busy}
          onClick={() => void run({ action: 'reject' })}
          className={`${btn} bg-brand-red text-white ring-brand-red`}
        >
          Yes, reject
        </button>
        <button type="button" onClick={() => setMode('idle')} className={`${btn} text-slate-700 ring-slate-300`}>
          No
        </button>
      </span>
    )
  }

  return (
    <span className="flex items-center gap-1" role="group" aria-label="Fact actions">
      {!verified && (
        <button
          type="button"
          disabled={busy}
          onClick={() => void run({ action: 'approve' })}
          title="Approve this fact"
          className={`${btn} text-emerald-800 ring-emerald-300 hover:bg-emerald-50`}
        >
          ✓ Approve
        </button>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          setText(item.text)
          setMode('edit')
        }}
        className={`${btn} text-navy ring-navy/40 hover:bg-navy/5`}
      >
        Edit
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => setMode('reject')}
        className={`${btn} text-brand-red ring-red-300 hover:bg-red-50`}
      >
        Reject
      </button>
    </span>
  )
}
