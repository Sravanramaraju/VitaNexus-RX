import request from "supertest";
import { describe, expect, it } from "vitest";
import { createApp } from "./app.js";

const app = createApp();

describe("API boundary", () => {
  it("reports service health with a correlation ID", async () => {
    const response = await request(app).get("/api/v1/health");
    expect(response.status).toBe(200);
    expect(response.body.data.status).toBe("ok");
    expect(response.headers["x-request-id"]).toBeTruthy();
  });

  it("returns a structured error for protected endpoints", async () => {
    const response = await request(app).get("/api/v1/patients");
    expect(response.status).toBe(401);
    expect(response.body.error.code).toBe("UNAUTHENTICATED");
  });

  it("returns a structured 404 for unknown routes", async () => {
    const response = await request(app).get("/api/v1/no-such-resource");
    expect(response.status).toBe(404);
    expect(response.body.error.code).toBe("NOT_FOUND");
  });
});
