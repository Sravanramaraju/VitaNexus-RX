import { z } from "zod";
import { config } from "../config.js";

export const HGNN_INPUT_CONTRACT_VERSION = "vitanexus-hgnn-event-profile-input-1.0";
export const HGNN_PROVIDER_VERSION = "python-hgnn-provider-1.0.0";

const modelSex = (value) => {
  const normalized = String(value || "").trim().toUpperCase();
  if (["F", "FEMALE", "WOMAN"].includes(normalized)) return "F";
  if (["M", "MALE", "MAN"].includes(normalized)) return "M";
  return "UNKNOWN";
};

const inferenceStatus = z.enum(["SUCCESS", "DEGRADED_COVERAGE"]);
const modelMetadataSchema = z.object({
  modelType: z.literal("HGNN"),
  modelFamily: z.literal("HGNN"),
  modelStage: z.literal("BASELINE"),
  validationStatus: z.literal("AUDIT_PENDING"),
  modelVersion: z.string().min(1).max(255),
  checkpointVersion: z.string().regex(/^[a-f0-9]{64}$/),
  trainingEpoch: z.number().int().positive(),
  eventVocabularyVersion: z.string().min(1).max(255),
  eventVocabularySize: z.number().int().positive(),
  graphSchemaVersion: z.string().min(1).max(255),
  featureSchemaVersion: z.string().min(1).max(255),
  eventScoreType: z.literal("BASELINE_MODEL_SCORE"),
  rankingInfluence: z.literal("none"),
}).passthrough();

const modelStatusSchema = modelMetadataSchema.extend({
  status: z.literal("READY"),
  device: z.enum(["cpu", "cuda"]),
  topK: z.number().int().positive(),
  nodeTypes: z.array(z.string().min(1)).min(1),
  edgeTypes: z.array(z.tuple([z.string().min(1), z.string().min(1), z.string().min(1)])).min(1),
  supportedInputs: z.array(z.string().min(1)).min(1),
}).strict();

const eventSchema = z.object({
  eventCode: z.string().min(1).max(255).nullable(),
  eventName: z.string().min(1).max(255),
  eventScore: z.number().finite().min(0).max(1),
  displayPercent: z.number().finite().min(0).max(100),
  rank: z.number().int().positive(),
}).strict();

const predictionSchema = modelMetadataSchema.extend({
  status: inferenceStatus,
  device: z.enum(["cpu", "cuda"]),
  topK: z.number().int().positive(),
  nodeTypes: z.array(z.string().min(1)).min(1),
  edgeTypes: z.array(z.tuple([z.string().min(1), z.string().min(1), z.string().min(1)])).min(1),
  supportedInputs: z.array(z.string().min(1)).min(1),
  coverage: z.object({
    status: z.enum(["FULL", "DEGRADED"]),
    unknownEntities: z.array(z.object({
      entityType: z.enum(["candidateDrug", "indication", "currentMedication"]),
      value: z.string().min(1).max(255),
    }).strict()),
  }).strict(),
  inputHash: z.string().regex(/^[a-f0-9]{64}$/),
  events: z.array(eventSchema).min(1),
  generatedAt: z.string().datetime({ offset: true }),
  interpretation: z.string().min(1),
}).strict().superRefine((value, context) => {
  if (value.events.length > value.topK) context.addIssue({ code: "custom", message: "HGNN event count exceeds the configured topK." });
  if (value.status === "SUCCESS" && value.coverage.status !== "FULL") context.addIssue({ code: "custom", message: "Successful HGNN output must have full coverage." });
  if (value.status === "DEGRADED_COVERAGE" && value.coverage.status !== "DEGRADED") context.addIssue({ code: "custom", message: "Degraded HGNN output must report degraded coverage." });
  const ranks = value.events.map((event) => event.rank);
  if (ranks.some((rank, index) => rank !== index + 1)) context.addIssue({ code: "custom", message: "HGNN event ranks must be contiguous and ordered." });
  for (let index = 1; index < value.events.length; index += 1) {
    const previous = value.events[index - 1];
    const current = value.events[index];
    if (previous.eventScore < current.eventScore || (previous.eventScore === current.eventScore && previous.eventName.localeCompare(current.eventName) > 0)) {
      context.addIssue({ code: "custom", message: "HGNN events are not deterministically sorted." });
      break;
    }
  }
});

const unavailableResult = (status, message) => ({
  status,
  modelType: "HGNN",
  modelFamily: "HGNN",
  modelStage: "BASELINE",
  validationStatus: "AUDIT_PENDING",
  eventScoreType: "BASELINE_MODEL_SCORE",
  events: [],
  coverage: { status: "UNAVAILABLE", unknownEntities: [] },
  rankingInfluence: "none",
  providerName: "PythonHgnnEventProvider",
  providerVersion: HGNN_PROVIDER_VERSION,
  message,
  generatedAt: new Date().toISOString(),
});

const responseError = async (response) => {
  try {
    const payload = await response.json();
    const detail = payload?.detail;
    if (typeof detail === "string") return { status: "HGNN_UNAVAILABLE", message: detail };
    if (typeof detail?.message === "string") return { status: detail.status || "HGNN_UNAVAILABLE", message: detail.message };
  } catch {
    // Preserve the explicit unavailable state when an intermediary returns non-JSON.
  }
  return { status: "HGNN_UNAVAILABLE", message: `HGNN service returned HTTP ${response.status}.` };
};

export const buildHgnnPredictionInput = ({ consultation, patient, requestId }) => ({
  requestId,
  patient: {
    age: patient.age,
    sex: modelSex(patient.gender),
    currentMedications: patient.medications
      .filter((medicine) => medicine.status === "ACTIVE")
      .map((medicine) => medicine.genericName)
      .sort(),
  },
  candidateDrug: { canonicalName: consultation.candidateGeneric },
  indication: { name: consultation.indication },
});

export const createPythonHgnnEventProvider = ({
  baseUrl = config.adrMlBaseUrl,
  timeoutMs = config.hgnnMlTimeoutMs,
  fetchImplementation = globalThis.fetch,
} = {}) => {
  const request = async (path, { method = "GET", body } = {}) => {
    if (!baseUrl) return unavailableResult("HGNN_UNAVAILABLE", "ADR_ML_BASE_URL is not configured.");
    try {
      const response = await fetchImplementation(`${baseUrl.replace(/\/$/, "")}${path}`, {
        method,
        headers: {
          ...(body ? { "content-type": "application/json" } : {}),
          "x-request-id": body?.requestId || "hgnn-status",
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!response.ok) {
        const error = await responseError(response);
        return unavailableResult(error.status, error.message);
      }
      return await response.json();
    } catch (error) {
      const timedOut = error?.name === "TimeoutError";
      return unavailableResult(
        timedOut ? "HGNN_UNAVAILABLE" : "INFERENCE_FAILED",
        timedOut ? "Baseline HGNN service request timed out." : "Baseline HGNN service could not be reached.",
      );
    }
  };

  return Object.freeze({
    providerName: "PythonHgnnEventProvider",
    providerVersion: HGNN_PROVIDER_VERSION,
    async getStatus() {
      const response = await request("/v1/hgnn/status");
      if (response.status !== "READY") return response;
      const parsed = modelStatusSchema.safeParse(response);
      return parsed.success ? parsed.data : unavailableResult("ARTIFACT_MISMATCH", "HGNN status response failed contract validation.");
    },
    async predict(input) {
      const response = await request("/v1/hgnn/predict-events", { method: "POST", body: input });
      if (!["SUCCESS", "DEGRADED_COVERAGE"].includes(response.status)) return response;
      const parsed = predictionSchema.safeParse(response);
      return parsed.success
        ? { ...parsed.data, inputContractVersion: HGNN_INPUT_CONTRACT_VERSION, providerName: this.providerName, providerVersion: HGNN_PROVIDER_VERSION }
        : unavailableResult("INFERENCE_FAILED", "HGNN prediction response failed contract validation.");
    },
  });
};

export const hgnnEventProvider = createPythonHgnnEventProvider();
