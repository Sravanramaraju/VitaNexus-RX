import { Activity, ArrowLeft, Clock3, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getEventRiskProfile } from "../lib/eventRiskProfile";
import { usePatient } from "../context/PatientContext";

export default function AdverseEventRisks() {
  const { patientId, visitId } = useParams();
  const navigate = useNavigate();
  const { patients } = usePatient();
  const patient = patients.find((item) => item.id === patientId);
  const visit = useMemo(() => patient?.visits.find((item) => item.id === visitId), [patient, visitId]);
  const [profile, setProfile] = useState(null);

  useEffect(() => { getEventRiskProfile(visitId).then(setProfile).catch(() => setProfile({ status: "model_not_available", message: "Individual adverse-event model validation is in progress." })); }, [visitId]);

  if (!patient || !visit) return <div className="surface p-6">Consultation not found.</div>;
  return <section className="mx-auto max-w-4xl space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="eyebrow">Supplementary Clinical Insight</p><h1 className="mt-1 text-2xl font-bold">Individual Adverse Event Risk Profile</h1><p className="mt-1 text-sm text-slate-500">{visit.prescribedDrug} · Patient {patient.publicId}</p></div>
      <span className="rounded-full bg-warning/15 px-3 py-1 text-xs font-bold text-warning">VALIDATION PENDING</span>
    </div>
    <article className="surface p-6">
      <div className="flex gap-4"><div className="rounded-xl bg-primary/10 p-3 text-primary"><Activity size={26} /></div><div><h2 className="text-lg font-bold">Event-level ADR predictions are not active</h2><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{profile?.message || "Individual adverse-event model validation is in progress."}</p></div></div>
      <div className="mt-5 grid gap-3 md:grid-cols-2"><div className="rounded-xl border border-border p-4 dark:border-slate-700"><Clock3 className="text-primary" size={20} /><p className="mt-2 text-sm font-bold">Prepared for future integration</p><p className="mt-1 text-xs text-slate-500">When validated, this view will show ordered event names and their model-estimated probabilities for this patient-drug context.</p></div><div className="rounded-xl border border-border p-4 dark:border-slate-700"><ShieldAlert className="text-primary" size={20} /><p className="mt-2 text-sm font-bold">Not part of drug ranking</p><p className="mt-1 text-xs text-slate-500">Event-level predictions are supplementary clinical information and will not change the safety-aware alternative ranking score.</p></div></div>
      <p className="mt-5 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-700/50 dark:text-slate-300">No HGNN weights are loaded and no event probability is displayed until its training and audit are completed.</p>
    </article>
    <button className="btn-secondary" onClick={() => navigate(`/patients/${patientId}/consultations/${visitId}/adr`)}><ArrowLeft size={16} />Back to overall adverse risk</button>
  </section>;
}
