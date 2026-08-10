import { stableHash } from "../utils.js";

export const ADR_INPUT_CONTRACT_VERSION = "vitanexus-adr-faers-input-1.0";

export const buildAdrPredictionInput = ({ consultation, patient }) => ({
  contractVersion: ADR_INPUT_CONTRACT_VERSION,
  age: patient.age,
  gender: patient.gender,
  existingMedications: patient.medications
    .filter((medicine) => medicine.status === "ACTIVE")
    .map((medicine) => ({ brand: medicine.brand || null, genericName: medicine.genericName })),
  newlyPrescribedDrug: {
    brand: consultation.candidateBrand || null,
    genericName: consultation.candidateGeneric,
  },
});

const scoreFrom = (value, min = 0, max = 100) => {
  const hex = stableHash(value).slice(0, 8);
  return min + (Number.parseInt(hex, 16) % (max - min + 1));
};
const category = (score) => (score >= 61 ? "High" : score >= 31 ? "Moderate" : "Low");

// This provider exists solely to maintain the production-shaped provider boundary
// until an approved Python model service is available. Its numeric outputs are
// deterministic development placeholders, not model inference.
export const mockAdrPredictionProvider = Object.freeze({
  providerName: "MockADRPredictionProvider",
  modelName: "vitanexus-demo-adr",
  modelVersion: "vitanexus-demo-adr-1.0.0",
  async predict(input) {
    const risk = Math.min(
      78,
      8 + input.existingMedications.length * 7 + input.age / 6 + scoreFrom(input.newlyPrescribedDrug.genericName, 0, 18),
    );
    const confidence = scoreFrom({ candidate: input.newlyPrescribedDrug.genericName, type: "adr-demo-confidence" }, 66, 91);
    const width = Math.max(3, Math.round((100 - confidence) / 2));

    return {
      predictedAdrRisk: Math.round(risk),
      riskCategory: category(risk),
      confidence,
      confidenceInterval: {
        lower: Math.max(0, Math.round(risk - width)),
        upper: Math.min(100, Math.round(risk + width)),
      },
      predictionStatus: "success",
      status: "DEMONSTRATION_ONLY",
      dataStatus: "DEVELOPMENT_PLACEHOLDER",
      disclaimer: "This deterministic development placeholder is not a medical-device model and must not guide treatment.",
      providerName: this.providerName,
      modelName: this.modelName,
      modelVersion: this.modelVersion,
      inputContractVersion: ADR_INPUT_CONTRACT_VERSION,
      uncertaintyStatus: "DEVELOPMENT_PLACEHOLDER_NOT_CALIBRATED_OR_CONFORMAL",
      generatedAt: new Date().toISOString(),
      explanations: [
        "The development placeholder uses only age, active-medication count, and candidate-medicine text.",
        "Gender is included in the approved ADR provider input contract but is not used by this placeholder.",
        "Disease, allergy, and other clinical-history data are excluded from this ADR provider input contract.",
        "A validated, governed model service must replace this provider before clinical use.",
      ],
    };
  },
});

// Replace this binding with a Python ADR model provider that implements
// { providerName, modelName, modelVersion, predict(input) } without changing
// routes, persistence, or the public API response contract.
export const adrPredictionProvider = mockAdrPredictionProvider;
