import { useMemo, useState } from 'react'
import { SECTION_ORDER, type Section, type Summary } from '../api/types'
import CriticalStrip from '../components/CriticalStrip'
import PatientHeader from '../components/PatientHeader'
import SectionAccordion from '../components/SectionAccordion'
import { summaryFixture } from '../fixtures'

const DOC_TYPE: Record<string, string> = {
  lab_report: 'Lab report',
  prescription: 'Prescription',
  discharge_summary: 'Discharge summary',
  unknown: 'Document',
}

/** `/doctor/session/:sessionId`: structured, trust-labelled summary. Layout only — uses the §11.1 fixture. */
export default function PatientView() {
  const summary: Summary = summaryFixture
  const sections = useMemo(
    () =>
      [...summary.sections].sort((a, b) => SECTION_ORDER.indexOf(a.key) - SECTION_ORDER.indexOf(b.key)),
    [summary],
  )
  const newFactIds = useMemo(() => new Set(summary.new_since_opened), [summary])
  const [openSections, setOpenSections] = useState<ReadonlySet<Section>>(() => new Set(sections.map((s) => s.key)))

  const toggle = (key: Section): void =>
    setOpenSections((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const documents = [...summary.documents].sort((a, b) => Number(b.pinned) - Number(a.pinned))

  return (
    <div className="flex min-h-full flex-col">
      <PatientHeader summary={summary} />

      <div className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-3">
          <CriticalStrip critical={summary.critical} />
          {sections.map((s) => (
            <SectionAccordion
              key={s.key}
              section={s}
              open={openSections.has(s.key)}
              onToggle={() => toggle(s.key)}
              newFactIds={newFactIds}
            />
          ))}
          <p className="text-xs text-slate-500">
            Summary v{summary.version} · generated {new Date(summary.generated_at).toLocaleString()}
          </p>
        </div>

        <aside aria-label="Documents" className="min-w-0">
          <h2 className="mb-2 font-semibold text-navy">Documents ({documents.length})</h2>
          <ul className="space-y-2">
            {documents.map((d) => (
              <li key={d.id} className="rounded-lg bg-white p-3 text-sm shadow-sm ring-1 ring-slate-200">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{DOC_TYPE[d.doc_type] ?? d.doc_type}</span>
                  {d.pinned && <span className="text-xs font-semibold text-brand-orange">Pinned</span>}
                </div>
                <div className="text-slate-500">
                  {d.doc_date ?? 'No date'} · {d.status}
                </div>
              </li>
            ))}
            {documents.length === 0 && <li className="text-sm text-slate-500">No documents</li>}
          </ul>
        </aside>
      </div>

      <footer className="sticky bottom-0 z-10 flex flex-wrap items-center gap-2 border-t border-slate-200 bg-white px-4 py-2">
        <span className="mr-auto text-sm text-slate-500">Outcome</span>
        {['Out', 'Recheck', 'Refer', 'Follow-up'].map((label) => (
          <button
            key={label}
            type="button"
            disabled
            title="Outcome actions arrive in a later task"
            className="rounded-md bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-500"
          >
            {label}
          </button>
        ))}
      </footer>
    </div>
  )
}
