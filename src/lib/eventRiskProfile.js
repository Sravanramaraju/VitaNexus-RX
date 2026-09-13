// The contract is intentionally available before HGNN production inference.
// It never fabricates event probabilities while validation is incomplete.
export const HGNN_EVENT_RISK_ENABLED = false;

export async function getEventRiskProfile() {
  return {
    status: "model_not_available",
    model: "HGNN",
    events: [],
    message: "Individual adverse-event model validation is in progress.",
  };
}
