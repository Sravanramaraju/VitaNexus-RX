import { describe, expect, it } from "vitest";
import { stableHash } from "../utils.js";
import { clinicalSafetyAssessment, recommendationRankingConfig, recommendations } from "./clinicalDemo.js";
import { buildRecommendationInput } from "./recommendationRankingService.js";

const consultation = { id: "consultation-1", candidateGeneric: "Ibuprofen", indication: "Pain" };
const patient = { age: 60, conditions: [{ display: "Chronic kidney disease" }], allergies: [], medications: [{ genericName: "Warfarin", status: "ACTIVE" }] };
const knowledgeRepository = {
  hasDdiDrugEvidence: async () => true,
  findPairwiseDrugInteraction: async (candidate, existing) => candidate === "Ibuprofen" && existing === "Warfarin" ? { drugA: "Ibuprofen", drugB: "Warfarin", rawSeverity: "Major", displaySeverity: "MAJOR", source: "DDInter 2.0", datasetVersion: "DDInter 2.0 import 2026-08-11" } : null,
  findDrugDiseaseAssessments: async (candidate, conditions) => candidate === "Ibuprofen" && conditions.some((condition) => condition.display === "Chronic kidney disease") ? [{ existingDisease: "Chronic kidney disease", proposedDrug: "Ibuprofen", assessment: "HIGH", relationship: "contraindicated in", evidence: "contraindicated in chronic kidney disease", source: "DrugCentral", datasetVersion: "DrugCentral 20231101" }] : [],
  findCandidateDrugs: async (indication) => indication === "Pain" ? [{ genericDrug: "Paracetamol", relationship: "has indication", evidence: "Pain", source: "DrugCentral", datasetVersion: "DrugCentral 20231101" }, { genericDrug: "Ibuprofen", relationship: "has indication", evidence: "Pain", source: "DrugCentral", datasetVersion: "DrugCentral 20231101" }] : [],
};
const provider = {
  predictBatch: async (inputs) => inputs.map(() => ({
    status: "ok",
    overall: { calibratedProbability: 0.2, uncertainty: { lower: 0.1, upper: 0.3 }, conservativeUpperBound: 0.3, conformal: { predictionSet: ["NO_DOCUMENTED_SERIOUS_OUTCOME"] } },
    specificAdrs: [],
    versions: { lightgbm: "test", bootstrap: "test", conformal: "test", hgnn: "test", preprocessing: "test" },
  })),
};

describe("dataset-backed clinical service contracts", () => {
  it("returns DDInter severity and no percentage risk", async () => {
    const result = await clinicalSafetyAssessment({ consultation, patient, knowledgeRepository });
    expect(result.drugDrug.severity).toBe("MAJOR");
    expect(result.drugDrug.findings[0]).toMatchObject({ rawSeverity: "Major", displaySeverity: "MAJOR", source: "DDInter 2.0" });
    expect(result.drugDrug.evaluatedPairs).toEqual([expect.objectContaining({ proposedDatasetTerms: ["ibuprofen"], existingDatasetTerms: ["warfarin"] })]);
    expect(JSON.stringify(result)).not.toContain("riskPercentage");
  });

  it("returns a DrugCentral HIGH/MODERATE/LOW assessment and no percentage", async () => {
    const result = await clinicalSafetyAssessment({ consultation, patient, knowledgeRepository });
    expect(result.drugDisease.assessment).toBe("HIGH");
    expect(result.drugDisease.findings[0]).toMatchObject({ existingDisease: "Chronic kidney disease", proposedDrug: "Ibuprofen", source: "DrugCentral" });
    expect(result.drugDisease).not.toHaveProperty("riskPercentage");
  });

  it("persists deterministic DrugCentral identity provenance in disease explanations", async () => {
    const repository = {
      ...knowledgeRepository,
      findDrugDiseaseAssessments: async () => ({
        findings: [{ enteredCondition: "Renal insufficiency", resolvedDisease: "Chronic kidney disease", diseaseIdentity: "UMLS:C1234567", relationship: "contraindication", assessment: "HIGH", source: "DrugCentral", datasetVersion: "DrugCentral 11012023" }],
        resolutions: [{ enteredCondition: "Renal insufficiency", status: "RESOLVED", matchType: "CONCEPT_SOURCE_ALIAS", diseaseIdentity: "UMLS:C1234567" }],
      }),
    };
    const result = await clinicalSafetyAssessment({ consultation, patient, knowledgeRepository: repository });
    expect(result.drugDisease.explanations[0]).toContain("Entered condition: Renal insufficiency → resolved DrugCentral term: Chronic kidney disease (UMLS:C1234567)");
    expect(result.drugDisease.assessment).toBe("HIGH");
  });

  it("keeps unresolved free-text conditions as no-match without claiming a relationship", async () => {
    const repository = {
      ...knowledgeRepository,
      findDrugDiseaseAssessments: async () => ({ findings: [], resolutions: [{ enteredCondition: "Unmapped local wording", status: "UNRESOLVED" }] }),
    };
    const result = await clinicalSafetyAssessment({ consultation: { ...consultation, candidateGeneric: "No relation candidate" }, patient: { ...patient, medications: [] }, knowledgeRepository: repository });
    expect(result.drugDisease.assessment).toBe("NOT_EVALUATED");
    expect(result.drugDisease.explanations[0]).toContain("could not be deterministically resolved");
  });

  it("keeps allergies out of DDI, drug-disease, and candidate alternatives", async () => {
    const withoutAllergy = await clinicalSafetyAssessment({ consultation, patient, knowledgeRepository });
    const withAllergy = await clinicalSafetyAssessment({ consultation, patient: { ...patient, allergies: [{ display: "Penicillin", severity: "severe" }] }, knowledgeRepository });
    expect(withAllergy).not.toHaveProperty("drugAllergy");
    expect(withAllergy.drugDrug).toEqual(withoutAllergy.drugDrug);
    expect(withAllergy.drugDisease).toEqual(withoutAllergy.drugDisease);
    expect(await recommendations({ consultation, patient: { ...patient, allergies: [{ display: "Penicillin", severity: "severe" }] }, knowledgeRepository, requestId: "test", provider })).toEqual(await recommendations({ consultation, patient, knowledgeRepository, requestId: "test", provider }));
  });

  it("returns DrugCentral indication candidates without a synthetic safety score", async () => {
    const result = await recommendations({ consultation, patient, knowledgeRepository, requestId: "test", provider });
    expect(result).toEqual([expect.objectContaining({ drug: "Paracetamol", source: "DrugCentral", rank: 1 })]);
    expect(result[0]).not.toHaveProperty("riskPct");
    expect(recommendationRankingConfig.candidateSource).toContain("DrugCentral");
  });

  it("keeps dataset-evaluation inputs stable when only allergies change", async () => {
    const patientWithAllergy = { ...patient, allergies: [{ display: "Penicillin", severity: "severe" }], gender: "Female" };
    const patientWithoutAllergy = { ...patient, allergies: [], gender: "Female" };
    const safetyWithAllergy = await clinicalSafetyAssessment({ consultation, patient: patientWithAllergy, knowledgeRepository });
    const safetyWithoutAllergy = await clinicalSafetyAssessment({ consultation, patient: patientWithoutAllergy, knowledgeRepository });
    expect(stableHash(buildRecommendationInput({ consultation, patient: patientWithAllergy, safety: safetyWithAllergy }))).toBe(stableHash(buildRecommendationInput({ consultation, patient: patientWithoutAllergy, safety: safetyWithoutAllergy })));
  });
});
