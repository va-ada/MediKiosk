import { Navigate, Route, Routes } from 'react-router-dom'
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
      <Route path="/doctor" element={<DoctorQueue />} />
      <Route path="/doctor/session/:sessionId" element={<PatientView />} />
      <Route path="/triage" element={<Triage />} />
      <Route path="/desk" element={<Desk />} />
      <Route path="/display" element={<Display />} />
      <Route path="/admin" element={<Admin />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
