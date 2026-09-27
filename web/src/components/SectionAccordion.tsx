import type { SummaryItem, SummarySection, VerifyFactRequest } from '../api/types'
import FactMenu from './FactMenu'
import TrustChip, { FlagChip } from './TrustChip'

interface Props {
  section: SummarySection
  open: boolean
  onToggle: () => void
  /** fact ids created after the doctor first opened the summary. */
  newFactIds?: ReadonlySet<string>
  /** Show the fact's source on its document (items with `source`). */
  onSourceClick?: (item: SummaryItem) => void
  /** This doctor has opened the section in this view (the server only lets the opener approve it). */
  openedByMe?: boolean
  onApprove?: () => void
  onVerify?: (item: SummaryItem, body: VerifyFactRequest) => Promise<boolean>
  busy?: boolean
}

/** One summary section (§11.1): header + items; HPI narrative on top; drugs from documents grouped apart. */
export default function SectionAccordion({
  section,
  open,
  onToggle,
  newFactIds,
  onSourceClick,
  openedByMe = false,
  onApprove,
  onVerify,
  busy = false,
}: Props) {
  const isDrugs = section.key === 'drugs'
  const current = isDrugs ? section.items.filter((i) => !i.found_in_documents) : section.items
  const fromDocs = isDrugs ? section.items.filter((i) => i.found_in_documents) : []
  const panelId = `section-${section.key}`
  const allVerified = section.items.length > 0 && section.items.every((i) => i.trust === 'doctor_verified')

  return (
    <section
      id={`sec-${section.key}`}
      className={`scroll-mt-32 rounded-lg bg-white shadow-sm ring-1 ${section.approved ? 'ring-emerald-300' : 'ring-slate-200'}`}
    >
      <div className="flex items-center gap-2 pr-3">
        <h2 className="min-w-0 flex-1">
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
        {onApprove && (
          <button
            type="button"
            onClick={onApprove}
            disabled={busy || !openedByMe || (section.approved && allVerified)}
            title={openedByMe ? 'Mark every fact in this section doctor-verified' : 'Open the section first'}
            className="shrink-0 rounded-md bg-brand-green px-3 py-1 text-sm font-semibold text-white disabled:bg-slate-200 disabled:text-slate-500"
          >
            {section.approved && allVerified ? 'Approved ✓' : 'Approve section'}
          </button>
        )}
      </div>

      {open && (
        <div id={panelId} className="border-t border-slate-100 px-4 py-3">
          {section.narrative && (
            <div className="mb-3 rounded-md bg-slate-50 p-3">
              <p className="leading-relaxed">{section.narrative}</p>
              {section.narrative_ai ? (
                <p className="mt-1 text-xs font-semibold text-amber-700">
                  AI-drafted from patient answers — verify against the facts below
                </p>
              ) : (
                <p className="mt-1 text-xs text-slate-500">Patient answers joined (no AI narrative)</p>
              )}
            </div>
          )}

          <ItemList items={current} newFactIds={newFactIds} onSourceClick={onSourceClick} onVerify={onVerify} busy={busy} />
          {current.length === 0 && fromDocs.length === 0 && <p className="text-sm text-slate-500">Nothing recorded.</p>}

          {fromDocs.length > 0 && (
            <div className="mt-3 rounded-md border border-dashed border-orange-300 bg-orange-50/50 p-3">
              <h3 className="mb-1 text-sm font-semibold text-orange-800">Found in documents — not yet verified</h3>
              <ItemList items={fromDocs} newFactIds={newFactIds} onSourceClick={onSourceClick} onVerify={onVerify} busy={busy} />
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
  onVerify,
  busy,
}: {
  items: SummaryItem[]
  newFactIds?: ReadonlySet<string>
  onSourceClick?: (item: SummaryItem) => void
  onVerify?: (item: SummaryItem, body: VerifyFactRequest) => Promise<boolean>
  busy: boolean
}) {
  if (items.length === 0) return null
  return (
    <ul className="divide-y divide-slate-100">
      {items.map((item) => (
        <li key={item.fact_id} className="flex flex-wrap items-start justify-between gap-2 py-2">
          <div className="min-w-0 flex-1">
            <p className={item.trust === 'rejected' ? 'text-slate-400 line-through' : ''}>{item.text}</p>
            {item.patient_words && <p className="text-sm text-slate-500 italic">“{item.patient_words}”</p>}
            {item.doctor_note && <p className="text-xs text-slate-500">{item.doctor_note}</p>}
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
          {onVerify && <FactMenu item={item} busy={busy} onVerify={onVerify} />}
        </li>
      ))}
    </ul>
  )
}
