import { describe, expect, it } from "vitest";
import { activeSafetyResult, mapAllergyInput, patientResponse } from "./repository.js";

describe("patient allergy profile contract", () => {
  it("preserves clinician-recorded allergy display and severity in the patient response", () => {
    const storedAllergy = mapAllergyInput({ display: "Penicillin", severity: "severe" });
    expect(storedAllergy).toMatchObject({ display: "Penicillin", severity: "severe", source: "clinician-entered" });

    const response = patientResponse({
      id: "patient-1",
      publicId: "P-0001",
      name: "Test Patient",
      age: 40,
      gender: "Female",
      version: 1,
      createdAt: new Date("2026-01-01"),
      updatedAt: new Date("2026-01-01"),
      allergies: [{ id: "allergy-1", ...storedAllergy, reaction: null }],
    });
    expect(response.allergies).toEqual([
      expect.objectContaining({ display: "Penicillin", severity: "severe" }),
    ]);
  });

  it("omits legacy automated drug-allergy output without changing the stored snapshot", () => {
    const legacy = { drugDrug: { riskPercentage: 12 }, drugAllergy: { riskPercentage: 90 }, overall: { riskPercentage: 90 } };
    const active = activeSafetyResult(legacy);
    expect(active).not.toHaveProperty("drugAllergy");
    expect(active.legacyFieldsOmitted).toEqual(["drugAllergy"]);
    expect(legacy.drugAllergy.riskPercentage).toBe(90);
  });
});
