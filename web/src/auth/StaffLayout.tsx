import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import AutoLock from './AutoLock'
import { logout } from './login'
import { ROLE_HOME, ROLE_LABEL } from './roles'
import { useAuth } from './store'

/** Header (name, role, department, logout) + auto-lock around every staff page. */
export default function StaffLayout() {
  const auth = useAuth()
  const navigate = useNavigate()
  // The triage/alert station must never be hidden behind a lock screen: alarms have to stay visible.
  const lockable = !useLocation().pathname.startsWith('/triage')

  const onLogout = async (): Promise<void> => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex items-center justify-between gap-4 bg-navy px-4 py-2 text-white">
        <Link to={auth ? ROLE_HOME[auth.staff.role] : '/login'} className="text-lg font-semibold tracking-wide">
          MediKiosk
        </Link>
        {auth && (
          <div className="flex items-center gap-4 text-sm">
            <span>
              <span className="font-semibold">{auth.staff.name}</span>
              <span className="text-white/75">
                {' · '}
                {ROLE_LABEL[auth.staff.role]}
                {auth.staff.department ? ` · ${auth.staff.department}` : ''}
                {auth.staff.room ? ` · ${auth.staff.room}` : ''}
              </span>
            </span>
            <button
              type="button"
              onClick={() => void onLogout()}
              className="rounded-md bg-white/15 px-3 py-1.5 font-medium hover:bg-white/25"
            >
              Log out
            </button>
          </div>
        )}
      </header>
      <div className="flex-1">
        <Outlet />
      </div>
      {lockable && <AutoLock key={auth?.staff.id ?? 'logged-out'} />}
    </div>
  )
}
