import { describe, expect, it } from "vitest";
import { adrPrediction, clinicalSafetyAssessment, recommendations } from "./clinicalDemo.js";

const consultation = { id: "consultation-1", candidateGeneric: "Aspirin" };
const patient = {
  age: 60,
  conditions: [],
  allergies: [],
  medications: [{ genericName: "Warfarin", status: "ACTIVE" }],
};

describe("demonstration clinical service contracts", () => {
  it("is deterministic and visibly labels the safety output as demonstration-only", () => {
    const first = clinicalSafetyAssessment({ consultation, patient });
    const second = clinicalSafetyAssessment({ consultation, patient });
    expect(first.status).toBe("DEMONSTRATION_ONLY");
    expect(first.drugDrug.riskPercentage).toBe(88);
    expect(second.drugDrug.riskPercentage).toBe(first.drugDrug.riskPercentage);
  });

  it("keeps ADR disease-independent and returns display-ready bounds", () => {
    const result = adrPrediction({ consultation, patient });
    expect(result.status).toBe("DEMONSTRATION_ONLY");
    expect(result.confidenceInterval.lower).toBeLessThanOrEqual(result.predictedAdrRisk);
    expect(result.confidenceInterval.upper).toBeGreaterThanOrEqual(result.predictedAdrRisk);
  });

  it("creates ordered, non-candidate demonstration alternatives", () => {
    const safety = clinicalSafetyAssessment({ consultation, patient });
    const adr = adrPrediction({ consultation, patient });
    const result = recommendations({ consultation, safety, adr });
    expect(result).toHaveLength(3);
    expect(result.every((item) => item.drug !== "Aspirin")).toBe(true);
    expect(result.map((item) => item.rank)).toEqual([1, 2, 3]);
  });
});
