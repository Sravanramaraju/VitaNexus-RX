import { describe, expect, it } from "vitest";
import { stableHash } from "../utils.js";
import { buildAdrPredictionInput } from "./adrPredictionProvider.js";
import { adrPrediction, clinicalSafetyAssessment, recommendationRankingConfig, recommendations } from "./clinicalDemo.js";
import { buildRecommendationInput } from "./recommendationRankingService.js";

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

  it("excludes clinician-recorded allergies from every automated safety result", () => {
    const withoutAllergy = clinicalSafetyAssessment({ consultation, patient });
    const withAllergy = clinicalSafetyAssessment({
      consultation,
      patient: { ...patient, allergies: [{ display: "Penicillin", severity: "severe" }] },
    });

    expect(withAllergy).not.toHaveProperty("drugAllergy");
    expect(withAllergy.drugDrug).toEqual(withoutAllergy.drugDrug);
    expect(withAllergy.drugDisease).toEqual(withoutAllergy.drugDisease);
    expect(withAllergy.overall).toEqual(withoutAllergy.overall);
  });

  it("keeps ADR disease-independent and returns display-ready bounds", async () => {
    const input = buildAdrPredictionInput({ consultation, patient: { ...patient, gender: "Female" } });
    const result = await adrPrediction(input);
    expect(result.status).toBe("DEMONSTRATION_ONLY");
    expect(input).not.toHaveProperty("conditions");
    expect(input).not.toHaveProperty("allergies");
    expect(result.modelName).toBe("vitanexus-demo-adr");
    expect(result.confidenceInterval.lower).toBeLessThanOrEqual(result.predictedAdrRisk);
    expect(result.confidenceInterval.upper).toBeGreaterThanOrEqual(result.predictedAdrRisk);
  });

  it("creates ordered, non-candidate demonstration alternatives", async () => {
    const safety = clinicalSafetyAssessment({ consultation, patient });
    const adr = await adrPrediction(buildAdrPredictionInput({ consultation, patient: { ...patient, gender: "Female" } }));
    const result = recommendations({ consultation, safety, adr });
    expect(result).toHaveLength(3);
    expect(result.every((item) => item.drug !== "Aspirin")).toBe(true);
    expect(result.map((item) => item.rank)).toEqual([1, 2, 3]);
    expect(recommendationRankingConfig.weightsStatus).toBe("PROVISIONAL");
  });

  it("keeps ADR and recommendation input hashes stable when only allergies change", async () => {
    const patientWithAllergy = { ...patient, allergies: [{ display: "Penicillin", severity: "severe" }], gender: "Female" };
    const patientWithoutAllergy = { ...patient, allergies: [], gender: "Female" };
    const adrInputWithAllergy = buildAdrPredictionInput({ consultation, patient: patientWithAllergy });
    const adrInputWithoutAllergy = buildAdrPredictionInput({ consultation, patient: patientWithoutAllergy });
    expect(stableHash(adrInputWithAllergy)).toBe(stableHash(adrInputWithoutAllergy));

    const safetyWithAllergy = clinicalSafetyAssessment({ consultation, patient: patientWithAllergy });
    const safetyWithoutAllergy = clinicalSafetyAssessment({ consultation, patient: patientWithoutAllergy });
    const adr = await adrPrediction(adrInputWithoutAllergy);
    const recommendationInputWithAllergy = buildRecommendationInput({ consultation, safety: safetyWithAllergy, adr });
    const recommendationInputWithoutAllergy = buildRecommendationInput({ consultation, safety: safetyWithoutAllergy, adr });
    expect(stableHash(recommendationInputWithAllergy)).toBe(stableHash(recommendationInputWithoutAllergy));
    expect(recommendations({ consultation, safety: safetyWithAllergy, adr })).toEqual(
      recommendations({ consultation, safety: safetyWithoutAllergy, adr }),
    );
  });
});
