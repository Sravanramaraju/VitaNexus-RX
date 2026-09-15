import { describe, expect, it } from "vitest";
import { isPositiveDrugCentralIndication } from "./drugcentralRelationships.js";

describe("DrugCentral indication relationship filtering", () => {
  it("accepts positive treatment relationships", () => {
    expect(isPositiveDrugCentralIndication(" indication ")).toBe(true);
    expect(isPositiveDrugCentralIndication("USED   FOR")).toBe(true);
  });

  it("never mistakes contraindication for indication", () => {
    expect(isPositiveDrugCentralIndication("contraindication")).toBe(false);
    expect(isPositiveDrugCentralIndication("warning")).toBe(false);
    expect(isPositiveDrugCentralIndication("precaution")).toBe(false);
  });
});
