import { getRankingReasons } from './explainability'

const randomInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min
const alternatives = ['Azithromycin', 'Amoxicillin', 'Cetirizine', 'Metformin', 'Losartan', 'Pantoprazole', 'Levosalbutamol', 'Doxycycline']

export function generateRiskResult() {
  const score = randomInt(10, 85)
  return { score, severity: score > 60 ? 'Severe' : score > 30 ? 'Moderate' : 'Mild', breakdown: { pharmacodynamic: randomInt(15, 90), pharmacokinetic: randomInt(10, 75) } }
}

export function generateConfidence() {
  const pct = randomInt(40, 98)
  const halfWidth = Math.max(2, Math.round((100 - pct) * 0.42))
  return { pct, intervalLow: Math.max(0, pct - halfWidth), intervalHigh: Math.min(100, pct + halfWidth), reliabilityLabel: pct > 85 ? 'Very High' : pct > 65 ? 'High' : pct > 45 ? 'Moderate' : 'Low' }
}

export function generateRecommendations(count = Math.random() > 0.5 ? 2 : 3) {
  return [...alternatives].sort(() => Math.random() - 0.5).slice(0, count).map((drug) => {
    const risk = generateRiskResult(); const confidence = generateConfidence()
    return { drug, riskPct: risk.score, confidencePct: confidence.pct, intervalLow: confidence.intervalLow, intervalHigh: confidence.intervalHigh, reasons: getRankingReasons() }
  }).sort((a, b) => a.riskPct - b.riskPct)
}

export function generateUpdatedRecommendations(feedback, previousRecommendations = []) {
  const effect = (feedback?.sideEffect || '').toLowerCase()
  return previousRecommendations.map((item) => ({ ...item, riskPct: Math.min(95, Math.max(5, item.riskPct + (item.drug.toLowerCase().includes(effect) ? 25 : randomInt(-12, 8)))), reasons: [...getRankingReasons().slice(0, 3), 'Ranking was updated after physician feedback.'] })).sort((a, b) => a.riskPct - b.riskPct)
}
