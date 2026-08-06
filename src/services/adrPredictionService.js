// This adapter is the sole frontend boundary for the future ADR prediction API.
// Replace the placeholder response with the backend request without changing ADR UI code.
const placeholderAdrPrediction = {
  predictedAdrRisk: 23,
  confidence: 94,
  confidenceInterval: { lower: 19, upper: 27 },
  riskCategory: "Moderate",
  predictionStatus: "success",
  explanations: [
    "This placeholder prediction will be replaced with a patient-specific model response.",
    "Patient demographics, active medications, and the newly prescribed medicine are included in the request.",
    "Disease data is intentionally excluded because clinical safety analysis already evaluates it.",
  ],
};

export async function requestAdrPrediction(request) {
  // Keep the request parameter at this boundary for future backend integration.
  void request;
  return placeholderAdrPrediction;
}
