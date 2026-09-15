import { describe, expect, it } from "vitest";
import { activeSafetyResult, consultationResponse, mapAllergyInput, patientResponse } from "./repository.js";
import { CLINICAL_ENGINE_VERSION } from "./services/clinicalEngineVersion.js";
import { rankingConfig } from "./services/rankingConfig.js";

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
    const legacy = { drugDrug: { severity: "MINOR" }, drugAllergy: { legacyOnly: true }, overall: { assessment: "LOW" } };
    const active = activeSafetyResult(legacy);
    expect(active).not.toHaveProperty("drugAllergy");
    expect(active.legacyFieldsOmitted).toEqual(["drugAllergy"]);
    expect(legacy.drugAllergy.legacyOnly).toBe(true);
  });

  it("does not expose a stale recommendation contract after the safety order changes", () => {
    const base = {
      id: "consultation-1",
      patientId: "patient-1",
      indication: "Pain",
      candidateGeneric: "Ibuprofen",
      status: "IN_PROGRESS",
      version: 1,
      createdAt: new Date("2026-01-01"),
      updatedAt: new Date("2026-01-01"),
      analyses: [],
      adrPredictions: [],
      hgnnEventPredictions: [],
      notes: [],
      followUps: [],
    };
    expect(consultationResponse({
      ...base,
      recommendations: [{ engineVersion: `${CLINICAL_ENGINE_VERSION}|old-ranking|hash`, recommendations: [{ drug: "stale" }] }],
    }).recommendations).toBeNull();
    expect(consultationResponse({
      ...base,
      recommendations: [{ engineVersion: `${CLINICAL_ENGINE_VERSION}|${rankingConfig.configId}|hash`, recommendations: [{ drug: "current" }] }],
    }).recommendations).toEqual([{ drug: "current" }]);
  });
});
