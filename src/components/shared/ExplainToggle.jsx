import { AnimatePresence, motion } from 'framer-motion'
import { Info } from 'lucide-react'
import { useState } from 'react'

export default function ExplainToggle({ reasons = [], label = 'Why?' }) {
  const [open, setOpen] = useState(false)
  return <div className="mt-2">
    <button type="button" onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline" aria-expanded={open}>
      <Info size={14} /> {label}
    </button>
    <AnimatePresence initial={false}>
      {open && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2, ease: 'easeInOut' }} className="overflow-hidden">
        <ul className="mt-2 list-disc space-y-1 rounded-lg bg-primary/10 px-7 py-3 text-xs leading-5 text-slate-700 dark:text-slate-200">
          {reasons.slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      </motion.div>}
    </AnimatePresence>
  </div>
}
