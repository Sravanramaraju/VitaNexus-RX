import { z } from "zod";
import { config } from "../config.js";

// Version 5 invalidates strict-coverage rows. Current-medication terms outside
// the vocabulary now receive an explicitly degraded result, while unresolved
// candidate, indication, and sex inputs remain unscored.
export const ADR_INPUT_CONTRACT_VERSION = "vitanexus-lightgbm-overall-risk-input-5.0";
export const ADR_PROVIDER_VERSION = "python-lightgbm-provider-2.0.0";

const conformalLabels = z.enum(["NO_DOCUMENTED_SERIOUS_OUTCOME", "SERIOUS_OUTCOME"]);
const inputCoverageSchema = z.object({
  sexKnown: z.boolean(),
  candidateKnown: z.boolean(),
  indicationKnown: z.boolean(),
  recognizedCurrentMedications: z.number().int().nonnegative(),
  unknownCurrentMedications: z.array(z.string()),
});

const versionSchema = z.object({
  preprocessing: z.string().min(1),
  features: z.string().min(1).optional(),
  lightgbm: z.string().min(1),
  bootstrap: z.string().min(1),
  conformal: z.string().min(1),
});

const successfulPredictionSchema = z.object({
  status: z.enum(["ok", "DEGRADED_COVERAGE"]),
  artifactMode: z.literal("FULL"),
  versions: versionSchema,
  overall: z.object({
    task: z.literal("serious-outcome classification among FAERS adverse-event reports"),
    riskProbability: z.number().min(0).max(1),
    riskPercent: z.number().min(0).max(100),
    uncertainty: z.object({ method: z.literal("bootstrap_model_variability"), level: z.literal(0.9), lower: z.number().min(0).max(1), upper: z.number().min(0).max(1), replicas: z.number().int().positive() }),
    adjustedRisk: z.number().min(0).max(1),
    conformal: z.object({
      method: z.literal("split_conformal_classification"), targetCoverage: z.literal(0.9), qHat: z.number().min(0).max(1),
      predictionSet: z.array(conformalLabels).max(2), setSize: z.number().int().min(0).max(2),
      reliability: z.enum(["UNAVAILABLE", "AMBIGUOUS", "FOCUSED_SERIOUS_OUTCOME", "FOCUSED_NO_DOCUMENTED_SERIOUS_OUTCOME"]),
      interpretation: z.string().min(1), calibrationVersion: z.string().min(1), interval: z.null(), intervalNote: z.string().min(1),
    }),
  }),
  model: z.literal("LightGBM"),
  modelVersion: z.string().min(1),
  inputCoverage: inputCoverageSchema,
  dataWindow: z.record(z.string(), z.string()),
  generatedAt: z.string(),
  message: z.string().min(1).optional(),
  clinicalInterpretation: z.object({ population: z.string(), limitations: z.array(z.string()) }),
}).superRefine((value, context) => {
  if (value.overall.uncertainty.lower > value.overall.uncertainty.upper) context.addIssue({ code: "custom", message: "Bootstrap lower bound exceeds upper bound." });
  if (value.overall.adjustedRisk !== value.overall.uncertainty.upper) context.addIssue({ code: "custom", message: "Adjusted risk must equal the established conservative bootstrap upper bound." });
  if (value.overall.conformal.setSize !== value.overall.conformal.predictionSet.length) context.addIssue({ code: "custom", message: "Conformal setSize does not match predictionSet." });
  const hasUnknownCurrentMedication = value.inputCoverage.unknownCurrentMedications.length > 0;
  if (value.status === "DEGRADED_COVERAGE" && (!hasUnknownCurrentMedication || !value.message)) context.addIssue({ code: "custom", message: "Degraded coverage must identify an unsupported current medicine and include a message." });
  if (value.status === "ok" && hasUnknownCurrentMedication) context.addIssue({ code: "custom", message: "A complete result cannot contain unsupported current medicines." });
});

const outOfVocabularySchema = z.object({
  status: z.literal("OUT_OF_VOCABULARY"),
  artifactMode: z.literal("FULL"),
  model: z.literal("LightGBM"),
  modelVersion: z.string().min(1),
  versions: versionSchema,
  inputCoverage: inputCoverageSchema,
  normalizedInput: z.object({
    sex: z.enum(["M", "F", "UNKNOWN"]),
    candidateDrug: z.string().min(1),
    indication: z.string().min(1),
    currentMedications: z.array(z.string()),
  }),
  dataWindow: z.record(z.string(), z.string()),
  generatedAt: z.string(),
  message: z.string().min(1),
});

const coverageSchema = z.object({
  status: z.enum(["FULL", "DEGRADED_COVERAGE", "OUT_OF_VOCABULARY"]),
  inputCoverage: inputCoverageSchema,
  normalizedInput: z.object({
    sex: z.enum(["M", "F", "UNKNOWN"]),
    candidateDrug: z.string().min(1),
    indication: z.string().min(1),
    currentMedications: z.array(z.string()),
  }),
});

const termCoverageItemSchema = z.object({ input: z.string(), normalized: z.string(), supported: z.boolean() });
const termCoverageSchema = z.object({
  status: z.literal("ok"),
  modelVersion: z.string().min(1),
  candidates: z.array(termCoverageItemSchema),
  indications: z.array(termCoverageItemSchema),
  medications: z.array(termCoverageItemSchema),
});

const unavailableResult = (status, message) => ({
  status,
  providerName: "PythonAdrModelProvider",
  providerVersion: ADR_PROVIDER_VERSION,
  message,
  generatedAt: new Date().toISOString(),
});

const responseErrorMessage = async (response) => {
  try {
    const payload = await response.json();
    const detail = payload?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const issues = detail.map((issue) => issue?.msg).filter(Boolean);
      if (issues.length) return issues.join("; ");
    }
    if (typeof detail?.message === "string") return detail.message;
  } catch {
    // The status code remains useful when a proxy returns a non-JSON response.
  }
  return null;
};

export const buildAdrPredictionInput = ({ consultation, patient, requestId, candidateGeneric = consultation.candidateGeneric }) => ({
  requestId,
  patient: {
    age: patient.age,
    sex: String(patient.gender || "").trim().toUpperCase() === "FEMALE" ? "F" : String(patient.gender || "").trim().toUpperCase() === "MALE" ? "M" : patient.gender,
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
      if (!response.ok) {
        const detail = await responseErrorMessage(response);
        return unavailableResult("ML_UNAVAILABLE", `ML service returned HTTP ${response.status}${detail ? `: ${detail}` : "."}`);
      }
      return await response.json();
    } catch (error) {
      return unavailableResult(error?.name === "TimeoutError" ? "ML_UNAVAILABLE" : "INFERENCE_FAILED", error?.name === "TimeoutError" ? "ML service request timed out." : "ML service could not be reached.");
    }
  };

  return Object.freeze({
    providerName: "PythonAdrModelProvider",
    modelName: "faers-serious-lightgbm",
    modelVersion: ADR_PROVIDER_VERSION,
    async predict(input) {
      const response = await request("/v1/predict", input);
      if (["ML_UNAVAILABLE", "INFERENCE_FAILED"].includes(response.status)) return response;
      if (response.status === "OUT_OF_VOCABULARY") {
        const parsed = outOfVocabularySchema.safeParse(response);
        return parsed.success ? { ...parsed.data, providerName: this.providerName, providerVersion: ADR_PROVIDER_VERSION, inputContractVersion: ADR_INPUT_CONTRACT_VERSION } : unavailableResult("INFERENCE_FAILED", "ML out-of-vocabulary response failed contract validation.");
      }
      const parsed = successfulPredictionSchema.safeParse(response);
      return parsed.success ? { ...parsed.data, providerName: this.providerName, providerVersion: ADR_PROVIDER_VERSION, inputContractVersion: ADR_INPUT_CONTRACT_VERSION } : unavailableResult("INFERENCE_FAILED", "ML service response failed contract validation.");
    },
    async checkCoverage(input) {
      const response = await request("/v1/lightgbm/input-coverage", input);
      if (["ML_UNAVAILABLE", "INFERENCE_FAILED"].includes(response.status)) return response;
      const parsed = coverageSchema.safeParse(response);
      return parsed.success ? parsed.data : unavailableResult("INFERENCE_FAILED", "ML input-coverage response failed contract validation.");
    },
    async checkTerms({ candidates = [], indications = [], medications = [] }) {
      const response = await request("/v1/lightgbm/term-coverage", { candidates, indications, medications });
      if (["ML_UNAVAILABLE", "INFERENCE_FAILED"].includes(response.status)) return response;
      const parsed = termCoverageSchema.safeParse(response);
      return parsed.success ? parsed.data : unavailableResult("INFERENCE_FAILED", "ML terminology-coverage response failed contract validation.");
    },
    async predictBatch(inputs) {
      if (!inputs.length) return [];
      const response = await request("/v1/predict-batch", { requests: inputs });
      if (["ML_UNAVAILABLE", "INFERENCE_FAILED"].includes(response.status)) return inputs.map(() => response);
      if (!Array.isArray(response.items) || response.items.length !== inputs.length) return inputs.map(() => unavailableResult("INFERENCE_FAILED", "ML batch response failed contract validation."));
      return response.items.map((item) => {
        if (item.error) return unavailableResult(item.error.status || "INFERENCE_FAILED", item.error.message || "ML inference failed.");
        if (item.result?.status === "OUT_OF_VOCABULARY") {
          const parsed = outOfVocabularySchema.safeParse(item.result);
          return parsed.success ? { ...parsed.data, providerName: this.providerName, providerVersion: ADR_PROVIDER_VERSION, inputContractVersion: ADR_INPUT_CONTRACT_VERSION } : unavailableResult("INFERENCE_FAILED", "ML batch out-of-vocabulary response failed contract validation.");
        }
        const parsed = successfulPredictionSchema.safeParse(item.result);
        return parsed.success ? { ...parsed.data, providerName: this.providerName, providerVersion: ADR_PROVIDER_VERSION, inputContractVersion: ADR_INPUT_CONTRACT_VERSION } : unavailableResult("INFERENCE_FAILED", "ML service response failed contract validation.");
      });
    },
  });
};

export const adrPredictionProvider = createPythonAdrPredictionProvider();
