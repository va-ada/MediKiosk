import { authStore, getToken } from '../auth/store'
import { fixtureBlobUrl, fixtureFor } from '../fixtures'

export const API_URL: string = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
export const WS_URL: string = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000').replace(/\/$/, '')
export const RELAY_URL: string = (import.meta.env.VITE_RELAY_URL || 'http://localhost:8003').replace(/\/$/, '')
export const RELAY_WS: string = import.meta.env.VITE_RELAY_WS || 'ws://localhost:8003/ws'
export const USE_FIXTURES: boolean = import.meta.env.VITE_USE_FIXTURES === 'true'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

/** §1 error: `{"error": {"code", "message"}}`. `status` 0 = network error (server unreachable). */
export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

export interface ApiOptions {
  /** Send the staff Bearer token (default true). The assisted desk sends `X-Kiosk-Id` instead. */
  auth?: boolean
  headers?: Record<string, string>
  signal?: AbortSignal
}

async function errorFrom(res: Response): Promise<ApiError> {
  try {
    const body: unknown = await res.json()
    if (typeof body === 'object' && body !== null && 'error' in body) {
      const err = (body as { error: { code?: unknown; message?: unknown } }).error
      if (typeof err.code === 'string') {
        return new ApiError(err.code, typeof err.message === 'string' ? err.message : err.code, res.status)
      }
    }
  } catch {
    // not JSON
  }
  return new ApiError('http_error', `HTTP ${res.status}`, res.status)
}

async function send(method: HttpMethod, path: string, body: unknown, options: ApiOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json', ...options.headers }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = options.auth === false ? null : getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: options.signal,
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError('network_error', 'Cannot reach the MediKiosk server')
  }
  if (!res.ok) {
    const err = await errorFrom(res)
    // An expired/invalid staff token: drop it so RequireRole sends the user back to /login.
    if (token && res.status === 401 && err.code === 'unauthorized') authStore.clear()
    throw err
  }
  return res
}

/**
 * Call the MediKiosk API. Returns the parsed JSON body, or `null` for 204 No Content
 * (e.g. `POST /api/queue/next` with an empty queue) — include `null` in `T` for such endpoints.
 * With `VITE_USE_FIXTURES=true`, GETs that have a fixture are served from `src/fixtures/`.
 */
export async function api<T>(method: HttpMethod, path: string, body?: unknown, options: ApiOptions = {}): Promise<T> {
  if (USE_FIXTURES && method === 'GET') {
    const fixture = fixtureFor(path)
    if (fixture !== undefined) return fixture as T
  }
  const res = await send(method, path, body, options)
  if (res.status === 204) return null as T
  return (await res.json()) as T
}

/** Fetch binary content (e.g. `/api/documents/{id}/image`) with the Bearer token; returns an object URL. */
export async function apiBlobUrl(path: string, options: ApiOptions = {}): Promise<string> {
  if (USE_FIXTURES) {
    const url = fixtureBlobUrl(path)
    if (url !== undefined) return url
  }
  const res = await send('GET', path, undefined, options)
  return URL.createObjectURL(await res.blob())
}
