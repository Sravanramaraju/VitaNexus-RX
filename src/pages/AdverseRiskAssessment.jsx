import { AlertTriangle, ChevronLeft, ChevronRight, Info, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { usePatient } from "../context/PatientContext";

const percent = (value) => `${Math.round(Number(value || 0) * 100)}%`;
const setInterpretation = (values = []) => {
  if (values.length === 0) return "Invalid/empty prediction set; clinical review is required.";
  if (values.length === 2) return "Ambiguous prediction: both outcome classes remain plausible at the configured conformal threshold.";
  return values[0] === "SERIOUS_OUTCOME" ? "Focused prediction toward the serious-outcome class." : "Focused prediction toward the no-documented-serious-outcome class.";
};

function Card({ title, children }) {
  return <article className="surface p-5"><h2 className="text-lg font-bold">{title}</h2>{children}</article>;
}

function StatusPanel({ state, message, onRetry }) {
  const unavailable = state === "UNAVAILABLE";
  return <Card title={unavailable ? "ML assessment unavailable" : "ADR assessment failed"}><div className="mt-4 flex gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4"><AlertTriangle className="mt-0.5 text-warning" size={20} /><div><p className="font-semibold">No low or zero risk has been inferred.</p><p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{message}</p><button className="btn-secondary mt-4" onClick={onRetry}>Retry assessment</button></div></div></Card>;
}

export default function AdverseRiskAssessment() {
  const { patientId, visitId } = useParams();
  const navigate = useNavigate();
  const { patients, saveAdrPrediction, getAdrPrediction, generateRecommendations, refreshPatients } = usePatient();
  const patient = patients.find((item) => item.id === patientId);
  const visit = useMemo(() => patient?.visits.find((item) => item.id === visitId), [patient, visitId]);
  const [prediction, setPrediction] = useState(visit?.adrPrediction || null);
  const [state, setState] = useState(visit?.adrPrediction ? (visit.adrPrediction.status === "DEGRADED_COVERAGE" ? "DEGRADED" : ["ML_UNAVAILABLE", "INFERENCE_FAILED"].includes(visit.adrPrediction.status) ? "UNAVAILABLE" : "SUCCESS") : "LOADING");
  const [message, setMessage] = useState(visit?.adrPrediction?.message || "");
  const [advancing, setAdvancing] = useState(false);

  const load = async () => {
    setState("LOADING"); setMessage("");
    try {
      let result;
      try { result = await getAdrPrediction(visitId); }
      catch { result = await saveAdrPrediction(patientId, visitId); }
      setPrediction(result);
      if (result.status === "DEGRADED_COVERAGE") setState("DEGRADED");
      else if (["ML_UNAVAILABLE", "INFERENCE_FAILED", "INSUFFICIENT_INPUT", "OUT_OF_VOCABULARY"].includes(result.status)) { setState("UNAVAILABLE"); setMessage(result.message || "The trained model service or artifacts are unavailable."); }
      else setState("SUCCESS");
    } catch (error) { setState("FAILED"); setMessage(error.message || "ADR analysis could not be completed."); }
  };

  useEffect(() => { if (!prediction && patient && visit) load(); }, [patientId, visitId, patient, visit]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!patient || !visit) return <div className="surface p-6">Consultation not found.</div>;
  const overall = prediction?.overall;
  const next = async () => {
    setAdvancing(true);
    try {
      await generateRecommendations(visitId);
      await refreshPatients();
      navigate(`/patients/${patientId}`, { state: { entry: "recommendations", visitId } });
    } finally { setAdvancing(false); }
  };

  return <section className="mx-auto max-w-5xl space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow">Adverse Risk Assessment</p><h1 className="mt-1 text-2xl font-bold">{visit.prescribedDrug} <span className="text-slate-400">—</span> {visit.indication}</h1><p className="mt-1 text-sm text-slate-500">FAERS-derived model assessment · Patient {patient.publicId}</p></div><span className={`rounded-full px-3 py-1 text-xs font-bold ${state === "SUCCESS" ? "bg-success/15 text-success" : state === "DEGRADED" ? "bg-warning/15 text-warning" : "bg-slate-200 text-slate-600"}`}>{state}</span></div>
    <nav className="flex flex-wrap gap-2" aria-label="Visit steps">{["Clinical Safety", "Adverse Risk Assessment", "Recommendations", "Follow-up"].map((label) => <span key={label} className={`rounded-full px-3 py-1 text-xs font-bold ${label === "Adverse Risk Assessment" ? "bg-primary text-white" : "bg-primary/10 text-primary"}`}>{label}</span>)}</nav>
    {state === "LOADING" && <Card title="Generating patient-context ADR assessment"><div className="mt-4 h-2 overflow-hidden rounded bg-primary/10"><div className="h-full w-2/3 animate-pulse rounded bg-primary" /></div><p className="mt-3 text-sm text-slate-500">Loading persisted results or requesting the internal ML service…</p></Card>}
    {["UNAVAILABLE", "FAILED"].includes(state) && <StatusPanel state={state} message={message} onRetry={load} />}
    {["SUCCESS", "DEGRADED"].includes(state) && overall && <>
      {state === "DEGRADED" && <div className="rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm"><strong>{prediction.artifactMode === "FAST_SMOKE" ? "Development smoke artifacts are loaded." : "Degraded input coverage."}</strong> {prediction.artifactMode === "FAST_SMOKE" ? "These estimates only verify the end-to-end pipeline and are not final evaluation results. Run the full training commands before scientific or clinical interpretation." : "Unrecognized inputs are shown below; the result is not presented as complete evidence."}</div>}
      <Card title="Overall Adverse Risk"><div className="mt-4 grid gap-4 md:grid-cols-3"><div className="rounded-xl bg-primary/5 p-4"><p className="flex items-center gap-1 text-xs font-semibold text-slate-500">LightGBM adverse-risk estimate <Info size={13} /></p><p className="mt-2 text-4xl font-bold text-primary">{percent(overall.riskProbability)}</p><p className="mt-2 text-xs text-slate-500">A calibrated FAERS report-level estimate, not population incidence or a patient diagnosis.</p></div><div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-700/50"><p className="text-xs font-semibold text-slate-500">90% bootstrap model-variability range</p><p className="mt-2 text-2xl font-bold">{percent(overall.uncertainty.lower)} – {percent(overall.uncertainty.upper)}</p><p className="mt-2 text-xs text-slate-500">Variation across {overall.uncertainty.replicas} full-model bootstrap replicas.</p></div><div className="rounded-xl border border-primary/20 bg-primary/5 p-4"><p className="text-xs font-semibold text-slate-500">Uncertainty-adjusted risk</p><p className="mt-2 text-3xl font-bold">{percent(overall.adjustedRisk)}</p><p className="mt-2 text-xs text-slate-500">The conservative upper bootstrap bound used as the 50% LightGBM ranking input.</p></div></div></Card>
      <Card title="LightGBM Prediction Reliability"><div className="mt-4 rounded-xl border border-border p-4 dark:border-slate-700"><p className="text-xs font-semibold text-slate-500">Split-conformal target coverage: {percent(overall.conformal.targetCoverage)}</p><p className="mt-2 text-sm font-bold">{overall.conformal.reliability.replaceAll("_", " ")}</p><p className="mt-2 break-words font-mono text-sm">&#123;{overall.conformal.predictionSet.join(", ")}&#125;</p><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{overall.conformal.interpretation || setInterpretation(overall.conformal.predictionSet)}</p><p className="mt-2 text-xs text-slate-500">{overall.conformal.intervalNote}</p></div></Card>
      <Card title="Individual Adverse Event Risks"><div className="mt-4 rounded-xl border border-warning/40 bg-warning/10 p-4"><p className="font-semibold">Event-level model validation is in progress.</p><p className="mt-1 text-sm text-slate-600 dark:text-slate-300">The future HGNN event profile is supplementary clinical insight. It is not active, does not supply predictions here, and never affects alternative-drug ranking.</p><button className="btn-secondary mt-4" onClick={() => navigate(`/patients/${patientId}/consultations/${visitId}/adverse-event-risks`)}>View event-risk module status</button></div></Card>
      <Card title="Why this result?"><div className="mt-4 grid gap-4 md:grid-cols-2"><div><p className="text-sm font-bold">Inputs used</p><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Age, sex, candidate drug, selected DrugCentral indication, and active/current medications.</p><p className="mt-2 text-xs text-slate-500">Known candidate: {String(prediction.inputCoverage.candidateKnown)} · Known indication: {String(prediction.inputCoverage.indicationKnown)} · Recognized medicines: {prediction.inputCoverage.recognizedCurrentMedications}</p></div><div><p className="text-sm font-bold">Model provenance</p><p className="mt-2 text-xs text-slate-500">LightGBM {prediction.versions.lightgbm}<br />Conformal {prediction.versions.conformal}<br />Data window {prediction.dataWindow.fit}<br />Generated {new Date(prediction.generatedAt).toLocaleString()}</p></div></div><div className="mt-4 flex gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-700/50 dark:text-slate-300"><ShieldCheck size={17} className="shrink-0 text-primary" /><span>FAERS has spontaneous-reporting bias and no full exposed-population denominator. This is decision support, not autonomous prescribing.</span></div></Card>
    </>}
    <div className="flex justify-between gap-3"><button className="btn-secondary" onClick={() => navigate(`/patients/${patientId}`, { state: { entry: "results", visitId } })}><ChevronLeft size={16} />Clinical Safety</button><button className="btn-primary" disabled={advancing} onClick={next}>{advancing ? "Evaluating alternatives…" : "Recommendations"}<ChevronRight size={16} /></button></div>
  </section>;
}
