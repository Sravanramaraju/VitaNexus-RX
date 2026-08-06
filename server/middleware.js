import crypto from "node:crypto";
import jwt from "jsonwebtoken";
import { ZodError } from "zod";
import { config } from "./config.js";

export const requestContext = (req, res, next) => {
  req.requestId = req.get("x-request-id") || crypto.randomUUID();
  res.setHeader("x-request-id", req.requestId);
  next();
};

export const authenticate = (req, res, next) => {
  const token = req.get("authorization")?.replace(/^Bearer\s+/i, "");
  if (!token) return next(Object.assign(new Error("Authentication is required."), { status: 401, code: "UNAUTHENTICATED" }));
  try {
    const payload = jwt.verify(token, config.jwtSecret);
    req.auth = { clinicianId: payload.sub, role: payload.role };
    return next();
  } catch {
    return next(Object.assign(new Error("Your session is invalid or has expired."), { status: 401, code: "INVALID_TOKEN" }));
  }
};

export const notFound = (req, res) =>
  res.status(404).json({
    error: { code: "NOT_FOUND", message: `No route matches ${req.method} ${req.originalUrl}.` },
    requestId: req.requestId,
  });

export const errorHandler = (error, req, res, next) => { // eslint-disable-line no-unused-vars
  if (error instanceof ZodError) {
    return res.status(422).json({
      error: {
        code: "VALIDATION_ERROR",
        message: "One or more fields are invalid.",
        details: error.issues.map((issue) => ({ path: issue.path.join("."), message: issue.message })),
      },
      requestId: req.requestId,
    });
  }
  if (error.code === "P2002") {
    return res.status(409).json({
      error: { code: "DUPLICATE_RECORD", message: "A record with this value already exists." },
      requestId: req.requestId,
    });
  }
  if (error.code === "P2025") {
    return res.status(404).json({
      error: { code: "NOT_FOUND", message: "The requested record no longer exists." },
      requestId: req.requestId,
    });
  }
  const status = error.status || 500;
  if (status >= 500) console.error(`[${req.requestId}]`, error);
  return res.status(status).json({
    error: {
      code: error.code || "INTERNAL_ERROR",
      message: status >= 500 ? "An unexpected server error occurred." : error.message,
    },
    requestId: req.requestId,
  });
};
