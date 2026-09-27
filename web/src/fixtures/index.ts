/**
 * Offline fixtures (VITE_USE_FIXTURES=true), built from CONTRACTS.md §11 examples.
 * Only GETs are served from here; writes still go to the server.
 */
import type { Alert, DisplayState, QueueItem, Summary } from '../api/types'
import alertsJson from './alerts.json'
import displayJson from './display.json'
import docD1 from './doc-d1.svg'
import docD2 from './doc-d2.svg'
import queueJson from './queue.json'
import summaryJson from './summary.json'

export const summaryFixture = summaryJson as unknown as Summary
export const queueFixture = queueJson as unknown as QueueItem[]
export const alertsFixture = alertsJson as unknown as Alert[]
export const displayFixture = displayJson as unknown as DisplayState

/** Placeholder images for fixture documents (drawn so the §11.1 bboxes land on real lines). */
const documentImages: Record<string, string> = { d1: docD1, d2: docD2 }

type FixtureBody = Summary | QueueItem[] | Alert[] | DisplayState

/** The fixture for a GET path, or undefined if there is none. */
export function fixtureFor(path: string): FixtureBody | undefined {
  const p = path.split('?')[0]
  if (/^\/api\/sessions\/[^/]+\/summary$/.test(p)) return summaryFixture
  if (p === '/api/queue') return queueFixture
  if (p === '/api/alerts') return alertsFixture
  if (p === '/api/display/state') return displayFixture
  return undefined
}

/** Placeholder image URL for `/api/documents/{id}/image`, or undefined. */
export function fixtureBlobUrl(path: string): string | undefined {
  const m = /^\/api\/documents\/([^/]+)\/image$/.exec(path.split('?')[0])
  if (!m) return undefined
  return documentImages[m[1]] ?? docD1
}
