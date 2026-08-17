import { spawn } from "node:child_process";
import process from "node:process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const viteCommand = path.join(
  projectRoot,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "vite.cmd" : "vite",
);

const services = [
  { name: "API", command: process.execPath, args: ["--watch", "server/index.js"] },
  { name: "web app", command: viteCommand, args: [] },
].map((service) => ({
  ...service,
  process: spawn(service.command, service.args, {
    cwd: projectRoot,
    stdio: "inherit",
  }),
}));

let shuttingDown = false;
const stopServices = (exitCode = 0) => {
  if (shuttingDown) return;
  shuttingDown = true;
  services.forEach(({ process: child }) => {
    if (child.exitCode === null && !child.killed) child.kill();
  });
  setTimeout(() => process.exit(exitCode), 250).unref();
};

services.forEach(({ name, process: child }) => {
  child.on("error", (error) => {
    console.error(`Unable to start the ${name}: ${error.message}`);
    stopServices(1);
  });
  child.on("exit", (code) => {
    if (!shuttingDown) {
      console.error(`${name} stopped unexpectedly${code === null ? "" : ` (exit ${code})`}.`);
      stopServices(code || 1);
    }
  });
});

process.once("SIGINT", () => stopServices());
process.once("SIGTERM", () => stopServices());
