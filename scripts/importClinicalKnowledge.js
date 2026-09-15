import "dotenv/config";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";
import { isPositiveDrugCentralIndication, POSITIVE_DRUGCENTRAL_INDICATION_RELATIONSHIPS } from "../server/services/drugcentralRelationships.js";
import { normalizeDdinterDrugName } from "../server/repositories/clinicalKnowledgeRepository.js";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
const prisma = new PrismaClient({ adapter });
const readNdjson = async function* (file) {
  const reader = readline.createInterface({ input: fs.createReadStream(file, { encoding: "utf8" }), crlfDelay: Infinity });
  for await (const line of reader) if (line.trim()) yield JSON.parse(line);
};
// Knowledge artifacts are immutable and uniquely constrained by their source/version
// identity. Batched createMany keeps imports practical for the full datasets while
// skipDuplicates makes reruns idempotent without touching patient data.
const importRecords = async (file, model) => {
  let processed = 0; let inserted = 0; let batch = [];
  const writeBatch = async () => {
    if (!batch.length) return;
    const result = await prisma[model].createMany({ data: batch, skipDuplicates: true });
    processed += batch.length; inserted += result.count; batch = [];
  };
  for await (const record of readNdjson(file)) {
    batch.push(record);
    if (batch.length === 500) await writeBatch();
  }
  await writeBatch();
  return { processed, inserted };
};

const isPositiveIndication = (record) => (
  record.indication
  && record.indication !== "\\N"
  && record.normalizedIndication
  && record.normalizedIndication !== "n"
  && isPositiveDrugCentralIndication(record.relationship)
);

const importDrugIndicationRecords = async (file) => {
  let processed = 0; let inserted = 0; let skipped = 0; let batch = [];
  const writeBatch = async () => {
    if (!batch.length) return;
    const result = await prisma.drugIndicationKnowledge.createMany({ data: batch, skipDuplicates: true });
    processed += batch.length; inserted += result.count; batch = [];
  };
  for await (const record of readNdjson(file)) {
    if (!isPositiveIndication(record)) { skipped += 1; continue; }
    batch.push(record);
    if (batch.length === 500) await writeBatch();
  }
  await writeBatch();
  return { processed, inserted, skipped };
};

// DrugCentral disease rows may acquire additional deterministic terminology
// fields in later pipeline versions. Upsert by the existing source/version key
// keeps re-imports idempotent while refreshing those non-patient reference rows.
const importDrugDiseaseRecords = async (file) => {
  let processed = 0; let inserted = 0; let batch = [];
  const writeBatch = async () => {
    if (!batch.length) return;
    const results = await Promise.all(batch.map((record) => prisma.drugDiseaseKnowledge.upsert({
      where: { normalizedDrug_normalizedDisease_relationship_source_datasetVersion: { normalizedDrug: record.normalizedDrug, normalizedDisease: record.normalizedDisease, relationship: record.relationship, source: record.source, datasetVersion: record.datasetVersion } },
      update: record,
      create: record,
    })));
    processed += batch.length; inserted += results.length; batch = [];
  };
  for await (const record of readNdjson(file)) {
    batch.push(record);
    if (batch.length === 100) await writeBatch();
  }
  await writeBatch();
  return { processed, inserted };
};

const terminology = path.join(projectRoot, "data", "processed", "indian-medicine", "terminology.ndjson");
const ddinter = path.join(projectRoot, "data", "processed", "ddinter", "interactions.ndjson");
if (!fs.existsSync(terminology) || !fs.existsSync(ddinter)) throw new Error("Run npm run data:process before importing clinical knowledge.");
const terminologyCount = await importRecords(terminology, "medicationTerminology");
const ddiCount = await importRecords(ddinter, "drugInteractionKnowledge");
// Remove rows imported before redundant DDInter parentheticals were normalized.
// The canonical replacements are imported first, so the cleanup never creates a
// coverage gap and remains idempotent on subsequent runs.
const legacyDdinterRows = await prisma.drugInteractionKnowledge.findMany({
  where: { source: "DDInter 2.0" },
  select: { id: true, drugA: true, normalizedDrugA: true, drugB: true, normalizedDrugB: true },
});
const legacyDdinterIds = legacyDdinterRows
  .filter((record) => normalizeDdinterDrugName(record.drugA) !== record.normalizedDrugA || normalizeDdinterDrugName(record.drugB) !== record.normalizedDrugB)
  .map((record) => record.id);
for (let index = 0; index < legacyDdinterIds.length; index += 1000) {
  await prisma.drugInteractionKnowledge.deleteMany({ where: { id: { in: legacyDdinterIds.slice(index, index + 1000) } } });
}
const drugCentralDirectory = path.join(projectRoot, "data", "processed", "drugcentral");
const diseaseFile = path.join(drugCentralDirectory, "drug-disease.ndjson");
const indicationFile = path.join(drugCentralDirectory, "drug-indications.ndjson");
// PostgreSQL COPY encodes null as `\\N`. The processor now maps it to null;
// discard only legacy invalid reference rows before the refreshed upsert.
await prisma.drugDiseaseKnowledge.deleteMany({ where: { source: "DrugCentral", OR: [{ existingDisease: "\\N" }, { umlsCui: "\\N" }, { snomedName: "\\N" }] } });
// Remove rows produced by the retired substring classifier (`contraindication`
// contains `indicat`) and invalid PostgreSQL null sentinels before re-import.
await prisma.drugIndicationKnowledge.deleteMany({
  where: {
    source: "DrugCentral",
    OR: [
      { indication: "\\N" },
      { normalizedIndication: "n" },
      { NOT: { relationship: { in: POSITIVE_DRUGCENTRAL_INDICATION_RELATIONSHIPS, mode: "insensitive" } } },
    ],
  },
});
const diseaseCount = fs.existsSync(diseaseFile) ? await importDrugDiseaseRecords(diseaseFile) : { processed: 0, inserted: 0 };
const indicationCount = fs.existsSync(indicationFile) ? await importDrugIndicationRecords(indicationFile) : { processed: 0, inserted: 0, skipped: 0 };
console.log(`Processed/imported terminology ${terminologyCount.processed}/${terminologyCount.inserted}, DDInter ${ddiCount.processed}/${ddiCount.inserted} (${legacyDdinterIds.length} legacy-normalized rows removed), DrugCentral disease ${diseaseCount.processed}/${diseaseCount.inserted}, DrugCentral indication ${indicationCount.processed}/${indicationCount.inserted} (${indicationCount.skipped} invalid or non-treatment rows skipped).`);
await prisma.$disconnect();
