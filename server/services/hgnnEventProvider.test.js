import { describe, expect, it, vi } from "vitest";
import { buildHgnnPredictionInput, createPythonHgnnEventProvider } from "./hgnnEventProvider.js";

const metadata = {
  modelType: "HGNN",
  modelFamily: "HGNN",
  modelStage: "BASELINE",
  validationStatus: "AUDIT_PENDING",
  modelVersion: "faers-specific-adr-hgnn-1.0.0",
  checkpointVersion: "a".repeat(64),
  trainingEpoch: 20,
  eventVocabularyVersion: "vocabulary-identity",
  eventVocabularySize: 100,
  graphSchemaVersion: "faers-hgnn-colab-training-2.0.0",
  featureSchemaVersion: "faers-hgnn-colab-training-2.0.0",
  device: "cpu",
  topK: 10,
  nodeTypes: ["report", "drug", "indication", "adr"],
  edgeTypes: [["report", "primary_suspect", "drug"]],
  supportedInputs: ["age", "sex", "candidateDrug", "indication", "currentMedications"],
  eventScoreType: "BASELINE_MODEL_SCORE",
  rankingInfluence: "none",
};

const prediction = {
  ...metadata,
  status: "SUCCESS",
  coverage: { status: "FULL", unknownEntities: [] },
  inputHash: "b".repeat(64),
  events: [
    { eventCode: null, eventName: "NAUSEA", eventScore: 0.31, displayPercent: 31, rank: 1 },
    { eventCode: null, eventName: "FATIGUE", eventScore: 0.2, displayPercent: 20, rank: 2 },
  ],
  generatedAt: new Date().toISOString(),
  interpretation: "Baseline model scores, not patient-incidence probabilities.",
};

describe("Python HGNN event provider", () => {
  it("validates status and actual ordered baseline scores", async () => {
    const fetchImplementation = vi.fn(async (url) => ({ ok: true, json: async () => url.endsWith("/status") ? { ...metadata, status: "READY" } : prediction }));
    const provider = createPythonHgnnEventProvider({ baseUrl: "http://ml", fetchImplementation });
    expect((await provider.getStatus()).status).toBe("READY");
    const result = await provider.predict({ requestId: "r" });
    expect(result.events.map((event) => event.eventName)).toEqual(["NAUSEA", "FATIGUE"]);
    expect(result.rankingInfluence).toBe("none");
    expect(result).not.toHaveProperty("probability");
  });

  it("rejects unsorted, non-finite, or malformed model output", async () => {
    const malformed = { ...prediction, events: [prediction.events[1], prediction.events[0]] };
    const provider = createPythonHgnnEventProvider({ baseUrl: "http://ml", fetchImplementation: async () => ({ ok: true, json: async () => malformed }) });
    const result = await provider.predict({ requestId: "r" });
    expect(result.status).toBe("INFERENCE_FAILED");
    expect(result.events).toEqual([]);
  });

  it("never substitutes zeros when the service is unavailable", async () => {
    const provider = createPythonHgnnEventProvider({ baseUrl: "http://ml", fetchImplementation: async () => { throw new Error("offline"); } });
    const result = await provider.predict({ requestId: "r" });
    expect(result.status).toBe("INFERENCE_FAILED");
    expect(result.events).toEqual([]);
    expect(result).not.toHaveProperty("eventScore");
  });

  it("builds only the five supported consultation inputs", () => {
    const input = buildHgnnPredictionInput({
      requestId: "r",
      consultation: { candidateGeneric: "Deferasirox", indication: "Iron overload" },
      patient: {
        age: 42,
        gender: "FEMALE",
        medications: [
          { genericName: "Warfarin", status: "ACTIVE" },
          { genericName: "Ibuprofen", status: "STOPPED" },
        ],
      },
    });
    expect(input).toEqual({
      requestId: "r",
      patient: { age: 42, sex: "F", currentMedications: ["Warfarin"] },
      candidateDrug: { canonicalName: "Deferasirox" },
      indication: { name: "Iron overload" },
    });
  });
});
