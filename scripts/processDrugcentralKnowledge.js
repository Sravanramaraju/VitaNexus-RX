import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { createGunzip } from "node:zlib";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const rawDirectory = path.join(projectRoot, "data", "raw", "durgcentral");
const dumpName = fs.readdirSync(rawDirectory).find((file) => file.endsWith(".sql.gz"));
if (!dumpName) throw new Error("No DrugCentral PostgreSQL dump was found in data/raw/durgcentral.");
const dump = path.join(rawDirectory, dumpName);
const version = `DrugCentral ${dumpName.match(/\d{8}/)?.[0] || "downloaded"}`;
const outputDirectory = path.join(projectRoot, "data", "processed", "drugcentral");
fs.mkdirSync(outputDirectory, { recursive: true });
const normalize = (value = "") => String(value || "").toLowerCase().trim().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
const copyValue = (value) => value && value !== "\\N" ? value : null;
const readDump = () => readline.createInterface({ input: fs.createReadStream(dump).pipe(createGunzip()), crlfDelay: Infinity });
const copyTable = (line) => line.match(/^COPY\s+(?:public\.)?([a-z_]+)\s+\(/i)?.[1]?.toLowerCase() || null;
const drugDiseaseAssessment = (relationship) => {
  const value = relationship.toLowerCase();
  if (/contraindicat|avoid/.test(value)) return "HIGH";
  if (/warning|caution|not recommended/.test(value)) return "MODERATE";
  if (/precaution|monitor/.test(value)) return "LOW";
  return null;
};
const isIndication = (relationship) => /indicat|treat|therapy|used for/.test(relationship.toLowerCase());

// The dump is parsed as PostgreSQL COPY sections. No drug/disease pair is hard-coded:
// relationship labels determine whether an imported row is a contraindication/caution
// or an indication relation, and source fields preserve the original evidence text.
const structures = new Map(); let table = null;
for await (const line of readDump()) {
  const nextTable = copyTable(line); if (nextTable) { table = nextTable; continue; }
  if (line === "\\.") { table = null; continue; }
  if (table !== "structures" || !line) continue;
  // DrugCentral `structures` COPY layout begins with `cd_id`, `cd_formula`, …
  // and stores the canonical drug name at column 10 (zero-based index 9).
  const fields = line.split("\t");
  const id = copyValue(fields[0]); const name = copyValue(fields[9]);
  if (id && name) structures.set(id, name);
}

const diseaseOut = fs.createWriteStream(path.join(outputDirectory, "drug-disease.ndjson"));
const indicationOut = fs.createWriteStream(path.join(outputDirectory, "drug-indications.ndjson"));
let diseaseCount = 0; let indicationCount = 0; table = null;
for await (const line of readDump()) {
  const nextTable = copyTable(line); if (nextTable) { table = nextTable; continue; }
  if (line === "\\.") { table = null; continue; }
  if (table !== "omop_relationship" || !line) continue;
  const [, rawStructId, , rawRelationship, rawConceptName, rawUmlsCui, rawSnomedName] = line.split("\t");
  const structId = copyValue(rawStructId);
  const relationship = copyValue(rawRelationship);
  const conceptName = copyValue(rawConceptName);
  const umlsCui = copyValue(rawUmlsCui);
  const snomedName = copyValue(rawSnomedName);
  const genericDrug = structures.get(structId);
  const disease = snomedName || conceptName;
  if (!genericDrug || !disease || !relationship) continue;
  const evidence = [relationship, conceptName, umlsCui].filter(Boolean).join(" | ");
  const assessment = drugDiseaseAssessment(relationship);
  if (assessment) {
    const normalizedDisease = normalize(disease);
    const normalizedConceptName = normalize(conceptName);
    const normalizedSnomedName = normalize(snomedName);
    const diseaseIdentity = umlsCui ? `UMLS:${umlsCui}` : `DRUGCENTRAL:${version}:${normalizedDisease}`;
    diseaseOut.write(`${JSON.stringify({ genericDrug, normalizedDrug: normalize(genericDrug), existingDisease: disease, normalizedDisease, diseaseIdentity, conceptName: conceptName || "", normalizedConceptName, umlsCui: umlsCui || null, snomedName: snomedName || null, normalizedSnomedName, relationship, assessment, evidence, source: "DrugCentral", datasetVersion: version })}\n`);
    diseaseCount += 1;
  }
  if (isIndication(relationship)) {
    indicationOut.write(`${JSON.stringify({ indication: disease, normalizedIndication: normalize(disease), genericDrug, normalizedDrug: normalize(genericDrug), relationship, evidence, source: "DrugCentral", datasetVersion: version })}\n`);
    indicationCount += 1;
  }
}
diseaseOut.end(); indicationOut.end();
console.log(`Processed ${diseaseCount} DrugCentral drug-disease and ${indicationCount} indication relationships from ${version}.`);
