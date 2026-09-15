import { describe, expect, it } from "vitest";
import { createClinicalKnowledgeRepository, ddinterSearchTerms, normalizeDdinterDrugName } from "./clinicalKnowledgeRepository.js";

describe("DDInter terminology alignment", () => {
  it("aligns Crocin's paracetamol ingredient with DDInter's acetaminophen term", () => {
    expect(ddinterSearchTerms("Paracetamol")).toEqual(["acetaminophen"]);
    expect(ddinterSearchTerms("Paracetamol/Acetaminophen + Tramadol")).toEqual(["acetaminophen", "tramadol"]);
  });

  it("removes only redundant DDInter parenthetical qualifiers", () => {
    expect(normalizeDdinterDrugName("Insulin aspart (aspart)")).toBe("insulin aspart");
    expect(normalizeDdinterDrugName("Insulin aspart (aspart protamine)")).toBe("insulin aspart aspart protamine");
    expect(normalizeDdinterDrugName("Hydrocortisone (topical)")).toBe("hydrocortisone topical");
  });

  it("finds the known DDInter acetaminophen-warfarin interaction for paracetamol", async () => {
    const findMany = async () => [{ normalizedDrugA: "acetaminophen", normalizedDrugB: "warfarin", drugA: "Acetaminophen", drugB: "Warfarin", rawSeverity: "Moderate", displaySeverity: "MODERATE", source: "DDInter 2.0", datasetVersion: "DDInter 2.0 import 2026-08-11", ddinterIdA: "DDInter14", ddinterIdB: "DDInter1951", importedAt: new Date() }];
    const repository = createClinicalKnowledgeRepository({ drugInteractionKnowledge: { findMany } });
    await expect(repository.findPairwiseDrugInteraction("Paracetamol", "Warfarin")).resolves.toMatchObject({ drugA: "Acetaminophen", drugB: "Warfarin", displaySeverity: "MODERATE" });
  });

  it("distinguishes a successful empty pair lookup from unresolved input", async () => {
    const records = [
      { normalizedDrugA: "acetaminophen", normalizedDrugB: "warfarin", drugA: "Acetaminophen", drugB: "Warfarin", ddinterIdA: "DDInter14", ddinterIdB: "DDInter1951", displaySeverity: "MODERATE", source: "DDInter 2.0" },
      { normalizedDrugA: "epinephrine", normalizedDrugB: "insulin aspart aspart", drugA: "Epinephrine", drugB: "Insulin aspart (aspart)", ddinterIdA: "DDInter652", ddinterIdB: "DDInter929", displaySeverity: "MODERATE", source: "DDInter 2.0" },
    ];
    const client = { drugInteractionKnowledge: { findMany: async ({ where }) => where.OR.some((item) => item.ddinterIdA || item.ddinterIdB) ? [] : records } };
    const repository = createClinicalKnowledgeRepository(client);

    await expect(repository.evaluateDdiPair("Insulin aspart", "Paracetamol")).resolves.toMatchObject({ status: "NO_DOCUMENTED_INTERACTION", lookupCompleted: true });
    await expect(repository.evaluateDdiPair("Unknown candidate", "Paracetamol")).resolves.toMatchObject({ status: "UNRESOLVED", lookupCompleted: false });
  });

  it("returns a protected failure state when the DDInter lookup throws", async () => {
    const repository = createClinicalKnowledgeRepository({ drugInteractionKnowledge: { findMany: async () => { throw new Error("database offline"); } } });
    await expect(repository.evaluateDdiPair("Ibuprofen", "Warfarin")).resolves.toMatchObject({ status: "LOOKUP_FAILED", lookupCompleted: false });
  });
});

const diseaseIdentity = "UMLS:C1234567";
const diseaseTerm = {
  diseaseIdentity,
  existingDisease: "Chronic kidney disease",
  normalizedDisease: "chronic kidney disease",
  conceptName: "Renal insufficiency",
  normalizedConceptName: "renal insufficiency",
  umlsCui: "C1234567",
  snomedName: "Chronic kidney disease",
  normalizedSnomedName: "chronic kidney disease",
  source: "DrugCentral",
  datasetVersion: "DrugCentral 11012023",
  importedAt: new Date(),
};
const diseaseRelationship = {
  ...diseaseTerm,
  genericDrug: "Ibuprofen",
  normalizedDrug: "ibuprofen",
  relationship: "contraindication",
  assessment: "HIGH",
  evidence: "contraindication | Renal insufficiency | C1234567",
};

const diseaseRepository = ({ resolve = [diseaseTerm], relationships = [diseaseRelationship] } = {}) =>
  createClinicalKnowledgeRepository({
    drugDiseaseKnowledge: {
      findMany: async ({ where }) => (where.normalizedDrug ? relationships : resolve),
    },
  });

describe("DrugCentral disease identity resolution", () => {
  it("retains an exact canonical disease match and its HIGH relationship", async () => {
    const result = await diseaseRepository().findDrugDiseaseAssessments("Ibuprofen", [{ display: "Chronic kidney disease" }]);
    expect(result.resolutions[0]).toMatchObject({ status: "RESOLVED", matchType: "CANONICAL_TERM", diseaseIdentity });
    expect(result.findings[0]).toMatchObject({ enteredCondition: "Chronic kidney disease", resolvedDisease: "Chronic kidney disease", assessment: "HIGH" });
  });

  it("resolves an exact DrugCentral concept-name alias to the same identity", async () => {
    const result = await diseaseRepository().findDrugDiseaseAssessments("Ibuprofen", [{ display: "Renal insufficiency" }]);
    expect(result.resolutions[0]).toMatchObject({ status: "RESOLVED", matchType: "CONCEPT_SOURCE_ALIAS", diseaseIdentity });
    expect(result.findings[0]).toMatchObject({ enteredCondition: "Renal insufficiency", resolvedDisease: "Chronic kidney disease" });
  });

  it("resolves an exact UMLS condition code without using free-text similarity", async () => {
    const result = await diseaseRepository().findDrugDiseaseAssessments("Ibuprofen", [{ display: "Legacy local text", code: "UMLS:C1234567" }]);
    expect(result.resolutions[0]).toMatchObject({ status: "RESOLVED", matchType: "UMLS_IDENTIFIER", umlsCui: "C1234567" });
    expect(result.findings).toHaveLength(1);
  });

  it("does not claim a relationship for unrelated free text", async () => {
    const result = await diseaseRepository({ resolve: [] }).findDrugDiseaseAssessments("Ibuprofen", [{ display: "Completely unrelated condition" }]);
    expect(result.resolutions[0]).toMatchObject({ status: "UNRESOLVED", enteredCondition: "Completely unrelated condition" });
    expect(result.findings).toEqual([]);
  });

  it("keeps a resolved condition as no-match when the proposed drug has no relationship", async () => {
    const result = await diseaseRepository({ relationships: [] }).findDrugDiseaseAssessments("Ibuprofen", [{ display: "Renal insufficiency" }]);
    expect(result.resolutions[0].status).toBe("RESOLVED");
    expect(result.findings).toEqual([]);
  });
});
