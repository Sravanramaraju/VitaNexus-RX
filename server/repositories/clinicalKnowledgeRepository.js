export const normalizeClinicalTerm = (value = "") =>
  value.toLowerCase().trim().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();

const severityOrder = { MAJOR: 3, MODERATE: 2, MINOR: 1, NOT_EVALUATED: 0 };
const assessmentOrder = { HIGH: 3, MODERATE: 2, LOW: 1, NOT_EVALUATED: 0 };
const ddinterSynonyms = Object.freeze({
  paracetamol: "acetaminophen",
  "paracetamol acetaminophen": "acetaminophen",
});
const ddiTerms = (value = "") => [...new Set(
  String(value)
    .split(/[+/]/)
    .map((part) => normalizeClinicalTerm(part))
    .filter(Boolean)
    .map((term) => ddinterSynonyms[term] || term),
)];
const canonicalPair = (first, second) => [first, second].sort();
const conditionCode = (condition) => String(condition.code || "").trim();
const umlsCode = (value) => {
  const match = String(value || "").trim().toUpperCase().match(/^(?:UMLS:)?(C\d{7})$/);
  return match?.[1] || null;
};
const diseaseIdentityCode = (value) => String(value || "").trim().startsWith("DRUGCENTRAL:") ? String(value).trim() : null;

// DDInter uses "Acetaminophen" whereas the Indian medicine source uses
// "Paracetamol" (for example, Crocin). It also stores individual ingredients,
// so combination products must be evaluated ingredient-by-ingredient.
export const ddinterSearchTerms = ddiTerms;

export const highestDdiSeverity = (values) =>
  values.reduce((highest, value) => (severityOrder[value] > severityOrder[highest] ? value : highest), "NOT_EVALUATED");

export const highestDiseaseAssessment = (values) =>
  values.reduce((highest, value) => (assessmentOrder[value] > assessmentOrder[highest] ? value : highest), "NOT_EVALUATED");

export const createClinicalKnowledgeRepository = (client) => ({
  async hasDdiDrugEvidence(drug) {
    const terms = ddiTerms(drug);
    if (!terms.length) return false;
    const count = await client.drugInteractionKnowledge.count({
      where: { source: "DDInter 2.0", OR: [{ normalizedDrugA: { in: terms } }, { normalizedDrugB: { in: terms } }] },
    });
    return count > 0;
  },

  async findPairwiseDrugInteraction(candidateDrug, existingDrug) {
    const candidateTerms = ddiTerms(candidateDrug);
    const existingTerms = ddiTerms(existingDrug);
    if (!candidateTerms.length || !existingTerms.length) return null;
    const pairs = candidateTerms.flatMap((candidateTerm) => existingTerms.map((existingTerm) => {
      const [normalizedDrugA, normalizedDrugB] = canonicalPair(candidateTerm, existingTerm);
      return { normalizedDrugA, normalizedDrugB };
    })).filter((pair) => pair.normalizedDrugA !== pair.normalizedDrugB);
    if (!pairs.length) return null;
    const records = await client.drugInteractionKnowledge.findMany({
      where: { source: "DDInter 2.0", OR: pairs },
      orderBy: { importedAt: "desc" },
    });
    const record = records.sort((first, second) => severityOrder[second.displaySeverity] - severityOrder[first.displaySeverity])[0];
    if (!record) return null;
    return {
      drugA: record.drugA,
      drugB: record.drugB,
      rawSeverity: record.rawSeverity,
      displaySeverity: record.displaySeverity,
      source: record.source,
      datasetVersion: record.datasetVersion,
      ddinterIdA: record.ddinterIdA,
      ddinterIdB: record.ddinterIdB,
      matchedCandidateIngredients: candidateTerms,
      matchedExistingIngredients: existingTerms,
    };
  },

  async findDrugDiseaseAssessments(candidateDrug, conditions) {
    const normalizedDrug = normalizeClinicalTerm(candidateDrug);
    if (!conditions.length) return { findings: [], resolutions: [] };
    const resolutions = await Promise.all(conditions.map(async (condition) => {
      const normalizedEnteredCondition = normalizeClinicalTerm(condition.display);
      const code = conditionCode(condition);
      const exactTerms = [
        { normalizedDisease: normalizedEnteredCondition },
        { normalizedConceptName: normalizedEnteredCondition },
        { normalizedSnomedName: normalizedEnteredCondition },
      ];
      const umlsCui = umlsCode(code);
      const diseaseIdentity = diseaseIdentityCode(code);
      if (umlsCui) exactTerms.push({ umlsCui });
      if (diseaseIdentity) exactTerms.push({ diseaseIdentity });
      const matches = await client.drugDiseaseKnowledge.findMany({
        where: { source: "DrugCentral", OR: exactTerms },
        distinct: ["diseaseIdentity"],
        orderBy: { importedAt: "desc" },
      });
      const identities = [...new Set(matches.map((record) => record.diseaseIdentity).filter(Boolean))];
      if (identities.length !== 1) return {
        enteredCondition: condition.display,
        enteredConditionCode: code || null,
        status: identities.length ? "AMBIGUOUS" : "UNRESOLVED",
        resolvedDisease: null,
        diseaseIdentity: null,
        umlsCui: null,
        source: "DrugCentral",
      };
      const record = matches.find((item) => item.diseaseIdentity === identities[0]);
      const matchType = umlsCui && record.umlsCui === umlsCui
        ? "UMLS_IDENTIFIER"
        : diseaseIdentity && record.diseaseIdentity === diseaseIdentity
          ? "DRUGCENTRAL_IDENTIFIER"
          : record.normalizedDisease === normalizedEnteredCondition
            ? "CANONICAL_TERM"
            : record.normalizedSnomedName === normalizedEnteredCondition
              ? "SNOMED_SOURCE_ALIAS"
              : "CONCEPT_SOURCE_ALIAS";
      return {
        enteredCondition: condition.display,
        enteredConditionCode: code || null,
        status: "RESOLVED",
        matchType,
        resolvedDisease: record.existingDisease,
        diseaseIdentity: record.diseaseIdentity,
        umlsCui: record.umlsCui || null,
        snomedName: record.snomedName || null,
        source: record.source,
        datasetVersion: record.datasetVersion,
      };
    }));
    const resolved = resolutions.filter((resolution) => resolution.status === "RESOLVED");
    if (!resolved.length) return { findings: [], resolutions };
    const records = await client.drugDiseaseKnowledge.findMany({
      where: { normalizedDrug, diseaseIdentity: { in: [...new Set(resolved.map((resolution) => resolution.diseaseIdentity))] }, source: "DrugCentral" },
      orderBy: { importedAt: "desc" },
    });
    const findings = records.flatMap((record) => resolved
      .filter((resolution) => resolution.diseaseIdentity === record.diseaseIdentity)
      .map((resolution) => ({
        enteredCondition: resolution.enteredCondition,
        enteredConditionCode: resolution.enteredConditionCode,
        conditionMatchType: resolution.matchType,
        resolvedDisease: resolution.resolvedDisease,
        diseaseIdentity: record.diseaseIdentity,
        umlsCui: record.umlsCui || null,
        snomedName: record.snomedName || null,
        existingDisease: record.existingDisease,
        proposedDrug: record.genericDrug,
        assessment: record.assessment,
        relationship: record.relationship,
        evidence: record.evidence,
        source: record.source,
        datasetVersion: record.datasetVersion,
      })));
    return { findings, resolutions };
  },

  async findCandidateDrugs(indication) {
    const normalizedIndication = normalizeClinicalTerm(indication);
    const records = await client.drugIndicationKnowledge.findMany({
      where: { normalizedIndication, source: "DrugCentral" },
      distinct: ["normalizedDrug"],
      orderBy: { genericDrug: "asc" },
      take: 25,
    });
    return records.map((record) => ({
      genericDrug: record.genericDrug,
      relationship: record.relationship,
      evidence: record.evidence,
      source: record.source,
      datasetVersion: record.datasetVersion,
    }));
  },
});
