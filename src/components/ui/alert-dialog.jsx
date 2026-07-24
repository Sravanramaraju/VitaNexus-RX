export function AlertDialog({ open, title, description, onCancel, onConfirm }) {
  if (!open) return null
  return <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4" role="dialog" aria-modal="true">
    <div className="surface w-full max-w-md p-6">
      <h2 className="text-lg font-bold">{title}</h2><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{description}</p>
      <div className="mt-6 flex justify-end gap-3"><button className="btn-secondary" onClick={onCancel}>Cancel</button><button className="btn-primary bg-danger hover:bg-danger" onClick={onConfirm}>Delete</button></div>
    </div>
  </div>
}
