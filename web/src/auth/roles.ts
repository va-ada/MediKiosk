import type { Role } from '../api/types'

/** Where each role lands after login. */
export const ROLE_HOME: Record<Role, string> = {
  doctor: '/doctor',
  nurse: '/triage',
  admin: '/admin',
  desk: '/desk',
}

export const ROLE_LABEL: Record<Role, string> = {
  doctor: 'Doctor',
  nurse: 'Nurse',
  admin: 'Admin',
  desk: 'Help desk',
}
