import { AlertTriangle, BrainCircuit, CheckCircle2, ChevronLeft, ChevronRight, Info, Search, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { usePatient } from "../context/PatientContext";
import { useTerminologySearch } from "../hooks/useTerminologySearch";

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

function CoverageCorrection({ prediction, visit, onCorrect, busy, error }) {
  const coverage = prediction?.inputCoverage || {};
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const { items, loading, error: lookupError } = useTerminologySearch("indications", query);
  const supportedItems = items.filter((item) => item.modelSupported === true);
  const unsupportedInputs = [
    ...(!coverage.sexKnown ? ["Patient sex is not encoded by the model."] : []),
    ...(!coverage.candidateKnown ? [`Candidate medicine “${visit.prescribedDrug}” is outside the model vocabulary.`] : []),
    ...(!coverage.indicationKnown ? [`Indication “${visit.indication}” is outside the model vocabulary.`] : []),
    ...(coverage.unknownCurrentMedications || []).map((name) => `Current medicine “${name}” is outside the model vocabulary.`),
  ];

  return <Card title="Input correction required">
    <div className="mt-4 rounded-xl border border-warning/40 bg-warning/10 p-4">
      <div className="flex gap-3"><AlertTriangle className="mt-0.5 shrink-0 text-warning" size={21} /><div><p className="font-semibold">LightGBM did not calculate a percentage.</p><p className="mt-1 text-sm text-slate-600 dark:text-slate-300">At least one input cannot be represented by the protected training vocabulary. No unknown value was treated as low risk, zero risk, or an ordinary model category.</p></div></div>
      {unsupportedInputs.length > 0 && <ul className="mt-3 space-y-1 pl-8 text-sm text-slate-700 dark:text-slate-200">{unsupportedInputs.map((item) => <li className="list-disc" key={item}>{item}</li>)}</ul>}
    </div>
    {!coverage.indicationKnown && <div className="mt-5 rounded-xl border border-border p-4 dark:border-slate-700">
      <label className="text-sm font-bold" htmlFor="correct-indication">Select the patient’s actual, model-supported indication</label>
      <p className="mt-1 text-xs text-slate-500">The system will not guess or automatically replace a diagnosis. Choose only the clinically correct indication.</p>
      <div className="relative mt-3">
        <Search className="pointer-events-none absolute left-3 top-3 text-slate-400" size={17} />
        <input id="correct-indication" className="input pl-10" value={selected ? selected.display : query} onChange={(event) => { setSelected(null); setQuery(event.target.value); }} placeholder="Search, for example: iron overload" />
        {query && !selected && <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-border bg-card shadow-lg dark:border-slate-600 dark:bg-slate-800">
          {loading ? <p className="px-3 py-3 text-sm text-slate-500">Checking model coverage…</p> : lookupError ? <p className="px-3 py-3 text-sm text-danger">{lookupError}</p> : supportedItems.length ? supportedItems.map((item) => <button type="button" key={item.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-primary/10" onClick={() => { setSelected(item); setQuery(""); }}><span className="font-semibold">{item.display}</span><span className="mt-0.5 flex items-center gap-1 text-xs text-success"><CheckCircle2 size={12} />Covered by current LightGBM · {item.source}</span></button>) : <p className="px-3 py-3 text-sm text-slate-500">No model-supported indication matches this search.</p>}
        </div>}
      </div>
      {selected && <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-success/10 p-3"><p className="text-sm"><strong>{selected.display}</strong><span className="ml-2 text-xs text-success">Full indication coverage confirmed</span></p><button type="button" className="btn-primary" disabled={busy} onClick={() => onCorrect(selected)}>{busy ? "Updating and reassessing…" : "Update indication and reassess"}</button></div>}
      <p className="mt-3 text-xs text-slate-500">Updating the indication invalidates the old ADR, event-profile, and recommendation results so they can be recalculated from consistent inputs.</p>
    </div>}
    {coverage.indicationKnown && unsupportedInputs.length > 0 && <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">Correct the patient sex or medication information in the patient record, then retry this assessment.</p>}
    {error && <p role="alert" className="mt-3 text-sm font-semibold text-danger">{error}</p>}
  </Card>;
}

export default function AdverseRiskAssessment() {
  const { patientId, visitId } = useParams();
  const navigate = useNavigate();
  const { patients, saveAdrPrediction, getAdrPrediction, correctConsultationIndication, generateRecommendations, refreshPatients } = usePatient();
  const patient = patients.find((item) => item.id === patientId);
  const visit = useMemo(() => patient?.visits.find((item) => item.id === visitId), [patient, visitId]);
  const [prediction, setPrediction] = useState(visit?.adrPrediction || null);
  const [state, setState] = useState(visit?.adrPrediction ? (["DEGRADED_COVERAGE", "OUT_OF_VOCABULARY"].includes(visit.adrPrediction.status) ? "NEEDS_INPUT" : ["ML_UNAVAILABLE", "INFERENCE_FAILED"].includes(visit.adrPrediction.status) ? "UNAVAILABLE" : "SUCCESS") : "LOADING");
  const [message, setMessage] = useState(visit?.adrPrediction?.message || "");
  const [advancing, setAdvancing] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [correctionError, setCorrectionError] = useState("");

  const load = async ({ regenerate = false } = {}) => {
    setState("LOADING"); setMessage("");
    try {
      let result;
      if (regenerate) result = await saveAdrPrediction(patientId, visitId);
      else {
        try { result = await getAdrPrediction(visitId); }
        catch { result = await saveAdrPrediction(patientId, visitId); }
      }
      setPrediction(result);
      if (["DEGRADED_COVERAGE", "OUT_OF_VOCABULARY"].includes(result.status)) { setState("NEEDS_INPUT"); setMessage(result.message || "One or more inputs are outside the model vocabulary."); }
      else if (["ML_UNAVAILABLE", "INFERENCE_FAILED", "INSUFFICIENT_INPUT"].includes(result.status)) { setState("UNAVAILABLE"); setMessage(result.message || "The trained model service or artifacts are unavailable."); }
      else setState("SUCCESS");
    } catch (error) { setState("FAILED"); setMessage(error.message || "ADR analysis could not be completed."); }
  };

  useEffect(() => { if (!prediction && patient && visit) load(); }, [patientId, visitId, patient, visit]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!patient || !visit) return <div className="surface p-6">Consultation not found.</div>;
  const overall = prediction?.overall;
  const correctIndication = async (selection) => {
    setCorrecting(true); setCorrectionError("");
    try {
      await correctConsultationIndication(visitId, selection, visit.version);
      await load({ regenerate: true });
    } catch (error) {
      setCorrectionError(error.message || "The indication could not be updated.");
    } finally { setCorrecting(false); }
  };
  const next = async () => {
    setAdvancing(true);
    try {
      await generateRecommendations(visitId);
      await refreshPatients();
      navigate(`/patients/${patientId}`, { state: { entry: "recommendations", visitId } });
    } finally { setAdvancing(false); }
  };

  return <section className="mx-auto max-w-5xl space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow">Adverse Risk Assessment</p><h1 className="mt-1 text-2xl font-bold">{visit.prescribedDrug} <span className="text-slate-400">—</span> {visit.indication}</h1><p className="mt-1 text-sm text-slate-500">FAERS-derived model assessment · Patient {patient.publicId}</p></div><span className={`rounded-full px-3 py-1 text-xs font-bold ${state === "SUCCESS" ? "bg-success/15 text-success" : state === "NEEDS_INPUT" ? "bg-warning/15 text-warning" : "bg-slate-200 text-slate-600"}`}>{state === "NEEDS_INPUT" ? "INPUT CORRECTION NEEDED" : state}</span></div>
    <nav className="flex flex-wrap gap-2" aria-label="Visit steps">
      <button type="button" className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary transition hover:bg-primary/20" onClick={() => navigate(`/patients/${patientId}`, { state: { entry: "results", visitId } })}>Clinical Safety</button>
      <button type="button" aria-current="step" className="cursor-default rounded-full bg-primary px-3 py-1 text-xs font-bold text-white">Adverse Risk Assessment</button>
      <button type="button" className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary transition hover:bg-primary/20" onClick={() => navigate(`/patients/${patientId}/consultations/${visitId}/adverse-event-risks`)}>Event Profile</button>
      <button type="button" disabled={advancing || state !== "SUCCESS"} className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary transition hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-45" onClick={next}>Recommendations</button>
      <button type="button" disabled title="Complete recommendations to unlock Follow-up" className="cursor-not-allowed rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary opacity-45">Follow-up</button>
    </nav>
    {state === "LOADING" && <Card title="Generating patient-context ADR assessment"><div className="mt-4 h-2 overflow-hidden rounded bg-primary/10"><div className="h-full w-2/3 animate-pulse rounded bg-primary" /></div><p className="mt-3 text-sm text-slate-500">Loading persisted results or requesting the internal ML service…</p></Card>}
    {["UNAVAILABLE", "FAILED"].includes(state) && <StatusPanel state={state} message={message} onRetry={() => load({ regenerate: true })} />}
    {state === "NEEDS_INPUT" && <CoverageCorrection prediction={prediction} visit={visit} onCorrect={correctIndication} busy={correcting} error={correctionError} />}
    {state === "SUCCESS" && overall && <>
      <Card title="Overall Adverse Risk"><div className="mt-4 grid gap-4 md:grid-cols-3"><div className="rounded-xl bg-primary/5 p-4"><p className="flex items-center gap-1 text-xs font-semibold text-slate-500">LightGBM adverse-risk estimate <Info size={13} /></p><p className="mt-2 text-4xl font-bold text-primary">{percent(overall.riskProbability)}</p><p className="mt-2 text-xs text-slate-500">A calibrated FAERS report-level estimate, not population incidence or a patient diagnosis.</p></div><div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-700/50"><p className="text-xs font-semibold text-slate-500">90% bootstrap model-variability range</p><p className="mt-2 text-2xl font-bold">{percent(overall.uncertainty.lower)} – {percent(overall.uncertainty.upper)}</p><p className="mt-2 text-xs text-slate-500">Variation across {overall.uncertainty.replicas} full-model bootstrap replicas.</p></div><div className="rounded-xl border border-primary/20 bg-primary/5 p-4"><p className="text-xs font-semibold text-slate-500">Uncertainty-adjusted risk</p><p className="mt-2 text-3xl font-bold">{percent(overall.adjustedRisk)}</p><p className="mt-2 text-xs text-slate-500">The conservative upper bootstrap bound used as the 50% LightGBM ranking input.</p></div></div></Card>
      <Card title="LightGBM Prediction Reliability"><div className="mt-4 rounded-xl border border-border p-4 dark:border-slate-700"><p className="text-xs font-semibold text-slate-500">Split-conformal target coverage: {percent(overall.conformal.targetCoverage)}</p><p className="mt-2 text-sm font-bold">{overall.conformal.reliability.replaceAll("_", " ")}</p><p className="mt-2 break-words font-mono text-sm">&#123;{overall.conformal.predictionSet.join(", ")}&#125;</p><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{overall.conformal.interpretation || setInterpretation(overall.conformal.predictionSet)}</p><p className="mt-2 text-xs text-slate-500">{overall.conformal.intervalNote}</p></div></Card>
      <Card title="Specific Event Profile"><div className="mt-4 flex flex-col gap-4 rounded-xl border border-primary/20 bg-gradient-to-r from-primary/5 to-accent/10 p-5 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary text-white"><BrainCircuit size={22} /></div><div><p className="font-semibold">Protected baseline HGNN is available</p><p className="mt-1 max-w-2xl text-sm text-slate-600 dark:text-slate-300">Open the supplementary ranked event-label profile. Its audit is pending, its scores are not patient-incidence probabilities, and it never affects alternative-drug ranking.</p></div></div><button className="btn-secondary shrink-0" onClick={() => navigate(`/patients/${patientId}/consultations/${visitId}/adverse-event-risks`)}>Open Event Profile<ChevronRight size={16} /></button></div></Card>
      <Card title="Why this result?"><div className="mt-4 grid gap-4 md:grid-cols-2"><div><p className="text-sm font-bold">Inputs used</p><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Age, sex, candidate drug, selected DrugCentral indication, and active/current medications.</p><p className="mt-2 text-xs text-slate-500">Known candidate: {String(prediction.inputCoverage.candidateKnown)} · Known indication: {String(prediction.inputCoverage.indicationKnown)} · Recognized medicines: {prediction.inputCoverage.recognizedCurrentMedications}</p></div><div><p className="text-sm font-bold">Model provenance</p><p className="mt-2 text-xs text-slate-500">LightGBM {prediction.versions.lightgbm}<br />Conformal {prediction.versions.conformal}<br />Data window {prediction.dataWindow.fit}<br />Generated {new Date(prediction.generatedAt).toLocaleString()}</p></div></div><div className="mt-4 flex gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-700/50 dark:text-slate-300"><ShieldCheck size={17} className="shrink-0 text-primary" /><span>FAERS has spontaneous-reporting bias and no full exposed-population denominator. This is decision support, not autonomous prescribing.</span></div></Card>
    </>}
    <div className="flex justify-between gap-3"><button className="btn-secondary" onClick={() => navigate(`/patients/${patientId}`, { state: { entry: "results", visitId } })}><ChevronLeft size={16} />Clinical Safety</button><button className="btn-primary" disabled={advancing || state !== "SUCCESS"} onClick={next}>{advancing ? "Evaluating alternatives…" : "Recommendations"}<ChevronRight size={16} /></button></div>
  </section>;
}
