import type { FactFlag, Trust } from '../api/types'
import { trustChip } from '../theme'

/** Trust label chip (patient_said blue, from_report orange, doctor_verified green, rejected grey). */
export default function TrustChip({ trust }: { trust: Trust }) {
  const t = trustChip[trust]
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap ring-1 ${t.className}`}>
      {t.label}
    </span>
  )
}

const FLAG: Record<FactFlag, { label: string; className: string }> = {
  unreadable: { label: 'Unreadable — check image', className: 'bg-red-50 text-brand-red ring-red-300' },
  patient_disputed: { label: 'Patient disputed', className: 'bg-red-50 text-brand-red ring-red-300' },
  patient_unsure: { label: 'Patient unsure', className: 'bg-amber-50 text-amber-800 ring-amber-300' },
  carried: { label: 'From earlier visit', className: 'bg-slate-100 text-slate-700 ring-slate-300' },
}

/** Fact flag chip (§11.1 `flags`). */
export function FlagChip({ flag }: { flag: FactFlag }) {
  const f = FLAG[flag]
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap ring-1 ${f.className}`}>
      {f.label}
    </span>
  )
}
