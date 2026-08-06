import { createApp } from "./app.js";
import { config } from "./config.js";
import { prisma } from "./db.js";

const app = createApp();
const server = app.listen(config.port, () => console.log(`VitaNexus-RX API listening on http://localhost:${config.port}/api/v1`));

const close = async () => {
  server.close(async () => {
    await prisma.$disconnect();
    process.exit(0);
  });
};
process.on("SIGINT", close);
process.on("SIGTERM", close);
