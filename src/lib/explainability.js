export const getDrugSelectionReasons = () => ['Brand recognized successfully.', 'Mapped to generic drug before analysis.']
export const getDDIPredictionReasons = (severity) => [
  `The DDInter 2.0 interaction is classified as ${severity.toLowerCase()}.`,
  'The classification is an ordinal dataset severity, not a patient-specific probability.',
  'Review the source relationship and the full medication context before prescribing.',
]
export const getDrugDiseaseReasons = () => [
  'DrugCentral relationship evidence is evaluated against recorded existing conditions.',
  'The assessment is HIGH, MODERATE, LOW, or NOT_EVALUATED; it is not a probability.',
]
export const getOverallClinicalRiskReasons = () => [
  'The overall assessment summarizes DDInter severity and DrugCentral drug-disease evidence.',
  'Allergy information remains visible to the clinician but is not an automated input.',
]
export const getRankingReasons = () => ['Candidates come from DrugCentral relationships for the selected indication only.', 'Safety gates exclude major DDInter interactions and high drug-disease restrictions before scoring.', 'The safety-aware score combines 50% uncertainty-adjusted LightGBM risk, 30% DDInter risk, and 20% DrugCentral drug-disease risk.', 'Conformal reliability modifies the LightGBM interpretation and has no separate ranking weight.', 'Allergy information is clinician reference only and is not used for ranking.']
export const getFeedbackUsageReasons = () => ['Doctor feedback improves future recommendation ranking.', 'Personal identifiers are not used for model decisions.']
