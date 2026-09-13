import { describe, expect, it } from "vitest";
import { compareRecommendations, rankRecommendations } from "./recommendationRankingService.js";

const scored = ({ drug, score, adjusted = score, ddi = 0, disease = 0 }) => ({
  drug,
  finalRiskScore: score,
  components: { lightgbmAdjustedRisk: adjusted, ddiRisk: ddi, drugDiseaseRisk: disease },
});

const consultation = { id: "visit", indication: "Pain", indicationId: "indication", indicationSource: "DrugCentral", indicationNormalized: "PAIN", indicationDatasetVersion: "test", candidateGeneric: "Current drug" };
const patient = { medications: [{ genericName: "Warfarin", status: "ACTIVE" }], conditions: [{ display: "Kidney disease" }] };
const provider = {
  predictBatch: async (inputs) => inputs.map(() => ({
    status: "ok",
    overall: { adjustedRisk: 0.3, conformal: { predictionSet: ["NO_DOCUMENTED_SERIOUS_OUTCOME"] } },
  })),
};
const repository = {
  findCandidateDrugs: async () => [
    { genericDrug: "Current drug" }, { genericDrug: "Lower risk" }, { genericDrug: "Major DDI" }, { genericDrug: "Unknown evidence" },
  ],
  hasDdiDrugEvidence: async (drug) => drug !== "Unknown evidence",
  findPairwiseDrugInteraction: async (drug) => drug === "Major DDI"
    ? { displaySeverity: "MAJOR", rawSeverity: "Major" }
    : null,
  findDrugDiseaseAssessments: async () => ({ findings: [], resolutions: [{ status: "RESOLVED" }] }),
};

describe("safety-aware alternative ranking", () => {
  it("prefers a lower final risk and resolves ties deterministically", () => {
    expect([scored({ drug: "B", score: 0.4 }), scored({ drug: "A", score: 0.2 })].sort(compareRecommendations)[0].drug).toBe("A");
    expect([scored({ drug: "B", score: 0.2, adjusted: 0.3 }), scored({ drug: "A", score: 0.2, adjusted: 0.3 })].sort(compareRecommendations)[0].drug).toBe("A");
  });

  it("excludes a major DDI before any weighted score", async () => {
    const results = await rankRecommendations({ consultation, patient, knowledgeRepository: repository, requestId: "test", provider });
    const major = results.find((item) => item.drug === "Major DDI");
    expect(major).toMatchObject({ status: "NOT_RECOMMENDED", rank: null });
    expect(major).not.toHaveProperty("finalRiskScore");
  });

  it("marks missing evidence for review instead of assigning zero risk", async () => {
    const results = await rankRecommendations({ consultation, patient, knowledgeRepository: repository, requestId: "test", provider });
    const unknown = results.find((item) => item.drug === "Unknown evidence");
    expect(unknown).toMatchObject({ status: "REQUIRES_REVIEW", rank: null });
    expect(unknown).not.toHaveProperty("finalRiskScore");
  });

  it("does not accept HGNN or allergy data as a scoring component", async () => {
    const baseline = await rankRecommendations({ consultation, patient, knowledgeRepository: repository, requestId: "test", provider });
    const withAllergyAndHgnn = await rankRecommendations({
      consultation,
      patient: { ...patient, allergies: [{ display: "Penicillin", severity: "severe" }] },
      knowledgeRepository: repository,
      requestId: "test",
      provider,
    });
    expect(withAllergyAndHgnn).toEqual(baseline);
    expect(baseline.filter((item) => item.status === "RECOMMENDED")[0].components).not.toHaveProperty("hgnnRisk");
  });
});
