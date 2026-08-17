import { highestDdiSeverity, highestDiseaseAssessment, normalizeClinicalTerm } from "../repositories/clinicalKnowledgeRepository.js";

export const recommendationRankingConfig = Object.freeze({
  configId: "vitanexus-drugcentral-evaluation-2.2",
  status: "DATASET_BACKED_EVALUATION",
  weightsStatus: "NOT_APPLICABLE",
  weightsReviewNote: "Each DrugCentral indication candidate is checked against the recorded active medicines and conditions using DDInter 2.0 and DrugCentral relationships. No ML score or probability is used.",
  candidateSource: "DrugCentral indication relationships",
});

// Only dataset inputs are included. Allergy data, FAERS data, and ADR-model outputs
// are deliberately excluded from candidate evaluation and its cache/input hash.
export const buildRecommendationInput = ({ consultation, patient, safety }) => ({
  consultationId: consultation.id,
  indication: consultation.indication,
  candidateGeneric: consultation.candidateGeneric,
  activeMedicines: patient.medications
    .filter((medicine) => medicine.status === "ACTIVE")
    .map((medicine) => medicine.genericName)
    .sort(),
  conditions: patient.conditions.map((condition) => condition.display).sort(),
  safety: {
    engineVersion: safety.engineVersion || null,
    drugDrug: { severity: safety.drugDrug?.severity || "NOT_EVALUATED", findings: safety.drugDrug?.findings || [] },
    drugDisease: { assessment: safety.drugDisease?.assessment || "NOT_EVALUATED", findings: safety.drugDisease?.findings || [] },
    overall: safety.overall,
  },
});

const overallAssessment = (ddiSeverity, diseaseAssessment) => {
  if (ddiSeverity === "MAJOR" || diseaseAssessment === "HIGH") return "HIGH";
  if (ddiSeverity === "MODERATE" || diseaseAssessment === "MODERATE") return "MODERATE";
  if (ddiSeverity === "MINOR" || diseaseAssessment === "LOW") return "LOW";
  return "NOT_EVALUATED";
};

const assessmentOrder = { LOW: 0, NOT_EVALUATED: 1, MODERATE: 2, HIGH: 3 };

const evaluateCandidate = async ({ candidate, patient, knowledgeRepository }) => {
  const activeMedicines = patient.medications.filter((medicine) => medicine.status === "ACTIVE");
  const interactionFindings = (await Promise.all(
    activeMedicines.map(async (medicine) => {
      const relationship = await knowledgeRepository.findPairwiseDrugInteraction(candidate.genericDrug, medicine.genericName);
      return relationship && { existingMedication: medicine.genericName, proposedDrug: candidate.genericDrug, ...relationship };
    }),
  )).filter(Boolean);
  const diseaseEvaluation = await knowledgeRepository.findDrugDiseaseAssessments(candidate.genericDrug, patient.conditions);
  const diseaseFindings = Array.isArray(diseaseEvaluation) ? diseaseEvaluation : diseaseEvaluation.findings;
  const diseaseResolutions = Array.isArray(diseaseEvaluation) ? [] : diseaseEvaluation.resolutions;
  const ddiSeverity = highestDdiSeverity(interactionFindings.map((finding) => finding.displaySeverity));
  const diseaseAssessment = highestDiseaseAssessment(diseaseFindings.map((finding) => finding.assessment));
  const assessment = overallAssessment(ddiSeverity, diseaseAssessment);

  return {
    drugDrug: { severity: ddiSeverity, findings: interactionFindings },
    drugDisease: { assessment: diseaseAssessment, findings: diseaseFindings, conditionResolutions: diseaseResolutions },
    assessment,
    dataStatus: interactionFindings.length || diseaseFindings.length ? "DATASET_MATCHED" : "NO_DATASET_MATCH",
  };
};

export const rankRecommendations = async ({ consultation, patient, knowledgeRepository }) => {
  const candidates = await knowledgeRepository.findCandidateDrugs(consultation.indication);
  const currentCandidate = normalizeClinicalTerm(consultation.candidateGeneric);
  const evaluatedCandidates = await Promise.all(candidates
    .filter((candidate) => normalizeClinicalTerm(candidate.genericDrug) !== currentCandidate)
    .map(async (candidate) => ({
      drug: candidate.genericDrug,
      indicationRelationship: candidate.relationship,
      evidence: candidate.evidence,
      source: candidate.source,
      datasetVersion: candidate.datasetVersion,
      ...await evaluateCandidate({ candidate, patient, knowledgeRepository }),
      reasons: [
        "Candidate identified from a DrugCentral indication relationship.",
        "DDInter 2.0 and DrugCentral are checked only for source relationships matching the recorded medicines and conditions.",
        "No ML, FAERS, probability, or synthetic risk score is used.",
      ],
    })));
  return evaluatedCandidates
    .sort((first, second) => assessmentOrder[first.assessment] - assessmentOrder[second.assessment] || first.drug.localeCompare(second.drug))
    .slice(0, 3)
    .map((candidate, index) => ({ ...candidate, rank: index + 1 }));
};
