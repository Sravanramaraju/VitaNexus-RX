import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const rawRoot = path.join(projectRoot, "data", "raw");
const processedRoot = path.join(projectRoot, "data", "processed");
const normalize = (value = "") => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
const timestampVersion = (file) => fs.statSync(file).mtime.toISOString().slice(0, 10);
const csvFields = (line) => {
  const fields = []; let value = ""; let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"' && line[index + 1] === '"') { value += '"'; index += 1; }
    else if (character === '"') quoted = !quoted;
    else if (character === "," && !quoted) { fields.push(value); value = ""; }
    else value += character;
  }
  fields.push(value);
  return fields;
};
const writeNdjson = (file, records) => fs.writeFileSync(file, records.map((record) => JSON.stringify(record)).join("\n") + (records.length ? "\n" : ""));

const processDdinter = () => {
  const directory = path.join(rawRoot, "ddinter");
  const outputDirectory = path.join(processedRoot, "ddinter");
  fs.mkdirSync(outputDirectory, { recursive: true });
  const seen = new Set(); const records = [];
  for (const fileName of fs.readdirSync(directory).filter((file) => file.endsWith(".csv"))) {
    const file = path.join(directory, fileName); const version = timestampVersion(file);
    const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);
    for (const line of lines.slice(1)) {
      if (!line) continue;
      const [ddinterIdA, drugA, ddinterIdB, drugB, rawSeverity] = csvFields(line);
      const displaySeverity = String(rawSeverity || "").trim().toUpperCase();
      if (!drugA || !drugB || !["MAJOR", "MODERATE", "MINOR"].includes(displaySeverity)) continue;
      const pair = [{ id: ddinterIdA, name: drugA, normalized: normalize(drugA) }, { id: ddinterIdB, name: drugB, normalized: normalize(drugB) }].sort((a, b) => a.normalized.localeCompare(b.normalized));
      const record = { drugA: pair[0].name, normalizedDrugA: pair[0].normalized, ddinterIdA: pair[0].id || null, drugB: pair[1].name, normalizedDrugB: pair[1].normalized, ddinterIdB: pair[1].id || null, rawSeverity: String(rawSeverity).trim(), displaySeverity, source: "DDInter 2.0", datasetVersion: `DDInter 2.0 import ${version}` };
      const key = `${record.normalizedDrugA}|${record.normalizedDrugB}|${record.displaySeverity}`;
      if (!seen.has(key)) { seen.add(key); records.push(record); }
    }
  }
  writeNdjson(path.join(outputDirectory, "interactions.ndjson"), records);
  console.log(`Processed ${records.length} unique DDInter 2.0 interactions.`);
};

const canonicalGeneric = (salt = "") => salt.replace(/\([^)]*\)/g, "").replace(/\s*\+\s*/g, " + ").replace(/\s+/g, " ").trim();
const processIndianMedicine = async () => {
  const directory = path.join(rawRoot, "indian medicne");
  const fileName = fs.readdirSync(directory).find((file) => file.endsWith(".csv"));
  if (!fileName) throw new Error("No Indian Medicine CSV was found.");
  const file = path.join(directory, fileName); const outputDirectory = path.join(processedRoot, "indian-medicine");
  fs.mkdirSync(outputDirectory, { recursive: true });
  const version = `Indian Medicine Dataset import ${timestampVersion(file)}`; const records = []; const seen = new Set();
  const reader = readline.createInterface({ input: fs.createReadStream(file, { encoding: "utf8" }), crlfDelay: Infinity });
  let header = true;
  for await (const line of reader) {
    if (header) { header = false; continue; }
    const [, brand, salt] = csvFields(line);
    const generic = canonicalGeneric(salt);
    if (!brand || !generic) continue;
    const record = { brand: brand.trim(), normalizedBrand: normalize(brand), generic, normalizedGeneric: normalize(generic), source: "Indian Medicine Dataset", version };
    const key = `${record.normalizedBrand}|${record.normalizedGeneric}`;
    if (!seen.has(key)) { seen.add(key); records.push(record); }
  }
  writeNdjson(path.join(outputDirectory, "terminology.ndjson"), records);
  console.log(`Processed ${records.length} Indian Medicine terminology mappings.`);
};

processDdinter();
await processIndianMedicine();
