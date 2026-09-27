import { useCallback, useMemo, useState } from 'react'
import { SECTION_ORDER, type Bbox, type Section, type Summary, type SummaryDocument, type SummaryItem } from '../api/types'
import CriticalStrip from '../components/CriticalStrip'
import DocumentViewer from '../components/DocumentViewer'
import DocumentsPanel from '../components/DocumentsPanel'
import PatientHeader from '../components/PatientHeader'
import SectionAccordion from '../components/SectionAccordion'
import { summaryFixture } from '../fixtures'

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

  const [viewer, setViewer] = useState<{ doc: SummaryDocument; bbox: Bbox | null } | null>(null)
  const closeViewer = useCallback(() => setViewer(null), [])
  const openSource = (item: SummaryItem): void => {
    const doc = summary.documents.find((d) => d.id === item.source?.document_id)
    if (doc) setViewer({ doc, bbox: item.source?.bbox ?? null })
  }

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
              onSourceClick={openSource}
            />
          ))}
          <p className="text-xs text-slate-500">
            Summary v{summary.version} · generated {new Date(summary.generated_at).toLocaleString()}
          </p>
        </div>

        <aside className="min-w-0">
          <DocumentsPanel documents={summary.documents} onOpen={(doc) => setViewer({ doc, bbox: null })} />
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

      {viewer && <DocumentViewer document={viewer.doc} bbox={viewer.bbox} onClose={closeViewer} />}
    </div>
  )
}
