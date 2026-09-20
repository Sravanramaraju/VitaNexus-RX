import { describe, expect, it, vi } from "vitest";
import { buildAdrPredictionInput, createPythonAdrPredictionProvider } from "./adrPredictionProvider.js";

const valid = {
  status: "ok",
  artifactMode: "FULL",
  model: "LightGBM", modelVersion: "l",
  versions: { preprocessing: "p", features: "f", lightgbm: "l", bootstrap: "b", conformal: "c" },
  overall: { task: "serious-outcome classification among FAERS adverse-event reports", riskProbability: 0.2, riskPercent: 20, uncertainty: { method: "bootstrap_model_variability", level: 0.9, lower: 0.1, upper: 0.3, replicas: 20 }, adjustedRisk: 0.3, conformal: { method: "split_conformal_classification", targetCoverage: 0.9, qHat: 0.7, predictionSet: ["NO_DOCUMENTED_SERIOUS_OUTCOME"], setSize: 1, reliability: "FOCUSED_NO_DOCUMENTED_SERIOUS_OUTCOME", interpretation: "Focused", calibrationVersion: "c", interval: null, intervalNote: "Prediction set" } },
  inputCoverage: { sexKnown: true, candidateKnown: true, indicationKnown: true, recognizedCurrentMedications: 1, unknownCurrentMedications: [] }, dataWindow: { fit: "2022Q1-2025Q2" }, generatedAt: new Date().toISOString(), clinicalInterpretation: { population: "FAERS", limitations: ["bias"] },
};

const outOfVocabulary = {
  status: "OUT_OF_VOCABULARY", artifactMode: "FULL", model: "LightGBM", modelVersion: "l",
  versions: valid.versions,
  inputCoverage: { sexKnown: true, candidateKnown: true, indicationKnown: false, recognizedCurrentMedications: 1, unknownCurrentMedications: [] },
  normalizedInput: { sex: "M", candidateDrug: "DEFERASIROX", indication: "DIAGNOSTIC AID", currentMedications: ["PARACETAMOL"] },
  dataWindow: valid.dataWindow, generatedAt: valid.generatedAt, message: "Unsupported indication; no score was calculated.",
};

describe("Python ADR provider", () => {
  it("validates and returns a real service response", async () => {
    const fetchImplementation = vi.fn(async () => ({ ok: true, json: async () => valid }));
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation });
    const result = await provider.predict({ requestId: "r" });
    expect(result.status).toBe("ok");
    expect(result.artifactMode).toBe("FULL");
    expect(result.overall.adjustedRisk).toBe(0.3);
    expect(result).not.toHaveProperty("specificAdrs");
  });
  it("never converts an unreachable service to LOW or zero", async () => {
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation: async () => { throw new Error("offline"); } });
    const result = await provider.predict({ requestId: "r" });
    expect(result.status).toBe("INFERENCE_FAILED");
    expect(result).not.toHaveProperty("overall");
  });
  it("includes FastAPI validation detail in an HTTP failure", async () => {
    const provider = createPythonAdrPredictionProvider({
      baseUrl: "http://ml",
      fetchImplementation: async () => ({
        ok: false,
        status: 422,
        json: async () => ({ detail: [{ msg: "Input should be 'DrugCentral'" }] }),
      }),
    });
    const result = await provider.predict({ requestId: "r" });
    expect(result.status).toBe("ML_UNAVAILABLE");
    expect(result.message).toContain("HTTP 422: Input should be 'DrugCentral'");
  });
  it("rejects malformed confidence-like output", async () => {
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation: async () => ({ ok: true, json: async () => ({ ...valid, overall: { ...valid.overall, adjustedRisk: 0 } }) }) });
    expect((await provider.predict({ requestId: "r" })).status).toBe("INFERENCE_FAILED");
  });
  it("rejects a smoke artifact rather than treating it as clinical evidence", async () => {
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation: async () => ({ ok: true, json: async () => ({ ...valid, artifactMode: "FAST_SMOKE" }) }) });
    expect((await provider.predict({ requestId: "r" })).status).toBe("INFERENCE_FAILED");
  });
  it("preserves an out-of-vocabulary result without inventing a score", async () => {
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation: async () => ({ ok: true, json: async () => outOfVocabulary }) });
    const result = await provider.predict({ requestId: "r" });
    expect(result.status).toBe("OUT_OF_VOCABULARY");
    expect(result.inputCoverage.indicationKnown).toBe(false);
    expect(result).not.toHaveProperty("overall");
  });
  it("accepts a degraded current-medication estimate with its explicit status", async () => {
    const degraded = {
      ...valid,
      status: "DEGRADED_COVERAGE",
      inputCoverage: { ...valid.inputCoverage, unknownCurrentMedications: ["UNLISTED MEDICINE"] },
      message: "Incomplete medication coverage.",
    };
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation: async () => ({ ok: true, json: async () => degraded }) });
    const result = await provider.predict({ requestId: "r" });
    expect(result.status).toBe("DEGRADED_COVERAGE");
    expect(result.overall.adjustedRisk).toBe(0.3);
    expect(result.inputCoverage.unknownCurrentMedications).toEqual(["UNLISTED MEDICINE"]);
  });
  it("checks complete-request and terminology coverage", async () => {
    const fetchImplementation = vi.fn(async (url) => ({
      ok: true,
      json: async () => url.endsWith("term-coverage")
        ? { status: "ok", modelVersion: "l", candidates: [], indications: [{ input: "Iron overload", normalized: "IRON OVERLOAD", supported: true }], medications: [] }
        : { status: "OUT_OF_VOCABULARY", inputCoverage: outOfVocabulary.inputCoverage, normalizedInput: outOfVocabulary.normalizedInput },
    }));
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation });
    expect((await provider.checkCoverage({ requestId: "r" })).status).toBe("OUT_OF_VOCABULARY");
    expect((await provider.checkTerms({ indications: ["Iron overload"] })).indications[0].supported).toBe(true);
  });
  it("maps stored Male/Female values to the protected M/F feature contract", () => {
    const input = buildAdrPredictionInput({
      requestId: "r",
      consultation: { candidateGeneric: "Deferasirox", indicationId: "i", indication: "Iron overload", indicationSource: "DrugCentral" },
      patient: { age: 20, gender: "Male", medications: [] },
    });
    expect(input.patient.sex).toBe("M");
  });
});
