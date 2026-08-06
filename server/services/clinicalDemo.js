import { stableHash } from "../utils.js";

const ENGINE_VERSION = "vitanexus-demo-rules-1.0.0";
const MODEL_VERSION = "vitanexus-demo-adr-1.0.0";

const scoreFrom = (value, min = 0, max = 100) => {
  const hex = stableHash(value).slice(0, 8);
  return min + (Number.parseInt(hex, 16) % (max - min + 1));
};
const category = (score) => (score >= 61 ? "High" : score >= 31 ? "Moderate" : "Low");
const reliability = (confidence) => (confidence >= 85 ? "High" : confidence >= 65 ? "Moderate" : "Low");
const clean = (value = "") => value.toLowerCase().replace(/[^a-z]/g, "");

const pairRule = (candidate, medicine) => {
  const a = clean(candidate);
  const b = clean(medicine);
  const pair = [a, b].sort().join("|");
  const rules = {
    "aspirin|warfarin": [88, "Concurrent use may increase bleeding risk; clinician review is required."],
    "ibuprofen|warfarin": [84, "Concurrent use may increase bleeding risk; clinician review is required."],
    "fluoxetine|tramadol": [82, "Concurrent use may increase serotonin-toxicity risk; clinician review is required."],
    "clarithromycin|simvastatin": [80, "Concurrent use may increase statin exposure; clinician review is required."],
  };
  return rules[pair] || null;
};

export const clinicalSafetyAssessment = ({ consultation, patient }) => {
  const activeMedicines = patient.medications.filter((medicine) => medicine.status === "ACTIVE");
  const interactionFindings = activeMedicines
    .map((medicine) => {
      const rule = pairRule(consultation.candidateGeneric, medicine.genericName);
      return rule && { medication: medicine.genericName, risk: rule[0], reason: rule[1] };
    })
    .filter(Boolean);
  const ddiRisk = interactionFindings.length
    ? Math.max(...interactionFindings.map((finding) => finding.risk))
    : scoreFrom({ candidate: consultation.candidateGeneric, activeMedicines: activeMedicines.map((m) => m.genericName) }, 4, 25);
  const diseaseRisk = patient.conditions.length ? scoreFrom(patient.conditions.map((item) => item.display), 8, 38) : 3;
  const allergyRisk = patient.allergies.some((allergy) => clean(allergy.display).includes(clean(consultation.candidateGeneric))) ? 90 : patient.allergies.length ? 12 : 2;
  const overallRisk = Math.max(ddiRisk, diseaseRisk, allergyRisk);
  const confidence = scoreFrom({ consultation: consultation.id, type: "confidence" }, 68, 94);
  const interval = Math.max(3, Math.round((100 - confidence) / 2));
  return {
    status: "DEMONSTRATION_ONLY",
    disclaimer: "This deterministic demonstration result is not clinically validated and must not be used for patient care.",
    engineVersion: ENGINE_VERSION,
    assessedAt: new Date().toISOString(),
    drugDrug: { riskPercentage: ddiRisk, category: category(ddiRisk), findings: interactionFindings, explanations: interactionFindings.length ? interactionFindings.map((f) => f.reason) : ["No demonstration interaction rule matched the active medication list."] },
    drugDisease: { riskPercentage: diseaseRisk, category: category(diseaseRisk), explanations: patient.conditions.length ? ["Demonstration-only disease context check; authoritative contraindication knowledge is not installed."] : ["No active conditions are recorded."] },
    drugAllergy: { riskPercentage: allergyRisk, category: category(allergyRisk), explanations: allergyRisk >= 90 ? ["The recorded allergy text overlaps with the candidate medicine; do not rely on this text match for clinical care."] : ["Demonstration-only allergy context check; authoritative allergy reconciliation is not installed."] },
    overall: { riskPercentage: overallRisk, category: category(overallRisk) },
    conformalReliability: { confidence, interval: { lower: Math.max(0, confidence - interval), upper: Math.min(100, confidence + interval) }, label: reliability(confidence) },
  };
};

export const adrPrediction = ({ consultation, patient }) => {
  const activeCount = patient.medications.filter((item) => item.status === "ACTIVE").length;
  const risk = Math.min(78, 8 + activeCount * 7 + patient.age / 6 + scoreFrom(consultation.candidateGeneric, 0, 18));
  const confidence = scoreFrom({ consultation: consultation.id, type: "adr" }, 66, 91);
  const width = Math.max(3, Math.round((100 - confidence) / 2));
  return {
    predictedAdrRisk: Math.round(risk),
    riskCategory: category(risk),
    confidence,
    confidenceInterval: { lower: Math.max(0, Math.round(risk - width)), upper: Math.min(100, Math.round(risk + width)) },
    predictionStatus: "success",
    status: "DEMONSTRATION_ONLY",
    disclaimer: "This deterministic demonstration prediction is not a medical-device model and must not guide treatment.",
    modelVersion: MODEL_VERSION,
    generatedAt: new Date().toISOString(),
    explanations: ["The demonstration calculation uses only age, active-medication count, and candidate-medicine text.", "Disease information is intentionally excluded from this ADR contract.", "A validated, governed model must replace this demonstration result before clinical use."],
  };
};

const alternatives = ["Paracetamol", "Cetirizine", "Pantoprazole", "Amoxicillin", "Losartan", "Metformin"];
export const recommendations = ({ consultation, safety, adr }) =>
  alternatives
    .filter((drug) => clean(drug) !== clean(consultation.candidateGeneric))
    .map((drug) => {
      const riskPct = scoreFrom({ drug, candidate: consultation.candidateGeneric, safety: safety.overall.riskPercentage }, 8, 48);
      return { drug, rank: 0, riskPct, category: category(riskPct), confidencePct: adr.confidence, intervalLow: Math.max(0, riskPct - 8), intervalHigh: Math.min(100, riskPct + 8), reasons: ["Demonstration-only alternative ranking; formulary and patient-specific suitability are not evaluated.", "Hard clinical exclusions require a validated knowledge base."] };
    })
    .sort((a, b) => a.riskPct - b.riskPct)
    .slice(0, 3)
    .map((item, index) => ({ ...item, rank: index + 1 }));

export const versions = { ENGINE_VERSION, MODEL_VERSION };
