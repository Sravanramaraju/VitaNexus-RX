ALTER TABLE "Consultation"
ADD COLUMN "indicationId" TEXT,
ADD COLUMN "indicationNormalized" TEXT,
ADD COLUMN "indicationSource" TEXT NOT NULL DEFAULT 'LEGACY_FREE_TEXT',
ADD COLUMN "indicationDatasetVersion" TEXT;

CREATE INDEX "Consultation_indicationId_idx" ON "Consultation"("indicationId");
