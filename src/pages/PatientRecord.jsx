import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, ChevronLeft, ChevronRight, ClipboardPlus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import ExplainToggle from '../components/shared/ExplainToggle'
import StatusBadge from '../components/shared/StatusBadge'
import { usePatient } from '../context/PatientContext'
import { getDDIPredictionReasons, getFeedbackUsageReasons, getRankingReasons, getReliabilityReasons } from '../lib/explainability'

export function resolveEntryStep(visit, navigationState) {
  if (navigationState?.entry === 'results') return 'results'
  if (navigationState?.entry === 'followup' && visit?.status === 'in-progress') return 'followup'
  if (visit?.status === 'completed') return 'results'
  return 'followup'
}

function RangeBar({ low = 0, high = 0 }) {
  const width = Math.max(2, high - low)
  return <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"><motion.div initial={{ width: 0 }} animate={{ width: `${width}%` }} transition={{ duration: 0.45, ease: 'easeInOut' }} className="h-full rounded-full bg-primary" style={{ marginLeft: `${low}%` }} /></div>
}

function ResultCard({ title, children }) {
  return <motion.article initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.25, ease: 'easeInOut' }} className="surface p-5"><h2 className="text-lg font-bold">{title}</h2>{children}</motion.article>
}

function Results({ visit, historical, onNext, onSaveNotes }) {
  const [notes, setNotes] = useState(visit.doctorNotes || ''); const risk = visit.riskResult; const confidence = visit.confidence
  useEffect(() => setNotes(visit.doctorNotes || ''), [visit.id, visit.doctorNotes])
  const severity = risk?.severity || 'Mild'
  const insights = [
    ['Prediction', getDDIPredictionReasons(severity)], ['Confidence', [`Prediction confidence is ${confidence?.pct ?? 0}%.`, 'The interval visualizes the uncertainty range.']],
    ['Reliability', getReliabilityReasons(confidence?.reliabilityLabel || 'Moderate')], ['Alternative Ranking', getRankingReasons()],
    ['Feedback Learning', visit.feedback ? getFeedbackUsageReasons() : ['Feedback learning becomes available after follow-up is submitted.']],
  ]
  return <div className="space-y-5"><div className="grid gap-5 lg:grid-cols-2"><ResultCard title="AI DDI Prediction"><div className="mt-4 flex flex-wrap items-center gap-3"><StatusBadge status={severity} /><span className="text-sm"><strong>{confidence?.pct ?? 0}%</strong> confidence</span><span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">{confidence?.reliabilityLabel}</span></div><ExplainToggle reasons={getDDIPredictionReasons(severity)} /></ResultCard>
      <ResultCard title="Conformal Reliability"><div className="mt-4 flex items-center justify-between gap-4"><span className="text-sm text-slate-600 dark:text-slate-300">Confidence interval</span><span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">{confidence?.reliabilityLabel}</span></div><RangeBar low={confidence?.intervalLow} high={confidence?.intervalHigh} /><p className="mt-2 text-xs text-slate-500">{confidence?.intervalLow}%–{confidence?.intervalHigh}%</p><ExplainToggle reasons={getReliabilityReasons(confidence?.reliabilityLabel || 'Moderate')} /></ResultCard></div>
    <ResultCard title="Alternative Medicines"><div className="mt-4 space-y-4">{(visit.recommendations || []).map((recommendation, index) => <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-700/50" key={`${recommendation.drug}-${index}`}><div className="flex items-center justify-between gap-3"><strong>{index + 1}. {recommendation.drug}</strong><span className="text-xs font-bold text-danger">Risk {recommendation.riskPct}%</span></div><div className="mt-2 flex justify-between text-xs text-slate-500"><span>Confidence {recommendation.confidencePct}%</span><span>{recommendation.intervalLow}%–{recommendation.intervalHigh}%</span></div><RangeBar low={recommendation.intervalLow} high={recommendation.intervalHigh} /></div>)}</div><ExplainToggle label="Why ranked?" reasons={getRankingReasons()} /></ResultCard>
    <ResultCard title="Doctor Notes"><textarea disabled={historical} className="input mt-4 min-h-28 disabled:opacity-70" value={notes} onChange={(event) => setNotes(event.target.value)} onBlur={() => onSaveNotes(notes)} />{!historical && <p className="mt-2 text-xs text-slate-500">Notes are saved when this field loses focus.</p>}</ResultCard>
    <ResultCard title="AI Decision Insights"><div className="mt-3 divide-y divide-border dark:divide-slate-700">{insights.map(([title, reasons]) => <div className="py-2" key={title}><div className="flex items-center justify-between"><span className="text-sm font-semibold">{title}</span><ExplainToggle reasons={reasons} /></div></div>)}</div></ResultCard>
    <div className="flex justify-end"><button onClick={onNext} className="btn-primary">{historical ? 'Next: Follow-up' : 'Continue to Follow-up'} <ChevronRight size={16} /></button></div>
  </div>
}

function FollowUp({ visit, historical, onSubmit, onNext }) {
  const [feedback, setFeedback] = useState(visit.feedback || { sideEffect: '', severity: 'Mild', duration: '' }); const [saved, setSaved] = useState(false)
  useEffect(() => { if (!saved) return undefined; const timer = setTimeout(onNext, 800); return () => clearTimeout(timer) }, [saved, onNext])
  if (historical) return <div className="space-y-5"><ResultCard title="Follow-up"><p className="mt-4 text-sm">Side effect: <strong>{visit.feedback?.sideEffect || 'Not recorded'}</strong></p><p className="mt-2 text-sm">Severity: <strong>{visit.feedback?.severity || 'Not recorded'}</strong></p><p className="mt-2 text-sm">Duration: <strong>{visit.feedback?.duration || 'Not recorded'}</strong></p></ResultCard><div className="flex justify-between"><button className="btn-secondary" onClick={() => onNext('results')}><ChevronLeft size={16} />Results</button><button className="btn-primary" onClick={() => onNext('updated')}>Next: Updated Recommendation <ChevronRight size={16} /></button></div></div>
  const submit = (event) => { event.preventDefault(); onSubmit(feedback); setSaved(true) }
  return <div className="space-y-5"><form onSubmit={submit} className="surface max-w-xl p-6"><h2 className="text-xl font-bold">Follow-up</h2><div className="mt-5 space-y-4"><label className="block text-sm font-semibold">Side effect<input required className="input mt-1" value={feedback.sideEffect} onChange={(e) => setFeedback({ ...feedback, sideEffect: e.target.value })} /></label><label className="block text-sm font-semibold">Severity<select className="input mt-1" value={feedback.severity} onChange={(e) => setFeedback({ ...feedback, severity: e.target.value })}><option>Mild</option><option>Moderate</option><option>Severe</option></select></label><label className="block text-sm font-semibold">Duration<input required className="input mt-1" value={feedback.duration} onChange={(e) => setFeedback({ ...feedback, duration: e.target.value })} /></label><button className="btn-primary" disabled={saved}>Save Follow-up</button></div></form>{saved && <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.2 }} className="surface max-w-xl border-l-4 border-l-success p-5"><div className="flex items-center gap-2 font-bold text-success"><CheckCircle2 size={18} />Feedback Saved</div><ExplainToggle label="How is this used?" reasons={getFeedbackUsageReasons()} /></motion.div>}</div>
}

function UpdatedRecommendations({ visit, historical, onBack }) {
  const items = visit.updatedRecommendations || []
  return <div className="space-y-5"><ResultCard title="Updated Recommendation"><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Recommendations re-ranked after physician feedback.</p><div className="mt-4 space-y-4">{items.length ? items.map((recommendation, index) => <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-700/50" key={`${recommendation.drug}-${index}`}><div className="flex items-center justify-between"><strong>{index + 1}. {recommendation.drug}</strong><span className="text-xs font-bold text-danger">Risk {recommendation.riskPct}%</span></div><RangeBar low={recommendation.intervalLow} high={recommendation.intervalHigh} /><p className="mt-2 text-xs text-slate-500">Confidence range {recommendation.intervalLow}%–{recommendation.intervalHigh}%</p></div>) : <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500 dark:bg-slate-700/50">Updated recommendations appear after follow-up feedback is saved.</p>}</div><ExplainToggle label="Why ranked?" reasons={getRankingReasons()} /></ResultCard>{historical && <button className="btn-secondary" onClick={onBack}><ChevronLeft size={16} />Follow-up</button>}</div>
}

export default function PatientRecord() {
  const { patientId } = useParams(); const location = useLocation(); const navigate = useNavigate(); const { patients, activeVisitId, setActiveVisitId, submitFeedback, saveVisitNotes } = usePatient(); const patient = patients.find((item) => item.id === patientId)
  const activeVisit = useMemo(() => patient?.visits.find((visit) => visit.id === activeVisitId) || patient?.visits.at(-1), [patient, activeVisitId])
  const stateForVisit = location.state?.visitId && location.state.visitId !== activeVisit?.id ? null : location.state
  const [step, setStep] = useState(() => resolveEntryStep(activeVisit, stateForVisit)); const [resolvedVisitId, setResolvedVisitId] = useState(activeVisit?.id || null)
  useEffect(() => { if (!patient) return; const preferred = location.state?.visitId; const valid = patient.visits.some((visit) => visit.id === activeVisitId); if (preferred && patient.visits.some((visit) => visit.id === preferred)) setActiveVisitId(preferred); else if (!valid) setActiveVisitId(patient.visits.at(-1).id) }, [patientId, patient, activeVisitId, location.state?.visitId, setActiveVisitId])
  useEffect(() => { if (activeVisit && resolvedVisitId !== activeVisit.id) { setStep(resolveEntryStep(activeVisit, stateForVisit)); setResolvedVisitId(activeVisit.id) } }, [activeVisit, resolvedVisitId, stateForVisit])
  if (!patient || !activeVisit) return <div className="surface p-6">Patient record not found.</div>
  const historical = activeVisit.status === 'completed'; const freshInProgress = activeVisit.status === 'in-progress' && location.state?.entry === 'results' && location.state?.visitId === activeVisit.id
  const submit = (feedback) => submitFeedback(patient.id, activeVisit.id, feedback)
  const body = step === 'results' ? <Results visit={activeVisit} historical={historical} onNext={() => setStep('followup')} onSaveNotes={(notes) => saveVisitNotes(patient.id, activeVisit.id, notes)} /> : step === 'followup' ? <FollowUp visit={activeVisit} historical={historical} onSubmit={submit} onNext={(target) => setStep(target || 'updated')} /> : <UpdatedRecommendations visit={activeVisit} historical={historical} onBack={() => setStep('followup')} />
  return <section className="mx-auto max-w-5xl"><div className="mb-6 flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow">Visit workspace</p><h1 className="mt-1 text-2xl font-bold">{activeVisit.prescribedDrug?.brand || 'Consultation'} <span className="text-slate-400">·</span> {activeVisit.diagnosis || 'Clinical review'}</h1></div>{!freshInProgress && <button onClick={() => navigate('/patients/new', { state: { existingPatientId: patient.id } })} className="btn-secondary"><ClipboardPlus size={16} />New Consultation</button>}</div><div className="mb-6 flex gap-2"><span className={`rounded-full px-3 py-1 text-xs font-bold ${step === 'results' ? 'bg-primary text-white' : 'bg-primary/10 text-primary'}`}>Results</span><span className={`rounded-full px-3 py-1 text-xs font-bold ${step === 'followup' ? 'bg-primary text-white' : 'bg-primary/10 text-primary'}`}>Follow-up</span><span className={`rounded-full px-3 py-1 text-xs font-bold ${step === 'updated' ? 'bg-primary text-white' : 'bg-primary/10 text-primary'}`}>Updated Recommendation</span></div><AnimatePresence mode="wait"><motion.div key={`${activeVisit.id}-${step}`} initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -18 }} transition={{ duration: 0.3, ease: 'easeInOut' }}>{body}</motion.div></AnimatePresence></section>
}
