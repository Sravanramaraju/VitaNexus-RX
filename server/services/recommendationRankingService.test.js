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
  evaluateDdiPair: async (drug) => drug === "Major DDI"
    ? { status: "DOCUMENTED_INTERACTION", lookupCompleted: true, interaction: { displaySeverity: "MAJOR", rawSeverity: "Major" } }
    : drug === "Unknown evidence"
      ? { status: "UNRESOLVED", lookupCompleted: false, candidateResolution: { status: "UNRESOLVED" }, existingResolution: { status: "RESOLVED" } }
      : { status: "NO_DOCUMENTED_INTERACTION", lookupCompleted: true, candidateResolution: { status: "RESOLVED" }, existingResolution: { status: "RESOLVED" } },
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

  it("allows a resolved successful empty DDInter result to continue into ranking", async () => {
    const results = await rankRecommendations({ consultation, patient, knowledgeRepository: repository, requestId: "test", provider });
    const empty = results.find((item) => item.drug === "Lower risk");
    expect(empty).toMatchObject({
      status: "RECOMMENDED",
      drugDrug: { severity: "NO_DOCUMENTED_INTERACTION", complete: true, normalizedRisk: 0.3 },
      drugDisease: { assessment: "NO_DOCUMENTED_RELATIONSHIP", complete: true, normalizedRisk: 0.3 },
    });
    expect(empty.rank).toBeTypeOf("number");
  });

  it("keeps an actual lookup failure behind the clinical-review gate", async () => {
    const failedRepository = { ...repository, evaluateDdiPair: async () => ({ status: "LOOKUP_FAILED", lookupCompleted: false }) };
    const results = await rankRecommendations({ consultation, patient, knowledgeRepository: failedRepository, requestId: "test", provider });
    expect(results.find((item) => item.drug === "Lower risk")).toMatchObject({ status: "REQUIRES_REVIEW", rank: null, drugDrug: { complete: false } });
  });

  it("does not mislabel a passed safety gate as clinical review when LightGBM input needs correction", async () => {
    const outOfVocabularyProvider = {
      predictBatch: async (inputs) => inputs.map(() => ({
        status: "OUT_OF_VOCABULARY",
        inputCoverage: { indicationKnown: false, candidateKnown: true, sexKnown: true, unknownCurrentMedications: [] },
      })),
    };
    const results = await rankRecommendations({ consultation, patient, knowledgeRepository: repository, requestId: "test", provider: outOfVocabularyProvider });
    expect(results.find((item) => item.drug === "Lower risk")).toMatchObject({
      status: "INPUT_CORRECTION_NEEDED",
      assessment: "INPUT_CORRECTION_NEEDED",
      gate: { status: "ELIGIBLE" },
      drugDrug: { severity: "NO_DOCUMENTED_INTERACTION", complete: true },
    });
  });

  it("ranks a degraded ADR estimate with half the normal LightGBM weight and a coverage penalty", async () => {
    const degradedProvider = {
      predictBatch: async (inputs) => inputs.map(() => ({
        status: "DEGRADED_COVERAGE",
        overall: { adjustedRisk: 0.3, conformal: { predictionSet: ["NO_DOCUMENTED_SERIOUS_OUTCOME"] } },
      })),
    };
    const results = await rankRecommendations({ consultation, patient, knowledgeRepository: repository, requestId: "test", provider: degradedProvider });
    const candidate = results.find((item) => item.drug === "Lower risk");
    expect(candidate).toMatchObject({
      status: "RECOMMENDED",
      ml: { status: "DEGRADED_COVERAGE" },
      components: {
        lightgbmWeight: 0.25,
        ddiWeight: 0.3,
        drugDiseaseWeight: 0.2,
        coveragePenaltyWeight: 0.25,
        coveragePenaltyRisk: 1,
      },
    });
    expect(candidate.finalRiskScore).toBeCloseTo(0.475);
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
