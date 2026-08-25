import { spawn, spawnSync } from "node:child_process";
import net from "node:net";
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

const responseContains = async (url, expectedText) => {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1_000) });
    return response.ok && (await response.text()).includes(expectedText);
  } catch {
    return false;
  }
};

const addressIsListening = (host, port) =>
  new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    let result = false;
    let finished = false;
    const finish = (isListening) => {
      if (finished) return;
      finished = true;
      result = isListening;
      socket.destroy();
    };
    socket.once("close", () => resolve(result));
    socket.setTimeout(750);
    socket.once("connect", () => finish(true));
    socket.once("error", () => finish(false));
    socket.once("timeout", () => finish(false));
  });

const portIsListening = async (port) =>
  (
    await Promise.all([
      addressIsListening("127.0.0.1", port),
      addressIsListening("::1", port),
    ])
  ).some(Boolean);

const stopProcessTree = (child) => {
  if (child.exitCode !== null || !child.pid) return;
  if (process.platform === "win32") {
    // Terminate descendants too if either service gains helper processes.
    spawnSync("taskkill.exe", ["/pid", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
    return;
  }
  child.kill("SIGTERM");
};

const startServices = () => {
  const serviceDefinitions = [
    // Keep the combined launcher single-process per service. Node watch mode
    // creates another Windows child that can survive when its watcher is killed.
    { name: "API", command: process.execPath, args: ["server/index.js"] },
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
    services.forEach(({ process: child }) => stopProcessTree(child));
    throw error;
  }

  let shuttingDown = false;
  const stopServices = (exitCode = 0) => {
    if (shuttingDown) return;
    shuttingDown = true;
    services.forEach(({ process: child }) => stopProcessTree(child));
    setTimeout(() => process.exit(exitCode), 250).unref();
  };

  services.forEach(({ name, process: child }) => {
    child.on("error", (error) => {
      console.error(`Unable to start the ${name}: ${error.message}`);
      stopServices(1);
    });
    child.on("exit", (code) => {
      // On Windows, Ctrl+C can terminate a child just before the launcher's
      // SIGINT handler runs. Defer classification so normal shutdown stays quiet.
      setTimeout(() => {
        if (!shuttingDown) {
          console.error(
            `${name} stopped unexpectedly${code === null ? "" : ` (exit ${code})`}.`,
          );
          stopServices(code || 1);
        }
      }, 100);
    });
  });

  process.once("SIGINT", () => stopServices());
  process.once("SIGTERM", () => stopServices());
};

const [existingWebApp, existingApi, webPortInUse, apiPortInUse] =
  await Promise.all([
    responseContains(
      "http://localhost:5173/register",
      "<title>VitaNexus-RX</title>",
    ),
    responseContains(
      "http://localhost:4000/api/v1/health",
      '"service":"vitanexus-rx-api"',
    ),
    portIsListening(5173),
    portIsListening(4000),
  ]);

const conflicts = [
  ...(webPortInUse ? ["5173 (web app)"] : []),
  ...(apiPortInUse ? ["4000 (API)"] : []),
];

if (existingWebApp && existingApi) {
  console.log("VitaNexus-RX is already running at http://localhost:5173.");
} else if (conflicts.length) {
  console.error(
    `Cannot start VitaNexus-RX because ${conflicts.join(" and ")} ${conflicts.length === 1 ? "is" : "are"} already in use.`,
  );
  console.error("Stop the existing process, then run npm run dev again.");
  process.exitCode = 1;
} else {
  startServices();
}
