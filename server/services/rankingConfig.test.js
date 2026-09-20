import { describe, expect, it } from "vitest";
import {
  RANKING_WEIGHT_TOTAL,
  RANKING_WEIGHTS,
  DEGRADED_ADR_RANKING_WEIGHTS,
  COVERAGE_PENALTY_RISK,
  normalizeDdiRisk,
  normalizeDrugDiseaseRisk,
} from "./rankingConfig.js";

describe("safety-aware ranking configuration", () => {
  it("uses exactly the locked 50/30/20 weighting", () => {
    expect(RANKING_WEIGHTS).toEqual({ adjustedLightgbmRisk: 0.5, ddiRisk: 0.3, drugDiseaseRisk: 0.2 });
    expect(RANKING_WEIGHT_TOTAL).toBe(1);
  });

  it("uses a conservative complete-score penalty when ADR medication coverage is degraded", () => {
    expect(DEGRADED_ADR_RANKING_WEIGHTS).toEqual({ adjustedLightgbmRisk: 0.25, ddiRisk: 0.3, drugDiseaseRisk: 0.2, coveragePenalty: 0.25 });
    expect(COVERAGE_PENALTY_RISK).toBe(1);
  });

  it("keeps missing evidence distinct from known low risk", () => {
    expect(normalizeDdiRisk("NOT_EVALUATED")).toBeNull();
    expect(normalizeDdiRisk("UNKNOWN_STATUS")).toBeNull();
    expect(normalizeDdiRisk("MINOR")).toBe(0.1);
    expect(normalizeDdiRisk("NO_DOCUMENTED_INTERACTION")).toBe(0.3);
    expect(normalizeDdiRisk("MODERATE")).toBe(0.5);
    expect(normalizeDrugDiseaseRisk("NOT_EVALUATED")).toBeNull();
    expect(normalizeDrugDiseaseRisk("LOW")).toBe(0.1);
    expect(normalizeDrugDiseaseRisk("NO_DOCUMENTED_RELATIONSHIP")).toBe(0.3);
    expect(normalizeDrugDiseaseRisk("MODERATE")).toBe(0.5);
  });
});
