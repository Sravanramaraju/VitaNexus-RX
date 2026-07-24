import { Outlet, useMatch } from 'react-router-dom'
import BottomNav from './BottomNav'
import Header from './Header'
import PatientContextBar from './PatientContextBar'
import Sidebar from './Sidebar'

export default function AppLayout() {
  const isRecord = Boolean(useMatch('/patients/:patientId'))
  return <div className="min-h-screen bg-background text-text dark:bg-slate-900 dark:text-slate-50"><Header />{isRecord && <PatientContextBar />}<Sidebar />
    <main className={`min-h-screen px-4 pb-24 md:pl-72 md:pr-8 md:pb-8 ${isRecord ? 'pt-36' : 'pt-24'}`}><Outlet /></main><BottomNav />
  </div>
}
