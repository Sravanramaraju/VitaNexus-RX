export const getDrugSelectionReasons = () => ['Brand recognized successfully.', 'Mapped to generic drug before analysis.']
export const getDDIPredictionReasons = (severity) => [
  `The predicted interaction is classified as ${severity.toLowerCase()}.`,
  'Both medicines may affect the same clinical pathway.',
  'Similar combinations informed this prediction.',
  'Prediction confidence is included with the result.',
]
export const getDrugDiseaseReasons = () => [
  'This placeholder assessment represents disease-related safety considerations.',
  'Patient-specific conditions can be incorporated when clinical data is connected.',
]
export const getOverallClinicalRiskReasons = () => [
  'Overall clinical risk summarizes the currently available safety signals.',
  'Additional patient-specific inputs can refine this assessment when connected.',
]
export const getReliabilityReasons = (label) => [
  `Reliability is classified as ${label.toLowerCase()}.`,
  'Similar medication combinations were seen during model evaluation.',
  'The confidence interval reflects prediction uncertainty.',
]
export const getRankingReasons = () => ['Lowest predicted interaction.', 'Similar therapeutic purpose.', 'High historical success.', 'Positive physician feedback.']
export const getFeedbackUsageReasons = () => ['Doctor feedback improves future recommendation ranking.', 'Personal identifiers are not used for model decisions.']
