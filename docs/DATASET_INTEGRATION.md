# Dataset integration

> **Authoritative runtime reference:** Read [CURRENT_SYSTEM_ARCHITECTURE.md](CURRENT_SYSTEM_ARCHITECTURE.md) first. This document is a concise dataset-pipeline companion; it does not override the current architecture guide.

## Raw sources detected

| Dataset | Raw artifact | Actual structure used | Role |
| --- | --- | --- | --- |
| DDInter 2.0 | `data/raw/ddinter/ddinter_downloads_code_*.csv` | CSV columns `DDInterID_A`, `Drug_A`, `DDInterID_B`, `Drug_B`, `Level` | Pairwise DDI severity only |
| DrugCentral | `data/raw/durgcentral/drugcentral.dump.11012023.sql.gz` | PostgreSQL dump; `omop_relationship` COPY columns include `struct_id`, `relationship_name`, `concept_name`, `umls_cui`, and `snomed_full_name` | Drug–disease and indication relationships |
| Indian Medicine | `data/raw/indian medicne/medicine_data.csv` | CSV columns include `product_name` and `salt_composition` | Brand/product to canonical generic terminology |

Raw files are immutable. The spelling of existing raw directories is retained to avoid altering downloaded data.

## Pipeline

1. `npm run data:process:core` reads DDInter and Indian Medicine data, validates required names/severities, canonicalizes text, de-duplicates, and writes NDJSON in `data/processed/`.
2. `npm run data:process:drugcentral` streams the DrugCentral dump and writes separate Drug–Disease and indication artifacts with source/version provenance.
3. `npx prisma migrate deploy` creates the knowledge tables.
4. `npm run data:import` upserts processed records into PostgreSQL. Patient data is never read or written by preprocessing.

The imported models are `MedicationTerminology`, `DrugInteractionKnowledge`, `DrugDiseaseKnowledge`, and `DrugIndicationKnowledge`. Indexed normalized text supports terminology, pairwise DDI, disease, and indication lookup. Every clinical relationship preserves its `source` and `datasetVersion`.

## Runtime behavior

- Medication lookup/resolution uses Indian Medicine mappings. It keeps entered, normalized, and generic names as separate values.
- DDInter records yield only `MAJOR`, `MODERATE`, or `MINOR`; no percentage is generated.
- DrugCentral disease relationships are mapped by transparent relationship-label rules: contraindication/avoid → `HIGH`, warning/caution/not recommended → `MODERATE`, precaution/monitor → `LOW`. Unrecognized relationships are not represented as a safety finding.
- DrugCentral indication rows produce candidates. Each candidate is now checked against the recorded active medicines and conditions using the same DDInter/DrugCentral dataset logic; it remains neither a probability nor a prescription recommendation.
- Allergies remain stored and displayed, but never enter DDI, drug–disease, alternative, recommendation, or ADR inputs.
- The active dataset workflow excludes ADR/ML outputs and FAERS/openFDA. Neither is processed, imported, or included in recommendation input hashes.
- DDInter matching is ingredient-aware: combination products are split on `+`/`/`, and Paracetamol (including Crocin-mapped products) is aligned to DDInter's `Acetaminophen` term. An unmatched pair is reported as `NO_MATCH_FOUND` in the UI, never as a synthetic low-risk result.

## API-backed UI

React authenticates through `/api/v1/auth/*` and uses the database API for patient/consultation records. Medication autocomplete calls `/terminology/medications`; indication and disease autocomplete call `/terminology/indications` and `/terminology/conditions`. The results screen reads persisted clinical-safety and candidate-evaluation snapshots, including DDInter severity, exact terms evaluated for unmatched pairs, DrugCentral evidence, source, and dataset version.
