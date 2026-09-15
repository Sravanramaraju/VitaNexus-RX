import { describe, expect, it } from "vitest";
import { clinicianProfileUpdateSchema } from "./schemas.js";

describe("clinician profile update schema", () => {
  it("accepts only normalized contact details", () => {
    expect(clinicianProfileUpdateSchema.parse({ email: " Doctor@Hospital.com ", phone: "9876543210" })).toEqual({ email: "doctor@hospital.com", phone: "9876543210" });
  });

  it("rejects attempts to edit protected professional details", () => {
    expect(() => clinicianProfileUpdateSchema.parse({ email: "doctor@hospital.com", phone: null, name: "Changed name" })).toThrow();
  });

  it("rejects an invalid phone number", () => {
    expect(() => clinicianProfileUpdateSchema.parse({ email: "doctor@hospital.com", phone: "123" })).toThrow();
  });
});
