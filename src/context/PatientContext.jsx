import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
import { api, apiJson } from "../lib/api";

const PatientContext = createContext(null);
const uiMedication = (item) => ({ drugName: item.genericName, enteredName: item.enteredName, normalizedName: item.normalizedName, brand: item.brand, generic: item.genericName, mappingSource: item.mappingSource, mappingVersion: item.mappingVersion, dosage: item.dosage || "", frequency: item.frequency || "", activeStatus: item.status });
const uiVisit = (item) => ({
  id: item.id, date: item.createdAt, prescribedDrug: item.prescription?.generic, prescription: { medicine: item.prescription ? { enteredName: item.prescription.enteredName, normalizedName: item.prescription.normalizedName, brand: item.prescription.brand, generic: item.prescription.generic, mappingSource: item.prescription.mappingSource, mappingVersion: item.prescription.mappingVersion } : null, dosage: item.prescription?.dosage || "", frequency: item.prescription?.frequency || "" }, indication: item.indication, diagnosis: item.indication, doctorNotes: item.latestNote?.text || "", riskResult: item.latestSafetyAssessment?.drugDrug || { severity: "NOT_EVALUATED", source: "DDInter 2.0" }, safetyResult: item.latestSafetyAssessment || null, recommendations: item.recommendations || [], adrPrediction: item.adrPrediction, feedback: item.followUps?.[0] || null, followUps: item.followUps || [], status: item.status, updatedRecommendations: item.recommendations || null,
});
const uiPatient = (item) => ({ id: item.id, publicId: item.publicId, name: item.name, age: item.age, gender: item.gender, version: item.version, diseases: item.conditions.map((condition) => ({ name: condition.display, code: condition.code || null, source: condition.source || "clinician-entered", duration: condition.duration || "", isCustom: false })), allergies: item.allergies.map((allergy) => ({ name: allergy.display, severity: allergy.severity || "Mild", isCustom: false })), currentMedications: item.medications.map(uiMedication), visits: item.consultations.map(uiVisit), createdAt: item.createdAt });
const clinicalPayload = (clinical) => ({
  conditions: (clinical.diseases || []).map((item) => ({ display: item.name, code: item.code || null, source: item.source || "clinician-entered", duration: item.duration || item.detail || "" })),
  allergies: (clinical.allergies || []).map((item) => ({ display: item.name, severity: item.severity || item.detail || "Mild" })),
  medications: (clinical.currentMedications || []).map((item) => ({ brand: item.brand || null, genericName: item.generic || item.drugName, dosage: item.dosage || null, frequency: item.frequency || null, status: item.activeStatus || "active" })),
});

export function PatientProvider({ children }) {
  const { doctor } = useAuth();
  const [patients, setPatients] = useState([]);
  const [activeVisitId, setActiveVisitId] = useState(null);
  const refreshPatients = useCallback(async () => {
    if (!doctor) { setPatients([]); return []; }
    const result = await api("/patients");
    const details = await Promise.all((result.items || result || []).map((patient) => api(`/patients/${patient.id}`)));
    const mapped = details.map(uiPatient); setPatients(mapped); return mapped;
  }, [doctor]);
  useEffect(() => { refreshPatients().catch(() => setPatients([])); setActiveVisitId(null); }, [refreshPatients]);

  const createPatient = async (basicInfo, clinicalInfo, consultationInfo) => {
    const patient = await apiJson("/patients", "POST", { ...basicInfo, ...clinicalPayload(clinicalInfo) });
    const consultation = await apiJson(`/patients/${patient.id}/consultations`, "POST", { indication: consultationInfo.indication, candidateBrand: consultationInfo.prescription.medicine.brand || null, candidateGeneric: consultationInfo.prescription.medicine.generic || null, dosage: consultationInfo.prescription.dosage, frequency: consultationInfo.prescription.frequency });
    const safety = await apiJson(`/consultations/${consultation.id}/clinical-safety-assessment`, "POST", {});
    const recommendations = await apiJson(`/consultations/${consultation.id}/recommendations`, "POST", {});
    await refreshPatients(); setActiveVisitId(consultation.id);
    return { patient: uiPatient(patient), visit: { ...uiVisit(consultation), riskResult: safety.drugDrug, safetyResult: safety, recommendations: recommendations.recommendations || [] } };
  };
  const addVisitToPatient = async (patientId, consultationInfo) => {
    const consultation = await apiJson(`/patients/${patientId}/consultations`, "POST", { indication: consultationInfo.indication, candidateBrand: consultationInfo.prescription.medicine.brand || null, candidateGeneric: consultationInfo.prescription.medicine.generic || null, dosage: consultationInfo.prescription.dosage, frequency: consultationInfo.prescription.frequency });
    await apiJson(`/consultations/${consultation.id}/clinical-safety-assessment`, "POST", {});
    await apiJson(`/consultations/${consultation.id}/recommendations`, "POST", {});
    const refreshed = await refreshPatients(); setActiveVisitId(consultation.id);
    const patient = refreshed.find((item) => item.id === patientId); return { patient, visit: patient?.visits.find((item) => item.id === consultation.id) };
  };
  const editPatient = async (patientId, basicInfo, clinicalInfo) => { await apiJson(`/patients/${patientId}`, "PATCH", { ...basicInfo, ...clinicalPayload(clinicalInfo) }); await refreshPatients(); };
  const deletePatientById = async (patientId) => { await api(`/patients/${patientId}`, { method: "DELETE" }); await refreshPatients(); };
  const saveVisitNotes = async (patientId, visitId, text) => { await apiJson(`/consultations/${visitId}/notes`, "PATCH", { text }); await refreshPatients(); };
  const saveAdrPrediction = async (patientId, visitId) => { await apiJson(`/consultations/${visitId}/adr-predictions`, "POST", {}); await refreshPatients(); };
  const submitFeedback = async (patientId, visitId, feedback) => { await apiJson(`/consultations/${visitId}/follow-ups`, "POST", { adverseEvent: feedback.sideEffect || feedback.adverseEvent, severity: feedback.severity || "Moderate", durationDays: Number(feedback.durationDays) || null, notes: feedback.notes || null }); await refreshPatients(); };
  const saveFollowUpDraft = () => {};
  return <PatientContext.Provider value={{ patients, refreshPatients, createPatient, addVisitToPatient, editPatient, deletePatientById, submitFeedback, saveFollowUpDraft, saveVisitNotes, saveAdrPrediction, activeVisitId, setActiveVisitId }}>{children}</PatientContext.Provider>;
}
export const usePatient = () => { const value = useContext(PatientContext); if (!value) throw new Error("usePatient must be used within PatientProvider"); return value; };
