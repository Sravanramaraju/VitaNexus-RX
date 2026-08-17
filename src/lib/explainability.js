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
export const getRankingReasons = () => ['Candidate drugs are identified from DrugCentral indication relationships.', 'Candidate-specific suitability is not represented as a synthetic risk percentage.', 'Allergy information is not used for ranking.']
export const getFeedbackUsageReasons = () => ['Doctor feedback improves future recommendation ranking.', 'Personal identifiers are not used for model decisions.']
