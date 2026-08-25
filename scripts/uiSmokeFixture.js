import process from "node:process";

const baseUrl = "http://127.0.0.1:4000/api/v1";
const credentials = { email: "codex-ui-smoke@example.test", password: "UiSmokePass1!" };
let token;
const api = async (path, method = "GET", body) => {
  const response = await fetch(`${baseUrl}${path}`, { method, headers: { ...(body ? { "content-type": "application/json" } : {}), ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) throw Object.assign(new Error(payload?.error?.message || `HTTP ${response.status}`), { status: response.status });
  return payload?.data;
};
try {
  token = (await api("/auth/login", "POST", credentials)).accessToken;
} catch (error) {
  if (error.status !== 401) throw error;
  token = (await api("/auth/register", "POST", { ...credentials, name: "Dr UI Smoke", specialty: "Clinical Informatics" })).accessToken;
}
const existing = (await api("/patients?q=ML%20UI%20Smoke")).items;
if (process.argv.includes("--cleanup")) {
  for (const patient of existing) await api(`/patients/${patient.id}`, "DELETE");
  console.log(JSON.stringify({ cleaned: existing.length }));
  process.exit(0);
}
let patient = existing[0] ? await api(`/patients/${existing[0].id}`) : await api("/patients", "POST", { name: "ML UI Smoke", age: 58, gender: "Male", conditions: [], allergies: [], medications: [{ genericName: "Warfarin", status: "active" }] });
let consultation = patient.consultations?.find((item) => item.status === "in-progress");
if (!consultation) {
  const indication = (await api("/terminology/indications?q=pain&limit=1")).items[0];
  const medicine = (await api("/terminology/medications?q=crocin&limit=1")).items[0];
  consultation = await api(`/patients/${patient.id}/consultations`, "POST", { indication: indication.display, indicationId: indication.id, indicationSource: indication.source, indicationDatasetVersion: indication.datasetVersion, candidateBrand: medicine.brand, candidateGeneric: medicine.genericName, dosage: "500 mg", frequency: "2d" });
  await api(`/consultations/${consultation.id}/clinical-safety-assessment`, "POST", {});
  await api(`/consultations/${consultation.id}/adr-predictions`, "POST", {});
  await api(`/consultations/${consultation.id}/recommendations`, "POST", {});
}
console.log(JSON.stringify({ email: credentials.email, password: credentials.password, patientId: patient.id, visitId: consultation.id, adrUrl: `http://localhost:5173/patients/${patient.id}/consultations/${consultation.id}/adr` }, null, 2));
