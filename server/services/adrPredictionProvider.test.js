import { describe, expect, it, vi } from "vitest";
import { createPythonAdrPredictionProvider } from "./adrPredictionProvider.js";

const valid = {
  status: "ok",
  artifactMode: "FULL",
  versions: { preprocessing: "p", features: "f", lightgbm: "l", bootstrap: "b", conformal: "c", hgnn: "h" },
  overall: { task: "serious-outcome classification among FAERS adverse-event reports", calibratedProbability: 0.2, uncertainty: { method: "bootstrap", level: 0.9, lower: 0.1, upper: 0.3, replicas: 20 }, conservativeUpperBound: 0.3, conformal: { method: "split_conformal", targetCoverage: 0.9, qHat: 0.7, predictionSet: ["NO_DOCUMENTED_SERIOUS_OUTCOME"], setSize: 1, calibrationVersion: "c" } },
  specificAdrs: [{ term: "Nausea", score: 0.4 }], inputCoverage: { candidateKnown: true, indicationKnown: true, recognizedCurrentMedications: 1, unknownCurrentMedications: [] }, dataWindow: { fit: "2022Q1-2025Q2" }, generatedAt: new Date().toISOString(), clinicalInterpretation: { population: "FAERS", limitations: ["bias"] },
};

describe("Python ADR provider", () => {
  it("validates and returns a real service response", async () => {
    const fetchImplementation = vi.fn(async () => ({ ok: true, json: async () => valid }));
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation });
    const result = await provider.predict({ requestId: "r" });
    expect(result.status).toBe("ok");
    expect(result.artifactMode).toBe("FULL");
    expect(result.overall.conservativeUpperBound).toBe(0.3);
  });
  it("never converts an unreachable service to LOW or zero", async () => {
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation: async () => { throw new Error("offline"); } });
    const result = await provider.predict({ requestId: "r" });
    expect(result.status).toBe("INFERENCE_FAILED");
    expect(result).not.toHaveProperty("overall");
  });
  it("rejects malformed confidence-like output", async () => {
    const provider = createPythonAdrPredictionProvider({ baseUrl: "http://ml", fetchImplementation: async () => ({ ok: true, json: async () => ({ ...valid, overall: { ...valid.overall, conservativeUpperBound: 0 } }) }) });
    expect((await provider.predict({ requestId: "r" })).status).toBe("INFERENCE_FAILED");
  });
});
