import { api } from '../api/client'
import type { LoginRequest, LoginResponse } from '../api/types'
import { authStore } from './store'

/** `POST /api/staff/login` (§4.1); stores the token on success. Throws ApiError (`invalid_pin`). */
export async function login(staffId: string, pin: string): Promise<LoginResponse> {
  const body: LoginRequest = { staff_id: staffId.trim().toUpperCase(), pin }
  const res = await api<LoginResponse>('POST', '/api/staff/login', body, { auth: false })
  authStore.set({ token: res.token, staff: res.staff })
  return res
}

/** Log out. Doctors first release their reserved rechecks (`POST /api/doctors/signout`, best effort). */
export async function logout(): Promise<void> {
  const current = authStore.get()
  if (current?.staff.role === 'doctor') {
    try {
      await api('POST', '/api/doctors/signout')
    } catch {
      // offline or token expired: logging out locally still matters more
    }
  }
  authStore.clear()
}
