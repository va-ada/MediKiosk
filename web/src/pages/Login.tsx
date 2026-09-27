import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { login } from '../auth/login'
import PinPad, { PIN_LENGTH } from '../auth/PinPad'
import { ROLE_HOME } from '../auth/roles'
import { useAuth } from '../auth/store'

/** `/login`: staff ID + 4-digit PIN keypad → role home. */
export default function Login() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [staffId, setStaffId] = useState('')
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (auth) return <Navigate to={ROLE_HOME[auth.staff.role]} replace />

  const submit = async (enteredPin: string): Promise<void> => {
    if (!staffId.trim()) {
      setError('Enter your staff ID first')
      setPin('')
      return
    }
    if (enteredPin.length !== PIN_LENGTH) return
    setBusy(true)
    setError(null)
    try {
      const res = await login(staffId, enteredPin)
      navigate(ROLE_HOME[res.staff.role], { replace: true })
    } catch (e) {
      setPin('')
      if (e instanceof ApiError && e.code === 'invalid_pin') setError('Wrong staff ID or PIN')
      else if (e instanceof ApiError) setError(e.message)
      else setError('Something went wrong — try again')
    } finally {
      setBusy(false)
    }
  }

  const onSubmit = (e: FormEvent): void => {
    e.preventDefault()
    void submit(pin)
  }

  return (
    <main className="flex min-h-full items-center justify-center p-4">
      <form onSubmit={onSubmit} className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-lg ring-1 ring-slate-200">
        <h1 className="text-center text-2xl font-bold text-navy">MediKiosk</h1>
        <p className="text-center text-slate-600">Staff login</p>

        <label htmlFor="staff-id" className="mt-6 block text-sm font-medium text-slate-700">
          Staff ID
        </label>
        <input
          id="staff-id"
          value={staffId}
          onChange={(e) => setStaffId(e.target.value.toUpperCase())}
          autoFocus
          autoComplete="username"
          autoCapitalize="characters"
          placeholder="e.g. D1"
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-3 text-xl tracking-wider focus:border-navy focus:ring-2 focus:ring-navy/30 focus:outline-none"
        />

        <p className="mt-5 mb-2 text-sm font-medium text-slate-700">PIN</p>
        <PinPad value={pin} onChange={setPin} onComplete={(p) => void submit(p)} disabled={busy} />

        <p className="mt-3 min-h-6 text-center text-sm font-medium text-brand-red" role="alert">
          {error}
        </p>
        <button
          type="submit"
          disabled={busy || pin.length !== PIN_LENGTH || !staffId.trim()}
          className="mt-2 w-full rounded-xl bg-navy py-3 text-lg font-semibold text-white disabled:opacity-40"
        >
          {busy ? 'Logging in…' : 'Log in'}
        </button>
      </form>
    </main>
  )
}
