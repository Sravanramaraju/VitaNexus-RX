// Demonstration data-access adapter. Clinical services depend on this interface,
// not on an embedded raw rule object. It is intentionally not a clinical knowledge base.
const DDI_DATASET_VERSION = "vitanexus-demo-ddi-2026.08";

const pairwiseDdiRules = new Map([
  ["aspirin|warfarin", { riskPercentage: 88, interactionSeverity: "High", explanation: "Concurrent use may increase bleeding risk; clinician review is required." }],
  ["ibuprofen|warfarin", { riskPercentage: 84, interactionSeverity: "High", explanation: "Concurrent use may increase bleeding risk; clinician review is required." }],
  ["fluoxetine|tramadol", { riskPercentage: 82, interactionSeverity: "High", explanation: "Concurrent use may increase serotonin-toxicity risk; clinician review is required." }],
  ["clarithromycin|simvastatin", { riskPercentage: 80, interactionSeverity: "High", explanation: "Concurrent use may increase statin exposure; clinician review is required." }],
]);

const canonicalDemoKey = (value = "") => value.toLowerCase().replace(/[^a-z]/g, "");

export const findPairwiseDrugInteraction = (candidateDrug, existingDrug) => {
  const pairKey = [canonicalDemoKey(candidateDrug), canonicalDemoKey(existingDrug)].sort().join("|");
  const rule = pairwiseDdiRules.get(pairKey);
  return rule
    ? {
        ...rule,
        source: "VitaNexus static demonstration DDI rules",
        datasetVersion: DDI_DATASET_VERSION,
        dataStatus: "DEMONSTRATION_ONLY",
      }
    : null;
};

// No drug-disease dataset is integrated in the backend at present. Drug-allergy
// evaluation is intentionally outside the current automated-analysis scope.
export const clinicalKnowledgeStatus = Object.freeze({
  drugDrug: {
    status: "PARTIALLY_IMPLEMENTED",
    source: "VitaNexus static demonstration DDI rules",
    datasetVersion: DDI_DATASET_VERSION,
  },
  drugDisease: { status: "NOT_INTEGRATED", source: null, datasetVersion: null },
});
