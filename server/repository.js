import { Prisma } from "@prisma/client";
import { fromMedicationStatus, toMedicationStatus } from "./utils.js";

export const patientInclude = {
  conditions: { where: { isActive: true } },
  allergies: { where: { isActive: true } },
  medications: { orderBy: { createdAt: "asc" } },
  consultations: { orderBy: { createdAt: "desc" }, include: { followUps: { orderBy: { createdAt: "desc" } }, notes: { orderBy: { updatedAt: "desc" }, take: 1 }, analyses: { orderBy: { createdAt: "desc" } }, adrPredictions: { orderBy: { createdAt: "desc" }, take: 1 }, recommendations: { orderBy: { createdAt: "desc" }, take: 1 } } },
};

export const mapMedicationInput = (medication) => ({
  brand: medication.brand || null,
  genericName: medication.genericName,
  enteredName: medication.enteredName || medication.brand || medication.genericName,
  normalizedName: medication.normalizedName || null,
  mappingSource: medication.mappingSource || null,
  mappingVersion: medication.mappingVersion || null,
  dosage: medication.dosage || null,
  frequency: medication.frequency || null,
  route: medication.route || null,
  status: toMedicationStatus(medication.status),
  source: medication.source || "clinician-entered",
});

export const mapConditionInput = (condition) => ({ display: condition.display, code: condition.code || null, duration: condition.duration || null, source: condition.source || "clinician-entered" });
export const mapAllergyInput = (allergy) => ({ display: allergy.display, code: allergy.code || null, severity: allergy.severity || null, reaction: allergy.reaction || null, source: allergy.source || "clinician-entered" });

// Legacy safety snapshots may contain an old demonstration-only drugAllergy field.
// It remains in historical JSON but is excluded from all active API projections.
export const activeSafetyResult = (result) => {
  if (!result) return null;
  const { drugAllergy, ...currentResult } = result;
  return drugAllergy
    ? { ...currentResult, legacyFieldsOmitted: ["drugAllergy"] }
    : currentResult;
};

export const patientResponse = (patient) => ({
  id: patient.id,
  publicId: patient.publicId,
  name: patient.name,
  age: patient.age,
  gender: patient.gender,
  version: patient.version,
  createdAt: patient.createdAt,
  updatedAt: patient.updatedAt,
  conditions: patient.conditions?.map((item) => ({ id: item.id, display: item.display, code: item.code, duration: item.duration, source: item.source })) || [],
  allergies: patient.allergies?.map((item) => ({ id: item.id, display: item.display, code: item.code, severity: item.severity, reaction: item.reaction, source: item.source })) || [],
  medications: patient.medications?.map((item) => ({ id: item.id, enteredName: item.enteredName || item.brand || item.genericName, normalizedName: item.normalizedName, brand: item.brand, genericName: item.genericName, mappingSource: item.mappingSource, mappingVersion: item.mappingVersion, dosage: item.dosage, frequency: item.frequency, route: item.route, status: fromMedicationStatus(item.status), source: item.source })) || [],
  consultations: patient.consultations?.map(consultationResponse) || [],
});

export const consultationResponse = (consultation) => ({
  id: consultation.id,
  patientId: consultation.patientId,
  indication: consultation.indication,
  indicationProvenance: { id: consultation.indicationId || null, normalizedName: consultation.indicationNormalized || null, source: consultation.indicationSource || "LEGACY_FREE_TEXT", datasetVersion: consultation.indicationDatasetVersion || null },
  prescription: { enteredName: consultation.candidateEnteredName || consultation.candidateBrand || consultation.candidateGeneric, normalizedName: consultation.candidateNormalizedName, brand: consultation.candidateBrand, generic: consultation.candidateGeneric, mappingSource: consultation.candidateMappingSource, mappingVersion: consultation.candidateMappingVersion, dosage: consultation.dosage, frequency: consultation.frequency, route: consultation.route },
  status: consultation.status.toLowerCase().replace("_", "-"),
  version: consultation.version,
  createdAt: consultation.createdAt,
  updatedAt: consultation.updatedAt,
  latestSafetyAssessment: activeSafetyResult(consultation.analyses?.find((item) => item.type === "SAFETY")?.result),
  adrPrediction: consultation.adrPredictions?.[0]?.result || null,
  recommendations: consultation.recommendations?.[0]?.recommendations || null,
  latestNote: consultation.notes?.[0] ? { text: consultation.notes[0].text, updatedAt: consultation.notes[0].updatedAt } : null,
  followUps: consultation.followUps?.map((item) => ({ id: item.id, adverseEvent: item.adverseEvent, eventCode: item.eventCode, severity: item.severity, durationDays: item.durationDays, notes: item.notes, createdAt: item.createdAt })) || [],
});

export const isPrismaConflict = (error) => error instanceof Prisma.PrismaClientKnownRequestError && error.code === "P2025";
