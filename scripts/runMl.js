import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const python = process.platform === "win32"
  ? path.join(projectRoot, "ml", ".venv", "Scripts", "python.exe")
  : path.join(projectRoot, "ml", ".venv", "bin", "python");

if (!existsSync(python)) {
  console.error("ML environment missing. Create ml/.venv and install ml/requirements.txt first.");
  process.exit(1);
}

const result = spawnSync(python, ["-m", "vitanexus_ml.cli", ...process.argv.slice(2)], {
  cwd: projectRoot,
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: path.join(projectRoot, "ml", "src") },
});
process.exit(result.status ?? 1);
