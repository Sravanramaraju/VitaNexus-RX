import { api, apiJson } from "./api";

export const getEventRiskProfile = async (consultationId) =>
  api(`/consultations/${consultationId}/adverse-event-risks`);

export const regenerateEventRiskProfile = async (consultationId) =>
  apiJson(`/consultations/${consultationId}/adverse-event-risks`, "POST", {});
