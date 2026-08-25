import { describe, expect, it } from "vitest";
import { compareRecommendations } from "./recommendationRankingService.js";

const candidate = ({ drug, tier, complete = true, upper = 0.2, set = ["NO_DOCUMENTED_SERIOUS_OUTCOME"], mlStatus = "ok" }) => ({
  drug,
  knownSafetyEvidence: { tier, complete },
  ml: mlStatus ? { status: mlStatus, overall: { conservativeUpperBound: upper, conformal: { predictionSet: set } } } : null,
});

describe("lexicographic P1/P2/P3 ranking", () => {
  it("P1 LOW dominates a better MODERATE ML score", () => {
    expect([candidate({ drug: "B", tier: "MODERATE", upper: 0.1 }), candidate({ drug: "A", tier: "LOW", upper: 0.25 })].sort(compareRecommendations)[0].drug).toBe("A");
  });
  it("uses bootstrap upper bound rather than point probability", () => {
    expect([candidate({ drug: "B", tier: "LOW", upper: 0.29 }), candidate({ drug: "A", tier: "LOW", upper: 0.22 })].sort(compareRecommendations)[0].drug).toBe("A");
  });
  it("uses conformal set only on an exact P1/P2 tie", () => {
    const ambiguous = candidate({ drug: "B", tier: "LOW", upper: 0.2, set: ["NO_DOCUMENTED_SERIOUS_OUTCOME", "SERIOUS_OUTCOME"] });
    const singleton = candidate({ drug: "A", tier: "LOW", upper: 0.2 });
    expect([ambiguous, singleton].sort(compareRecommendations)[0].drug).toBe("A");
  });
  it("HIGH cannot be rescued by favorable ML", () => {
    expect([candidate({ drug: "A", tier: "HIGH", upper: 0.01 }), candidate({ drug: "B", tier: "LOW", upper: 0.5 })].sort(compareRecommendations)[0].drug).toBe("B");
  });
  it("incomplete evidence is not silently treated as complete LOW evidence", () => {
    const unresolved = candidate({ drug: "A", tier: "LOW", complete: false, upper: 0.1 });
    const complete = candidate({ drug: "B", tier: "LOW", complete: true, upper: 0.2 });
    expect([unresolved, complete].sort(compareRecommendations)[0].drug).toBe("B");
  });
  it("missing ML is not imputed as zero", () => {
    const unavailable = candidate({ drug: "A", tier: "LOW", mlStatus: "ML_UNAVAILABLE" });
    const evaluated = candidate({ drug: "B", tier: "LOW", upper: 0.4 });
    expect([unavailable, evaluated].sort(compareRecommendations)[0].drug).toBe("B");
  });
});
