import { ddinterSearchTerms, highestDdiSeverity, highestDiseaseAssessment } from "../repositories/clinicalKnowledgeRepository.js";
import { adrPredictionProvider } from "./adrPredictionProvider.js";
import { rankRecommendations, recommendationRankingConfig } from "./recommendationRankingService.js";
import { CLINICAL_ENGINE_VERSION } from "./clinicalEngineVersion.js";

const ENGINE_VERSION = CLINICAL_ENGINE_VERSION;
const overallAssessment = (ddiSeverity, diseaseAssessment, evidenceComplete) => {
  if (ddiSeverity === "MAJOR" || diseaseAssessment === "HIGH") return "HIGH";
  if (ddiSeverity === "MODERATE" || diseaseAssessment === "MODERATE") return "MODERATE";
  if (ddiSeverity === "MINOR" || diseaseAssessment === "LOW") return "LOW";
  if (evidenceComplete) return "NO_DOCUMENTED_RELATIONSHIP";
  return "NOT_EVALUATED";
};

// Allergies deliberately are not accepted here. They remain part of the patient record
// for clinician review, but are not an automated clinical-engine input.
export const clinicalSafetyAssessment = async ({ consultation, patient, knowledgeRepository }) => {
  const activeMedicines = patient.medications.filter((medicine) => medicine.status === "ACTIVE");
  const evaluatedPairs = await Promise.all(activeMedicines.map(async (medicine) => {
    const evaluation = await knowledgeRepository.evaluateDdiPair(consultation.candidateGeneric, medicine.genericName);
    return {
      proposedDrug: consultation.candidateGeneric,
      proposedDatasetTerms: ddinterSearchTerms(consultation.candidateGeneric),
      existingMedication: medicine.genericName,
      existingDatasetTerms: ddinterSearchTerms(medicine.genericName),
      ...evaluation,
    };
  }));
  const interactionFindings = evaluatedPairs.filter((pair) => pair.status === "DOCUMENTED_INTERACTION").map((pair) => ({
    existingMedication: pair.existingMedication,
    proposedDrug: pair.proposedDrug,
    ...pair.interaction,
  }));
  const diseaseEvaluation = await knowledgeRepository.findDrugDiseaseAssessments(consultation.candidateGeneric, patient.conditions);
  const diseaseFindings = Array.isArray(diseaseEvaluation) ? diseaseEvaluation : diseaseEvaluation.findings;
  const diseaseResolutions = Array.isArray(diseaseEvaluation) ? [] : diseaseEvaluation.resolutions;
  const ddiComplete = evaluatedPairs.every((pair) => ["DOCUMENTED_INTERACTION", "NO_DOCUMENTED_INTERACTION"].includes(pair.status));
  const ddiSeverity = interactionFindings.length ? highestDdiSeverity(interactionFindings.map((finding) => finding.displaySeverity)) : ddiComplete ? "NO_DOCUMENTED_INTERACTION" : "NOT_EVALUATED";
  const diseaseComplete = patient.conditions.length === 0 || (diseaseResolutions.length === patient.conditions.length && diseaseResolutions.every((resolution) => resolution.status === "RESOLVED"));
  const diseaseAssessment = diseaseFindings.length
    ? highestDiseaseAssessment(diseaseFindings.map((finding) => finding.assessment))
    : diseaseComplete
      ? "NO_DOCUMENTED_RELATIONSHIP"
      : "NOT_EVALUATED";

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
      complete: ddiComplete,
      dataStatus: !evaluatedPairs.length ? "NO_ACTIVE_MEDICATIONS" : !ddiComplete ? "INCOMPLETE_EVIDENCE" : interactionFindings.length ? "DATASET_MATCHED" : "NO_DOCUMENTED_INTERACTION",
      explanations: evaluatedPairs.length
        ? evaluatedPairs.map((pair) => pair.status === "DOCUMENTED_INTERACTION"
          ? `${pair.interaction.drugA} + ${pair.interaction.drugB}: ${pair.interaction.rawSeverity} (${pair.interaction.source}).`
          : pair.status === "NO_DOCUMENTED_INTERACTION"
            ? `Both DDInter identifiers resolved and the lookup completed; no interaction record exists for ${pair.proposedDrug} + ${pair.existingMedication}.`
            : pair.status === "LOOKUP_FAILED"
              ? `The DDInter lookup failed for ${pair.proposedDrug} + ${pair.existingMedication}; clinical review is required.`
              : `A DDInter identifier could not be resolved unambiguously for ${pair.proposedDrug} + ${pair.existingMedication}; clinical review is required.`)
        : ["No active medicines were available for a DDInter 2.0 check."],
    },
    drugDisease: {
      assessment: diseaseAssessment,
      complete: diseaseComplete,
      findings: diseaseFindings,
      conditionResolutions: diseaseResolutions,
      source: "DrugCentral",
      dataStatus: !patient.conditions.length ? "NO_ACTIVE_CONDITIONS" : !diseaseComplete ? "INCOMPLETE_EVIDENCE" : diseaseFindings.length ? "DATASET_MATCHED" : "NO_DOCUMENTED_RELATIONSHIP",
      explanations: diseaseFindings.length
        ? diseaseFindings.map((finding) => `Entered condition: ${finding.enteredCondition} → resolved DrugCentral term: ${finding.resolvedDisease} (${finding.diseaseIdentity}) → DrugCentral relationship: ${finding.relationship} → assessment: ${finding.assessment}. Source: ${finding.source} ${finding.datasetVersion}.`)
        : diseaseResolutions.length
          ? diseaseResolutions.map((resolution) => resolution.status === "RESOLVED"
            ? `Entered condition: ${resolution.enteredCondition} → resolved DrugCentral term: ${resolution.resolvedDisease} (${resolution.diseaseIdentity}), but no DrugCentral relationship was found for the proposed drug.`
            : `Entered condition: ${resolution.enteredCondition} could not be deterministically resolved to a DrugCentral disease identity; no relationship was claimed.`)
          : ["No active patient conditions were available for a DrugCentral drug-disease check."],
    },
    overall: {
      assessment: overallAssessment(ddiSeverity, diseaseAssessment, ddiComplete && diseaseComplete),
      dataStatus: !ddiComplete || !diseaseComplete ? "INCOMPLETE_EVIDENCE" : interactionFindings.length || diseaseFindings.length ? "DATASET_MATCHED" : "NO_DOCUMENTED_RELATIONSHIP",
      explanation: "An ordinal synthesis of DDInter severity and DrugCentral drug-disease assessment; it is not a probability or percentage.",
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
