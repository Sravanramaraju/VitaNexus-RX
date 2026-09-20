// Research configuration: these project-level ranking hyperparameters are not
// claimed to be universally clinically validated.
export const RANKING_WEIGHTS = Object.freeze({
  adjustedLightgbmRisk: 0.50,
  ddiRisk: 0.30,
  drugDiseaseRisk: 0.20,
});

export const DEGRADED_ADR_RANKING_WEIGHTS = Object.freeze({
  adjustedLightgbmRisk: 0.25,
  ddiRisk: 0.30,
  drugDiseaseRisk: 0.20,
  coveragePenalty: 0.25,
});

export const COVERAGE_PENALTY_RISK = 1.00;

export const RANKING_WEIGHT_TOTAL = Object.values(RANKING_WEIGHTS).reduce((total, value) => total + value, 0);

if (Math.abs(RANKING_WEIGHT_TOTAL - 1) > Number.EPSILON) {
  throw new Error("VitaNexus-RX ranking weights must sum to exactly 1.00.");
}

// These ordinal mappings only normalize existing DDInter/DrugCentral evidence
// for the transparent ranking calculation. Missing evidence remains null.
// The project-agreed DDInter evidence order is:
// documented MINOR/LOW, successful lookup with no documented pair,
// documented MODERATE, documented MAJOR/HIGH.
// A successful empty lookup is therefore not treated as zero risk: absence of
// a DDInter record is less reassuring than a documented minor interaction, but
// it remains eligible and is safer than a documented moderate interaction.
export const DDI_RISK_BY_SEVERITY = Object.freeze({
  MINOR: 0.10,
  NO_DOCUMENTED_INTERACTION: 0.30,
  MODERATE: 0.50,
  MAJOR: 0.90,
});
export const DRUG_DISEASE_RISK_BY_ASSESSMENT = Object.freeze({
  LOW: 0.10,
  NO_DOCUMENTED_RELATIONSHIP: 0.30,
  MODERATE: 0.50,
  HIGH: 0.90,
});

export const normalizeDdiRisk = (severity) => DDI_RISK_BY_SEVERITY[severity] ?? null;
export const normalizeDrugDiseaseRisk = (assessment) => DRUG_DISEASE_RISK_BY_ASSESSMENT[assessment] ?? null;
export const normalizeProbability = (value) => Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;

export const isSevereDdi = (severity) => severity === "MAJOR";
export const isSeriousDrugDiseaseRestriction = (assessment) => assessment === "HIGH";

export const rankingConfig = Object.freeze({
  configId: "vitanexus-safety-aware-degraded-adr-1.2.0",
  weights: RANKING_WEIGHTS,
  degradedAdrWeights: DEGRADED_ADR_RANKING_WEIGHTS,
  coveragePenaltyRisk: COVERAGE_PENALTY_RISK,
  weightsStatus: "CONFIGURED_RESEARCH_HYPERPARAMETERS",
  candidateSource: "DrugCentral indication relationships",
  formula: "Full coverage: 0.50 × uncertainty-adjusted LightGBM risk + 0.30 × DDI risk + 0.20 × drug-disease risk. Degraded ADR coverage: 0.25 × uncertainty-adjusted LightGBM risk + 0.30 × DDI risk + 0.20 × drug-disease risk + 0.25 × coverage penalty.",
  missingDataPolicy: "requires_review",
});
