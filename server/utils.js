import crypto from "node:crypto";

export const stableHash = (value) =>
  crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex");

export const publicClinician = (clinician) => ({
  id: clinician.id,
  name: clinician.name,
  email: clinician.email,
  phone: clinician.phone,
  gender: clinician.gender,
  specialty: clinician.specialty,
  practiceSetting: clinician.practiceSetting,
  role: clinician.role,
  createdAt: clinician.createdAt,
});

export const normalizedText = (value) => value.trim().replace(/\s+/g, " ");

export const toMedicationStatus = (value = "active") =>
  ({ active: "ACTIVE", "on-hold": "ON_HOLD", discontinued: "DISCONTINUED" })[
    value.toLowerCase()
  ] || "ACTIVE";

export const fromMedicationStatus = (value) =>
  ({ ACTIVE: "active", ON_HOLD: "on-hold", DISCONTINUED: "discontinued" })[value] ||
  "active";

export const audit = (client, event) =>
  client.auditEvent.create({
    data: {
      actorId: event.actorId,
      action: event.action,
      entityType: event.entityType,
      entityId: event.entityId,
      requestId: event.requestId,
      metadata: event.metadata,
    },
  });
