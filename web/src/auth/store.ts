import { useSyncExternalStore } from 'react'
import type { StaffPublic } from '../api/types'

/** Logged-in staff member. Kept in memory and mirrored to sessionStorage (cleared when the tab closes). */
export interface AuthState {
  token: string
  staff: StaffPublic
}

const KEY = 'medikiosk.auth'
const listeners = new Set<() => void>()

function load(): AuthState | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      'token' in parsed &&
      'staff' in parsed &&
      typeof parsed.token === 'string'
    ) {
      return parsed as AuthState
    }
  } catch {
    // unreadable storage: treat as logged out
  }
  return null
}

let state: AuthState | null = load()

function emit(): void {
  listeners.forEach((fn) => fn())
}

export const authStore = {
  get(): AuthState | null {
    return state
  },
  set(next: AuthState): void {
    state = next
    try {
      sessionStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      // storage unavailable: memory only
    }
    emit()
  },
  clear(): void {
    state = null
    try {
      sessionStorage.removeItem(KEY)
    } catch {
      // ignore
    }
    emit()
  },
  subscribe(fn: () => void): () => void {
    listeners.add(fn)
    return () => listeners.delete(fn)
  },
}

export function getToken(): string | null {
  return state?.token ?? null
}

/** React hook: the current auth state (re-renders on login/logout). */
export function useAuth(): AuthState | null {
  return useSyncExternalStore(authStore.subscribe, authStore.get)
}
