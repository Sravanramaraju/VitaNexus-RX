import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardPlus,
  UserPlus,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import ExplainToggle from "../components/shared/ExplainToggle";
import { usePatient } from "../context/PatientContext";
import { SIDE_EFFECT_TERMS } from "../data/sideEffects";
import { requestAdrPrediction } from "../services/adrPredictionService";
import {
  getDrugAllergyReasons,
  getDrugDiseaseReasons,
  getDDIPredictionReasons,
  getFeedbackUsageReasons,
  getOverallClinicalRiskReasons,
  getRankingReasons,
  getReliabilityReasons,
} from "../lib/explainability";

export function resolveEntryStep(visit, navigationState) {
  if (navigationState?.entry === "results") return "results";
  if (navigationState?.entry === "followup" && visit?.status === "in-progress")
    return "followup";
  if (visit?.status === "completed") return "results";
  return "followup";
}

function RangeBar({ low = 0, high = 0 }) {
  const width = Math.max(2, high - low);
  return (
    <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${width}%` }}
        transition={{ duration: 0.45, ease: "easeInOut" }}
        className="h-full rounded-full bg-primary"
        style={{ marginLeft: `${low}%` }}
      />
    </div>
  );
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

const severityFromRisk = (risk) =>
  risk > 60 ? "High" : risk > 30 ? "Moderate" : "Low";
const normalizeSeverity = (severity, risk) => {
  if (severity === "Contraindicated") return "Contraindicated";
  if (severity === "Severe") return "High";
  if (severity === "Mild") return "Low";
  return severity || severityFromRisk(risk || 0);
};
const reliabilityFromConfidence = (label, pct) => {
  if (label === "Very High" || label === "High" || pct > 65) return "High";
  if (label === "Moderate" || pct > 45) return "Medium";
  return "Low";
};
const formatDuration = (duration) =>
  /^\d+$/.test(String(duration)) ? `${duration} days` : duration;

function InteractionSeverityBadge({ severity }) {
  const tone =
    severity === "Contraindicated" || severity === "High"
      ? "bg-danger"
      : severity === "Moderate"
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

function AdrRiskAssessment({ patient, visit, onBack, onNext, onSave }) {
  const [prediction, setPrediction] = useState(visit.adrPrediction || null);
  const [status, setStatus] = useState(
    visit.adrPrediction?.predictionStatus || "loading",
  );
  const [error, setError] = useState("");
  const candidateDrug =
    visit.prescription?.medicine || visit.prescribedDrug || null;

  const loadPrediction = useCallback(async () => {
    setStatus("loading");
    setError("");
    try {
      const candidateName = (
        candidateDrug?.generic ||
        candidateDrug?.drugName ||
        candidateDrug?.brand ||
        ""
      ).toLowerCase();
      const response = await requestAdrPrediction({
        patientId: patient.id,
        age: patient.age,
        gender: patient.gender,
        currentMedications: (patient.currentMedications || []).filter(
          (medication) =>
            medication.activeStatus === "active" &&
            (medication.drugName || medication.generic || medication.brand || "").toLowerCase() !==
              candidateName,
        ),
        candidateDrug,
      });
      if (!response) {
        setPrediction(null);
        setStatus("unavailable");
        return;
      }
      setPrediction(response);
      setStatus(response.predictionStatus || "success");
      onSave(response);
    } catch {
      setStatus("failed");
      setError("The ADR prediction could not be loaded.");
    }
  }, [candidateDrug, onSave, patient]);

  useEffect(() => {
    if (visit.adrPrediction?.predictionStatus === "success") {
      setPrediction(visit.adrPrediction);
      setStatus("success");
      return;
    }
    loadPrediction();
  }, [loadPrediction, visit.adrPrediction, visit.id]);

  const riskCategory = prediction?.riskCategory || "Low";
  return (
    <div className="space-y-5">
      <div>
        <p className="eyebrow">Clinical safety analysis</p>
        <h2 className="mt-1 text-xl font-bold">
          Adverse Drug Reaction Risk Assessment
        </h2>
        <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
          Evaluate the predicted probability of an adverse drug reaction based
          on patient demographics, current medications and the newly prescribed
          medicine.
        </p>
      </div>

      {status === "loading" && (
        <ResultCard title="ADR Prediction">
          <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">
            Loading prediction...
          </p>
        </ResultCard>
      )}

      {status === "failed" && (
        <ResultCard title="ADR Prediction">
          <p className="mt-4 text-sm text-danger">{error}</p>
          <button className="btn-secondary mt-4" onClick={loadPrediction}>
            Retry
          </button>
        </ResultCard>
      )}

      {status === "unavailable" && (
        <ResultCard title="ADR Prediction">
          <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">
            No prediction available.
          </p>
          <button className="btn-secondary mt-4" onClick={loadPrediction}>
            Retry
          </button>
        </ResultCard>
      )}

      {status === "success" && prediction && (
        <ResultCard title="ADR Prediction">
          <div className="mt-4 grid gap-5 sm:grid-cols-2">
            <Metric label="Predicted ADR Risk (%)">
              <span className="text-4xl font-bold text-primary">
                {prediction.predictedAdrRisk}%
              </span>
            </Metric>
            <Metric label="Risk Category">
              <InteractionSeverityBadge severity={riskCategory} />
            </Metric>
            <Metric label="Prediction Confidence">
              {prediction.confidence}%
            </Metric>
            <Metric label="Confidence Interval">
              {prediction.confidenceInterval?.lower}% -{" "}
              {prediction.confidenceInterval?.upper}%
            </Metric>
          </div>
          <ExplainToggle reasons={prediction.explanations || []} />
          {/* Reserved for future ML metadata and feature-importance outputs. */}
        </ResultCard>
      )}

      <div className="flex flex-wrap justify-between gap-3">
        <button className="btn-secondary" onClick={onBack}>
          <ChevronLeft size={16} />
          Clinical Safety Analysis
        </button>
        <button
          className="btn-primary"
          onClick={onNext}
          disabled={status !== "success"}
        >
          Recommended Safer Alternatives
          <ChevronRight size={16} />
        </button>
      </div>
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
        Select the standardized term used for DrugBank/FAERS matching.
      </p>
    </>
  );
}

function Results({
  patient,
  visit,
  historical,
  stage,
  onStageChange,
  onSaveAdr,
  onSaveNotes,
  onAddPatient,
}) {
  const [notes, setNotes] = useState(visit.doctorNotes || "");
  const risk = visit.riskResult;
  const confidence = visit.confidence;
  const severity = normalizeSeverity(risk?.severity, risk?.score);
  const reliability = reliabilityFromConfidence(
    confidence?.reliabilityLabel,
    confidence?.pct,
  );

  useEffect(
    () => setNotes(visit.doctorNotes || ""),
    [visit.id, visit.doctorNotes],
  );

  const insights = [
    ["Prediction", getDDIPredictionReasons(severity)],
    [
      "Confidence",
      [
        `Prediction confidence is ${confidence?.pct ?? 0}%.`,
        "The interval visualizes the uncertainty range.",
      ],
    ],
    [
      "Reliability",
      getReliabilityReasons(confidence?.reliabilityLabel || "Moderate"),
    ],
    ["Alternative Ranking", getRankingReasons()],
    [
      "Feedback Learning",
      visit.feedback
        ? getFeedbackUsageReasons()
        : ["Feedback learning becomes available after follow-up is submitted."],
    ],
  ];

  if (stage === "adr") {
    return (
      <AdrRiskAssessment
        patient={patient}
        visit={visit}
        onBack={() => onStageChange("results")}
        onNext={() => onStageChange("recommendations")}
        onSave={onSaveAdr}
      />
    );
  }

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
                <Metric label="Interaction Risk (%)">{risk?.score ?? 0}%</Metric>
                <Metric label="Interaction Severity">
                  <InteractionSeverityBadge severity={severity} />
                </Metric>
                <Metric label="Confidence">{confidence?.pct ?? 0}%</Metric>
                <Metric label="Reliability">{reliability}</Metric>
                <Metric label="Confidence Interval" className="col-span-2">
                  {confidence?.intervalLow ?? 0}% - {confidence?.intervalHigh ?? 0}%
                </Metric>
              </div>
              <ExplainToggle reasons={getDDIPredictionReasons(severity)} />
            </section>

            <section className="border-t border-border pt-4 dark:border-slate-700">
              <h3 className="text-sm font-bold">Drug–Disease Analysis</h3>
              <div className="mt-3">
                <Metric label="Interaction Risk (%)">42%</Metric>
              </div>
              <ExplainToggle reasons={getDrugDiseaseReasons()} />
            </section>

            <section className="border-t border-border pt-4 dark:border-slate-700">
              <h3 className="text-sm font-bold">Drug–Allergy Analysis</h3>
              <div className="mt-3">
                <Metric label="Interaction Risk (%)">18%</Metric>
              </div>
              <ExplainToggle reasons={getDrugAllergyReasons()} />
            </section>

            <section className="rounded-lg border border-primary/20 bg-primary/5 p-4">
              <h3 className="text-sm font-bold">Overall Clinical Risk</h3>
              <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
                <Metric label="Overall Risk (%)">{risk?.score ?? 0}%</Metric>
                <Metric label="Confidence">{confidence?.pct ?? 0}%</Metric>
              </div>
              <ExplainToggle reasons={getOverallClinicalRiskReasons()} />
            </section>
          </div>
        </ResultCard>

        <ResultCard title="Conformal Reliability">
          <div className="mt-4 flex items-center justify-between gap-4">
            <span className="text-sm text-slate-600 dark:text-slate-300">
              Confidence interval
            </span>
            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">
              {confidence?.reliabilityLabel}
            </span>
          </div>
          <RangeBar
            low={confidence?.intervalLow}
            high={confidence?.intervalHigh}
          />
          <p className="mt-2 text-xs text-slate-500">
            {confidence?.intervalLow}% - {confidence?.intervalHigh}%
          </p>
          <ExplainToggle
            reasons={getReliabilityReasons(
              confidence?.reliabilityLabel || "Moderate",
            )}
          />
        </ResultCard>
      </div>

          <div className="flex flex-wrap justify-end gap-3">
            <button
              type="button"
              onClick={() => onStageChange("adr")}
              className="btn-primary"
            >
              Continue to ADR Assessment
              <ChevronRight size={16} />
            </button>
          </div>
        </>
      )}

      {stage === "recommendations" && (
        <>
      <ResultCard title="Recommended Safer Alternatives">
        <div className="mt-4 space-y-4">
          {(visit.recommendations || []).map((recommendation, index) => {
            const alternativeSeverity = severityFromRisk(
              recommendation.riskPct,
            );
            const alternativeReliability = reliabilityFromConfidence(
              null,
              recommendation.confidencePct,
            );
            return (
              <div
                className="rounded-lg bg-slate-50 p-3 dark:bg-slate-700/50"
                key={`${recommendation.drug}-${index}`}
              >
                <strong>
                  {index + 1}. {recommendation.drug}
                </strong>
                <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
                  <Metric label="Interaction Severity">
                    <InteractionSeverityBadge severity={alternativeSeverity} />
                  </Metric>
                  <Metric label="Predicted Interaction Risk">
                    {recommendation.riskPct}%
                  </Metric>
                  <Metric label="Prediction Confidence">
                    {recommendation.confidencePct}%
                  </Metric>
                  <Metric label="Reliability">{alternativeReliability}</Metric>
                  <Metric label="Drug–Disease Risk">42%</Metric>
                  <Metric label="Drug–Allergy Risk">18%</Metric>
                  <Metric label="Confidence Interval" className="col-span-2">
                    {recommendation.intervalLow}% -{" "}
                    {recommendation.intervalHigh}%
                  </Metric>
                </div>
                <RangeBar
                  low={recommendation.intervalLow}
                  high={recommendation.intervalHigh}
                />
              </div>
            );
          })}
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
              const severity = severityFromRisk(recommendation.riskPct);
              const reliability = reliabilityFromConfidence(
                null,
                recommendation.confidencePct,
              );
              return (
                <div
                  className="rounded-lg bg-slate-50 p-3 dark:bg-slate-700/50"
                  key={`${recommendation.drug}-${index}`}
                >
                  <strong>
                    {index + 1}. {recommendation.drug}
                  </strong>
                  <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4">
                    <Metric label="Interaction Severity">
                      <InteractionSeverityBadge severity={severity} />
                    </Metric>
                    <Metric label="Predicted Interaction Risk">
                      {recommendation.riskPct}%
                    </Metric>
                    <Metric label="Prediction Confidence">
                      {recommendation.confidencePct}%
                    </Metric>
                    <Metric label="Reliability">{reliability}</Metric>
                    <Metric label="Drug–Disease Risk">42%</Metric>
                    <Metric label="Drug–Allergy Risk">18%</Metric>
                    <Metric label="Confidence Interval" className="col-span-2">
                      {recommendation.intervalLow}% -{" "}
                      {recommendation.intervalHigh}%
                    </Metric>
                  </div>
                  <RangeBar
                    low={recommendation.intervalLow}
                    high={recommendation.intervalHigh}
                  />
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
    ["adr", "ADR Risk Assessment"],
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
    saveAdrPrediction,
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
    adr: activeVisit?.status === "completed",
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
        adr: activeVisit.status === "completed",
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
    step === "results" || step === "adr" || step === "recommendations" ? (
      <Results
        patient={patient}
        visit={activeVisit}
        historical={historical}
        stage={step}
        onStageChange={(target) =>
          target === "results" ? goToVisitedStep(target) : advanceToStep(target)
        }
        onSaveAdr={(adrPrediction) =>
          saveAdrPrediction(patient.id, activeVisit.id, adrPrediction)
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
