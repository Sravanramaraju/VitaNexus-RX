CREATE TABLE "HgnnEventPrediction" (
    "id" TEXT NOT NULL,
    "consultationId" TEXT NOT NULL,
    "result" JSONB NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "checkpointVersion" TEXT NOT NULL,
    "modelStage" TEXT NOT NULL,
    "validationStatus" TEXT NOT NULL,
    "inputHash" TEXT NOT NULL,
    "coverageStatus" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "generatedAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "HgnnEventPrediction_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "HgnnEventPrediction_consultationId_modelVersion_checkpointVersion_inputHash_key"
ON "HgnnEventPrediction"("consultationId", "modelVersion", "checkpointVersion", "inputHash");

CREATE INDEX "HgnnEventPrediction_consultationId_createdAt_idx"
ON "HgnnEventPrediction"("consultationId", "createdAt");

ALTER TABLE "HgnnEventPrediction"
ADD CONSTRAINT "HgnnEventPrediction_consultationId_fkey"
FOREIGN KEY ("consultationId") REFERENCES "Consultation"("id") ON DELETE CASCADE ON UPDATE CASCADE;
