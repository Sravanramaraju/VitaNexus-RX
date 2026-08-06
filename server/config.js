import "dotenv/config";

const isProduction = process.env.NODE_ENV === "production";

if (isProduction && !process.env.JWT_ACCESS_SECRET) {
  throw new Error("JWT_ACCESS_SECRET must be configured in production.");
}

export const config = Object.freeze({
  environment: process.env.NODE_ENV || "development",
  isProduction,
  port: Number(process.env.PORT || 4000),
  corsOrigin: process.env.CORS_ORIGIN || "http://localhost:5173",
  jwtSecret: process.env.JWT_ACCESS_SECRET || "development-only-change-this-secret",
  jwtExpiresIn: process.env.JWT_ACCESS_EXPIRES_IN || "15m",
});
