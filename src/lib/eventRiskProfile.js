import { api } from "./api";

// The API contract exists before HGNN production inference. It never fabricates
// event probabilities while validation is incomplete.
export const HGNN_EVENT_RISK_ENABLED = false;

export const getEventRiskProfile = async (consultationId) => api(`/consultations/${consultationId}/adverse-event-risks`);
