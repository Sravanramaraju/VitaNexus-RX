export const POSITIVE_DRUGCENTRAL_INDICATION_RELATIONSHIPS = Object.freeze([
  "indication",
  "treatment",
  "therapy",
  "used for",
]);

const normalizedRelationship = (value) => String(value || "").trim().toLowerCase().replace(/\s+/g, " ");

export const isPositiveDrugCentralIndication = (value) => (
  POSITIVE_DRUGCENTRAL_INDICATION_RELATIONSHIPS.includes(normalizedRelationship(value))
);
