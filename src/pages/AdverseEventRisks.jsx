import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  Database,
  GitBranch,
  Info,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getEventRiskProfile, regenerateEventRiskProfile } from "../lib/eventRiskProfile";
import { usePatient } from "../context/PatientContext";

const unavailableStatuses = new Set(["HGNN_UNAVAILABLE", "ARTIFACT_MISMATCH", "INFERENCE_FAILED"]);
const titleCase = (value = "") => value.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
const compactVersion = (value = "") => value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;

function Wizard({ patientId, visitId, active, onRecommendations, advancing }) {
  const navigate = useNavigate();
  const steps = [
    { id: "safety", label: "Clinical Safety", action: () => navigate(`/patients/${patientId}`, { state: { entry: "results", visitId } }) },
    { id: "adr", label: "Adverse Risk Assessment", action: () => navigate(`/patients/${patientId}/consultations/${visitId}/adr`) },
    { id: "events", label: "Event Profile" },
    { id: "recommendations", label: "Recommendations", action: onRecommendations },
    { id: "followup", label: "Follow-up", disabled: true },
  ];
  return <nav className="flex flex-wrap gap-2" aria-label="Visit steps">
    {steps.map((step) => <button
      key={step.id}
      type="button"
      aria-current={active === step.id ? "step" : undefined}
      disabled={step.disabled || advancing}
      onClick={step.action}
      title={step.disabled ? "Complete recommendations to unlock Follow-up" : `Open ${step.label}`}
      className={`rounded-full px-3 py-1 text-xs font-bold transition ${active === step.id ? "cursor-default bg-primary text-white" : "bg-primary/10 text-primary hover:bg-primary/20"} disabled:cursor-not-allowed disabled:opacity-45`}
    >{step.label}</button>)}
  </nav>;
}

function LoadingProfile() {
  return <article className="surface overflow-hidden" aria-live="polite">
    <div className="border-b border-border bg-gradient-to-r from-primary/10 via-card to-accent/10 p-6 dark:border-slate-700 dark:from-primary/20 dark:via-slate-800 dark:to-accent/10">
      <div className="flex items-center gap-4"><div className="grid h-12 w-12 place-items-center rounded-2xl bg-primary text-white shadow-lg"><BrainCircuit className="animate-pulse" size={25} /></div><div><h2 className="text-lg font-bold">Analyzing the event profile</h2><p className="mt-1 text-sm text-slate-500">Running the protected baseline HGNN on the encoded consultation graph…</p></div></div>
    </div>
    <div className="space-y-4 p-6">{[82, 68, 54, 43, 35].map((width) => <div key={width} className="flex animate-pulse items-center gap-4"><div className="h-9 w-9 rounded-xl bg-primary/10" /><div className="flex-1"><div className="h-3 rounded bg-slate-200 dark:bg-slate-700" style={{ width: `${Math.max(30, width - 15)}%` }} /><div className="mt-2 h-2 rounded-full bg-slate-100 dark:bg-slate-700"><div className="h-full rounded-full bg-primary/20" style={{ width: `${width}%` }} /></div></div></div>)}</div>
  </article>;
}

function UnavailableProfile({ profile, onRetry, retrying }) {
  return <article className="surface overflow-hidden">
    <div className="flex gap-4 border-l-4 border-warning bg-warning/10 p-6"><div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-warning/15 text-warning"><AlertTriangle size={23} /></div><div><p className="eyebrow !text-warning">Explicit unavailable state</p><h2 className="mt-1 text-xl font-bold">The HGNN event profile is unavailable</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-300">{profile?.message || "The protected baseline model or one of its verified artifacts could not be loaded. No event score has been assumed or replaced with zero."}</p><button type="button" className="btn-secondary mt-5" disabled={retrying} onClick={onRetry}><RefreshCw size={16} className={retrying ? "animate-spin" : ""} />{retrying ? "Retrying…" : "Retry event profile"}</button></div></div>
  </article>;
}

function EventRows({ events }) {
  if (!events?.length) return <div className="rounded-xl border border-dashed border-border p-8 text-center dark:border-slate-700"><Activity className="mx-auto text-slate-400" /><h3 className="mt-3 font-bold">No event labels were returned</h3><p className="mt-1 text-sm text-slate-500">No zero values are displayed. Retry the profile or check the HGNN service.</p></div>;
  return <ol className="space-y-3" aria-label="Ranked baseline HGNN event scores">
    {events.map((event) => {
      const visualWidth = Math.max(2, Number(event.displayPercent));
      return <li key={`${event.rank}-${event.eventName}`} className="group rounded-xl border border-border bg-card p-4 transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md dark:border-slate-700 dark:bg-slate-800">
        <div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary/10 text-sm font-extrabold text-primary">{String(event.rank).padStart(2, "0")}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline justify-between gap-2"><div><h3 className="font-bold text-text dark:text-slate-50">{titleCase(event.eventName)}</h3>{event.eventCode && <p className="mt-0.5 text-xs text-slate-500">Vocabulary code {event.eventCode}</p>}</div><div className="text-right"><p className="text-lg font-extrabold tabular-nums text-primary">{Number(event.displayPercent).toFixed(2)}%</p><p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">model score</p></div></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700" role="progressbar" aria-valuemin="0" aria-valuemax="1" aria-valuenow={event.eventScore} aria-valuetext={`${event.displayPercent} percent baseline model score`}><div className="h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all" style={{ width: `${visualWidth}%` }} /></div></div></div>
      </li>;
    })}
  </ol>;
}

export default function AdverseEventRisks() {
  const { patientId, visitId } = useParams();
  const navigate = useNavigate();
  const { patients, generateRecommendations, refreshPatients } = usePatient();
  const patient = patients.find((item) => item.id === patientId);
  const visit = useMemo(() => patient?.visits.find((item) => item.id === visitId), [patient, visitId]);
  const [profile, setProfile] = useState(null);
  const [state, setState] = useState("LOADING");
  const [retrying, setRetrying] = useState(false);
  const [advancing, setAdvancing] = useState(false);

  const load = async ({ regenerate = false } = {}) => {
    setState("LOADING");
    try {
      const result = regenerate ? await regenerateEventRiskProfile(visitId) : await getEventRiskProfile(visitId);
      setProfile(result);
      setState(unavailableStatuses.has(result.status) ? "UNAVAILABLE" : "READY");
    } catch (error) {
      setProfile({ status: "HGNN_UNAVAILABLE", message: error.message || "The baseline HGNN service could not be reached." });
      setState("UNAVAILABLE");
    }
  };

  useEffect(() => { if (visitId) load(); }, [visitId]); // eslint-disable-line react-hooks/exhaustive-deps

  const retry = async () => { setRetrying(true); try { await load({ regenerate: true }); } finally { setRetrying(false); } };
  const openRecommendations = async () => {
    setAdvancing(true);
    try {
      await generateRecommendations(visitId);
      await refreshPatients();
      navigate(`/patients/${patientId}`, { state: { entry: "recommendations", visitId } });
    } finally { setAdvancing(false); }
  };

  if (!patient || !visit) return <div className="surface p-6">Consultation not found.</div>;
  const ready = state === "READY" && !unavailableStatuses.has(profile?.status);
  const degraded = profile?.status === "DEGRADED_COVERAGE";
  return <section className="mx-auto max-w-6xl space-y-5">
    <header className="relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/10 via-card to-accent/10 p-6 shadow-sm dark:from-primary/20 dark:via-slate-800 dark:to-accent/10 sm:p-7">
      <div className="pointer-events-none absolute -right-10 -top-14 h-44 w-44 rounded-full border-[26px] border-primary/5" />
      <div className="relative flex flex-wrap items-start justify-between gap-4"><div className="flex min-w-0 gap-4"><div className="hidden h-14 w-14 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-primary to-accent text-white shadow-lg sm:grid"><BrainCircuit size={29} /></div><div><p className="eyebrow">Supplementary clinical insight</p><h1 className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">Specific Event Profile</h1><p className="mt-2 text-sm text-slate-600 dark:text-slate-300"><strong>{visit.prescribedDrug}</strong> <span className="mx-1 text-slate-400">·</span> {visit.indication} <span className="mx-1 text-slate-400">·</span> Patient {patient.publicId}</p></div></div><div className="flex flex-wrap gap-2"><span className="rounded-full border border-primary/20 bg-card/80 px-3 py-1 text-xs font-bold text-primary dark:bg-slate-800">BASELINE HGNN</span><span className="rounded-full border border-warning/25 bg-warning/10 px-3 py-1 text-xs font-bold text-warning">AUDIT PENDING</span></div></div>
    </header>
    <Wizard patientId={patientId} visitId={visitId} active="events" onRecommendations={openRecommendations} advancing={advancing} />
    {state === "LOADING" && <LoadingProfile />}
    {state === "UNAVAILABLE" && <UnavailableProfile profile={profile} onRetry={retry} retrying={retrying} />}
    {ready && <>
      {degraded && <div className="flex gap-3 rounded-xl border border-warning/35 bg-warning/10 p-4 text-sm"><AlertTriangle className="mt-0.5 shrink-0 text-warning" size={19} /><div><strong>Limited graph coverage.</strong> One or more inputs were not found in the saved development associations. The baseline scores are shown with this limitation and are not presented as complete evidence.</div></div>}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(18rem,.75fr)]">
        <article className="surface overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-5 dark:border-slate-700"><div><p className="eyebrow">Ordered model output</p><h2 className="mt-1 text-xl font-bold">Ranked event-label associations</h2></div><span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${degraded ? "bg-warning/10 text-warning" : "bg-accent/15 text-accent"}`}>{degraded ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}{degraded ? "LIMITED COVERAGE" : "FULL COVERAGE"}</span></div><div className="p-5"><div className="mb-5 flex gap-3 rounded-xl bg-primary/5 p-4 text-sm leading-6 text-slate-600 dark:text-slate-300"><Info className="mt-0.5 shrink-0 text-primary" size={18} /><p>Higher values mean the baseline HGNN learned a stronger association with that event label in its FAERS-derived graph. These values are <strong>model scores—not the patient’s chance of experiencing the event</strong>.</p></div><EventRows events={profile.events} /></div></article>
        <aside className="space-y-5"><article className="surface overflow-hidden"><div className="bg-gradient-to-r from-primary to-accent p-5 text-white"><Sparkles size={22} /><h2 className="mt-3 text-lg font-bold">How to read this panel</h2></div><div className="space-y-4 p-5 text-sm"><div className="flex gap-3"><ShieldCheck className="shrink-0 text-accent" size={19} /><p><strong>Supplementary only.</strong><br /><span className="text-slate-500">It supports review; it does not diagnose or prescribe.</span></p></div><div className="flex gap-3"><GitBranch className="shrink-0 text-primary" size={19} /><p><strong>No ranking influence.</strong><br /><span className="text-slate-500">LightGBM and recommendation ordering remain unchanged.</span></p></div><div className="flex gap-3"><Database className="shrink-0 text-primary" size={19} /><p><strong>Baseline evidence.</strong><br /><span className="text-slate-500">External audit and calibration are still pending.</span></p></div></div></article>
          <details className="surface group overflow-hidden"><summary className="flex cursor-pointer list-none items-center justify-between p-5 font-bold"><span className="flex items-center gap-2"><BrainCircuit className="text-primary" size={19} />Model details</span><ChevronDown className="transition group-open:rotate-180" size={18} /></summary><dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-3 border-t border-border p-5 text-xs dark:border-slate-700"><dt className="text-slate-500">Stage</dt><dd className="text-right font-semibold">Baseline</dd><dt className="text-slate-500">Validation</dt><dd className="text-right font-semibold">Audit pending</dd><dt className="text-slate-500">Training epoch</dt><dd className="text-right font-semibold">{profile.trainingEpoch}</dd><dt className="text-slate-500">Vocabulary</dt><dd className="text-right font-semibold">{profile.eventVocabularySize} events</dd><dt className="text-slate-500">Model</dt><dd className="text-right font-mono" title={profile.modelVersion}>{compactVersion(profile.modelVersion)}</dd><dt className="text-slate-500">Checkpoint</dt><dd className="text-right font-mono" title={profile.checkpointVersion}>{compactVersion(profile.checkpointVersion)}</dd><dt className="text-slate-500">Device</dt><dd className="text-right font-semibold uppercase">{profile.device}</dd><dt className="text-slate-500">Generated</dt><dd className="text-right font-semibold">{profile.generatedAt ? new Date(profile.generatedAt).toLocaleString() : "—"}</dd></dl></details>
        </aside>
      </div>
      <article className="surface flex gap-3 p-5"><ShieldCheck className="mt-0.5 shrink-0 text-primary" size={20} /><div><h2 className="font-bold">Interpretation and limitations</h2><p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">{profile.interpretation} The profile is an audit-pending baseline output, is not a patient-incidence estimate, and has no effect on clinical safety gates, candidate generation, LightGBM prediction, recommendation scoring, or tie-breaking.</p></div></article>
    </>}
    <div className="flex flex-col justify-between gap-3 sm:flex-row"><button className="btn-secondary" onClick={() => navigate(`/patients/${patientId}/consultations/${visitId}/adr`)}><ArrowLeft size={16} />Adverse Risk Assessment</button><button className="btn-primary" disabled={advancing} onClick={openRecommendations}>{advancing ? "Evaluating alternatives…" : "Recommendations"}<ArrowRight size={16} /></button></div>
  </section>;
}
