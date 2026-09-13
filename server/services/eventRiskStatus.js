// Event-level ADR inference is intentionally unavailable until HGNN validation
// is complete. This is an explicit API contract, not a fallback prediction.
export const eventRiskStatus = Object.freeze({
  status: "model_not_available",
  model: "HGNN",
  events: [],
  message: "Individual adverse-event model validation is in progress.",
  rankingInfluence: "none",
});
