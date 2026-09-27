import type { Summary } from '../api/types'

const LANGUAGE: Record<string, string> = { hi: 'Hindi', en: 'English' }
const DEPARTMENT: Record<string, string> = { ayurveda: 'Ayurveda', general: 'General' }

/** Sticky patient header with the allergy banner and red-flag tag (§11.1). */
export default function PatientHeader({ summary }: { summary: Summary }) {
  const { patient, informant, token, critical } = summary
  const complaint = summary.sections.find((s) => s.key === 'complaint')?.items[0]?.text
  const allergies = critical.allergies

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 shadow-sm backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-4 py-2">
        <span className="rounded-md bg-navy px-2 py-1 font-mono text-lg font-bold text-white">{token.display}</span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">
            {patient.name}{' '}
            <span className="font-normal text-slate-600">
              {patient.age} {patient.sex}
            </span>
          </h1>
          <p className="text-sm text-slate-600">
            {patient.hospital_id}
            {' · '}
            {patient.abha_number ? `ABHA ${patient.abha_number}` : 'No ABHA'}
            {' · '}
            {LANGUAGE[patient.language] ?? patient.language}
            {' · '}
            {informant.type === 'self' ? 'Answered by patient' : `Answered by ${informant.relation ?? 'proxy'}`}
            {' · '}
            {DEPARTMENT[token.department] ?? token.department}
          </p>
        </div>
        {complaint && (
          <div className="text-sm">
            <span className="text-slate-500">Complaint </span>
            <span className="font-semibold">{complaint}</span>
          </div>
        )}
        {critical.red_flags.length > 0 && (
          <span className="rounded-full bg-brand-red px-3 py-1 text-sm font-bold text-white">
            ⚠ Red flag{critical.red_flags.length > 1 ? `s (${critical.red_flags.length})` : ''}
          </span>
        )}
      </div>
      {allergies.length > 0 && (
        <div className="bg-brand-red px-4 py-1.5 text-sm font-semibold text-white" role="alert">
          ALLERGY: {allergies.map((a) => a.text).join(' · ')}
        </div>
      )}
    </header>
  )
}
