// Research configuration: these project-level ranking hyperparameters are not
// claimed to be universally clinically validated.
export const RANKING_WEIGHTS = Object.freeze({
  adjustedLightgbmRisk: 0.50,
  ddiRisk: 0.30,
  drugDiseaseRisk: 0.20,
});

export const RANKING_WEIGHT_TOTAL = Object.values(RANKING_WEIGHTS).reduce((total, value) => total + value, 0);

if (Math.abs(RANKING_WEIGHT_TOTAL - 1) > Number.EPSILON) {
  throw new Error("VitaNexus-RX ranking weights must sum to exactly 1.00.");
}

// These ordinal mappings only normalize existing DDInter/DrugCentral evidence
// for the transparent ranking calculation. Missing evidence remains null.
export const DDI_RISK_BY_SEVERITY = Object.freeze({ MINOR: 0.10, MODERATE: 0.50, MAJOR: 0.90 });
export const DRUG_DISEASE_RISK_BY_ASSESSMENT = Object.freeze({ LOW: 0.10, MODERATE: 0.50, HIGH: 0.90 });

export const normalizeDdiRisk = (severity) => DDI_RISK_BY_SEVERITY[severity] ?? (severity === "NOT_EVALUATED" ? null : 0);
export const normalizeDrugDiseaseRisk = (assessment) => DRUG_DISEASE_RISK_BY_ASSESSMENT[assessment] ?? (assessment === "NOT_EVALUATED" ? null : 0);
export const normalizeProbability = (value) => Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;

export const isSevereDdi = (severity) => severity === "MAJOR";
export const isSeriousDrugDiseaseRestriction = (assessment) => assessment === "HIGH";

export const rankingConfig = Object.freeze({
  configId: "vitanexus-safety-aware-50-30-20-1.0.0",
  weights: RANKING_WEIGHTS,
  weightsStatus: "CONFIGURED_RESEARCH_HYPERPARAMETERS",
  candidateSource: "DrugCentral indication relationships",
  formula: "0.50 × uncertainty-adjusted LightGBM risk + 0.30 × DDI risk + 0.20 × drug-disease risk",
  missingDataPolicy: "requires_review",
});
