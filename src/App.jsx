import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import { AuthProvider, useAuth } from './context/AuthContext'
import { PatientProvider } from './context/PatientContext'
import { ThemeProvider } from './context/ThemeContext'
import Dashboard from './pages/Dashboard'
import Landing from './pages/Landing'
import Login from './pages/Login'
import NewPatient from './pages/NewPatient'
import PatientRecord from './pages/PatientRecord'
import Register from './pages/Register'
import AdverseRiskAssessment from './pages/AdverseRiskAssessment'

function ProtectedRoute() { const { doctor, authLoading } = useAuth(); return authLoading ? <div className="p-6 text-sm text-slate-500">Restoring secure session…</div> : doctor ? <Outlet /> : <Navigate to="/login" replace /> }
function PublicOnly({ children }) { const { doctor, authLoading } = useAuth(); return authLoading ? <div className="p-6 text-sm text-slate-500">Restoring secure session…</div> : doctor ? <Navigate to="/dashboard" replace /> : children }

export default function App() {
  return <BrowserRouter><AuthProvider><PatientProvider><ThemeProvider><Routes>
    <Route path="/" element={<PublicOnly><Landing /></PublicOnly>} /><Route path="/register" element={<PublicOnly><Register /></PublicOnly>} /><Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
    <Route element={<ProtectedRoute />}><Route element={<AppLayout />}><Route path="/dashboard" element={<Dashboard />} /><Route path="/patients/new" element={<NewPatient />} /><Route path="/patients/:patientId" element={<PatientRecord />} /><Route path="/patients/:patientId/consultations/:visitId/adr" element={<AdverseRiskAssessment />} /></Route></Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></ThemeProvider></PatientProvider></AuthProvider></BrowserRouter>
}
