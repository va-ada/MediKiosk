import type { NewSinceItem, Section } from '../api/types'

interface Props {
  items: NewSinceItem[]
  sectionTitle: (key: Section) => string
  onJump: (key: Section) => void
  onDismiss: () => void
}

/** "New since you opened" — facts that arrived after the doctor first opened this summary (e.g. a late report). */
export default function NewSinceBanner({ items, sectionTitle, onJump, onDismiss }: Props) {
  if (items.length === 0) return null
  return (
    <section
      role="status"
      aria-label="New since you opened"
      className="rounded-lg bg-blue-50 p-3 ring-1 ring-navy/30"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-semibold text-navy">
          New since you opened ({items.length})
        </h2>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-md px-2 py-0.5 text-sm font-semibold text-navy ring-1 ring-navy/40 hover:bg-white"
        >
          Dismiss
        </button>
      </div>
      <ul className="mt-1 space-y-0.5 text-sm">
        {items.map((it) => (
          <li key={it.fact_id}>
            <button type="button" onClick={() => onJump(it.section)} className="text-left hover:underline">
              <span className="font-semibold">{sectionTitle(it.section)}:</span> {it.text}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
