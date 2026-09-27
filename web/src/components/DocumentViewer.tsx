import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import type { Bbox, SummaryDocument } from '../api/types'
import { DOC_TYPE_LABEL, useDocumentImage } from './DocumentsPanel'

const MIN_ZOOM = 0.5
const MAX_ZOOM = 4

/** bbox in image pixels → CSS percentages of the displayed image (so it scales with zoom). */
export function bboxToPercent(bbox: Bbox, natural: { width: number; height: number }) {
  const [x, y, w, h] = bbox
  return {
    left: (x / natural.width) * 100,
    top: (y / natural.height) * 100,
    width: (w / natural.width) * 100,
    height: (h / natural.height) * 100,
  }
}

interface Props {
  document: SummaryDocument
  /** Highlight rectangle for the fact that was clicked, in image pixels. */
  bbox?: Bbox | null
  onClose: () => void
}

/** Modal document viewer with zoom (buttons) and pan (drag), plus an optional source highlight. */
export default function DocumentViewer({ document: doc, bbox, onClose }: Props) {
  const { url, error } = useDocumentImage(doc.image_url)
  const [zoom, setZoom] = useState(1)
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Bring the highlight into view once the image size is known (and after zoom changes).
  useEffect(() => {
    const el = scroller.current
    if (!el || !natural || !bbox) return
    const p = bboxToPercent(bbox, natural)
    const content = el.firstElementChild as HTMLElement | null
    if (!content) return
    el.scrollTo({
      left: ((p.left + p.width / 2) / 100) * content.offsetWidth - el.clientWidth / 2,
      top: ((p.top + p.height / 2) / 100) * content.offsetHeight - el.clientHeight / 2,
    })
  }, [natural, bbox, zoom])

  const clampZoom = (z: number): number => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(z * 100) / 100))

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>): void => {
    const el = scroller.current
    if (!el) return
    drag.current = { x: e.clientX, y: e.clientY, left: el.scrollLeft, top: el.scrollTop }
    el.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>): void => {
    const el = scroller.current
    const d = drag.current
    if (!el || !d) return
    el.scrollLeft = d.left - (e.clientX - d.x)
    el.scrollTop = d.top - (e.clientY - d.y)
  }
  const endDrag = (): void => {
    drag.current = null
  }

  const highlight = bbox && natural ? bboxToPercent(bbox, natural) : null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${DOC_TYPE_LABEL[doc.doc_type]} ${doc.doc_date ?? ''}`}
      className="fixed inset-0 z-40 flex flex-col bg-slate-900/80"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="flex items-center gap-2 bg-white px-4 py-2 shadow">
        <span className="mr-auto font-semibold text-navy">
          {DOC_TYPE_LABEL[doc.doc_type]} · {doc.doc_date ?? 'No date'}
          {bbox && <span className="ml-2 text-sm font-normal text-brand-orange">source highlighted</span>}
        </span>
        <button type="button" className="rounded-md px-3 py-1 ring-1 ring-slate-300" onClick={() => setZoom((z) => clampZoom(z - 0.25))} aria-label="Zoom out">
          −
        </button>
        <span className="w-14 text-center text-sm tabular-nums">{Math.round(zoom * 100)}%</span>
        <button type="button" className="rounded-md px-3 py-1 ring-1 ring-slate-300" onClick={() => setZoom((z) => clampZoom(z + 0.25))} aria-label="Zoom in">
          +
        </button>
        <button type="button" className="rounded-md px-3 py-1 text-sm ring-1 ring-slate-300" onClick={() => setZoom(1)}>
          Fit
        </button>
        <button type="button" className="rounded-md bg-navy px-3 py-1 text-sm font-semibold text-white" onClick={onClose}>
          Close
        </button>
      </div>

      <div
        ref={scroller}
        className="relative m-4 flex-1 cursor-grab overflow-auto rounded-lg bg-slate-700 active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        {/* width is a percentage of the viewport: zoom 1 = fit to width */}
        <div className="relative mx-auto select-none" style={{ width: `${zoom * 100}%` }}>
          {url && (
            <img
              src={url}
              alt={`${DOC_TYPE_LABEL[doc.doc_type]} page`}
              draggable={false}
              className="block h-auto w-full bg-white"
              onLoad={(e) => setNatural({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
            />
          )}
          {highlight && (
            <div
              data-testid="source-highlight"
              className="pointer-events-none absolute rounded-sm bg-yellow-300/30 ring-4 ring-brand-orange"
              style={{
                left: `${highlight.left}%`,
                top: `${highlight.top}%`,
                width: `${highlight.width}%`,
                height: `${highlight.height}%`,
              }}
            />
          )}
        </div>
        {!url && !error && <p className="p-6 text-white">Loading image…</p>}
        {error && <p className="p-6 text-red-200">{error}</p>}
      </div>
    </div>
  )
}
