import "dotenv/config";

const isProduction = process.env.NODE_ENV === "production";
const configuredCorsOrigins = new Set(
  (process.env.CORS_ORIGIN || "http://localhost:5173")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
);
const developmentLoopbackOrigin = /^https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/;

if (isProduction && !process.env.JWT_ACCESS_SECRET) {
  throw new Error("JWT_ACCESS_SECRET must be configured in production.");
}

export const config = Object.freeze({
  environment: process.env.NODE_ENV || "development",
  isProduction,
  port: Number(process.env.PORT || 4000),
  isCorsOriginAllowed: (origin) =>
    !origin ||
    configuredCorsOrigins.has(origin) ||
    (!isProduction && developmentLoopbackOrigin.test(origin)),
  jwtSecret: process.env.JWT_ACCESS_SECRET || "development-only-change-this-secret",
  jwtExpiresIn: process.env.JWT_ACCESS_EXPIRES_IN || "15m",
  adrMlBaseUrl: process.env.ADR_ML_BASE_URL || "http://127.0.0.1:8000",
  adrMlTimeoutMs: Math.max(1000, Number(process.env.ADR_ML_TIMEOUT_MS || 30000)),
});
