import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import type { Role } from '../api/types'
import { ROLE_HOME } from './roles'
import { useAuth } from './store'

/** Renders children only for a logged-in staff member with one of `roles`; otherwise redirects. */
export default function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const auth = useAuth()
  const location = useLocation()
  if (!auth) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (!roles.includes(auth.staff.role)) return <Navigate to={ROLE_HOME[auth.staff.role]} replace />
  return <>{children}</>
}
