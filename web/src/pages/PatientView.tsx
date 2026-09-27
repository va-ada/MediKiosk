import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, USE_FIXTURES, api } from '../api/client'
import {
  SECTION_ORDER,
  type Bbox,
  type Fact,
  type OkResponse,
  type Section,
  type Summary,
  type SummaryDocument,
  type SummaryItem,
  type VerifyFactRequest,
  type WsMessage,
} from '../api/types'
import CriticalStrip from '../components/CriticalStrip'
import DocumentViewer from '../components/DocumentViewer'
import DocumentsPanel from '../components/DocumentsPanel'
import NewSinceBanner from '../components/NewSinceBanner'
import OutcomeBar from '../components/OutcomeBar'
import PatientHeader from '../components/PatientHeader'
import SectionAccordion from '../components/SectionAccordion'
import { useChannel } from '../ws/useChannel'

const errorText = (e: unknown, fallback: string): string => (e instanceof ApiError ? e.message : fallback)

/** `/doctor/session/:sessionId`: structured, trust-labelled summary with per-section and per-fact verification. */
export default function PatientView() {
  const { sessionId = '' } = useParams()
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Re-fetch coalescing: one request in flight, at most one queued behind it.
  const inFlight = useRef(false)
  const again = useRef(false)
  const load = useCallback(async (): Promise<void> => {
    if (inFlight.current) {
      again.current = true
      return
    }
    inFlight.current = true
    try {
      do {
        again.current = false
        const s = await api<Summary>('GET', `/api/sessions/${sessionId}/summary`)
        setSummary(s)
        setLoadError(null)
      } while (again.current)
    } catch (e) {
      setLoadError(errorText(e, 'Could not load the summary'))
    } finally {
      inFlight.current = false
    }
  }, [sessionId])

  useEffect(() => {
    setSummary(null)
    void load()
  }, [load])

  const version = summary?.version
  const onMessage = useCallback(
    (msg: WsMessage) => {
      if (msg.type === 'summary.ready' && msg.data.session_id === sessionId && msg.data.version !== version) void load()
    },
    [sessionId, version, load],
  )
  const { connected } = useChannel('queue', onMessage)
  // Catch up on anything missed while the socket was down.
  const lastConnected = useRef<boolean | null>(null)
  useEffect(() => {
    if (connected && lastConnected.current === false) void load()
    if (connected || lastConnected.current !== null) lastConnected.current = connected
  }, [connected, load])

  const sections = useMemo(
    () =>
      summary
        ? [...summary.sections].sort((a, b) => SECTION_ORDER.indexOf(a.key) - SECTION_ORDER.indexOf(b.key))
        : [],
    [summary],
  )

  // Sections expanded on screen, and sections THIS doctor opened on the server in this view.
  const [expanded, setExpanded] = useState<ReadonlySet<Section>>(new Set())
  const [openedByMe, setOpenedByMe] = useState<ReadonlySet<Section>>(new Set())
  const opening = useRef(new Set<Section>())

  const markOpened = useCallback(
    async (key: Section): Promise<void> => {
      if (openedByMe.has(key) || opening.current.has(key)) return
      opening.current.add(key)
      try {
        if (!USE_FIXTURES) await api<OkResponse>('POST', `/api/sessions/${sessionId}/sections/${key}/open`)
        setOpenedByMe((prev) => new Set(prev).add(key))
      } catch (e) {
        setNotice(errorText(e, 'Could not record that the section was opened'))
      } finally {
        opening.current.delete(key)
      }
    },
    [openedByMe, sessionId],
  )

  const expand = (keys: Section[]): void => {
    setExpanded((prev) => {
      const next = new Set(prev)
      keys.forEach((k) => next.add(k))
      return next
    })
    keys.forEach((k) => void markOpened(k))
  }
  const toggle = (key: Section): void => {
    if (expanded.has(key)) {
      setExpanded((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    } else expand([key])
  }

  const approve = async (key: Section): Promise<void> => {
    if (USE_FIXTURES) {
      setNotice('Fixture mode — approvals are not sent to the server.')
      return
    }
    setBusy(true)
    setNotice(null)
    try {
      await api<OkResponse>('POST', `/api/sessions/${sessionId}/sections/${key}/approve`)
      await load()
    } catch (e) {
      if (e instanceof ApiError && e.code === 'section_not_opened') {
        setOpenedByMe((prev) => {
          const next = new Set(prev)
          next.delete(key)
          return next
        })
      }
      setNotice(errorText(e, 'Could not approve the section'))
    } finally {
      setBusy(false)
    }
  }

  const verify = async (item: SummaryItem, body: VerifyFactRequest): Promise<boolean> => {
    if (USE_FIXTURES) {
      setNotice('Fixture mode — verification is not sent to the server.')
      return false
    }
    setBusy(true)
    setNotice(null)
    try {
      await api<Fact>('POST', `/api/facts/${item.fact_id}/verify`, body)
      await load()
      return true
    } catch (e) {
      setNotice(errorText(e, 'Could not update the fact'))
      return false
    } finally {
      setBusy(false)
    }
  }

  const [dismissedNew, setDismissedNew] = useState<ReadonlySet<string>>(new Set())
  const newItems = useMemo(
    () => (summary?.new_since_opened ?? []).filter((n) => !dismissedNew.has(n.fact_id)),
    [summary, dismissedNew],
  )
  const newFactIds = useMemo(() => new Set((summary?.new_since_opened ?? []).map((n) => n.fact_id)), [summary])
  const sectionTitle = (key: Section): string => sections.find((s) => s.key === key)?.title ?? key
  const jumpTo = (key: Section): void => {
    expand([key])
    requestAnimationFrame(() => document.getElementById(`sec-${key}`)?.scrollIntoView({ behavior: 'smooth' }))
  }

  const [viewer, setViewer] = useState<{ doc: SummaryDocument; bbox: Bbox | null } | null>(null)
  const closeViewer = useCallback(() => setViewer(null), [])
  const openSource = (item: SummaryItem): void => {
    const doc = summary?.documents.find((d) => d.id === item.source?.document_id)
    if (doc) setViewer({ doc, bbox: item.source?.bbox ?? null })
  }

  if (!summary) {
    return (
      <main className="p-6">
        {loadError ? (
          <div className="rounded-md bg-red-50 p-4 text-brand-red ring-1 ring-red-200" role="alert">
            <p className="font-semibold">{loadError}</p>
            <div className="mt-2 flex gap-3">
              <button type="button" onClick={() => void load()} className="rounded-md bg-navy px-3 py-1 text-white">
                Retry
              </button>
              <Link to="/doctor" className="rounded-md px-3 py-1 text-navy ring-1 ring-navy/40">
                Back to queue
              </Link>
            </div>
          </div>
        ) : (
          <p className="text-slate-500">Loading summary…</p>
        )}
      </main>
    )
  }

  const unopened = sections.filter((s) => !expanded.has(s.key)).map((s) => s.key)

  return (
    <div className="flex min-h-full flex-col">
      <PatientHeader summary={summary} />

      <div className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-3">
          <CriticalStrip critical={summary.critical} />
          {loadError && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-brand-red ring-1 ring-red-200" role="alert">
              {loadError} — showing the last loaded version.
            </p>
          )}
          {notice && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200" role="status">
              {notice}
            </p>
          )}
          <NewSinceBanner
            items={newItems}
            sectionTitle={sectionTitle}
            onJump={jumpTo}
            onDismiss={() => setDismissedNew(new Set(summary.new_since_opened.map((n) => n.fact_id)))}
          />
          <div className="flex items-center justify-between gap-2 text-sm text-slate-600">
            <span>Open a section to review it; approve marks all its facts doctor-verified.</span>
            {unopened.length > 0 && (
              <button
                type="button"
                onClick={() => expand(unopened)}
                className="shrink-0 rounded-md px-3 py-1 font-semibold text-navy ring-1 ring-navy/40 hover:bg-navy/5"
              >
                Open all
              </button>
            )}
          </div>
          {sections.map((s) => (
            <SectionAccordion
              key={s.key}
              section={s}
              open={expanded.has(s.key)}
              onToggle={() => toggle(s.key)}
              newFactIds={newFactIds}
              onSourceClick={openSource}
              openedByMe={openedByMe.has(s.key)}
              onApprove={() => void approve(s.key)}
              onVerify={verify}
              busy={busy}
            />
          ))}
          <p className="text-xs text-slate-500">
            Summary v{summary.version} · generated {new Date(summary.generated_at).toLocaleString()} ·{' '}
            {USE_FIXTURES ? 'fixtures' : connected ? 'live' : 'reconnecting…'}
          </p>
        </div>

        <aside className="min-w-0">
          <DocumentsPanel documents={summary.documents} onOpen={(doc) => setViewer({ doc, bbox: null })} />
        </aside>
      </div>

      <OutcomeBar
        sessionId={summary.session_id}
        department={summary.token.department}
        tokenDisplay={summary.token.display}
      />

      {viewer && <DocumentViewer document={viewer.doc} bbox={viewer.bbox} onClose={closeViewer} />}
    </div>
  )
}
