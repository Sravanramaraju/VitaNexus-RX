import { CheckCircle2, Clock3, LayoutDashboard } from 'lucide-react'
import { NavLink, useParams } from 'react-router-dom'
import { usePatient } from '../../context/PatientContext'

const labelDate = (date) => new Date(date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
export default function Sidebar() {
  const { patientId } = useParams(); const { patients, activeVisitId, setActiveVisitId } = usePatient()
  const patient = patients.find((item) => item.id === patientId); const isRecord = Boolean(patient)
  return <aside className={`app-sidebar fixed bottom-0 left-0 z-20 hidden w-64 flex-col border-r border-border bg-card px-3 py-5 shadow-sm md:flex dark:border-slate-700 dark:bg-slate-800 ${isRecord ? 'top-32' : 'top-16'}`}>
    {!isRecord ? <NavLink to="/dashboard" className="flex items-center gap-3 rounded-lg bg-primary/10 px-3 py-2 text-sm font-bold text-primary"><LayoutDashboard size={17} />Dashboard</NavLink> : <>
      <p className="px-2 text-xs font-bold uppercase tracking-wide text-slate-500">Visit timeline</p>
      <div className="mt-3 space-y-1 overflow-y-auto">{patient.visits.map((visit, index) => <button type="button" onClick={() => setActiveVisitId(visit.id)} key={visit.id} className={`flex w-full items-center gap-2 rounded-lg px-3 py-3 text-left text-sm transition ${activeVisitId === visit.id ? 'bg-primary/10 text-primary' : 'hover:bg-slate-100 dark:hover:bg-slate-700'}`}>
        {visit.status === 'completed' ? <CheckCircle2 size={16} className="text-success" /> : <Clock3 size={16} className="text-warning" />}<span><strong className="block">Visit {index + 1}</strong><small className="text-slate-500">{labelDate(visit.date)}</small></span>
      </button>)}</div>
    </>}
  </aside>
}
