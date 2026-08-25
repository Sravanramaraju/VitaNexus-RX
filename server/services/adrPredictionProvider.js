import { z } from "zod";
import { config } from "../config.js";

export const ADR_INPUT_CONTRACT_VERSION = "vitanexus-adr-faers-input-2.0";
export const ADR_PROVIDER_VERSION = "python-faers-provider-1.0.0";

const conformalLabels = z.enum(["NO_DOCUMENTED_SERIOUS_OUTCOME", "SERIOUS_OUTCOME"]);
const successfulPredictionSchema = z.object({
  status: z.enum(["ok", "DEGRADED_COVERAGE"]),
  artifactMode: z.enum(["FULL", "FAST_SMOKE"]),
  versions: z.object({
    preprocessing: z.string().min(1),
    features: z.string().min(1).optional(),
    lightgbm: z.string().min(1),
    bootstrap: z.string().min(1),
    conformal: z.string().min(1),
    hgnn: z.string().min(1),
  }),
  overall: z.object({
    task: z.literal("serious-outcome classification among FAERS adverse-event reports"),
    calibratedProbability: z.number().min(0).max(1),
    uncertainty: z.object({ method: z.literal("bootstrap"), level: z.literal(0.9), lower: z.number().min(0).max(1), upper: z.number().min(0).max(1), replicas: z.number().int().positive().optional() }),
    conservativeUpperBound: z.number().min(0).max(1),
    conformal: z.object({ method: z.literal("split_conformal"), targetCoverage: z.literal(0.9), qHat: z.number().min(0).max(1), predictionSet: z.array(conformalLabels).max(2), setSize: z.number().int().min(0).max(2), calibrationVersion: z.string().min(1) }),
  }),
  specificAdrs: z.array(z.object({ term: z.string().min(1).max(255), score: z.number().min(0).max(1) })).max(100),
  inputCoverage: z.object({ candidateKnown: z.boolean(), indicationKnown: z.boolean(), recognizedCurrentMedications: z.number().int().nonnegative(), unknownCurrentMedications: z.array(z.string()) }),
  dataWindow: z.record(z.string(), z.string()),
  generatedAt: z.string(),
  clinicalInterpretation: z.object({ population: z.string(), limitations: z.array(z.string()) }),
}).superRefine((value, context) => {
  if (value.overall.uncertainty.lower > value.overall.uncertainty.upper) context.addIssue({ code: "custom", message: "Bootstrap lower bound exceeds upper bound." });
  if (value.overall.conservativeUpperBound !== value.overall.uncertainty.upper) context.addIssue({ code: "custom", message: "Conservative upper bound must equal the bootstrap upper bound." });
  if (value.overall.conformal.setSize !== value.overall.conformal.predictionSet.length) context.addIssue({ code: "custom", message: "Conformal setSize does not match predictionSet." });
});

const unavailableResult = (status, message) => ({
  status,
  providerName: "PythonAdrModelProvider",
  providerVersion: ADR_PROVIDER_VERSION,
  message,
  generatedAt: new Date().toISOString(),
});

export const buildAdrPredictionInput = ({ consultation, patient, requestId, candidateGeneric = consultation.candidateGeneric }) => ({
  requestId,
  patient: {
    age: patient.age,
    sex: patient.gender,
    currentMedications: patient.medications
      .filter((medicine) => medicine.status === "ACTIVE")
      .map((medicine) => medicine.genericName)
      .sort(),
  },
  candidateDrug: {
    canonicalName: candidateGeneric,
    ingredients: String(candidateGeneric).split(/[+/]/).map((value) => value.trim()).filter(Boolean),
  },
  indication: {
    id: consultation.indicationId,
    name: consultation.indication,
    source: consultation.indicationSource,
  },
});

export const createPythonAdrPredictionProvider = ({ baseUrl = config.adrMlBaseUrl, timeoutMs = config.adrMlTimeoutMs, fetchImplementation = globalThis.fetch } = {}) => {
  const request = async (path, body) => {
    if (!baseUrl) return unavailableResult("ML_UNAVAILABLE", "ADR_ML_BASE_URL is not configured.");
    try {
      const response = await fetchImplementation(`${baseUrl.replace(/\/$/, "")}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-request-id": body.requestId || body.requests?.[0]?.requestId || "unknown" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!response.ok) return unavailableResult("ML_UNAVAILABLE", `ML service returned HTTP ${response.status}.`);
      return await response.json();
    } catch (error) {
      return unavailableResult(error?.name === "TimeoutError" ? "ML_UNAVAILABLE" : "INFERENCE_FAILED", error?.name === "TimeoutError" ? "ML service request timed out." : "ML service could not be reached.");
    }
  };

  return Object.freeze({
    providerName: "PythonAdrModelProvider",
    modelName: "faers-serious-lightgbm-and-specific-adr-hgnn",
    modelVersion: ADR_PROVIDER_VERSION,
    async predict(input) {
      const response = await request("/v1/predict", input);
      if (["ML_UNAVAILABLE", "INFERENCE_FAILED"].includes(response.status)) return response;
      const parsed = successfulPredictionSchema.safeParse(response);
      return parsed.success ? { ...parsed.data, providerName: this.providerName, providerVersion: ADR_PROVIDER_VERSION, inputContractVersion: ADR_INPUT_CONTRACT_VERSION } : unavailableResult("INFERENCE_FAILED", "ML service response failed contract validation.");
    },
    async predictBatch(inputs) {
      if (!inputs.length) return [];
      const response = await request("/v1/predict-batch", { requests: inputs });
      if (["ML_UNAVAILABLE", "INFERENCE_FAILED"].includes(response.status)) return inputs.map(() => response);
      if (!Array.isArray(response.items) || response.items.length !== inputs.length) return inputs.map(() => unavailableResult("INFERENCE_FAILED", "ML batch response failed contract validation."));
      return response.items.map((item) => {
        if (item.error) return unavailableResult(item.error.status || "INFERENCE_FAILED", item.error.message || "ML inference failed.");
        const parsed = successfulPredictionSchema.safeParse(item.result);
        return parsed.success ? { ...parsed.data, providerName: this.providerName, providerVersion: ADR_PROVIDER_VERSION, inputContractVersion: ADR_INPUT_CONTRACT_VERSION } : unavailableResult("INFERENCE_FAILED", "ML service response failed contract validation.");
      });
    },
  });
};

export const adrPredictionProvider = createPythonAdrPredictionProvider();
