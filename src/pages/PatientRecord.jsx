import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, ChevronLeft, ChevronRight, ClipboardPlus, UserPlus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import ExplainToggle from '../components/shared/ExplainToggle'
import { usePatient } from '../context/PatientContext'
import { getDrugAllergyReasons, getDrugDiseaseReasons, getDDIPredictionReasons, getFeedbackUsageReasons, getOverallClinicalRiskReasons, getRankingReasons, getReliabilityReasons } from '../lib/explainability'

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

const severityFromRisk = (risk) => risk > 60 ? 'High' : risk > 30 ? 'Moderate' : 'Low'
const normalizeSeverity = (severity, risk) => {
  if (severity === 'Contraindicated') return 'Contraindicated'
  if (severity === 'Severe') return 'High'
  if (severity === 'Mild') return 'Low'
  return severity || severityFromRisk(risk || 0)
}
const reliabilityFromConfidence = (label, pct) => {
  if (label === 'Very High' || label === 'High' || pct > 65) return 'High'
  if (label === 'Moderate' || pct > 45) return 'Medium'
  return 'Low'
}

function InteractionSeverityBadge({ severity }) {
  const tone = severity === 'Contraindicated' || severity === 'High' ? 'bg-danger' : severity === 'Moderate' ? 'bg-warning text-slate-900' : 'bg-success'
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold text-white ${tone}`}>{severity}</span>
}

function Metric({ label, children, className = '' }) {
  return <div className={className}><p className="text-xs font-medium text-slate-500 dark:text-slate-300">{label}</p><div className="mt-1 text-sm font-semibold">{children}</div></div>
}

function Results({ visit, historical, onNext, onSaveNotes, onAddPatient }) {
  const [notes, setNotes] = useState(visit.doctorNotes || '')
  const risk = visit.riskResult
  const confidence = visit.confidence
  const severity = normalizeSeverity(risk?.severity, risk?.score)
  const reliability = reliabilityFromConfidence(confidence?.reliabilityLabel, confidence?.pct)

  useEffect(() => setNotes(visit.doctorNotes || ''), [visit.id, visit.doctorNotes])

  const insights = [
    ['Prediction', getDDIPredictionReasons(severity)],
    ['Confidence', [`Prediction confidence is ${confidence?.pct ?? 0}%.`, 'The interval visualizes the uncertainty range.']],
    ['Reliability', getReliabilityReasons(confidence?.reliabilityLabel || 'Moderate')],
    ['Alternative Ranking', getRankingReasons()],
    ['Feedback Learning', visit.feedback ? getFeedbackUsageReasons() : ['Feedback learning becomes available after follow-up is submitted.']],
  ]

  return <div className="space-y-5">
    <div className="space-y-5">
      <ResultCard title="Clinical Safety Analysis">
        <div className="mt-4 space-y-4">
          <section>
            <h3 className="text-sm font-bold">Drug–Drug Analysis</h3>
            <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
              <Metric label="Interaction Risk (%)">{risk?.score ?? 0}%</Metric>
              <Metric label="Interaction Severity"><InteractionSeverityBadge severity={severity} /></Metric>
              <Metric label="Confidence">{confidence?.pct ?? 0}%</Metric>
              <Metric label="Reliability">{reliability}</Metric>
              <Metric label="Confidence Interval" className="col-span-2">{confidence?.intervalLow ?? 0}% - {confidence?.intervalHigh ?? 0}%</Metric>
            </div>
            <ExplainToggle reasons={getDDIPredictionReasons(severity)} />
          </section>
          <section className="border-t border-border pt-4 dark:border-slate-700">
            <h3 className="text-sm font-bold">Drug–Disease Analysis</h3>
            <div className="mt-3"><Metric label="Interaction Risk (%)">42%</Metric></div>
            <ExplainToggle reasons={getDrugDiseaseReasons()} />
          </section>
          <section className="border-t border-border pt-4 dark:border-slate-700">
            <h3 className="text-sm font-bold">Drug–Allergy Analysis</h3>
            <div className="mt-3"><Metric label="Interaction Risk (%)">18%</Metric></div>
            <ExplainToggle reasons={getDrugAllergyReasons()} />
          </section>
          <section className="border-t border-border pt-4 dark:border-slate-700">
            <h3 className="text-sm font-bold">Overall Clinical Risk</h3>
            <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
              <Metric label="Overall Risk (%)">{risk?.score ?? 0}%</Metric>
              <Metric label="Confidence">{confidence?.pct ?? 0}%</Metric>
              <Metric label="Confidence Interval" className="col-span-2">{confidence?.intervalLow ?? 0}% - {confidence?.intervalHigh ?? 0}%</Metric>
            </div>
            <ExplainToggle reasons={getOverallClinicalRiskReasons()} />
          </section>
        </div>
      </ResultCard>

      <ResultCard title="Conformal Reliability">
        <div className="mt-4 flex items-center justify-between gap-4"><span className="text-sm text-slate-600 dark:text-slate-300">Confidence interval</span><span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">{confidence?.reliabilityLabel}</span></div>
        <RangeBar low={confidence?.intervalLow} high={confidence?.intervalHigh} />
        <p className="mt-2 text-xs text-slate-500">{confidence?.intervalLow}% - {confidence?.intervalHigh}%</p>
        <ExplainToggle reasons={getReliabilityReasons(confidence?.reliabilityLabel || 'Moderate')} />
      </ResultCard>
    </div>

    <ResultCard title="Recommended Safer Alternatives">
      <div className="mt-4 space-y-4">
        {(visit.recommendations || []).map((recommendation, index) => {
          const alternativeSeverity = severityFromRisk(recommendation.riskPct)
          const alternativeReliability = reliabilityFromConfidence(null, recommendation.confidencePct)
          return <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-700/50" key={`${recommendation.drug}-${index}`}>
            <strong>{index + 1}. {recommendation.drug}</strong>
            <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
              <Metric label="Interaction Severity"><InteractionSeverityBadge severity={alternativeSeverity} /></Metric>
              <Metric label="Predicted Interaction Risk">{recommendation.riskPct}%</Metric>
              <Metric label="Prediction Confidence">{recommendation.confidencePct}%</Metric>
              <Metric label="Reliability">{alternativeReliability}</Metric>
              <Metric label="Drug–Disease Risk">42%</Metric>
              <Metric label="Drug–Allergy Risk">18%</Metric>
              <Metric label="Confidence Interval" className="col-span-2">{recommendation.intervalLow}% - {recommendation.intervalHigh}%</Metric>
            </div>
            <RangeBar low={recommendation.intervalLow} high={recommendation.intervalHigh} />
          </div>
        })}
      </div>
      <ExplainToggle label="Why ranked?" reasons={getRankingReasons()} />
    </ResultCard>

    <ResultCard title="Doctor Notes">
      <textarea disabled={historical} className="input mt-4 min-h-28 disabled:opacity-70" value={notes} onChange={(event) => setNotes(event.target.value)} onBlur={() => onSaveNotes(notes)} />
      {!historical && <p className="mt-2 text-xs text-slate-500">Notes are saved when this field loses focus.</p>}
    </ResultCard>

    <ResultCard title="AI Decision Insights">
      <div className="mt-3 divide-y divide-border dark:divide-slate-700">{insights.map(([title, reasons]) => <div className="py-2" key={title}><div className="flex items-center justify-between"><span className="text-sm font-semibold">{title}</span><ExplainToggle reasons={reasons} /></div></div>)}</div>
    </ResultCard>

    <div className="flex flex-wrap justify-end gap-3"><button type="button" onClick={onAddPatient} className="btn-primary"><UserPlus size={16} />Add New Patient</button><button onClick={onNext} className="btn-primary">{historical ? 'Next: Follow-up' : 'Continue to Follow-up'} <ChevronRight size={16} /></button></div>
  </div>
}

function FollowUp({ visit, historical, onSubmit, onNext, onAddPatient }) {
  const [feedback, setFeedback] = useState(visit.feedback || { sideEffect: '', severity: 'Mild', duration: '' })
  const [saved, setSaved] = useState(false)
  const [addingFurtherFollowUp, setAddingFurtherFollowUp] = useState(false)
  useEffect(() => { if (!saved) return undefined; const timer = setTimeout(onNext, 800); return () => clearTimeout(timer) }, [saved, onNext])
  const submit = (event) => { event.preventDefault(); onSubmit(feedback); setSaved(true) }
  const startFurtherFollowUp = () => { setFeedback({ sideEffect: '', severity: 'Mild', duration: '' }); setAddingFurtherFollowUp(true); setSaved(false) }

  if (historical) return <div className="space-y-5"><ResultCard title="Follow-up"><p className="mt-4 text-sm">Side effect: <strong>{visit.feedback?.sideEffect || 'Not recorded'}</strong></p><p className="mt-2 text-sm">Severity: <strong>{visit.feedback?.severity || 'Not recorded'}</strong></p><p className="mt-2 text-sm">Duration: <strong>{visit.feedback?.duration || 'Not recorded'}</strong></p>{visit.followUps?.length > 0 && <div className="mt-5 border-t border-border pt-4 dark:border-slate-700"><p className="text-sm font-bold">Further follow-ups</p><div className="mt-3 space-y-3">{visit.followUps.map((followUp) => <div key={followUp.id} className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-700/50"><p><strong>{new Date(followUp.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</strong></p><p className="mt-1">Side effect: {followUp.sideEffect}</p><p>Severity: {followUp.severity} · Duration: {followUp.duration}</p></div>)}</div></div>}{!addingFurtherFollowUp && <button type="button" onClick={startFurtherFollowUp} className="btn-primary mt-5"><CheckCircle2 size={16} />Add Further Follow-up</button>}</ResultCard>{addingFurtherFollowUp && <form onSubmit={submit} className="surface max-w-xl p-6"><h2 className="text-xl font-bold">Add Further Follow-up</h2><div className="mt-5 space-y-4"><label className="block text-sm font-semibold">Side effect<input required className="input mt-1" value={feedback.sideEffect} onChange={(event) => setFeedback({ ...feedback, sideEffect: event.target.value })} /></label><label className="block text-sm font-semibold">Severity<select className="input mt-1" value={feedback.severity} onChange={(event) => setFeedback({ ...feedback, severity: event.target.value })}><option>Mild</option><option>Moderate</option><option>Severe</option></select></label><label className="block text-sm font-semibold">Duration<input required className="input mt-1" value={feedback.duration} onChange={(event) => setFeedback({ ...feedback, duration: event.target.value })} /></label><button className="btn-primary" disabled={saved}>Save Further Follow-up</button></div></form>}{saved && <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.2 }} className="surface max-w-xl border-l-4 border-l-success p-5"><div className="flex items-center gap-2 font-bold text-success"><CheckCircle2 size={18} />Further Follow-up Saved</div><ExplainToggle label="How is this used?" reasons={getFeedbackUsageReasons()} /></motion.div>}<div className="flex justify-between"><button className="btn-secondary" onClick={() => onNext('results')}><ChevronLeft size={16} />Results</button><button className="btn-primary" onClick={() => onNext('updated')}>Next: Follow-up Recommendation <ChevronRight size={16} /></button></div></div>

  return <div className="space-y-5"><form onSubmit={submit} className="surface max-w-xl p-6"><h2 className="text-xl font-bold">Follow-up</h2><div className="mt-5 space-y-4"><label className="block text-sm font-semibold">Side effect<input required className="input mt-1" value={feedback.sideEffect} onChange={(event) => setFeedback({ ...feedback, sideEffect: event.target.value })} /></label><label className="block text-sm font-semibold">Severity<select className="input mt-1" value={feedback.severity} onChange={(event) => setFeedback({ ...feedback, severity: event.target.value })}><option>Mild</option><option>Moderate</option><option>Severe</option></select></label><label className="block text-sm font-semibold">Duration<input required className="input mt-1" value={feedback.duration} onChange={(event) => setFeedback({ ...feedback, duration: event.target.value })} /></label><div className="flex flex-wrap gap-3"><button className="btn-primary" disabled={saved}>Save Follow-up</button><button type="button" onClick={onAddPatient} className="btn-primary"><UserPlus size={16} />Add New Patient</button></div></div></form>{saved && <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.2 }} className="surface max-w-xl border-l-4 border-l-success p-5"><div className="flex items-center gap-2 font-bold text-success"><CheckCircle2 size={18} />Feedback Saved</div><ExplainToggle label="How is this used?" reasons={getFeedbackUsageReasons()} /></motion.div>}</div>
}

function UpdatedRecommendations({ visit, historical, onBack }) {
  const items = visit.updatedRecommendations || []
  return <div className="space-y-5"><ResultCard title="Follow-up Recommendation"><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Recommendations re-ranked after physician feedback.</p><div className="mt-4 space-y-4">{items.length ? items.map((recommendation, index) => { const severity = severityFromRisk(recommendation.riskPct); const reliability = reliabilityFromConfidence(null, recommendation.confidencePct); return <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-700/50" key={`${recommendation.drug}-${index}`}><strong>{index + 1}. {recommendation.drug}</strong><div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4"><Metric label="Interaction Severity"><InteractionSeverityBadge severity={severity} /></Metric><Metric label="Predicted Interaction Risk">{recommendation.riskPct}%</Metric><Metric label="Prediction Confidence">{recommendation.confidencePct}%</Metric><Metric label="Reliability">{reliability}</Metric><Metric label="Confidence Interval" className="col-span-2">{recommendation.intervalLow}% - {recommendation.intervalHigh}%</Metric></div><RangeBar low={recommendation.intervalLow} high={recommendation.intervalHigh} /></div>}) : <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500 dark:bg-slate-700/50">Follow-up recommendations appear after feedback is saved.</p>}</div><ExplainToggle label="Why ranked?" reasons={getRankingReasons()} /></ResultCard>{historical && <button className="btn-secondary" onClick={onBack}><ChevronLeft size={16} />Follow-up</button>}</div>
}

function WizardSteps({ activeStep, visitedSteps, onStepChange }) {
  const steps = [
    ['results', 'Results'],
    ['followup', 'Follow-up'],
    ['updated', 'Follow-up Recommendation'],
  ]

  return <nav className="mb-6 flex flex-wrap gap-2" aria-label="Visit steps">
    {steps.map(([id, label]) => {
      const available = visitedSteps[id]
      const active = activeStep === id
      return <button
        key={id}
        type="button"
        onClick={() => onStepChange(id)}
        disabled={!available}
        aria-current={active ? 'step' : undefined}
        title={available ? `Open ${label}` : `Complete the previous step to unlock ${label}`}
        className={`rounded-full px-3 py-1 text-xs font-bold transition ${active ? 'bg-primary text-white' : 'bg-primary/10 text-primary'} ${available ? 'cursor-pointer hover:bg-primary/20' : 'cursor-not-allowed opacity-45'}`}
      >
        {label}
      </button>
    })}
  </nav>
}

export default function PatientRecord() {
  const { patientId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { patients, activeVisitId, setActiveVisitId, submitFeedback, saveVisitNotes } = usePatient()
  const patient = patients.find((item) => item.id === patientId)
  const activeVisit = useMemo(() => patient?.visits.find((visit) => visit.id === activeVisitId) || patient?.visits.at(-1), [patient, activeVisitId])
  const stateForVisit = location.state?.visitId && location.state.visitId !== activeVisit?.id ? null : location.state
  const [step, setStep] = useState(() => resolveEntryStep(activeVisit, stateForVisit))
  const [resolvedVisitId, setResolvedVisitId] = useState(activeVisit?.id || null)
  const [visitedSteps, setVisitedSteps] = useState(() => ({
    results: true,
    followup: activeVisit?.status === 'completed' || resolveEntryStep(activeVisit, stateForVisit) === 'followup',
    updated: activeVisit?.status === 'completed',
  }))

  useEffect(() => {
    if (!patient) return
    const preferred = location.state?.visitId
    const valid = patient.visits.some((visit) => visit.id === activeVisitId)
    if (preferred && patient.visits.some((visit) => visit.id === preferred)) setActiveVisitId(preferred)
    else if (!valid) setActiveVisitId(patient.visits.at(-1).id)
  }, [patientId, patient, activeVisitId, location.state?.visitId, setActiveVisitId])

  useEffect(() => {
    if (activeVisit && resolvedVisitId !== activeVisit.id) {
      setStep(resolveEntryStep(activeVisit, stateForVisit))
      setVisitedSteps({
        results: true,
        followup: activeVisit.status === 'completed' || resolveEntryStep(activeVisit, stateForVisit) === 'followup',
        updated: activeVisit.status === 'completed',
      })
      setResolvedVisitId(activeVisit.id)
    }
  }, [activeVisit, resolvedVisitId, stateForVisit])

  if (!patient || !activeVisit) return <div className="surface p-6">Patient record not found.</div>

  const historical = activeVisit.status === 'completed'
  const freshInProgress = activeVisit.status === 'in-progress' && location.state?.entry === 'results' && location.state?.visitId === activeVisit.id
  const submit = (feedback) => submitFeedback(patient.id, activeVisit.id, feedback)
  const startNewPatient = () => navigate('/patients/new')
  const goToVisitedStep = (target) => {
    if (visitedSteps[target]) setStep(target)
  }
  const advanceToStep = (target) => {
    setVisitedSteps((current) => ({ ...current, [target]: true }))
    setStep(target)
  }
  const body = step === 'results'
    ? <Results visit={activeVisit} historical={historical} onNext={() => advanceToStep('followup')} onSaveNotes={(notes) => saveVisitNotes(patient.id, activeVisit.id, notes)} onAddPatient={startNewPatient} />
    : step === 'followup'
      ? <FollowUp visit={activeVisit} historical={historical} onSubmit={submit} onNext={(target) => target === 'results' ? goToVisitedStep('results') : advanceToStep('updated')} onAddPatient={startNewPatient} />
      : <UpdatedRecommendations visit={activeVisit} historical={historical} onBack={() => goToVisitedStep('followup')} />

  return <section className="mx-auto max-w-5xl"><div className="mb-6 flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow">Visit workspace</p><h1 className="mt-1 text-2xl font-bold">{activeVisit.prescribedDrug?.brand || 'Consultation'} <span className="text-slate-400">-</span> {activeVisit.diagnosis || 'Clinical review'}</h1></div>{!freshInProgress && <button onClick={() => navigate('/patients/new', { state: { existingPatientId: patient.id } })} className="btn-secondary"><ClipboardPlus size={16} />New Consultation</button>}</div><WizardSteps activeStep={step} visitedSteps={visitedSteps} onStepChange={goToVisitedStep} /><AnimatePresence mode="wait"><motion.div key={`${activeVisit.id}-${step}`} initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -18 }} transition={{ duration: 0.3, ease: 'easeInOut' }}>{body}</motion.div></AnimatePresence></section>
}
