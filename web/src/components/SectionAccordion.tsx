import type { SummaryItem, SummarySection } from '../api/types'
import TrustChip, { FlagChip } from './TrustChip'

interface Props {
  section: SummarySection
  open: boolean
  onToggle: () => void
  /** fact ids created after the doctor first opened the summary. */
  newFactIds?: ReadonlySet<string>
  /** Show the fact's source on its document (items with `source`). */
  onSourceClick?: (item: SummaryItem) => void
}

/** One summary section (§11.1): header + items; HPI narrative on top; drugs from documents grouped apart. */
export default function SectionAccordion({ section, open, onToggle, newFactIds, onSourceClick }: Props) {
  const isDrugs = section.key === 'drugs'
  const current = isDrugs ? section.items.filter((i) => !i.found_in_documents) : section.items
  const fromDocs = isDrugs ? section.items.filter((i) => i.found_in_documents) : []
  const panelId = `section-${section.key}`

  return (
    <section className="rounded-lg bg-white shadow-sm ring-1 ring-slate-200">
      <h2>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={panelId}
          className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left"
        >
          <span className="flex items-center gap-2 font-semibold text-navy">
            <span aria-hidden className="inline-block w-3 text-slate-400">
              {open ? '▾' : '▸'}
            </span>
            {section.title}
            <span className="text-sm font-normal text-slate-500">({section.items.length})</span>
          </span>
          <span className="flex gap-1.5 text-xs">
            {section.approved ? (
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 font-semibold text-emerald-800">Approved</span>
            ) : section.opened ? (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">Viewed</span>
            ) : null}
          </span>
        </button>
      </h2>

      {open && (
        <div id={panelId} className="border-t border-slate-100 px-4 py-3">
          {section.narrative && (
            <div className="mb-3 rounded-md bg-slate-50 p-3">
              <p className="leading-relaxed">{section.narrative}</p>
              <p className="mt-1 text-xs font-medium text-amber-700">AI-drafted from patient answers — verify</p>
            </div>
          )}

          <ItemList items={current} newFactIds={newFactIds} onSourceClick={onSourceClick} />
          {current.length === 0 && fromDocs.length === 0 && <p className="text-sm text-slate-500">Nothing recorded.</p>}

          {fromDocs.length > 0 && (
            <div className="mt-3 rounded-md border border-dashed border-orange-300 bg-orange-50/50 p-3">
              <h3 className="mb-1 text-sm font-semibold text-orange-800">Found in documents — not yet verified</h3>
              <ItemList items={fromDocs} newFactIds={newFactIds} onSourceClick={onSourceClick} />
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function ItemList({
  items,
  newFactIds,
  onSourceClick,
}: {
  items: SummaryItem[]
  newFactIds?: ReadonlySet<string>
  onSourceClick?: (item: SummaryItem) => void
}) {
  if (items.length === 0) return null
  return (
    <ul className="divide-y divide-slate-100">
      {items.map((item) => (
        <li key={item.fact_id} className="flex flex-wrap items-start justify-between gap-2 py-2">
          <div className="min-w-0 flex-1">
            <p className={item.trust === 'rejected' ? 'text-slate-400 line-through' : ''}>{item.text}</p>
            {item.patient_words && <p className="text-sm text-slate-500 italic">“{item.patient_words}”</p>}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {newFactIds?.has(item.fact_id) && (
              <span className="rounded-full bg-navy px-2 py-0.5 text-xs font-semibold text-white">New</span>
            )}
            {item.flags.map((f) => (
              <FlagChip key={f} flag={f} />
            ))}
            <TrustChip trust={item.trust} />
            {item.source && onSourceClick && (
              <button
                type="button"
                onClick={() => onSourceClick(item)}
                className="rounded-md px-2 py-0.5 text-xs font-semibold text-navy ring-1 ring-navy/40 hover:bg-navy/5"
              >
                View source
              </button>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
