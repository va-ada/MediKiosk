import { Navigate, Route, Routes } from 'react-router-dom'
import RequireRole from './auth/RequireRole'
import StaffLayout from './auth/StaffLayout'
import Admin from './pages/Admin'
import Desk from './pages/Desk'
import Display from './pages/Display'
import DoctorQueue from './pages/DoctorQueue'
import Login from './pages/Login'
import PatientView from './pages/PatientView'
import Triage from './pages/Triage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {/* Public: the waiting-hall display board has no login. */}
      <Route path="/display" element={<Display />} />
      <Route element={<StaffLayout />}>
        <Route
          path="/doctor"
          element={
            <RequireRole roles={['doctor']}>
              <DoctorQueue />
            </RequireRole>
          }
        />
        <Route
          path="/doctor/session/:sessionId"
          element={
            <RequireRole roles={['doctor']}>
              <PatientView />
            </RequireRole>
          }
        />
        <Route
          path="/triage"
          element={
            <RequireRole roles={['nurse', 'doctor']}>
              <Triage />
            </RequireRole>
          }
        />
        <Route
          path="/desk"
          element={
            <RequireRole roles={['desk']}>
              <Desk />
            </RequireRole>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireRole roles={['admin']}>
              <Admin />
            </RequireRole>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
