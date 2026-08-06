import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useAuth } from "./AuthContext";
import {
  addPatient,
  deletePatient,
  getNextPatientId,
  getPatients,
  updatePatient,
} from "../lib/storage";
import {
  generateConfidence,
  generateRecommendations,
  generateRiskResult,
  generateUpdatedRecommendations,
} from "../lib/mockEngine";

const PatientContext = createContext(null);
const makeVisit = (consultationInfo) => ({
  id: crypto.randomUUID(),
  date: new Date().toISOString(),
  // These fields are presentation/state data only. Future services can use the
  // same shape without changing the consultation UI.
  prescribedDrug: consultationInfo.prescription?.medicine || consultationInfo.prescribedDrug,
  prescription: consultationInfo.prescription || null,
  indication: consultationInfo.indication || consultationInfo.diagnosis || "",
  diagnosis: consultationInfo.indication || consultationInfo.diagnosis || "",
  doctorNotes: consultationInfo.doctorNotes || "",
  riskResult: generateRiskResult(),
  confidence: generateConfidence(),
  recommendations: generateRecommendations(),
  adrPrediction: null,
  feedback: null,
  updatedRecommendations: null,
  status: "in-progress",
});

const prescribedMedication = (consultationInfo) => {
  const medicine = consultationInfo.prescription?.medicine || consultationInfo.prescribedDrug;
  if (!medicine) return null;
  return {
    drugName: medicine.generic || medicine.brand,
    brand: medicine.brand,
    generic: medicine.generic,
    dosage: consultationInfo.prescription?.dosage || "",
    frequency: consultationInfo.prescription?.frequency || "",
    activeStatus: "active",
  };
};

const addPrescriptionToCurrentMedications = (currentMedications = [], consultationInfo) => {
  const medication = prescribedMedication(consultationInfo);
  if (!medication) return currentMedications;
  const name = (medication.drugName || "").toLowerCase();
  const exists = currentMedications.some(
    (item) => (item.drugName || item.generic || item.brand || "").toLowerCase() === name,
  );
  return exists ? currentMedications : [...currentMedications, medication];
};

export function PatientProvider({ children }) {
  const { doctor } = useAuth();
  const [patients, setPatients] = useState([]);
  const [activeVisitId, setActiveVisitId] = useState(null);
  const refreshPatients = useCallback(
    () => setPatients(doctor ? getPatients(doctor.id) : []),
    [doctor],
  );
  useEffect(() => {
    refreshPatients();
    setActiveVisitId(null);
  }, [refreshPatients]);

  const createPatient = (basicInfo, clinicalInfo, consultationInfo) => {
    const visit = makeVisit(consultationInfo);
    const patient = {
      id: getNextPatientId(),
      doctorId: doctor.id,
      ...basicInfo,
      ...clinicalInfo,
      currentMedications: addPrescriptionToCurrentMedications(
        clinicalInfo.currentMedications,
        consultationInfo,
      ),
      visits: [visit],
      createdAt: new Date().toISOString(),
    };
    addPatient(patient);
    refreshPatients();
    setActiveVisitId(visit.id);
    return patient;
  };
  const addVisitToPatient = (patientId, consultationInfo) => {
    const visit = makeVisit(consultationInfo);
    const updated = updatePatient(patientId, (patient) => ({
      ...patient,
      currentMedications: addPrescriptionToCurrentMedications(
        patient.currentMedications,
        consultationInfo,
      ),
      visits: [...patient.visits, visit],
    }));
    refreshPatients();
    setActiveVisitId(visit.id);
    return { patient: updated, visit };
  };
  const editPatient = (patientId, basicInfo, clinicalInfo) => {
    updatePatient(patientId, (patient) => ({
      ...patient,
      ...basicInfo,
      ...clinicalInfo,
    }));
    refreshPatients();
  };
  const deletePatientById = (patientId) => {
    deletePatient(patientId);
    refreshPatients();
  };
  const submitFeedback = (patientId, visitId, feedback) => {
    const updated = updatePatient(patientId, (patient) => ({
      ...patient,
      visits: patient.visits.map((visit) => {
        if (visit.id !== visitId) return visit;
        if (visit.status === "completed") {
          const furtherFollowUp = {
            id: crypto.randomUUID(),
            date: new Date().toISOString(),
            ...feedback,
          };
          return {
            ...visit,
            followUps: [...(visit.followUps || []), furtherFollowUp],
            updatedRecommendations: generateUpdatedRecommendations(
              feedback,
              visit.updatedRecommendations?.length
                ? visit.updatedRecommendations
                : visit.recommendations,
            ),
          };
        }
        return {
          ...visit,
          feedback,
          feedbackDraft: undefined,
          updatedRecommendations: generateUpdatedRecommendations(
            feedback,
            visit.recommendations,
          ),
          status: "completed",
        };
      }),
    }));
    refreshPatients();
    return updated;
  };
  const saveFollowUpDraft = (patientId, visitId, feedbackDraft) => {
    updatePatient(patientId, (patient) => ({
      ...patient,
      visits: patient.visits.map((visit) =>
        visit.id === visitId ? { ...visit, feedbackDraft } : visit,
      ),
    }));
    refreshPatients();
  };
  const saveVisitNotes = (patientId, visitId, doctorNotes) => {
    updatePatient(patientId, (patient) => ({
      ...patient,
      visits: patient.visits.map((visit) =>
        visit.id === visitId ? { ...visit, doctorNotes } : visit,
      ),
    }));
    refreshPatients();
  };
  const saveAdrPrediction = (patientId, visitId, adrPrediction) => {
    updatePatient(patientId, (patient) => ({
      ...patient,
      visits: patient.visits.map((visit) =>
        visit.id === visitId ? { ...visit, adrPrediction } : visit,
      ),
    }));
    refreshPatients();
  };

  return (
    <PatientContext.Provider
      value={{
        patients,
        refreshPatients,
        createPatient,
        addVisitToPatient,
        editPatient,
        deletePatientById,
        submitFeedback,
        saveFollowUpDraft,
        saveVisitNotes,
        saveAdrPrediction,
        activeVisitId,
        setActiveVisitId,
      }}
    >
      {children}
    </PatientContext.Provider>
  );
}

export const usePatient = () => {
  const value = useContext(PatientContext);
  if (!value) throw new Error("usePatient must be used within PatientProvider");
  return value;
};
