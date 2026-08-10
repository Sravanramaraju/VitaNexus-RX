import { stableHash } from "../utils.js";

export const recommendationRankingConfig = Object.freeze({
  configId: "vitanexus-demo-ranking-1.0",
  status: "DEMONSTRATION_ONLY",
  weightsStatus: "PROVISIONAL",
  weightsReviewNote: "Ranking weights are provisional and will be reviewed/finalized after completion and evaluation of the ADR ML model.",
  candidateSource: "Static demonstration candidate list",
});

// Only the safety and ADR fields used by the current ranking contract are hashed.
// This excludes clinician-recorded allergies and volatile generation timestamps.
export const buildRecommendationInput = ({ consultation, safety, adr }) => ({
  consultationId: consultation.id,
  candidateGeneric: consultation.candidateGeneric,
  safety: {
    engineVersion: safety.engineVersion || null,
    drugDrug: safety.drugDrug,
    drugDisease: safety.drugDisease,
    overall: safety.overall,
  },
  adr: {
    modelName: adr.modelName || null,
    modelVersion: adr.modelVersion || null,
    inputContractVersion: adr.inputContractVersion || null,
    predictedAdrRisk: adr.predictedAdrRisk,
    riskCategory: adr.riskCategory,
    confidence: adr.confidence,
    confidenceInterval: adr.confidenceInterval,
  },
});

const alternatives = ["Paracetamol", "Cetirizine", "Pantoprazole", "Amoxicillin", "Losartan", "Metformin"];
const clean = (value = "") => value.toLowerCase().replace(/[^a-z]/g, "");
const scoreFrom = (value, min = 0, max = 100) => {
  const hex = stableHash(value).slice(0, 8);
  return min + (Number.parseInt(hex, 16) % (max - min + 1));
};
const category = (score) => (score >= 61 ? "High" : score >= 31 ? "Moderate" : "Low");

// Ranking remains explicitly demonstrative until candidate-specific clinical safety,
// ADR inference, formulary, and hard-exclusion data sources are integrated.
export const rankRecommendations = ({ consultation, safety, adr }) =>
  alternatives
    .filter((drug) => clean(drug) !== clean(consultation.candidateGeneric))
    .map((drug) => {
      const riskPct = scoreFrom(
        { drug, candidate: consultation.candidateGeneric, safety: safety.overall.riskPercentage },
        8,
        48,
      );
      return {
        drug,
        rank: 0,
        riskPct,
        category: category(riskPct),
        confidencePct: adr.confidence,
        intervalLow: Math.max(0, riskPct - 8),
        intervalHigh: Math.min(100, riskPct + 8),
        dataStatus: "DEVELOPMENT_PLACEHOLDER",
        reasons: [
          "Development-placeholder alternative ranking; candidate-specific clinical safety and ADR inference are not integrated.",
          "Formulary, patient-specific suitability, and hard clinical exclusions are not evaluated.",
        ],
      };
    })
    .sort((a, b) => a.riskPct - b.riskPct)
    .slice(0, 3)
    .map((item, index) => ({ ...item, rank: index + 1 }));
