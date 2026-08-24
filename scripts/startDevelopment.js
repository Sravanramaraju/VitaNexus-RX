import { spawn } from "node:child_process";
import process from "node:process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const viteEntryPoint = path.join(
  projectRoot,
  "node_modules",
  "vite",
  "bin",
  "vite.js",
);

const serviceDefinitions = [
  { name: "API", command: process.execPath, args: ["--watch", "server/index.js"] },
  // Run Vite through Node instead of vite.cmd. Windows cannot spawn a .cmd
  // shim without a shell, which previously left the API process orphaned.
  { name: "web app", command: process.execPath, args: [viteEntryPoint] },
];

const services = [];
try {
  serviceDefinitions.forEach((service) => {
    services.push({
      ...service,
      process: spawn(service.command, service.args, {
        cwd: projectRoot,
        stdio: "inherit",
      }),
    });
  });
} catch (error) {
  services.forEach(({ process: child }) => child.kill());
  throw error;
}

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
