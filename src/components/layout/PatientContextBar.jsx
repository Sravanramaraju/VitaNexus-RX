import { useParams } from 'react-router-dom'
import { usePatient } from '../../context/PatientContext'
import StatusBadge from '../shared/StatusBadge'

export default function PatientContextBar() {
  const { patientId } = useParams(); const { patients } = usePatient(); const patient = patients.find((item) => item.id === patientId)
  if (!patient) return null
  const active = patient.visits.some((visit) => visit.status === 'in-progress')
  return <div className="patient-context-bar fixed inset-x-0 top-16 z-30 flex h-16 items-center gap-3 border-b border-border bg-primary/5 px-4 md:px-6 dark:border-slate-700 dark:bg-slate-800">
    <span className="truncate font-semibold">{patient.name}</span><span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">{patient.id}</span><StatusBadge status={active ? 'Active' : 'Completed'} />
  </div>
}
