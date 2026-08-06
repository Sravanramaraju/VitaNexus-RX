import express from "express";
import crypto from "node:crypto";
import cors from "cors";
import helmet from "helmet";
import morgan from "morgan";
import rateLimit from "express-rate-limit";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { config } from "./config.js";
import { prisma } from "./db.js";
import { authenticate, errorHandler, notFound, requestContext } from "./middleware.js";
import { allergySchema, conditionSchema, consultationSchema, draftSchema, followUpSchema, loginSchema, medicationSchema, noteSchema, patientCreateSchema, patientUpdateSchema, profileSchema, registrationSchema } from "./schemas.js";
import { audit, normalizedText, publicClinician, stableHash } from "./utils.js";
import { clinicalSafetyAssessment, adrPrediction, recommendations, versions } from "./services/clinicalDemo.js";
import { consultationResponse, mapAllergyInput, mapConditionInput, mapMedicationInput, patientInclude, patientResponse } from "./repository.js";

const asyncRoute = (handler) => (req, res, next) => Promise.resolve(handler(req, res, next)).catch(next);
const tokenFor = (clinician) => jwt.sign({ role: clinician.role }, config.jwtSecret, { subject: clinician.id, expiresIn: config.jwtExpiresIn });
const send = (res, status, data, requestId) => res.status(status).json({ data, requestId });
const forbidden = () => Object.assign(new Error("You do not have access to this record."), { status: 404, code: "NOT_FOUND" });
const conflict = () => Object.assign(new Error("The record has changed. Refresh it and retry your update."), { status: 409, code: "VERSION_CONFLICT" });

const getPatient = async (client, clinicianId, id, include = patientInclude) => {
  const patient = await client.patient.findFirst({ where: { id, clinicianId, deletedAt: null }, ...(include ? { include } : {}) });
  if (!patient) throw forbidden();
  return patient;
};
const getConsultation = async (client, clinicianId, id, includePatient = true) => {
  const consultation = await client.consultation.findFirst({
    where: { id, clinicianId, patient: { deletedAt: null } },
    include: { patient: includePatient ? { include: { conditions: { where: { isActive: true } }, allergies: { where: { isActive: true } }, medications: true } } : false, followUps: { orderBy: { createdAt: "desc" } }, notes: { orderBy: { updatedAt: "desc" }, take: 1 }, analyses: { orderBy: { createdAt: "desc" } }, adrPredictions: { orderBy: { createdAt: "desc" }, take: 1 }, recommendations: { orderBy: { createdAt: "desc" }, take: 1 } },
  });
  if (!consultation) throw forbidden();
  return consultation;
};

const replaceProfileCollection = async (req, res, entity, schema, mapper) => {
  const body = profileSchema.parse(req.body);
  const items = body.items.map((item) => schema.parse(item));
  const patient = await getPatient(prisma, req.auth.clinicianId, req.params.patientId, false);
  if (body.expectedVersion && patient.version !== body.expectedVersion) throw conflict();
  const relation = entity === "conditions" ? "conditions" : entity === "allergies" ? "allergies" : "medications";
  const result = await prisma.$transaction(async (tx) => {
    await tx[entity === "conditions" ? "patientCondition" : entity === "allergies" ? "patientAllergy" : "patientMedication"].deleteMany({ where: { patientId: patient.id } });
    await tx.patient.update({ data: { [relation]: { create: items.map(mapper) }, version: { increment: 1 } }, where: { id: patient.id } });
    const updated = await getPatient(tx, req.auth.clinicianId, patient.id);
    await audit(tx, { actorId: req.auth.clinicianId, action: `PATIENT_${entity.toUpperCase()}_REPLACED`, entityType: "Patient", entityId: patient.id, requestId: req.requestId, metadata: { count: items.length } });
    return updated;
  });
  send(res, 200, patientResponse(result), req.requestId);
};

export const createApp = () => {
  const app = express();
  app.disable("x-powered-by");
  app.use(requestContext);
  app.use(helmet());
  app.use(cors({ origin: config.corsOrigin.split(",").map((origin) => origin.trim()), credentials: false }));
  app.use(express.json({ limit: "1mb" }));
  app.use(morgan(config.isProduction ? "combined" : "dev"));

  app.get("/api/v1/health", (req, res) => send(res, 200, { status: "ok", service: "vitanexus-rx-api", timestamp: new Date().toISOString() }, req.requestId));
  app.get("/api/v1/ready", asyncRoute(async (req, res) => { await prisma.$queryRaw`SELECT 1`; send(res, 200, { status: "ready" }, req.requestId); }));

  const authLimiter = rateLimit({ windowMs: 15 * 60 * 1000, limit: 10, standardHeaders: "draft-8", legacyHeaders: false, handler: (req, res) => res.status(429).json({ error: { code: "RATE_LIMITED", message: "Too many authentication attempts. Try again later." }, requestId: req.requestId }) });
  app.post("/api/v1/auth/register", authLimiter, asyncRoute(async (req, res) => {
    const input = registrationSchema.parse(req.body);
    const passwordHash = await bcrypt.hash(input.password, 12);
    const clinician = await prisma.$transaction(async (tx) => {
      const { password, ...profile } = input;
      void password;
      const created = await tx.clinician.create({ data: { ...profile, passwordHash } });
      await audit(tx, { actorId: created.id, action: "CLINICIAN_REGISTERED", entityType: "Clinician", entityId: created.id, requestId: req.requestId });
      return created;
    });
    send(res, 201, { clinician: publicClinician(clinician), accessToken: tokenFor(clinician), tokenType: "Bearer", expiresIn: config.jwtExpiresIn }, req.requestId);
  }));
  app.post("/api/v1/auth/login", authLimiter, asyncRoute(async (req, res) => {
    const input = loginSchema.parse(req.body);
    const clinician = await prisma.clinician.findUnique({ where: { email: input.email } });
    if (!clinician || !(await bcrypt.compare(input.password, clinician.passwordHash))) throw Object.assign(new Error("Invalid email or password."), { status: 401, code: "INVALID_CREDENTIALS" });
    await audit(prisma, { actorId: clinician.id, action: "CLINICIAN_LOGGED_IN", entityType: "Clinician", entityId: clinician.id, requestId: req.requestId });
    send(res, 200, { clinician: publicClinician(clinician), accessToken: tokenFor(clinician), tokenType: "Bearer", expiresIn: config.jwtExpiresIn }, req.requestId);
  }));
  app.get("/api/v1/auth/me", authenticate, asyncRoute(async (req, res) => {
    const clinician = await prisma.clinician.findUniqueOrThrow({ where: { id: req.auth.clinicianId } });
    send(res, 200, publicClinician(clinician), req.requestId);
  }));
  app.post("/api/v1/auth/logout", authenticate, asyncRoute(async (req, res) => {
    await audit(prisma, { actorId: req.auth.clinicianId, action: "CLINICIAN_LOGGED_OUT", entityType: "Clinician", entityId: req.auth.clinicianId, requestId: req.requestId });
    send(res, 200, { loggedOut: true, message: "Discard the access token on the client." }, req.requestId);
  }));

  app.get("/api/v1/patients", authenticate, asyncRoute(async (req, res) => {
    const query = String(req.query.q || "").trim();
    const status = String(req.query.status || "").toLowerCase();
    const patients = await prisma.patient.findMany({ where: { clinicianId: req.auth.clinicianId, deletedAt: null, ...(query ? { OR: [{ name: { contains: query, mode: "insensitive" } }, { publicId: { contains: query, mode: "insensitive" } }] } : {}) }, include: { consultations: { select: { id: true, status: true, createdAt: true }, orderBy: { createdAt: "desc" } } }, orderBy: { updatedAt: "desc" }, take: Math.min(Number(req.query.limit || 50), 100) });
    const summaries = patients.map((patient) => ({ id: patient.id, publicId: patient.publicId, name: patient.name, age: patient.age, gender: patient.gender, updatedAt: patient.updatedAt, latestConsultation: patient.consultations[0] || null, consultationCount: patient.consultations.length })).filter((patient) => !status || patient.latestConsultation?.status.toLowerCase().replace("_", "-") === status);
    send(res, 200, { items: summaries, count: summaries.length }, req.requestId);
  }));
  app.post("/api/v1/patients", authenticate, asyncRoute(async (req, res) => {
    const input = patientCreateSchema.parse(req.body);
    const patient = await prisma.$transaction(async (tx) => {
      const number = await tx.patient.count({ where: { clinicianId: req.auth.clinicianId } }) + 1;
      const created = await tx.patient.create({ data: { clinicianId: req.auth.clinicianId, publicId: `P-${String(number).padStart(4, "0")}-${crypto.randomUUID().slice(0, 4).toUpperCase()}`, name: input.name, age: input.age, gender: input.gender, conditions: { create: input.conditions.map(mapConditionInput) }, allergies: { create: input.allergies.map(mapAllergyInput) }, medications: { create: input.medications.map(mapMedicationInput) } }, include: patientInclude });
      await audit(tx, { actorId: req.auth.clinicianId, action: "PATIENT_CREATED", entityType: "Patient", entityId: created.id, requestId: req.requestId });
      return created;
    });
    send(res, 201, patientResponse(patient), req.requestId);
  }));
  app.get("/api/v1/patients/:patientId", authenticate, asyncRoute(async (req, res) => send(res, 200, patientResponse(await getPatient(prisma, req.auth.clinicianId, req.params.patientId)), req.requestId)));
  app.patch("/api/v1/patients/:patientId", authenticate, asyncRoute(async (req, res) => {
    const input = patientUpdateSchema.parse(req.body);
    const existing = await getPatient(prisma, req.auth.clinicianId, req.params.patientId, false);
    if (input.expectedVersion && existing.version !== input.expectedVersion) throw conflict();
    const patient = await prisma.$transaction(async (tx) => {
      const data = { ...(input.name !== undefined ? { name: input.name } : {}), ...(input.age !== undefined ? { age: input.age } : {}), ...(input.gender !== undefined ? { gender: input.gender } : {}), version: { increment: 1 } };
      if (input.conditions) data.conditions = { deleteMany: {}, create: input.conditions.map(mapConditionInput) };
      if (input.allergies) data.allergies = { deleteMany: {}, create: input.allergies.map(mapAllergyInput) };
      if (input.medications) data.medications = { deleteMany: {}, create: input.medications.map(mapMedicationInput) };
      await tx.patient.update({ where: { id: existing.id }, data });
      const updated = await getPatient(tx, req.auth.clinicianId, existing.id);
      await audit(tx, { actorId: req.auth.clinicianId, action: "PATIENT_UPDATED", entityType: "Patient", entityId: existing.id, requestId: req.requestId });
      return updated;
    });
    send(res, 200, patientResponse(patient), req.requestId);
  }));
  app.delete("/api/v1/patients/:patientId", authenticate, asyncRoute(async (req, res) => {
    const patient = await getPatient(prisma, req.auth.clinicianId, req.params.patientId, false);
    await prisma.$transaction(async (tx) => { await tx.patient.update({ where: { id: patient.id }, data: { deletedAt: new Date(), version: { increment: 1 } } }); await audit(tx, { actorId: req.auth.clinicianId, action: "PATIENT_ARCHIVED", entityType: "Patient", entityId: patient.id, requestId: req.requestId }); });
    res.status(204).end();
  }));
  app.put("/api/v1/patients/:patientId/conditions", authenticate, asyncRoute((req, res) => replaceProfileCollection(req, res, "conditions", conditionSchema, mapConditionInput)));
  app.put("/api/v1/patients/:patientId/allergies", authenticate, asyncRoute((req, res) => replaceProfileCollection(req, res, "allergies", allergySchema, mapAllergyInput)));
  app.put("/api/v1/patients/:patientId/medications", authenticate, asyncRoute((req, res) => replaceProfileCollection(req, res, "medications", medicationSchema, mapMedicationInput)));

  app.post("/api/v1/patients/:patientId/consultations", authenticate, asyncRoute(async (req, res) => {
    const input = consultationSchema.parse(req.body);
    const patient = await getPatient(prisma, req.auth.clinicianId, req.params.patientId, false);
    const consultation = await prisma.$transaction(async (tx) => { const created = await tx.consultation.create({ data: { patientId: patient.id, clinicianId: req.auth.clinicianId, ...input } }); await audit(tx, { actorId: req.auth.clinicianId, action: "CONSULTATION_CREATED", entityType: "Consultation", entityId: created.id, requestId: req.requestId }); return created; });
    send(res, 201, consultationResponse(consultation), req.requestId);
  }));
  app.get("/api/v1/consultations/:consultationId", authenticate, asyncRoute(async (req, res) => send(res, 200, consultationResponse(await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId)), req.requestId)));
  app.patch("/api/v1/consultations/:consultationId/notes", authenticate, asyncRoute(async (req, res) => {
    const input = noteSchema.parse(req.body); const consultation = await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId, false);
    const note = await prisma.$transaction(async (tx) => { const created = await tx.doctorNote.create({ data: { consultationId: consultation.id, authorId: req.auth.clinicianId, text: input.text } }); await audit(tx, { actorId: req.auth.clinicianId, action: "CONSULTATION_NOTE_APPENDED", entityType: "Consultation", entityId: consultation.id, requestId: req.requestId }); return created; });
    send(res, 201, { id: note.id, text: note.text, version: note.version, createdAt: note.createdAt }, req.requestId);
  }));

  app.post("/api/v1/consultations/:consultationId/clinical-safety-assessment", authenticate, asyncRoute(async (req, res) => {
    const consultation = await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId);
    const input = { consultation: { id: consultation.id, candidateGeneric: consultation.candidateGeneric }, patient: consultation.patient };
    const inputHash = stableHash(input); const result = clinicalSafetyAssessment(input);
    const analysis = await prisma.$transaction(async (tx) => { const created = await tx.clinicalAnalysis.upsert({ where: { consultationId_type_engineVersion: { consultationId: consultation.id, type: "SAFETY", engineVersion: versions.ENGINE_VERSION } }, update: { result, inputHash }, create: { consultationId: consultation.id, type: "SAFETY", result, inputHash, engineVersion: versions.ENGINE_VERSION } }); await audit(tx, { actorId: req.auth.clinicianId, action: "SAFETY_ASSESSMENT_GENERATED", entityType: "Consultation", entityId: consultation.id, requestId: req.requestId, metadata: { engineVersion: versions.ENGINE_VERSION } }); return created; });
    send(res, 200, { id: analysis.id, ...result }, req.requestId);
  }));
  app.get("/api/v1/consultations/:consultationId/clinical-safety-assessment", authenticate, asyncRoute(async (req, res) => { const consultation = await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId); const record = consultation.analyses.find((item) => item.type === "SAFETY"); if (!record) throw Object.assign(new Error("No safety assessment has been generated."), { status: 404, code: "ASSESSMENT_NOT_FOUND" }); send(res, 200, record.result, req.requestId); }));

  app.post("/api/v1/consultations/:consultationId/adr-predictions", authenticate, asyncRoute(async (req, res) => {
    const consultation = await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId); const input = { consultation: { id: consultation.id, candidateGeneric: consultation.candidateGeneric }, patient: consultation.patient }; const inputHash = stableHash(input); const result = adrPrediction(input);
    const prediction = await prisma.$transaction(async (tx) => { const created = await tx.adrPrediction.upsert({ where: { consultationId_modelVersion_inputHash: { consultationId: consultation.id, modelVersion: versions.MODEL_VERSION, inputHash } }, update: { result }, create: { consultationId: consultation.id, result, inputHash, modelVersion: versions.MODEL_VERSION } }); await audit(tx, { actorId: req.auth.clinicianId, action: "ADR_PREDICTION_GENERATED", entityType: "Consultation", entityId: consultation.id, requestId: req.requestId, metadata: { modelVersion: versions.MODEL_VERSION } }); return created; });
    send(res, 200, { id: prediction.id, ...result }, req.requestId);
  }));
  app.get("/api/v1/consultations/:consultationId/adr-prediction", authenticate, asyncRoute(async (req, res) => { const consultation = await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId); const record = consultation.adrPredictions[0]; if (!record) throw Object.assign(new Error("No ADR prediction has been generated."), { status: 404, code: "PREDICTION_NOT_FOUND" }); send(res, 200, record.result, req.requestId); }));

  app.post("/api/v1/consultations/:consultationId/recommendations", authenticate, asyncRoute(async (req, res) => {
    const consultation = await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId); const safety = consultation.analyses.find((item) => item.type === "SAFETY")?.result || clinicalSafetyAssessment({ consultation, patient: consultation.patient }); const adr = consultation.adrPredictions[0]?.result || adrPrediction({ consultation, patient: consultation.patient }); const inputHash = stableHash({ safety, adr, consultationId: consultation.id }); const result = recommendations({ consultation, safety, adr });
    const record = await prisma.$transaction(async (tx) => { const created = await tx.recommendationSet.upsert({ where: { consultationId_engineVersion_inputHash: { consultationId: consultation.id, engineVersion: versions.ENGINE_VERSION, inputHash } }, update: { recommendations: result }, create: { consultationId: consultation.id, recommendations: result, inputHash, engineVersion: versions.ENGINE_VERSION } }); await audit(tx, { actorId: req.auth.clinicianId, action: "RECOMMENDATIONS_GENERATED", entityType: "Consultation", entityId: consultation.id, requestId: req.requestId }); return created; });
    send(res, 200, { id: record.id, status: "DEMONSTRATION_ONLY", disclaimer: "These are not clinically validated treatment alternatives.", recommendations: result }, req.requestId);
  }));
  app.get("/api/v1/consultations/:consultationId/recommendations", authenticate, asyncRoute(async (req, res) => { const consultation = await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId); const record = consultation.recommendations[0]; if (!record) throw Object.assign(new Error("No recommendations have been generated."), { status: 404, code: "RECOMMENDATIONS_NOT_FOUND" }); send(res, 200, { status: "DEMONSTRATION_ONLY", recommendations: record.recommendations }, req.requestId); }));

  app.post("/api/v1/consultations/:consultationId/follow-ups", authenticate, asyncRoute(async (req, res) => { const input = followUpSchema.parse(req.body); const consultation = await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId, false); const followUp = await prisma.$transaction(async (tx) => { const created = await tx.followUp.create({ data: { consultationId: consultation.id, authorId: req.auth.clinicianId, ...input } }); await tx.consultation.update({ where: { id: consultation.id }, data: { status: "COMPLETED", version: { increment: 1 } } }); await audit(tx, { actorId: req.auth.clinicianId, action: "FOLLOW_UP_APPENDED", entityType: "Consultation", entityId: consultation.id, requestId: req.requestId }); return created; }); send(res, 201, followUp, req.requestId); }));
  app.get("/api/v1/consultations/:consultationId/follow-ups", authenticate, asyncRoute(async (req, res) => { const consultation = await getConsultation(prisma, req.auth.clinicianId, req.params.consultationId); send(res, 200, consultation.followUps, req.requestId); }));

  app.get("/api/v1/terminology/medications", authenticate, asyncRoute(async (req, res) => { const q = normalizedText(String(req.query.q || "")); const records = await prisma.medicationTerminology.findMany({ where: q ? { OR: [{ brand: { contains: q, mode: "insensitive" } }, { generic: { contains: q, mode: "insensitive" } }] } : {}, orderBy: { brand: "asc" }, take: Math.min(Number(req.query.limit || 20), 50) }); send(res, 200, { items: records }, req.requestId); }));
  app.get("/api/v1/terminology/indications", authenticate, (req, res) => send(res, 200, { version: "2026.08", items: ["Pain or fever", "Allergic rhinitis", "Acid reflux", "Hypertension", "Type 2 diabetes", "Bacterial infection"] }, req.requestId));
  app.get("/api/v1/terminology/conditions", authenticate, (req, res) => send(res, 200, { version: "2026.08", items: ["Hypertension", "Type 2 diabetes", "Asthma", "Chronic kidney disease", "Liver disease"] }, req.requestId));
  app.get("/api/v1/terminology/adverse-events", authenticate, (req, res) => send(res, 200, { version: "2026.08", items: ["Nausea", "Rash", "Dizziness", "Headache", "Diarrhea", "Fatigue"] }, req.requestId));

  app.get("/api/v1/patient-intake-drafts/:scope", authenticate, asyncRoute(async (req, res) => { const draft = await prisma.intakeDraft.findUnique({ where: { clinicianId_scope: { clinicianId: req.auth.clinicianId, scope: req.params.scope } } }); if (!draft) throw Object.assign(new Error("Draft not found."), { status: 404, code: "DRAFT_NOT_FOUND" }); send(res, 200, draft, req.requestId); }));
  app.put("/api/v1/patient-intake-drafts/:scope", authenticate, asyncRoute(async (req, res) => { const input = draftSchema.parse(req.body); const existing = await prisma.intakeDraft.findUnique({ where: { clinicianId_scope: { clinicianId: req.auth.clinicianId, scope: req.params.scope } } }); if (input.expectedVersion && existing && input.expectedVersion !== existing.version) throw conflict(); const draft = await prisma.intakeDraft.upsert({ where: { clinicianId_scope: { clinicianId: req.auth.clinicianId, scope: req.params.scope } }, update: { payload: input.payload, version: { increment: 1 } }, create: { clinicianId: req.auth.clinicianId, scope: req.params.scope, payload: input.payload } }); send(res, 200, draft, req.requestId); }));
  app.delete("/api/v1/patient-intake-drafts/:scope", authenticate, asyncRoute(async (req, res) => { await prisma.intakeDraft.deleteMany({ where: { clinicianId: req.auth.clinicianId, scope: req.params.scope } }); res.status(204).end(); }));

  app.use(notFound);
  app.use(errorHandler);
  return app;
};
