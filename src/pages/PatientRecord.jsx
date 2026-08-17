import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardPlus,
  UserPlus,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import ExplainToggle from "../components/shared/ExplainToggle";
import { usePatient } from "../context/PatientContext";
import { SIDE_EFFECT_TERMS } from "../data/sideEffects";
import {
  getDrugDiseaseReasons,
  getDDIPredictionReasons,
  getFeedbackUsageReasons,
  getOverallClinicalRiskReasons,
  getRankingReasons,
} from "../lib/explainability";

export function resolveEntryStep(visit, navigationState) {
  if (navigationState?.entry === "results") return "results";
  if (navigationState?.entry === "followup" && visit?.status === "in-progress")
    return "followup";
  if (visit?.status === "completed") return "results";
  return "followup";
}

function ResultCard({ title, children }) {
  return (
    <motion.article
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25, ease: "easeInOut" }}
      className="surface p-5"
    >
      <h2 className="text-lg font-bold">{title}</h2>
      {children}
    </motion.article>
  );
}

const normalizeSeverity = (severity) => severity || "NOT_EVALUATED";
const formatDuration = (duration) =>
  /^\d+$/.test(String(duration)) ? `${duration} days` : duration;
const datasetResultLabel = (value, dataStatus) =>
  dataStatus === "NO_DATASET_MATCH" || value === "NOT_EVALUATED"
    ? "NO INTERACTION DETECTED"
    : value;

function AssessmentBadge({ severity }) {
  if (severity === "NO INTERACTION DETECTED") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-800 bg-emerald-900 px-2.5 py-1 text-xs font-bold tracking-wide text-emerald-50 dark:border-emerald-400 dark:bg-emerald-950 dark:text-emerald-100">
        <CheckCircle2 size={13} aria-hidden="true" />
        {severity}
      </span>
    );
  }
  const tone =
    severity === "Contraindicated" || severity === "High" || severity === "HIGH" || severity === "MAJOR"
      ? "bg-danger"
      : severity === "Moderate" || severity === "MODERATE"
        ? "bg-warning text-slate-900"
        : "bg-success";
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold text-white ${tone}`}
    >
      {severity}
    </span>
  );
}

function Metric({ label, children, className = "" }) {
  return (
    <div className={className}>
      <p className="text-xs font-medium text-slate-500 dark:text-slate-300">
        {label}
      </p>
      <div className="mt-1 text-sm font-semibold">{children}</div>
    </div>
  );
}

function SideEffectField({ value, onChange }) {
  return (
    <>
      <input
        required
        list="side-effect-terms"
        className="input mt-1"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search and select a side effect"
      />
      <datalist id="side-effect-terms">
        {SIDE_EFFECT_TERMS.map((term) => (
          <option value={term} key={term} />
        ))}
      </datalist>
      <p className="mt-1 text-xs text-slate-500">
        Record a standardized term for clinician follow-up. This workflow does not query FAERS.
      </p>
    </>
  );
}

function Results({
  visit,
  historical,
  stage,
  onStageChange,
  onSaveNotes,
  onAddPatient,
}) {
  const [notes, setNotes] = useState(visit.doctorNotes || "");
  const safety = visit.safetyResult;
  const risk = safety?.drugDrug || visit.riskResult;
  const severity = normalizeSeverity(risk?.severity);

  useEffect(
    () => setNotes(visit.doctorNotes || ""),
    [visit.id, visit.doctorNotes],
  );

  const insights = [
    ["Dataset result", risk?.explanations || getDDIPredictionReasons(severity)],
    ["Evidence", ["DDI severity is a DDInter 2.0 classification, not a probability.", "Drug-disease assessment is derived from DrugCentral relationships when available."]],
    ["Alternative Ranking", getRankingReasons()],
    [
      "Feedback Learning",
      visit.feedback
        ? getFeedbackUsageReasons()
        : ["Feedback learning becomes available after follow-up is submitted."],
    ],
  ];

  return (
    <div className="space-y-5">
      {stage === "results" && (
        <>
      <div className="space-y-5">
        <ResultCard title="Clinical Safety Analysis">
          <div className="mt-4 space-y-4">
            <section>
              <h3 className="text-sm font-bold">Drug–Drug Analysis</h3>
              <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
                <Metric label="Severity">
                  <AssessmentBadge severity={datasetResultLabel(severity, risk?.dataStatus)} />
                </Metric>
                <Metric label="Source">{risk?.source || "DDInter 2.0"}</Metric>
              </div>
              <p className="mt-3 text-xs text-slate-500">{risk?.dataStatus === "NO_DATASET_MATCH" ? "Evaluation completed: no DDInter 2.0 record exists for the compared dataset terms shown under Why?." : "Evaluation completed with matching DDInter 2.0 source evidence."}</p>
              <ExplainToggle reasons={risk?.explanations || getDDIPredictionReasons(severity)} />
            </section>

            <section className="border-t border-border pt-4 dark:border-slate-700">
              <h3 className="text-sm font-bold">Drug–Disease Analysis</h3>
              <div className="mt-3">
                <Metric label="Assessment"><AssessmentBadge severity={datasetResultLabel(safety?.drugDisease?.assessment, safety?.drugDisease?.dataStatus)} /></Metric>
                <Metric label="Source">{safety?.drugDisease?.source || "DrugCentral"}</Metric>
                {safety?.drugDisease?.findings?.map((finding, index) => <Metric key={`${finding.existingDisease}-${index}`} label={`${finding.existingDisease} / ${finding.proposedDrug}`} className="col-span-2">{finding.evidence || finding.relationship}</Metric>)}
              </div>
              <ExplainToggle reasons={getDrugDiseaseReasons()} />
            </section>

            <section className="rounded-lg border border-primary/20 bg-primary/5 p-4">
              <h3 className="text-sm font-bold">Overall Clinical Assessment</h3>
              <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
                <Metric label="Assessment"><AssessmentBadge severity={datasetResultLabel(safety?.overall?.assessment || (severity === "MAJOR" ? "HIGH" : severity === "MODERATE" ? "MODERATE" : severity === "MINOR" ? "LOW" : "NOT_EVALUATED"), safety?.overall?.dataStatus)} /></Metric>
                <Metric label="Basis">DDInter 2.0 + DrugCentral</Metric>
              </div>
              <ExplainToggle reasons={getOverallClinicalRiskReasons()} />
            </section>
          </div>
        </ResultCard>

        <ResultCard title="Dataset Evaluation Status">
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
            DDInter 2.0 and DrugCentral checks are complete. “No match found” is a completed source check, not a missing dataset import.
          </p>
        </ResultCard>
      </div>

          <div className="flex flex-wrap justify-end gap-3">
            <button
              type="button"
              onClick={() => onStageChange("recommendations")}
              className="btn-primary"
            >
              View Dataset-Evaluated Alternatives
              <ChevronRight size={16} />
            </button>
          </div>
        </>
      )}

      {stage === "recommendations" && (
        <>
        <ResultCard title="Recommended Safer Alternatives">
        <div className="mt-4 space-y-4">
          {(visit.recommendations || []).length ? (visit.recommendations || []).map((recommendation, index) => {
            return (
              <div
                className="rounded-lg bg-slate-50 p-3 dark:bg-slate-700/50"
                key={`${recommendation.drug}-${index}`}
              >
                <strong>
                  {index + 1}. {recommendation.drug}
                </strong>
                <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
                  <Metric label="Assessment"><AssessmentBadge severity={datasetResultLabel(recommendation.assessment, recommendation.dataStatus)} /></Metric>
                  <Metric label="Source">{recommendation.source || "DrugCentral"}</Metric>
                  <Metric label="Indication relationship" className="col-span-2">{recommendation.indicationRelationship || "Candidate lookup pending"}</Metric>
                  <Metric label="DDInter check"><AssessmentBadge severity={datasetResultLabel(recommendation.drugDrug?.severity, recommendation.dataStatus)} /></Metric>
                  <Metric label="DrugCentral condition check"><AssessmentBadge severity={datasetResultLabel(recommendation.drugDisease?.assessment, recommendation.dataStatus)} /></Metric>
                </div>
              </div>
            );
          }) : <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600 dark:bg-slate-700/50 dark:text-slate-200">Evaluation completed: DrugCentral has no indication candidate for this exact recorded indication. Choose a dataset indication from the lookup to obtain candidate results.</p>}
        </div>
        <ExplainToggle label="Why ranked?" reasons={getRankingReasons()} />
      </ResultCard>

      <ResultCard title="Doctor Notes">
        <textarea
          disabled={historical}
          className="input mt-4 min-h-28 disabled:opacity-70"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          onBlur={() => onSaveNotes(notes)}
        />
        {!historical && (
          <p className="mt-2 text-xs text-slate-500">
            Notes are saved when this field loses focus.
          </p>
        )}
      </ResultCard>

      <ResultCard title="AI Decision Insights">
        <div className="mt-3 divide-y divide-border dark:divide-slate-700">
          {insights.map(([title, reasons]) => (
            <div className="py-2" key={title}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">{title}</span>
                <ExplainToggle reasons={reasons} />
              </div>
            </div>
          ))}
        </div>
      </ResultCard>

      <div className="flex flex-wrap justify-end gap-3">
        <button type="button" onClick={onAddPatient} className="btn-primary">
          <UserPlus size={16} />
          Add New Patient
        </button>
        <button onClick={() => onStageChange("followup")} className="btn-primary">
          {historical ? "Next: Follow-up" : "Continue to Follow-up"}{" "}
          <ChevronRight size={16} />
        </button>
      </div>
        </>
      )}
    </div>
  );
}

function FollowUp({
  visit,
  historical,
  onSubmit,
  onSaveDraft,
  onNext,
  onAddPatient,
}) {
  const [feedback, setFeedback] = useState(
    visit.feedbackDraft ||
      visit.feedback || { sideEffect: "", severity: "Mild", duration: "" },
  );
  const [saved, setSaved] = useState(false);
  const [addingFurtherFollowUp, setAddingFurtherFollowUp] = useState(false);
  useEffect(() => {
    if (!saved) return undefined;
    const timer = setTimeout(onNext, 800);
    return () => clearTimeout(timer);
  }, [saved, onNext]);
  const submit = (event) => {
    event.preventDefault();
    onSubmit(feedback);
    setSaved(true);
  };
  const changeFeedback = (changes) => {
    const nextFeedback = { ...feedback, ...changes };
    setFeedback(nextFeedback);
    onSaveDraft?.(nextFeedback);
  };
  const startFurtherFollowUp = () => {
    changeFeedback({ sideEffect: "", severity: "Mild", duration: "" });
    setAddingFurtherFollowUp(true);
    setSaved(false);
  };

  if (historical)
    return (
      <div className="space-y-5">
        <ResultCard title="Follow-up">
          <p className="mt-4 text-sm">
            Side effect:{" "}
            <strong>{visit.feedback?.sideEffect || "Not recorded"}</strong>
          </p>
          <p className="mt-2 text-sm">
            Severity:{" "}
            <strong>{visit.feedback?.severity || "Not recorded"}</strong>
          </p>
          <p className="mt-2 text-sm">
            Duration:{" "}
            <strong>
              {formatDuration(visit.feedback?.duration) || "Not recorded"}
            </strong>
          </p>
          {visit.followUps?.length > 0 && (
            <div className="mt-5 border-t border-border pt-4 dark:border-slate-700">
              <p className="text-sm font-bold">Further follow-ups</p>
              <div className="mt-3 space-y-3">
                {visit.followUps.map((followUp) => (
                  <div
                    key={followUp.id}
                    className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-700/50"
                  >
                    <p>
                      <strong>
                        {new Date(followUp.date).toLocaleDateString("en-IN", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </strong>
                    </p>
                    <p className="mt-1">Side effect: {followUp.sideEffect}</p>
                    <p>
                      Severity: {followUp.severity} · Duration:{" "}
                      {formatDuration(followUp.duration)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {!addingFurtherFollowUp && (
            <button
              type="button"
              onClick={startFurtherFollowUp}
              className="btn-primary mt-5"
            >
              <CheckCircle2 size={16} />
              Add Further Follow-up
            </button>
          )}
        </ResultCard>
        {addingFurtherFollowUp && (
          <form onSubmit={submit} className="surface max-w-xl p-6">
            <h2 className="text-xl font-bold">Add Further Follow-up</h2>
            <div className="mt-5 space-y-4">
              <label className="block text-sm font-semibold">
                Side effect
                <SideEffectField
                  value={feedback.sideEffect}
                  onChange={(sideEffect) => changeFeedback({ sideEffect })}
                />
              </label>
              <label className="block text-sm font-semibold">
                Severity
                <select
                  className="input mt-1"
                  value={feedback.severity}
                  onChange={(event) =>
                    changeFeedback({ severity: event.target.value })
                  }
                >
                  <option>Mild</option>
                  <option>Moderate</option>
                  <option>Severe</option>
                </select>
              </label>
              <label className="block text-sm font-semibold">
                Duration (days)
                <input
                  required
                  type="number"
                  min="1"
                  step="1"
                  inputMode="numeric"
                  className="input mt-1"
                  placeholder="Number of days"
                  value={feedback.duration}
                  onChange={(event) =>
                    changeFeedback({ duration: event.target.value })
                  }
                />
              </label>
              <button className="btn-primary" disabled={saved}>
                Save Further Follow-up
              </button>
            </div>
          </form>
        )}
        {saved && (
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.2 }}
            className="surface max-w-xl border-l-4 border-l-success p-5"
          >
            <div className="flex items-center gap-2 font-bold text-success">
              <CheckCircle2 size={18} />
              Further Follow-up Saved
            </div>
            <ExplainToggle
              label="How is this used?"
              reasons={getFeedbackUsageReasons()}
            />
          </motion.div>
        )}
        <div className="flex justify-between">
          <button className="btn-secondary" onClick={() => onNext("results")}>
            <ChevronLeft size={16} />
            Results
          </button>
          <button className="btn-primary" onClick={() => onNext("updated")}>
            Next: Follow-up Recommendation <ChevronRight size={16} />
          </button>
        </div>
      </div>
    );

  return (
    <div className="space-y-5">
      <form onSubmit={submit} className="surface max-w-xl p-6">
        <h2 className="text-xl font-bold">Follow-up</h2>
        <div className="mt-5 space-y-4">
          <label className="block text-sm font-semibold">
            Side effect
            <SideEffectField
              value={feedback.sideEffect}
              onChange={(sideEffect) => changeFeedback({ sideEffect })}
            />
          </label>
          <label className="block text-sm font-semibold">
            Severity
            <select
              className="input mt-1"
              value={feedback.severity}
              onChange={(event) =>
                changeFeedback({ severity: event.target.value })
              }
            >
              <option>Mild</option>
              <option>Moderate</option>
              <option>Severe</option>
            </select>
          </label>
          <label className="block text-sm font-semibold">
            Duration (days)
            <input
              required
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              className="input mt-1"
              placeholder="Number of days"
              value={feedback.duration}
              onChange={(event) =>
                changeFeedback({ duration: event.target.value })
              }
            />
          </label>
          <div className="flex flex-wrap gap-3">
            <button className="btn-primary" disabled={saved}>
              Save Follow-up
            </button>
            <button
              type="button"
              onClick={onAddPatient}
              className="btn-primary"
            >
              <UserPlus size={16} />
              Add New Patient
            </button>
          </div>
        </div>
      </form>
      {saved && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.2 }}
          className="surface max-w-xl border-l-4 border-l-success p-5"
        >
          <div className="flex items-center gap-2 font-bold text-success">
            <CheckCircle2 size={18} />
            Feedback Saved
          </div>
          <ExplainToggle
            label="How is this used?"
            reasons={getFeedbackUsageReasons()}
          />
        </motion.div>
      )}
    </div>
  );
}

function UpdatedRecommendations({ visit, historical, onBack }) {
  const items = visit.updatedRecommendations || [];
  return (
    <div className="space-y-5">
      <ResultCard title="Follow-up Recommendation">
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Recommendations re-ranked after physician feedback.
        </p>
        <div className="mt-4 space-y-4">
          {items.length ? (
            items.map((recommendation, index) => {
              return (
                <div
                  className="rounded-lg bg-slate-50 p-3 dark:bg-slate-700/50"
                  key={`${recommendation.drug}-${index}`}
                >
                  <strong>
                    {index + 1}. {recommendation.drug}
                  </strong>
                  <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
                    <Metric label="Assessment">
                      <AssessmentBadge severity={datasetResultLabel(recommendation.assessment, recommendation.dataStatus)} />
                    </Metric>
                    <Metric label="Source">{recommendation.source || "DrugCentral"}</Metric>
                    <Metric label="Indication relationship" className="col-span-2">{recommendation.indicationRelationship || "Candidate lookup pending"}</Metric>
                  </div>
                </div>
              );
            })
          ) : (
            <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500 dark:bg-slate-700/50">
              Follow-up recommendations appear after feedback is saved.
            </p>
          )}
        </div>
        <ExplainToggle label="Why ranked?" reasons={getRankingReasons()} />
      </ResultCard>
      {historical && (
        <button className="btn-secondary" onClick={onBack}>
          <ChevronLeft size={16} />
          Follow-up
        </button>
      )}
    </div>
  );
}

function WizardSteps({ activeStep, visitedSteps, onStepChange }) {
  const steps = [
    ["results", "Clinical Safety"],
    ["recommendations", "Recommendations"],
    ["followup", "Follow-up"],
    ["updated", "Follow-up Recommendation"],
  ];

  return (
    <nav className="mb-6 flex flex-wrap gap-2" aria-label="Visit steps">
      {steps.map(([id, label]) => {
        const available = visitedSteps[id];
        const active = activeStep === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onStepChange(id)}
            disabled={!available}
            aria-current={active ? "step" : undefined}
            title={
              available
                ? `Open ${label}`
                : `Complete the previous step to unlock ${label}`
            }
            className={`rounded-full px-3 py-1 text-xs font-bold transition ${active ? "bg-primary text-white" : "bg-primary/10 text-primary"} ${available ? "cursor-pointer hover:bg-primary/20" : "cursor-not-allowed opacity-45"}`}
          >
            {label}
          </button>
        );
      })}
    </nav>
  );
}

export default function PatientRecord() {
  const { patientId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const {
    patients,
    activeVisitId,
    setActiveVisitId,
    submitFeedback,
    saveFollowUpDraft,
    saveVisitNotes,
  } = usePatient();
  const patient = patients.find((item) => item.id === patientId);
  const activeVisit = useMemo(
    () =>
      patient?.visits.find((visit) => visit.id === activeVisitId) ||
      patient?.visits.at(-1),
    [patient, activeVisitId],
  );
  const stateForVisit =
    location.state?.visitId && location.state.visitId !== activeVisit?.id
      ? null
      : location.state;
  const [step, setStep] = useState(() =>
    resolveEntryStep(activeVisit, stateForVisit),
  );
  const [resolvedVisitId, setResolvedVisitId] = useState(
    activeVisit?.id || null,
  );
  const [visitedSteps, setVisitedSteps] = useState(() => ({
    results: true,
    recommendations: activeVisit?.status === "completed",
    followup:
      activeVisit?.status === "completed" ||
      resolveEntryStep(activeVisit, stateForVisit) === "followup",
    updated: activeVisit?.status === "completed",
  }));

  useEffect(() => {
    if (!patient) return;
    const preferred = location.state?.visitId;
    const valid = patient.visits.some((visit) => visit.id === activeVisitId);
    if (preferred && patient.visits.some((visit) => visit.id === preferred))
      setActiveVisitId(preferred);
    else if (!valid) setActiveVisitId(patient.visits.at(-1).id);
  }, [
    patientId,
    patient,
    activeVisitId,
    location.state?.visitId,
    setActiveVisitId,
  ]);

  useEffect(() => {
    if (activeVisit && resolvedVisitId !== activeVisit.id) {
      setStep(resolveEntryStep(activeVisit, stateForVisit));
      setVisitedSteps({
        results: true,
        recommendations: activeVisit.status === "completed",
        followup:
          activeVisit.status === "completed" ||
          resolveEntryStep(activeVisit, stateForVisit) === "followup",
        updated: activeVisit.status === "completed",
      });
      setResolvedVisitId(activeVisit.id);
    }
  }, [activeVisit, resolvedVisitId, stateForVisit]);

  if (!patient || !activeVisit)
    return <div className="surface p-6">Patient record not found.</div>;

  const historical = activeVisit.status === "completed";
  const freshInProgress =
    activeVisit.status === "in-progress" &&
    location.state?.entry === "results" &&
    location.state?.visitId === activeVisit.id;
  const submit = (feedback) =>
    submitFeedback(patient.id, activeVisit.id, feedback);
  const startNewPatient = () => navigate("/patients/new");
  const goToVisitedStep = (target) => {
    if (visitedSteps[target]) setStep(target);
  };
  const advanceToStep = (target) => {
    setVisitedSteps((current) => ({ ...current, [target]: true }));
    setStep(target);
  };
  const body =
    step === "results" || step === "recommendations" ? (
      <Results
        visit={activeVisit}
        historical={historical}
        stage={step}
        onStageChange={(target) =>
          target === "results" ? goToVisitedStep(target) : advanceToStep(target)
        }
        onSaveNotes={(notes) =>
          saveVisitNotes(patient.id, activeVisit.id, notes)
        }
        onAddPatient={startNewPatient}
      />
    ) : step === "followup" ? (
      <FollowUp
        visit={activeVisit}
        historical={historical}
        onSubmit={submit}
        onSaveDraft={(feedbackDraft) =>
          saveFollowUpDraft(patient.id, activeVisit.id, feedbackDraft)
        }
        onNext={(target) =>
          target === "results"
            ? goToVisitedStep("results")
            : advanceToStep("updated")
        }
        onAddPatient={startNewPatient}
      />
    ) : (
      <UpdatedRecommendations
        visit={activeVisit}
        historical={historical}
        onBack={() => goToVisitedStep("followup")}
      />
    );

  return (
    <section className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Visit workspace</p>
          <h1 className="mt-1 text-2xl font-bold">
            {activeVisit.prescribedDrug?.brand || "Consultation"}{" "}
            <span className="text-slate-400">-</span>{" "}
            {activeVisit.diagnosis || "Clinical review"}
          </h1>
        </div>
        {!freshInProgress && (
          <button
            onClick={() =>
              navigate("/patients/new", {
                state: { existingPatientId: patient.id },
              })
            }
            className="btn-secondary"
          >
            <ClipboardPlus size={16} />
            New Consultation
          </button>
        )}
      </div>
      <WizardSteps
        activeStep={step}
        visitedSteps={visitedSteps}
        onStepChange={goToVisitedStep}
      />
      <AnimatePresence mode="wait">
        <motion.div
          key={`${activeVisit.id}-${step}`}
          initial={{ opacity: 0, x: 18 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -18 }}
          transition={{ duration: 0.3, ease: "easeInOut" }}
        >
          {body}
        </motion.div>
      </AnimatePresence>
    </section>
  );
}
