import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { login, logout } from './login'
import PinPad from './PinPad'
import { useAuth } from './store'

export const IDLE_LOCK_MS = 5 * 60 * 1000
const ACTIVITY_EVENTS = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'] as const

/**
 * After 5 minutes without input, covers the page with a PIN re-entry overlay for the same staff member.
 * The page underneath stays mounted, so its state is kept.
 */
export default function AutoLock() {
  const auth = useAuth()
  const [locked, setLocked] = useState(false)
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    // StaffLayout remounts this component per staff login (key), so a new login always starts unlocked.
    if (!auth || locked) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const arm = (): void => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => setLocked(true), IDLE_LOCK_MS)
    }
    arm()
    ACTIVITY_EVENTS.forEach((ev) => window.addEventListener(ev, arm, { passive: true }))
    return () => {
      if (timer) clearTimeout(timer)
      ACTIVITY_EVENTS.forEach((ev) => window.removeEventListener(ev, arm))
    }
  }, [auth, locked])

  if (!auth || !locked) return null

  const unlock = async (entered: string): Promise<void> => {
    setBusy(true)
    setError(null)
    try {
      await login(auth.staff.id, entered)
      setPin('')
      setLocked(false)
    } catch (e) {
      setPin('')
      setError(e instanceof ApiError && e.code === 'invalid_pin' ? 'Wrong PIN — try again' : errorText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="autolock-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-md"
    >
      <div className="w-full max-w-sm rounded-2xl bg-white p-6 text-center shadow-xl">
        <h2 id="autolock-title" className="text-xl font-semibold text-navy">
          Screen locked
        </h2>
        <p className="mt-1 text-slate-600">
          {auth.staff.name} ({auth.staff.id}) — enter your PIN to continue
        </p>
        <div className="mt-5">
          <PinPad value={pin} onChange={setPin} onComplete={(p) => void unlock(p)} disabled={busy} />
        </div>
        <p className="mt-3 min-h-6 text-sm font-medium text-brand-red" role="alert">
          {error}
        </p>
        <button type="button" onClick={() => void logout()} className="mt-2 text-sm text-slate-600 underline">
          Not {auth.staff.name}? Log out
        </button>
      </div>
    </div>
  )
}

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Something went wrong — try again'
}
