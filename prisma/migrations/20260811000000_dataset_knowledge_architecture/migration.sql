ALTER TABLE "PatientMedication"
  ADD COLUMN "enteredName" TEXT,
  ADD COLUMN "normalizedName" TEXT,
  ADD COLUMN "mappingSource" TEXT,
  ADD COLUMN "mappingVersion" TEXT;

ALTER TABLE "Consultation"
  ADD COLUMN "candidateEnteredName" TEXT,
  ADD COLUMN "candidateNormalizedName" TEXT,
  ADD COLUMN "candidateMappingSource" TEXT,
  ADD COLUMN "candidateMappingVersion" TEXT;

ALTER TABLE "MedicationTerminology"
  ADD COLUMN "normalizedBrand" TEXT NOT NULL DEFAULT '',
  ADD COLUMN "normalizedGeneric" TEXT NOT NULL DEFAULT '';

CREATE INDEX "MedicationTerminology_normalizedBrand_idx" ON "MedicationTerminology"("normalizedBrand");
CREATE INDEX "MedicationTerminology_normalizedGeneric_idx" ON "MedicationTerminology"("normalizedGeneric");

CREATE TABLE "DrugInteractionKnowledge" (
  "id" TEXT NOT NULL,
  "drugA" TEXT NOT NULL,
  "normalizedDrugA" TEXT NOT NULL,
  "ddinterIdA" TEXT,
  "drugB" TEXT NOT NULL,
  "normalizedDrugB" TEXT NOT NULL,
  "ddinterIdB" TEXT,
  "rawSeverity" TEXT NOT NULL,
  "displaySeverity" TEXT NOT NULL,
  "source" TEXT NOT NULL,
  "datasetVersion" TEXT NOT NULL,
  "importedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "DrugInteractionKnowledge_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "DrugInteractionKnowledge_normalizedDrugA_normalizedDrugB_source_datasetVersion_key" ON "DrugInteractionKnowledge"("normalizedDrugA", "normalizedDrugB", "source", "datasetVersion");
CREATE INDEX "DrugInteractionKnowledge_normalizedDrugA_idx" ON "DrugInteractionKnowledge"("normalizedDrugA");
CREATE INDEX "DrugInteractionKnowledge_normalizedDrugB_idx" ON "DrugInteractionKnowledge"("normalizedDrugB");

CREATE TABLE "DrugDiseaseKnowledge" (
  "id" TEXT NOT NULL,
  "genericDrug" TEXT NOT NULL,
  "normalizedDrug" TEXT NOT NULL,
  "existingDisease" TEXT NOT NULL,
  "normalizedDisease" TEXT NOT NULL,
  "relationship" TEXT NOT NULL,
  "assessment" TEXT NOT NULL,
  "evidence" TEXT,
  "source" TEXT NOT NULL,
  "datasetVersion" TEXT NOT NULL,
  "importedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "DrugDiseaseKnowledge_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "DrugDiseaseKnowledge_normalizedDrug_normalizedDisease_relationship_source_datasetVersion_key" ON "DrugDiseaseKnowledge"("normalizedDrug", "normalizedDisease", "relationship", "source", "datasetVersion");
CREATE INDEX "DrugDiseaseKnowledge_normalizedDrug_idx" ON "DrugDiseaseKnowledge"("normalizedDrug");
CREATE INDEX "DrugDiseaseKnowledge_normalizedDisease_idx" ON "DrugDiseaseKnowledge"("normalizedDisease");

CREATE TABLE "DrugIndicationKnowledge" (
  "id" TEXT NOT NULL,
  "indication" TEXT NOT NULL,
  "normalizedIndication" TEXT NOT NULL,
  "genericDrug" TEXT NOT NULL,
  "normalizedDrug" TEXT NOT NULL,
  "relationship" TEXT NOT NULL,
  "evidence" TEXT,
  "source" TEXT NOT NULL,
  "datasetVersion" TEXT NOT NULL,
  "importedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "DrugIndicationKnowledge_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "DrugIndicationKnowledge_normalizedIndication_normalizedDrug_relationship_source_datasetVersion_key" ON "DrugIndicationKnowledge"("normalizedIndication", "normalizedDrug", "relationship", "source", "datasetVersion");
CREATE INDEX "DrugIndicationKnowledge_normalizedIndication_idx" ON "DrugIndicationKnowledge"("normalizedIndication");
