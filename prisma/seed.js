import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const terminology = path.join(projectRoot, "data", "processed", "indian-medicine", "terminology.ndjson");
if (!existsSync(terminology)) throw new Error("Processed terminology is missing. Run npm run data:process before npm run db:seed.");
const child = spawn(process.execPath, [path.join(projectRoot, "scripts", "importClinicalKnowledge.js")], { stdio: "inherit" });
child.on("exit", (code) => process.exitCode = code || 0);
