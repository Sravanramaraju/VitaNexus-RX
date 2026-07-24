export default function StatusBadge({ status, className = '' }) {
  const active = status === 'Active' || status === 'in-progress'
  const severityClass = status === 'Severe' ? 'bg-danger' : status === 'Moderate' ? 'bg-warning text-slate-900' : status === 'Mild' ? 'bg-success' : active ? 'bg-success' : 'bg-slate-500'
  const label = status === 'in-progress' ? 'Active' : status === 'completed' ? 'Completed' : status
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold text-white ${severityClass} ${className}`}>{label}</span>
}
