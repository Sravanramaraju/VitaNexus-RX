import { highestDdiSeverity, highestDiseaseAssessment, normalizeClinicalTerm } from "../repositories/clinicalKnowledgeRepository.js";
import { adrPredictionProvider, buildAdrPredictionInput } from "./adrPredictionProvider.js";
import {
  isSeriousDrugDiseaseRestriction,
  isSevereDdi,
  normalizeDdiRisk,
  normalizeDrugDiseaseRisk,
  normalizeProbability,
  rankingConfig,
} from "./rankingConfig.js";

export const RANKING_ENGINE_VERSION = rankingConfig.configId;
export const recommendationRankingConfig = rankingConfig;

export const buildRecommendationInput = ({ consultation, patient, safety, candidates = [], modelVersions = {} }) => ({
  consultationId: consultation.id,
  indication: {
    id: consultation.indicationId,
    name: consultation.indication,
    normalized: consultation.indicationNormalized,
    source: consultation.indicationSource,
    datasetVersion: consultation.indicationDatasetVersion,
  },
  candidateGeneric: consultation.candidateGeneric,
  activeMedicines: patient.medications
    .filter((medicine) => medicine.status === "ACTIVE")
    .map((medicine) => medicine.genericName)
    .sort(),
  conditions: patient.conditions.map((condition) => ({ display: condition.display, code: condition.code || null }))
    .sort((first, second) => first.display.localeCompare(second.display)),
  safety: {
    engineVersion: safety.engineVersion || null,
    drugDrug: { severity: safety.drugDrug?.severity || "NOT_EVALUATED", findings: safety.drugDrug?.findings || [] },
    drugDisease: { assessment: safety.drugDisease?.assessment || "NOT_EVALUATED", findings: safety.drugDisease?.findings || [] },
  },
  candidates,
  versions: { ranking: RANKING_ENGINE_VERSION, ...modelVersions },
});

const ddiTier = (severity) => severity === "MAJOR" ? "HIGH" : severity === "MODERATE" ? "MODERATE" : severity === "MINOR" ? "LOW" : severity === "NO_DOCUMENTED_INTERACTION" ? "NO_DOCUMENTED_INTERACTION" : "NOT_EVALUATED";
const diseaseTier = (assessment) => ["LOW", "NO_DOCUMENTED_RELATIONSHIP", "MODERATE", "HIGH"].includes(assessment) ? assessment : "NOT_EVALUATED";

const candidateSafetyGate = ({ drugDrug, drugDisease }) => {
  if (isSevereDdi(drugDrug.severity)) return { status: "NOT_RECOMMENDED", reasons: ["Excluded from normal ranking because DDInter reports a major interaction."] };
  if (isSeriousDrugDiseaseRestriction(drugDisease.assessment)) return { status: "NOT_RECOMMENDED", reasons: ["Excluded from normal ranking because DrugCentral reports a high/serious drug-disease restriction."] };
  if (!drugDrug.complete || !drugDisease.complete) return { status: "REQUIRES_REVIEW", reasons: ["One or more essential DDInter or DrugCentral evaluations are unavailable; no safety score was inferred."] };
  return { status: "ELIGIBLE", reasons: [] };
};

const evaluateKnownSafety = async ({ candidate, patient, knowledgeRepository }) => {
  const activeMedicines = patient.medications.filter((medicine) => medicine.status === "ACTIVE");
  const interactions = await Promise.all(activeMedicines.map(async (medicine) => {
    const evaluation = await knowledgeRepository.evaluateDdiPair(candidate.genericDrug, medicine.genericName);
    const common = { existingMedication: medicine.genericName, proposedDrug: candidate.genericDrug, source: "DDInter 2.0", lookupCompleted: evaluation.lookupCompleted, candidateResolution: evaluation.candidateResolution, existingResolution: evaluation.existingResolution };
    if (evaluation.status === "DOCUMENTED_INTERACTION") return { ...common, status: "DOCUMENTED_INTERACTION", ...evaluation.interaction };
    if (evaluation.status === "NO_DOCUMENTED_INTERACTION") return { ...common, status: "NO_DOCUMENTED_INTERACTION" };
    return { ...common, status: evaluation.status, issue: evaluation.status === "LOOKUP_FAILED" ? "DDInter lookup failed." : "One or both drug identifiers could not be resolved unambiguously." };
  }));
  const interactionFindings = interactions.filter((item) => item.status === "DOCUMENTED_INTERACTION");
  const ddiComplete = interactions.every((item) => ["DOCUMENTED_INTERACTION", "NO_DOCUMENTED_INTERACTION"].includes(item.status));
  const ddiSeverity = interactionFindings.length ? highestDdiSeverity(interactionFindings.map((finding) => finding.displaySeverity)) : ddiComplete ? "NO_DOCUMENTED_INTERACTION" : "NOT_EVALUATED";

  const diseaseEvaluation = await knowledgeRepository.findDrugDiseaseAssessments(candidate.genericDrug, patient.conditions);
  const diseaseFindings = Array.isArray(diseaseEvaluation) ? diseaseEvaluation : diseaseEvaluation.findings;
  const diseaseResolutions = Array.isArray(diseaseEvaluation) ? [] : diseaseEvaluation.resolutions;
  const diseaseComplete = patient.conditions.length === 0 || (diseaseResolutions.length === patient.conditions.length && diseaseResolutions.every((resolution) => resolution.status === "RESOLVED"));
  const diseaseAssessment = diseaseFindings.length
    ? highestDiseaseAssessment(diseaseFindings.map((finding) => finding.assessment))
    : diseaseComplete
      ? "NO_DOCUMENTED_RELATIONSHIP"
      : "NOT_EVALUATED";

  const drugDrug = {
    severity: ddiSeverity,
    evidenceTier: ddiTier(ddiSeverity),
    complete: ddiComplete,
    evaluations: interactions,
    findings: interactionFindings,
    normalizedRisk: ddiComplete ? (activeMedicines.length ? normalizeDdiRisk(ddiSeverity) ?? 0 : 0) : null,
  };
  const drugDisease = {
    assessment: diseaseAssessment,
    evidenceTier: diseaseTier(diseaseAssessment),
    complete: diseaseComplete,
    findings: diseaseFindings,
    conditionResolutions: diseaseResolutions,
    normalizedRisk: diseaseComplete ? normalizeDrugDiseaseRisk(diseaseAssessment) : null,
  };
  const gate = candidateSafetyGate({ drugDrug, drugDisease });
  return {
    drugDrug,
    drugDisease,
    knownSafetyEvidence: {
      complete: ddiComplete && diseaseComplete,
      label: ddiComplete && diseaseComplete ? "Fully evaluated evidence" : "Requires Clinical Review",
      unresolved: [
        ...interactions.filter((item) => !["DOCUMENTED_INTERACTION", "NO_DOCUMENTED_INTERACTION"].includes(item.status)).map((item) => item.status === "LOOKUP_FAILED" ? `DDInter lookup failed: ${item.proposedDrug} + ${item.existingMedication}` : `DDInter identifier unresolved: ${item.proposedDrug} + ${item.existingMedication}`),
        ...diseaseResolutions.filter((item) => item.status !== "RESOLVED").map((item) => `DrugCentral: ${item.enteredCondition}`),
      ],
    },
    gate,
    assessment: gate.status,
    dataStatus: ddiComplete && diseaseComplete ? "FULLY_EVALUATED" : "INCOMPLETE_EVIDENCE",
  };
};

const isMlAvailable = (candidate) => candidate.ml?.status === "ok" && normalizeProbability(candidate.ml?.overall?.adjustedRisk) !== null;

const scoreCandidate = (candidate) => {
  if (candidate.gate.status !== "ELIGIBLE") {
    return {
      ...candidate,
      status: candidate.gate.status,
      assessment: candidate.gate.status,
      reasons: candidate.gate.reasons,
    };
  }
  if (!isMlAvailable(candidate)) {
    const inputCorrectionNeeded = candidate.ml?.status === "OUT_OF_VOCABULARY";
    return {
      ...candidate,
      status: inputCorrectionNeeded ? "INPUT_CORRECTION_NEEDED" : "RANKING_UNAVAILABLE",
      assessment: inputCorrectionNeeded ? "INPUT_CORRECTION_NEEDED" : "RANKING_UNAVAILABLE",
      reasons: [
        ...candidate.gate.reasons,
        inputCorrectionNeeded
          ? "The DDInter and DrugCentral safety gate passed, but LightGBM could not rank this candidate because a consultation input is outside its trained vocabulary."
          : "The DDInter and DrugCentral safety gate passed, but LightGBM ranking is currently unavailable; no ranking score was inferred.",
      ],
    };
  }
  const adjustedRisk = normalizeProbability(candidate.ml.overall.adjustedRisk);
  const ddiRisk = candidate.drugDrug.normalizedRisk;
  const drugDiseaseRisk = candidate.drugDisease.normalizedRisk;
  if (adjustedRisk === null || ddiRisk === null || drugDiseaseRisk === null) {
    return { ...candidate, status: "REQUIRES_REVIEW", assessment: "REQUIRES_REVIEW", reasons: [...candidate.gate.reasons, "An essential ranking dimension is unavailable; no score was inferred."] };
  }
  const finalRiskScore = (
    rankingConfig.weights.adjustedLightgbmRisk * adjustedRisk
    + rankingConfig.weights.ddiRisk * ddiRisk
    + rankingConfig.weights.drugDiseaseRisk * drugDiseaseRisk
  );
  return {
    ...candidate,
    status: "RECOMMENDED",
    assessment: "RECOMMENDED",
    finalRiskScore,
    safetyScore: (1 - finalRiskScore) * 100,
    components: {
      lightgbmAdjustedRisk: adjustedRisk,
      lightgbmWeight: rankingConfig.weights.adjustedLightgbmRisk,
      ddiRisk,
      ddiWeight: rankingConfig.weights.ddiRisk,
      drugDiseaseRisk,
      drugDiseaseWeight: rankingConfig.weights.drugDiseaseRisk,
    },
    reasons: [
      "Candidate identified from a DrugCentral same-indication relationship.",
      "Score combines uncertainty-adjusted LightGBM adverse risk, DDInter risk, and DrugCentral drug-disease risk.",
    ],
  };
};

export const compareRecommendations = (first, second) => {
  const scoreDifference = first.finalRiskScore - second.finalRiskScore;
  if (Math.abs(scoreDifference) > Number.EPSILON) return scoreDifference;
  const adjustedDifference = first.components.lightgbmAdjustedRisk - second.components.lightgbmAdjustedRisk;
  if (Math.abs(adjustedDifference) > Number.EPSILON) return adjustedDifference;
  const ddiDifference = first.components.ddiRisk - second.components.ddiRisk;
  if (Math.abs(ddiDifference) > Number.EPSILON) return ddiDifference;
  const diseaseDifference = first.components.drugDiseaseRisk - second.components.drugDiseaseRisk;
  if (Math.abs(diseaseDifference) > Number.EPSILON) return diseaseDifference;
  return first.drug.localeCompare(second.drug);
};

const rankExplanation = (candidate) => `Safety-aware ranking: ${(candidate.components.lightgbmWeight * 100).toFixed(0)}% uncertainty-adjusted LightGBM risk, ${(candidate.components.ddiWeight * 100).toFixed(0)}% DDInter risk, and ${(candidate.components.drugDiseaseWeight * 100).toFixed(0)}% DrugCentral drug-disease risk. Conformal information modifies the LightGBM interpretation and has no independent weight.`;

export const rankRecommendations = async ({ consultation, patient, knowledgeRepository, requestId, provider = adrPredictionProvider }) => {
  const candidates = await knowledgeRepository.findCandidateDrugs(consultation.indication);
  const currentCandidate = normalizeClinicalTerm(consultation.candidateGeneric);
  const alternatives = candidates.filter((candidate) => normalizeClinicalTerm(candidate.genericDrug) !== currentCandidate);
  const knownEvaluations = await Promise.all(alternatives.map(async (candidate) => ({
    drug: candidate.genericDrug,
    indicationRelationship: candidate.relationship,
    evidence: candidate.evidence,
    source: candidate.source,
    datasetVersion: candidate.datasetVersion,
    ...await evaluateKnownSafety({ candidate, patient, knowledgeRepository }),
  })));
  const mlEligible = knownEvaluations.filter((candidate) => candidate.gate.status === "ELIGIBLE");
  const mlResults = await provider.predictBatch(mlEligible.map((candidate, index) => buildAdrPredictionInput({
    consultation,
    patient,
    requestId: `${requestId}:candidate:${index}`,
    candidateGeneric: candidate.drug,
  })));
  const resultByDrug = new Map(mlEligible.map((candidate, index) => [candidate.drug, mlResults[index]]));
  const assessed = knownEvaluations.map((candidate) => scoreCandidate({ ...candidate, ml: resultByDrug.get(candidate.drug) || null }));
  const recommended = assessed.filter((candidate) => candidate.status === "RECOMMENDED").sort(compareRecommendations).map((candidate, index) => ({
    ...candidate,
    rank: index + 1,
    ranking: { engineVersion: RANKING_ENGINE_VERSION, formula: rankingConfig.formula, explanation: rankExplanation(candidate) },
  }));
  const flagged = assessed.filter((candidate) => candidate.status !== "RECOMMENDED").sort((first, second) => first.drug.localeCompare(second.drug)).map((candidate) => ({ ...candidate, rank: null }));
  return [...recommended, ...flagged];
};
