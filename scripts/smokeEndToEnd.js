import process from "node:process";

const baseUrl = process.env.SMOKE_API_BASE_URL || "http://127.0.0.1:4000/api/v1";
const requestId = `ml-smoke-${Date.now()}`;
let token = null;

const api = async (path, { method = "GET", body } = {}) => {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      ...(body ? { "content-type": "application/json" } : {}),
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      "x-request-id": `${requestId}:${path}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(`${method} ${path} failed (${response.status}): ${payload?.error?.message || JSON.stringify(payload)}`);
  return payload?.data;
};

const indication = (await api("/terminology/indications?q=pain&limit=1")).items[0];
const medicine = (await api("/terminology/medications?q=crocin&limit=1")).items[0];
if (!indication?.id || indication.source !== "DrugCentral" || !medicine?.id) throw new Error("Required DrugCentral/Indian Medicine test terminology is unavailable.");

const registration = await api("/auth/register", {
  method: "POST",
  body: { name: "Dr ML Smoke", email: `ml-smoke-${Date.now()}@example.test`, password: "SmokePass1!", specialty: "Clinical Informatics" },
});
token = registration.accessToken;
const patient = await api("/patients", {
  method: "POST",
  body: { name: "ML Integration Smoke", age: 58, gender: "Male", conditions: [], allergies: [], medications: [{ genericName: "Warfarin", status: "active" }] },
});

try {
  const consultation = await api(`/patients/${patient.id}/consultations`, {
    method: "POST",
    body: {
      indication: indication.display,
      indicationId: indication.id,
      indicationSource: indication.source,
      indicationDatasetVersion: indication.datasetVersion,
      candidateBrand: medicine.brand,
      candidateGeneric: medicine.genericName,
      dosage: "500 mg",
      frequency: "2d",
    },
  });
  const safety = await api(`/consultations/${consultation.id}/clinical-safety-assessment`, { method: "POST", body: {} });
  const adr = await api(`/consultations/${consultation.id}/adr-predictions`, { method: "POST", body: {} });
  const persistedAdr = await api(`/consultations/${consultation.id}/adr-predictions`);
  const recommendations = await api(`/consultations/${consultation.id}/recommendations`, { method: "POST", body: {} });
  await api(`/consultations/${consultation.id}/follow-ups`, { method: "POST", body: { adverseEvent: "Nausea", severity: "Mild", durationDays: 1, notes: "Automated local smoke record." } });
  const refreshed = await api(`/patients/${patient.id}`);
  if (adr.status !== "ok" && adr.status !== "DEGRADED_COVERAGE") throw new Error(`Expected available ML inference, received ${adr.status}`);
  if (persistedAdr.versions?.lightgbm !== adr.versions?.lightgbm) throw new Error("Persisted ADR version does not match generated result.");
  if (!Array.isArray(recommendations.recommendations)) throw new Error("Recommendation response is missing candidates.");
  if (refreshed.consultations[0]?.followUps?.length !== 1) throw new Error("Follow-up did not persist.");
  console.log(JSON.stringify({
    status: "ok",
    requestId,
    indication: consultation.indicationProvenance,
    safetyEngine: safety.engineVersion,
    adrStatus: adr.status,
    lightgbmVersion: adr.versions.lightgbm,
    bootstrapReplicas: adr.overall.uncertainty.replicas,
    conformalSet: adr.overall.conformal.predictionSet,
    recommendationCount: recommendations.recommendations.length,
    rankingEngine: recommendations.ranking.configId,
    followUpPersisted: true,
  }, null, 2));
} finally {
  await api(`/patients/${patient.id}`, { method: "DELETE" });
}
