import { z } from "zod";

const text = (max = 255) => z.string().trim().min(1).max(max);
const optionalText = (max = 255) => z.string().trim().max(max).optional().nullable();

export const registrationSchema = z.object({
  name: text(120).regex(/^[A-Za-z][A-Za-z .'-]*$/, "Name contains unsupported characters."),
  email: z.string().trim().email().max(254).transform((value) => value.toLowerCase()),
  password: z.string().min(8).max(128).regex(/[A-Za-z]/, "Password must include a letter.").regex(/\d/, "Password must include a number.").regex(/[^A-Za-z0-9]/, "Password must include a special character."),
  phone: optionalText(30),
  gender: optionalText(50),
  specialty: optionalText(120),
  practiceSetting: optionalText(120),
});

export const loginSchema = z.object({
  email: z.string().trim().email().max(254).transform((value) => value.toLowerCase()),
  password: z.string().min(1).max(128),
});

export const medicationSchema = z.object({
  brand: optionalText(),
  genericName: optionalText(),
  dosage: optionalText(100),
  frequency: optionalText(100),
  route: optionalText(100),
  status: z.enum(["active", "on-hold", "discontinued"]).default("active"),
  source: optionalText(100),
}).refine((value) => value.brand || value.genericName, "A brand or generic medication name is required.");

export const conditionSchema = z.object({ display: text(), code: optionalText(100), duration: optionalText(100), source: optionalText(100) });
export const allergySchema = z.object({ display: text(), code: optionalText(100), severity: optionalText(100), reaction: optionalText(255), source: optionalText(100) });

export const patientCreateSchema = z.object({
  name: text(120),
  age: z.coerce.number().int().min(0).max(130),
  gender: text(50),
  conditions: z.array(conditionSchema).max(100).default([]),
  allergies: z.array(allergySchema).max(100).default([]),
  medications: z.array(medicationSchema).max(100).default([]),
});

export const patientUpdateSchema = patientCreateSchema.partial().extend({ expectedVersion: z.coerce.number().int().positive().optional() });
export const profileSchema = z.object({ items: z.array(z.unknown()).max(100), expectedVersion: z.coerce.number().int().positive().optional() });

export const consultationSchema = z.object({
  indication: text(),
  indicationId: z.string().uuid(),
  indicationSource: z.literal("DrugCentral"),
  indicationDatasetVersion: text(120),
  candidateBrand: optionalText(),
  candidateGeneric: optionalText(),
  dosage: text(100),
  frequency: text(100).regex(/^(1d|2d|3d|1w|2w|3w)$/i, "Frequency must be one of 1d, 2d, 3d, 1w, 2w, or 3w."),
  route: optionalText(100),
}).refine((value) => value.candidateBrand || value.candidateGeneric, "A brand or generic prescribed drug name is required.");

export const noteSchema = z.object({ text: text(10_000) });
export const followUpSchema = z.object({ adverseEvent: text(), eventCode: optionalText(100), severity: text(50), durationDays: z.coerce.number().int().min(0).max(3650).optional().nullable(), notes: optionalText(10_000) });
export const draftSchema = z.object({ payload: z.record(z.string(), z.unknown()), expectedVersion: z.coerce.number().int().positive().optional() });
