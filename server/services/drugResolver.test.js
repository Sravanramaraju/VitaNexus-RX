import { describe, expect, it } from "vitest";
import { resolveDrug } from "./drugResolver.js";

const terminologyClient = {
  medicationTerminology: {
    findFirst: async ({ where }) => where.OR.some((clause) => clause.normalizedBrand === "dolo 650")
      ? { brand: "Dolo 650 Tablet", generic: "Paracetamol", source: "Indian Medicine Dataset", version: "Indian Medicine Dataset import 2026-08-11" }
      : null,
  },
};

describe("shared drug resolver", () => {
  it("maps an Indian brand to its canonical generic using imported terminology", async () => {
    await expect(resolveDrug(terminologyClient, { enteredName: "Dolo 650" })).resolves.toMatchObject({ enteredName: "Dolo 650", normalizedName: "dolo 650", genericName: "Paracetamol", mappingSource: "Indian Medicine Dataset" });
  });

  it("keeps a generic input usable when no brand mapping exists", async () => {
    await expect(resolveDrug(terminologyClient, { enteredName: "Metformin", genericName: "Metformin" })).resolves.toMatchObject({ genericName: "Metformin", mappingSource: null });
  });
});
