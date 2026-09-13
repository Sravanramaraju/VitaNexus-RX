import { describe, expect, it } from "vitest";
import { eventRiskStatus } from "./eventRiskStatus.js";

describe("pending event-risk API contract", () => {
  it("never fabricates HGNN event probabilities before validation", () => {
    expect(eventRiskStatus).toEqual(expect.objectContaining({ status: "model_not_available", model: "HGNN", events: [], rankingInfluence: "none" }));
    expect(eventRiskStatus).not.toHaveProperty("probability");
  });
});
