import { highestDdiSeverity, highestDiseaseAssessment, normalizeClinicalTerm } from "../repositories/clinicalKnowledgeRepository.js";
import { adrPredictionProvider, buildAdrPredictionInput } from "./adrPredictionProvider.js";

export const RANKING_ENGINE_VERSION = "vitanexus-lexicographic-p1-p2-p3-1.0.0";
export const recommendationRankingConfig = Object.freeze({
  configId: RANKING_ENGINE_VERSION,
  status: "ML_ENHANCED_DATASET_BACKED_EVALUATION",
  weightsStatus: "NOT_APPLICABLE_LEXICOGRAPHIC",
  candidateSource: "DrugCentral indication relationships",
  priorities: [
    "P1 known DDInter/DrugCentral safety tier and evidence completeness",
    "P2 lower 90% bootstrap upper bound",
    "P3 conformal prediction-set preference",
    "P4 canonical drug name",
  ],
});

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
  conditions: patient.conditions.map((condition) => ({ display: condition.display, code: condition.code || null })).sort((first, second) => first.display.localeCompare(second.display)),
  safety: {
    engineVersion: safety.engineVersion || null,
    drugDrug: { severity: safety.drugDrug?.severity || "NOT_EVALUATED", findings: safety.drugDrug?.findings || [] },
    drugDisease: { assessment: safety.drugDisease?.assessment || "NOT_EVALUATED", findings: safety.drugDisease?.findings || [] },
    overall: safety.overall,
  },
  candidates,
  versions: { ranking: RANKING_ENGINE_VERSION, ...modelVersions },
});

const ddiTier = (severity) => severity === "MAJOR" ? "HIGH" : severity === "MODERATE" ? "MODERATE" : severity === "MINOR" ? "LOW" : "NOT_EVALUATED";
const diseaseTier = (assessment) => ["LOW", "MODERATE", "HIGH"].includes(assessment) ? assessment : "NOT_EVALUATED";
const tierOrder = { LOW: 0, MODERATE: 1, HIGH: 2, NOT_EVALUATED: 3 };
const conformalOrder = (predictionSet = []) => {
  const normalized = [...predictionSet].sort().join("|");
  if (normalized === "NO_DOCUMENTED_SERIOUS_OUTCOME") return 0;
  if (normalized === "NO_DOCUMENTED_SERIOUS_OUTCOME|SERIOUS_OUTCOME") return 1;
  if (normalized === "SERIOUS_OUTCOME") return 2;
  return 3;
};
const isMlAvailable = (candidate) => ["ok", "DEGRADED_COVERAGE"].includes(candidate.ml?.status) && Number.isFinite(candidate.ml?.overall?.conservativeUpperBound);

export const compareRecommendations = (first, second) => {
  const firstTier = tierOrder[first.knownSafetyEvidence.tier] ?? tierOrder.NOT_EVALUATED;
  const secondTier = tierOrder[second.knownSafetyEvidence.tier] ?? tierOrder.NOT_EVALUATED;
  if (firstTier !== secondTier) return firstTier - secondTier;
  if (first.knownSafetyEvidence.complete !== second.knownSafetyEvidence.complete) return first.knownSafetyEvidence.complete ? -1 : 1;
  const firstMl = isMlAvailable(first);
  const secondMl = isMlAvailable(second);
  if (firstMl !== secondMl) return firstMl ? -1 : 1;
  if (firstMl && secondMl) {
    const upperDifference = first.ml.overall.conservativeUpperBound - second.ml.overall.conservativeUpperBound;
    if (Math.abs(upperDifference) > Number.EPSILON) return upperDifference;
    const conformalDifference = conformalOrder(first.ml.overall.conformal.predictionSet) - conformalOrder(second.ml.overall.conformal.predictionSet);
    if (conformalDifference) return conformalDifference;
  }
  return first.drug.localeCompare(second.drug);
};

const worstTier = (...tiers) => tiers.reduce((worst, tier) => (tierOrder[tier] > tierOrder[worst] ? tier : worst), "LOW");

const evaluateKnownSafety = async ({ candidate, patient, knowledgeRepository }) => {
  const activeMedicines = patient.medications.filter((medicine) => medicine.status === "ACTIVE");
  const candidateDdiKnown = activeMedicines.length ? await knowledgeRepository.hasDdiDrugEvidence(candidate.genericDrug) : true;
  const interactions = await Promise.all(activeMedicines.map(async (medicine) => {
    const [relationship, existingKnown] = await Promise.all([
      knowledgeRepository.findPairwiseDrugInteraction(candidate.genericDrug, medicine.genericName),
      knowledgeRepository.hasDdiDrugEvidence(medicine.genericName),
    ]);
    if (relationship) return { status: "DATASET_MATCHED", existingMedication: medicine.genericName, proposedDrug: candidate.genericDrug, ...relationship };
    if (candidateDdiKnown && existingKnown) return { status: "NO_INTERACTION_DETECTED", existingMedication: medicine.genericName, proposedDrug: candidate.genericDrug, source: "DDInter 2.0" };
    return { status: "UNRESOLVED", existingMedication: medicine.genericName, proposedDrug: candidate.genericDrug, source: "DDInter 2.0" };
  }));
  const interactionFindings = interactions.filter((item) => item.status === "DATASET_MATCHED");
  const ddiSeverity = highestDdiSeverity(interactionFindings.map((finding) => finding.displaySeverity));
  const ddiComplete = interactions.every((item) => item.status !== "UNRESOLVED");
  const ddiEvidenceTier = interactionFindings.length ? ddiTier(ddiSeverity) : ddiComplete ? "LOW" : "NOT_EVALUATED";

  const diseaseEvaluation = await knowledgeRepository.findDrugDiseaseAssessments(candidate.genericDrug, patient.conditions);
  const diseaseFindings = Array.isArray(diseaseEvaluation) ? diseaseEvaluation : diseaseEvaluation.findings;
  const diseaseResolutions = Array.isArray(diseaseEvaluation) ? [] : diseaseEvaluation.resolutions;
  const diseaseAssessment = highestDiseaseAssessment(diseaseFindings.map((finding) => finding.assessment));
  const diseaseComplete = patient.conditions.length === 0 || (diseaseResolutions.length === patient.conditions.length && diseaseResolutions.every((resolution) => resolution.status === "RESOLVED"));
  const diseaseEvidenceTier = diseaseFindings.length ? diseaseTier(diseaseAssessment) : diseaseComplete ? "LOW" : "NOT_EVALUATED";
  const knownTier = worstTier(ddiEvidenceTier, diseaseEvidenceTier);
  const complete = ddiComplete && diseaseComplete;
  return {
    drugDrug: { severity: ddiSeverity, evidenceTier: ddiEvidenceTier, complete: ddiComplete, evaluations: interactions, findings: interactionFindings },
    drugDisease: { assessment: diseaseAssessment, evidenceTier: diseaseEvidenceTier, complete: diseaseComplete, findings: diseaseFindings, conditionResolutions: diseaseResolutions },
    knownSafetyEvidence: {
      tier: knownTier,
      complete,
      label: complete ? "Fully evaluated evidence" : "Requires Clinical Review",
      unresolved: [
        ...interactions.filter((item) => item.status === "UNRESOLVED").map((item) => `DDInter: ${item.existingMedication}`),
        ...diseaseResolutions.filter((item) => item.status !== "RESOLVED").map((item) => `DrugCentral: ${item.enteredCondition}`),
      ],
    },
    assessment: knownTier,
    dataStatus: complete ? "FULLY_EVALUATED" : "INCOMPLETE_EVIDENCE",
  };
};

const rankExplanation = (candidate, allCandidates) => {
  const preceding = allCandidates.filter((item) => compareRecommendations(item, candidate) < 0)[0];
  if (!preceding) {
    if (isMlAvailable(candidate)) return `Ranked first in the ${candidate.knownSafetyEvidence.tier} known-safety tier with complete evidence preferred, then the lowest available conservative serious-outcome upper bound.`;
    return `Ranked first by known-safety evidence. ML-enhanced ranking was unavailable and no risk value was substituted.`;
  }
  if (tierOrder[candidate.knownSafetyEvidence.tier] > tierOrder[preceding.knownSafetyEvidence.tier]) return `Ranked below ${preceding.drug} because known DDInter/DrugCentral evidence has priority over ML estimates.`;
  if (!candidate.knownSafetyEvidence.complete) return "Ranked below fully evaluated candidates in the same known-safety tier because material clinical evidence is unresolved.";
  if (!isMlAvailable(candidate)) return "ML evaluation was unavailable; no zero-risk value was imputed, so fully evaluated ML candidates are preferred within this known-safety tier.";
  return "Ranked by the lower 90% bootstrap upper bound within the same known-safety tier; conformal output and canonical name resolve exact ties.";
};

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
  const mlInputs = knownEvaluations.map((candidate, index) => buildAdrPredictionInput({
    consultation, patient, requestId: `${requestId}:candidate:${index}`, candidateGeneric: candidate.drug,
  }));
  const mlResults = await provider.predictBatch(mlInputs);
  const evaluated = knownEvaluations.map((candidate, index) => ({ ...candidate, ml: mlResults[index] }));
  const sorted = [...evaluated].sort(compareRecommendations);
  return sorted.slice(0, 3).map((candidate, index) => ({
    ...candidate,
    rank: index + 1,
    ranking: {
      p1: candidate.knownSafetyEvidence,
      p2: isMlAvailable(candidate) ? candidate.ml.overall.conservativeUpperBound : null,
      p3: isMlAvailable(candidate) ? candidate.ml.overall.conformal.predictionSet : null,
      engineVersion: RANKING_ENGINE_VERSION,
      explanation: rankExplanation(candidate, sorted),
    },
    reasons: [
      "Candidate identified from a DrugCentral indication relationship.",
      "Known DDInter/DrugCentral evidence is evaluated before learned FAERS evidence.",
      isMlAvailable(candidate) ? "The bootstrap upper bound ranks candidates within the same known-safety tier." : "ML-enhanced ranking unavailable; no low or zero risk was inferred.",
    ],
  }));
};
