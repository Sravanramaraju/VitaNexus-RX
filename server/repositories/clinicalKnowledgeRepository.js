export const normalizeClinicalTerm = (value = "") =>
  value.toLowerCase().trim().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();

const severityOrder = { MAJOR: 3, MODERATE: 2, MINOR: 1, NOT_EVALUATED: 0 };
const assessmentOrder = { HIGH: 3, MODERATE: 2, LOW: 1, NOT_EVALUATED: 0 };
const ddinterSynonyms = Object.freeze({
  paracetamol: "acetaminophen",
  "paracetamol acetaminophen": "acetaminophen",
});
// DDInter sometimes repeats a drug token in parentheses, for example
// "Insulin aspart (aspart)". Remove a parenthetical only when every qualifier
// token is already present outside it. Meaningful qualifiers such as
// "(topical)" or "(aspart protamine)" remain distinct.
export const normalizeDdinterDrugName = (value = "") => {
  const source = String(value || "");
  const outsideTokens = new Set(normalizeClinicalTerm(source.replace(/\([^)]*\)/g, " ")).split(" ").filter(Boolean));
  return normalizeClinicalTerm(source.replace(/\(([^)]*)\)/g, (full, qualifier) => {
    const qualifierTokens = normalizeClinicalTerm(qualifier).split(" ").filter(Boolean);
    return qualifierTokens.length && qualifierTokens.every((token) => outsideTokens.has(token)) ? "" : full;
  }));
};
const ddiTerms = (value = "") => [...new Set(
  String(value)
    .split(/[+/]/)
    .map((part) => normalizeDdinterDrugName(part))
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

export const createClinicalKnowledgeRepository = (client) => {
  const resolveDdinterDrug = async (drug) => {
    const terms = ddiTerms(drug);
    if (!terms.length) return { status: "UNRESOLVED", enteredDrug: drug, terms: [], entities: [], reason: "EMPTY_TERM" };
    const records = await client.drugInteractionKnowledge.findMany({
      where: {
        source: "DDInter 2.0",
        OR: terms.flatMap((term) => [
          { normalizedDrugA: term }, { normalizedDrugA: { startsWith: `${term} ` } },
          { normalizedDrugB: term }, { normalizedDrugB: { startsWith: `${term} ` } },
        ]),
      },
    });
    const resolutions = terms.map((term) => {
      const entities = records.flatMap((record) => [
        ...(normalizeDdinterDrugName(record.drugA) === term ? [{ id: record.ddinterIdA, name: record.drugA, normalizedName: term }] : []),
        ...(normalizeDdinterDrugName(record.drugB) === term ? [{ id: record.ddinterIdB, name: record.drugB, normalizedName: term }] : []),
      ]).filter((entity, index, list) => list.findIndex((item) => (item.id || item.name) === (entity.id || entity.name)) === index);
      if (!entities.length) return { term, status: "UNRESOLVED", entities: [] };
      if (entities.length > 1) return { term, status: "AMBIGUOUS", entities };
      return { term, status: "RESOLVED", entities };
    });
    const unresolved = resolutions.filter((item) => item.status !== "RESOLVED");
    return {
      status: unresolved.length ? (unresolved.some((item) => item.status === "AMBIGUOUS") ? "AMBIGUOUS" : "UNRESOLVED") : "RESOLVED",
      enteredDrug: drug,
      terms,
      entities: resolutions.flatMap((item) => item.status === "RESOLVED" ? item.entities : []),
      termResolutions: resolutions,
      source: "DDInter 2.0",
    };
  };

  const evaluateDdiPair = async (candidateDrug, existingDrug) => {
    try {
      const [candidateResolution, existingResolution] = await Promise.all([
        resolveDdinterDrug(candidateDrug),
        resolveDdinterDrug(existingDrug),
      ]);
      if (candidateResolution.status !== "RESOLVED" || existingResolution.status !== "RESOLVED") {
        return { status: "UNRESOLVED", lookupCompleted: false, candidateResolution, existingResolution, source: "DDInter 2.0" };
      }
      const pairs = candidateResolution.entities.flatMap((candidate) => existingResolution.entities.flatMap((existing) => {
        if (candidate.id && existing.id) return [
          { ddinterIdA: candidate.id, ddinterIdB: existing.id },
          { ddinterIdA: existing.id, ddinterIdB: candidate.id },
        ];
        const [normalizedDrugA, normalizedDrugB] = canonicalPair(candidate.normalizedName, existing.normalizedName);
        return normalizedDrugA === normalizedDrugB ? [] : [{ normalizedDrugA, normalizedDrugB }];
      }));
      const records = pairs.length ? await client.drugInteractionKnowledge.findMany({
        where: { source: "DDInter 2.0", OR: pairs },
        orderBy: { importedAt: "desc" },
      }) : [];
      const record = records.sort((first, second) => severityOrder[second.displaySeverity] - severityOrder[first.displaySeverity])[0];
      if (!record) return { status: "NO_DOCUMENTED_INTERACTION", lookupCompleted: true, candidateResolution, existingResolution, source: "DDInter 2.0" };
      return {
        status: "DOCUMENTED_INTERACTION",
        lookupCompleted: true,
        candidateResolution,
        existingResolution,
        interaction: {
          drugA: record.drugA,
          drugB: record.drugB,
          rawSeverity: record.rawSeverity,
          displaySeverity: record.displaySeverity,
          source: record.source,
          datasetVersion: record.datasetVersion,
          ddinterIdA: record.ddinterIdA,
          ddinterIdB: record.ddinterIdB,
          matchedCandidateIngredients: candidateResolution.terms,
          matchedExistingIngredients: existingResolution.terms,
        },
        source: "DDInter 2.0",
      };
    } catch {
      return { status: "LOOKUP_FAILED", lookupCompleted: false, candidateResolution: null, existingResolution: null, source: "DDInter 2.0" };
    }
  };

  return {
  resolveDdinterDrug,
  evaluateDdiPair,
  async hasDdiDrugEvidence(drug) {
    return (await resolveDdinterDrug(drug)).status === "RESOLVED";
  },

  async findPairwiseDrugInteraction(candidateDrug, existingDrug) {
    const evaluation = await evaluateDdiPair(candidateDrug, existingDrug);
    return evaluation.status === "DOCUMENTED_INTERACTION" ? evaluation.interaction : null;
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
  };
};
