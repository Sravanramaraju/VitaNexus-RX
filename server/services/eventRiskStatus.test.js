import { describe, expect, it } from "vitest";
import { eventRiskStatus } from "./eventRiskStatus.js";

describe("baseline event-profile product contract", () => {
  it("labels the HGNN as audit-pending supplementary evidence", () => {
    expect(eventRiskStatus).toEqual(expect.objectContaining({ status: "BASELINE_ACTIVE_AUDIT_PENDING", model: "HGNN", modelStage: "BASELINE", validationStatus: "AUDIT_PENDING", rankingInfluence: "none" }));
    expect(eventRiskStatus).not.toHaveProperty("probability");
    expect(eventRiskStatus).not.toHaveProperty("events");
  });
});
