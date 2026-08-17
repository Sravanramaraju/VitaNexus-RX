import { getRankingReasons } from './explainability'

const alternatives = ['Azithromycin', 'Amoxicillin', 'Cetirizine', 'Metformin', 'Losartan', 'Pantoprazole', 'Levosalbutamol', 'Doxycycline']
const choose = (values) => values[Math.floor(Math.random() * values.length)]

// Local presentation fixtures intentionally use ordinal labels only. Production
// data comes from DDInter 2.0 / DrugCentral through the backend API.
export function generateRiskResult() {
  return { severity: choose(['MAJOR', 'MODERATE', 'MINOR']), source: 'DDInter 2.0 (pending API lookup)' }
}

export function generateConfidence() {
  return { status: 'NOT_IMPLEMENTED' }
}

export function generateRecommendations(count = Math.random() > 0.5 ? 2 : 3) {
  return [...alternatives].sort(() => Math.random() - 0.5).slice(0, count).map((drug, index) => ({
    drug,
    rank: index + 1,
    assessment: 'NOT_EVALUATED',
    source: 'DrugCentral (pending API lookup)',
    reasons: getRankingReasons(),
  }))
}

export function generateUpdatedRecommendations(feedback, previousRecommendations = []) {
  void feedback
  return previousRecommendations.map((item, index) => ({ ...item, rank: index + 1, reasons: [...getRankingReasons().slice(0, 3), 'List was refreshed after physician feedback; no allergy data was used.'] }))
}
