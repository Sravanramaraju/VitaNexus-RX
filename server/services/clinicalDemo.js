import { stableHash } from "../utils.js";
import { clinicalKnowledgeStatus, findPairwiseDrugInteraction } from "../repositories/clinicalKnowledgeRepository.js";
import { adrPredictionProvider } from "./adrPredictionProvider.js";
import { rankRecommendations, recommendationRankingConfig } from "./recommendationRankingService.js";

const ENGINE_VERSION = "vitanexus-demo-rules-1.2.0";
const scoreFrom = (value, min = 0, max = 100) => {
  const hex = stableHash(value).slice(0, 8);
  return min + (Number.parseInt(hex, 16) % (max - min + 1));
};
const category = (score) => (score >= 61 ? "High" : score >= 31 ? "Moderate" : "Low");
const reliability = (confidence) => (confidence >= 85 ? "High" : confidence >= 65 ? "Moderate" : "Low");

export const clinicalSafetyAssessment = ({ consultation, patient }) => {
  const activeMedicines = patient.medications.filter((medicine) => medicine.status === "ACTIVE");
  const interactionFindings = activeMedicines
    .map((medicine) => {
      const rule = findPairwiseDrugInteraction(consultation.candidateGeneric, medicine.genericName);
      return rule && {
        medication: medicine.genericName,
        riskPercentage: rule.riskPercentage,
        interactionSeverity: rule.interactionSeverity,
        reason: rule.explanation,
        source: rule.source,
        datasetVersion: rule.datasetVersion,
        dataStatus: rule.dataStatus,
      };
    })
    .filter(Boolean);
  const ddiRisk = interactionFindings.length
    ? Math.max(...interactionFindings.map((finding) => finding.riskPercentage))
    : scoreFrom({ candidate: consultation.candidateGeneric, activeMedicines: activeMedicines.map((medicine) => medicine.genericName) }, 4, 25);
  const diseaseRisk = patient.conditions.length ? scoreFrom(patient.conditions.map((item) => item.display), 8, 38) : 3;
  const overallRisk = Math.max(ddiRisk, diseaseRisk);
  const confidence = scoreFrom({ consultation: consultation.id, type: "confidence" }, 68, 94);
  const intervalWidth = Math.max(3, Math.round((100 - confidence) / 2));
  const confidenceInterval = { lower: Math.max(0, confidence - intervalWidth), upper: Math.min(100, confidence + intervalWidth) };
  const uncertainty = {
    confidence,
    interval: confidenceInterval,
    label: reliability(confidence),
    status: "DEVELOPMENT_PLACEHOLDER_NOT_CONFORMAL",
    explanation: "This hash-derived display value is not calibrated confidence, a prediction interval, or conformal prediction.",
  };

  return {
    status: "DEMONSTRATION_ONLY",
    dataStatus: "PARTIALLY_IMPLEMENTED_DEMONSTRATION",
    disclaimer: "This deterministic demonstration result is not clinically validated and must not be used for patient care.",
    engineVersion: ENGINE_VERSION,
    assessedAt: new Date().toISOString(),
    drugDrug: {
      riskPercentage: ddiRisk,
      interactionSeverity: category(ddiRisk),
      category: category(ddiRisk),
      findings: interactionFindings,
      confidence: uncertainty.confidence,
      confidenceInterval,
      reliability: uncertainty.label,
      uncertaintyStatus: uncertainty.status,
      explanations: interactionFindings.length
        ? interactionFindings.map((finding) => finding.reason)
        : ["No static demonstration interaction rule matched the active medication list; the displayed low risk is a development placeholder, not a negative interaction finding."],
      knowledgeSource: clinicalKnowledgeStatus.drugDrug,
    },
    drugDisease: {
      riskPercentage: diseaseRisk,
      category: category(diseaseRisk),
      dataStatus: "DEVELOPMENT_PLACEHOLDER",
      explanations: patient.conditions.length
        ? ["No drug-disease knowledge dataset is integrated; this display value is a development placeholder."]
        : ["No active conditions are recorded; no drug-disease knowledge assessment was performed."],
      knowledgeSource: clinicalKnowledgeStatus.drugDisease,
    },
    overall: { riskPercentage: overallRisk, category: category(overallRisk), dataStatus: "DEVELOPMENT_PLACEHOLDER" },
    conformalReliability: uncertainty,
  };
};

export const adrPrediction = async (input) => adrPredictionProvider.predict(input);

export const recommendations = ({ consultation, safety, adr }) => rankRecommendations({ consultation, safety, adr });

export const versions = {
  ENGINE_VERSION,
  MODEL_VERSION: adrPredictionProvider.modelVersion,
  MODEL_NAME: adrPredictionProvider.modelName,
  ADR_PROVIDER_NAME: adrPredictionProvider.providerName,
  RANKING_CONFIG_ID: recommendationRankingConfig.configId,
};

export { recommendationRankingConfig };
