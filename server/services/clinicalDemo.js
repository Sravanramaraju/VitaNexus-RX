import { ddinterSearchTerms, highestDdiSeverity, highestDiseaseAssessment } from "../repositories/clinicalKnowledgeRepository.js";
import { adrPredictionProvider } from "./adrPredictionProvider.js";
import { rankRecommendations, recommendationRankingConfig } from "./recommendationRankingService.js";

const ENGINE_VERSION = "vitanexus-knowledge-2.2.0";
const overallAssessment = (ddiSeverity, diseaseAssessment) => {
  if (ddiSeverity === "MAJOR" || diseaseAssessment === "HIGH") return "HIGH";
  if (ddiSeverity === "MODERATE" || diseaseAssessment === "MODERATE") return "MODERATE";
  if (ddiSeverity === "MINOR" || diseaseAssessment === "LOW") return "LOW";
  return "NOT_EVALUATED";
};

// Allergies deliberately are not accepted here. They remain part of the patient record
// for clinician review, but are not an automated clinical-engine input.
export const clinicalSafetyAssessment = async ({ consultation, patient, knowledgeRepository }) => {
  const activeMedicines = patient.medications.filter((medicine) => medicine.status === "ACTIVE");
  const evaluatedPairs = activeMedicines.map((medicine) => ({
    proposedDrug: consultation.candidateGeneric,
    proposedDatasetTerms: ddinterSearchTerms(consultation.candidateGeneric),
    existingMedication: medicine.genericName,
    existingDatasetTerms: ddinterSearchTerms(medicine.genericName),
  }));
  const interactionFindings = (await Promise.all(
    activeMedicines.map(async (medicine) => {
      const relationship = await knowledgeRepository.findPairwiseDrugInteraction(consultation.candidateGeneric, medicine.genericName);
      return relationship && {
        existingMedication: medicine.genericName,
        proposedDrug: consultation.candidateGeneric,
        ...relationship,
      };
    }),
  )).filter(Boolean);
  const diseaseEvaluation = await knowledgeRepository.findDrugDiseaseAssessments(consultation.candidateGeneric, patient.conditions);
  const diseaseFindings = Array.isArray(diseaseEvaluation) ? diseaseEvaluation : diseaseEvaluation.findings;
  const diseaseResolutions = Array.isArray(diseaseEvaluation) ? [] : diseaseEvaluation.resolutions;
  const ddiSeverity = highestDdiSeverity(interactionFindings.map((finding) => finding.displaySeverity));
  const diseaseAssessment = highestDiseaseAssessment(diseaseFindings.map((finding) => finding.assessment));

  return {
    status: "DATASET_BACKED_WHEN_MATCHED",
    dataStatus: interactionFindings.length || diseaseFindings.length ? "DATASET_MATCHED" : "NO_DATASET_MATCH",
    disclaimer: "Dataset relationships support clinical review and are not patient-specific probabilities or a substitute for professional judgement.",
    engineVersion: ENGINE_VERSION,
    assessedAt: new Date().toISOString(),
    drugDrug: {
      severity: ddiSeverity,
      findings: interactionFindings,
      evaluatedPairs,
      source: "DDInter 2.0",
      dataStatus: interactionFindings.length ? "DATASET_MATCHED" : "NO_DATASET_MATCH",
      explanations: interactionFindings.length
        ? interactionFindings.map((finding) => `${finding.drugA} + ${finding.drugB}: ${finding.rawSeverity} (${finding.source}).`)
        : evaluatedPairs.length
          ? evaluatedPairs.map((pair) => `No DDInter 2.0 record for ${pair.proposedDatasetTerms.join(" / ")} + ${pair.existingDatasetTerms.join(" / ")}.`)
          : ["No active medicines were available for a DDInter 2.0 check."],
    },
    drugDisease: {
      assessment: diseaseAssessment,
      findings: diseaseFindings,
      conditionResolutions: diseaseResolutions,
      source: "DrugCentral",
      dataStatus: diseaseFindings.length ? "DATASET_MATCHED" : "NO_DATASET_MATCH",
      explanations: diseaseFindings.length
        ? diseaseFindings.map((finding) => `Entered condition: ${finding.enteredCondition} → resolved DrugCentral term: ${finding.resolvedDisease} (${finding.diseaseIdentity}) → DrugCentral relationship: ${finding.relationship} → assessment: ${finding.assessment}. Source: ${finding.source} ${finding.datasetVersion}.`)
        : diseaseResolutions.length
          ? diseaseResolutions.map((resolution) => resolution.status === "RESOLVED"
            ? `Entered condition: ${resolution.enteredCondition} → resolved DrugCentral term: ${resolution.resolvedDisease} (${resolution.diseaseIdentity}), but no DrugCentral relationship was found for the proposed drug.`
            : `Entered condition: ${resolution.enteredCondition} could not be deterministically resolved to a DrugCentral disease identity; no relationship was claimed.`)
          : ["No active patient conditions were available for a DrugCentral drug-disease check."],
    },
    overall: {
      assessment: overallAssessment(ddiSeverity, diseaseAssessment),
      dataStatus: interactionFindings.length || diseaseFindings.length ? "DATASET_MATCHED" : "NO_DATASET_MATCH",
      explanation: "An ordinal synthesis of DDInter severity and DrugCentral drug-disease assessment; it is not a probability or percentage.",
    },
    conformalReliability: {
      status: "NOT_IMPLEMENTED",
      explanation: "No calibrated confidence, prediction interval, or conformal reliability measure is produced by this clinical-safety workflow.",
    },
  };
};

export const adrPrediction = async (input) => adrPredictionProvider.predict(input);

export const recommendations = async ({ consultation, patient, knowledgeRepository, requestId, provider }) =>
  rankRecommendations({ consultation, patient, knowledgeRepository, requestId, provider });

export const versions = {
  ENGINE_VERSION,
  MODEL_VERSION: adrPredictionProvider.modelVersion,
  MODEL_NAME: adrPredictionProvider.modelName,
  ADR_PROVIDER_NAME: adrPredictionProvider.providerName,
  RANKING_CONFIG_ID: recommendationRankingConfig.configId,
};

export { recommendationRankingConfig };
