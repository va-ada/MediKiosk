import { useEffect, useState } from 'react'
import { ApiError, apiBlobUrl } from '../api/client'
import type { DocStatus, DocType, SummaryDocument } from '../api/types'

export const DOC_TYPE_LABEL: Record<DocType, string> = {
  lab_report: 'Lab report',
  prescription: 'Prescription',
  discharge_summary: 'Discharge summary',
  unknown: 'Document',
}

const STATUS_BADGE: Record<DocStatus, { label: string; className: string }> = {
  pending: { label: 'Reading…', className: 'bg-amber-100 text-amber-800' },
  processed: { label: 'Read', className: 'bg-emerald-100 text-emerald-800' },
  failed: { label: 'Could not read', className: 'bg-red-100 text-brand-red' },
}

/** One fetch per image path while the page is open (thumbnail and viewer share it). */
const imageCache = new Map<string, Promise<string>>()

/** Load `/api/documents/{id}/image` with the Bearer token → object URL. */
export function useDocumentImage(path: string): { url: string | null; error: string | null } {
  const [state, setState] = useState<{ path: string; url: string | null; error: string | null }>({
    path,
    url: null,
    error: null,
  })

  useEffect(() => {
    let alive = true
    let pending = imageCache.get(path)
    if (!pending) {
      pending = apiBlobUrl(path)
      imageCache.set(path, pending)
      pending.catch(() => imageCache.delete(path)) // let a later render retry
    }
    pending.then(
      (url) => alive && setState({ path, url, error: null }),
      (e: unknown) =>
        alive &&
        setState({
          path,
          url: null,
          error: e instanceof ApiError && e.code === 'patient_erased' ? 'Image erased at patient request' : 'Image unavailable',
        }),
    )
    return () => {
      alive = false
    }
  }, [path])

  return state.path === path ? { url: state.url, error: state.error } : { url: null, error: null }
}

/** Pinned first, then newest `doc_date` first (undated last). */
export function sortDocuments(docs: SummaryDocument[]): SummaryDocument[] {
  return [...docs].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    if (a.doc_date === b.doc_date) return 0
    if (!a.doc_date) return 1
    if (!b.doc_date) return -1
    return b.doc_date.localeCompare(a.doc_date)
  })
}

interface Props {
  documents: SummaryDocument[]
  onOpen: (doc: SummaryDocument) => void
}

/** Right-hand documents column: thumbnails with status badges. */
export default function DocumentsPanel({ documents, onOpen }: Props) {
  const docs = sortDocuments(documents)
  return (
    <section aria-label="Documents">
      <h2 className="mb-2 font-semibold text-navy">Documents ({docs.length})</h2>
      {docs.length === 0 && <p className="text-sm text-slate-500">No documents</p>}
      <ul className="grid grid-cols-2 gap-2 lg:grid-cols-1 xl:grid-cols-2">
        {docs.map((d) => (
          <li key={d.id}>
            <Thumbnail doc={d} onOpen={onOpen} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function Thumbnail({ doc, onOpen }: { doc: SummaryDocument; onOpen: (doc: SummaryDocument) => void }) {
  const { url, error } = useDocumentImage(doc.image_url)
  const badge = STATUS_BADGE[doc.status]
  return (
    <button
      type="button"
      onClick={() => onOpen(doc)}
      className="w-full overflow-hidden rounded-lg bg-white text-left shadow-sm ring-1 ring-slate-200 hover:ring-navy"
    >
      <div className="flex h-32 items-center justify-center overflow-hidden bg-slate-100">
        {url ? (
          <img src={url} alt="" className="h-full w-full object-cover object-top" />
        ) : (
          <span className="px-2 text-center text-xs text-slate-500">{error ?? 'Loading…'}</span>
        )}
      </div>
      <div className="p-2 text-xs">
        <div className="flex items-center justify-between gap-1">
          <span className="font-semibold">{DOC_TYPE_LABEL[doc.doc_type]}</span>
          {doc.pinned && <span className="font-semibold text-brand-orange">Pinned</span>}
        </div>
        <div className="mt-1 flex items-center justify-between gap-1">
          <span className="text-slate-500">{doc.doc_date ?? 'No date'}</span>
          <span className={`rounded-full px-1.5 py-0.5 font-semibold ${badge.className}`}>{badge.label}</span>
        </div>
      </div>
    </button>
  )
}
