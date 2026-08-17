ALTER TABLE "DrugDiseaseKnowledge"
  ADD COLUMN "diseaseIdentity" TEXT NOT NULL DEFAULT '',
  ADD COLUMN "conceptName" TEXT NOT NULL DEFAULT '',
  ADD COLUMN "normalizedConceptName" TEXT NOT NULL DEFAULT '',
  ADD COLUMN "umlsCui" TEXT,
  ADD COLUMN "snomedName" TEXT,
  ADD COLUMN "normalizedSnomedName" TEXT NOT NULL DEFAULT '';

-- Existing imported rows remain usable before the idempotent import refreshes
-- them with the full structured source fields. The evidence column already
-- contains `relationship | concept_name | umls_cui` for these rows.
UPDATE "DrugDiseaseKnowledge"
SET
  "conceptName" = CASE WHEN "evidence" IS NULL THEN "existingDisease" ELSE split_part("evidence", ' | ', 2) END,
  "normalizedConceptName" = CASE WHEN "evidence" IS NULL THEN "normalizedDisease" ELSE lower(regexp_replace(trim(split_part("evidence", ' | ', 2)), '[^a-z0-9]+', ' ', 'g')) END,
  "umlsCui" = NULLIF((regexp_match(COALESCE("evidence", ''), '(C[0-9]{7})'))[1], ''),
  "snomedName" = "existingDisease",
  "normalizedSnomedName" = "normalizedDisease";

UPDATE "DrugDiseaseKnowledge"
SET "diseaseIdentity" = CASE
  WHEN "umlsCui" IS NOT NULL THEN 'UMLS:' || "umlsCui"
  ELSE 'DRUGCENTRAL:' || "datasetVersion" || ':' || "normalizedDisease"
END;

CREATE INDEX "DrugDiseaseKnowledge_diseaseIdentity_idx" ON "DrugDiseaseKnowledge"("diseaseIdentity");
CREATE INDEX "DrugDiseaseKnowledge_umlsCui_idx" ON "DrugDiseaseKnowledge"("umlsCui");
CREATE INDEX "DrugDiseaseKnowledge_normalizedConceptName_idx" ON "DrugDiseaseKnowledge"("normalizedConceptName");
CREATE INDEX "DrugDiseaseKnowledge_normalizedSnomedName_idx" ON "DrugDiseaseKnowledge"("normalizedSnomedName");
