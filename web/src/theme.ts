import type { Lane, Trust } from './api/types'

/** Brand colours (also defined as Tailwind theme colours in index.css: navy, brand-orange, brand-green, brand-red). */
export const colors = {
  navy: '#1F497D',
  orange: '#E07B24',
  green: '#1E8E6A',
  red: '#C0392B',
} as const

/** Trust chip styles: patient_said blue, from_report orange, doctor_verified green, rejected grey. */
export const trustChip: Record<Trust, { label: string; className: string }> = {
  patient_said: { label: 'Patient said', className: 'bg-blue-100 text-blue-800 ring-blue-300' },
  from_report: { label: 'From report', className: 'bg-orange-100 text-orange-800 ring-orange-300' },
  doctor_verified: { label: 'Doctor verified', className: 'bg-emerald-100 text-emerald-800 ring-emerald-300' },
  rejected: { label: 'Rejected', className: 'bg-gray-200 text-gray-600 ring-gray-300 line-through' },
}

/** Lane accent styles for queue groups. */
export const laneStyle: Record<Lane, { label: string; className: string }> = {
  emergency: { label: 'Emergency', className: 'border-brand-red bg-red-50 text-brand-red' },
  priority: { label: 'Priority', className: 'border-brand-orange bg-orange-50 text-brand-orange' },
  normal: { label: 'Normal', className: 'border-navy bg-slate-50 text-navy' },
}
