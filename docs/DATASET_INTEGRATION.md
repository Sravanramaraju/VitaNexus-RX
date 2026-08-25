# Dataset integration

Raw files are immutable and excluded from Git. The existing typo-bearing directories are preserved because import scripts depend on them.

| Source | Development/runtime role |
| --- | --- |
| Indian Medicine Dataset | brand/product → canonical generic terminology |
| DDInter 2.0 | pairwise DDI severity |
| DrugCentral 11012023 | disease evidence and same-indication candidates |
| FDA FAERS ASCII 2022Q1–2025Q4 | model development, tuning, calibration, conformal calibration |
| FDA FAERS ASCII 2026Q1–2026Q2 | untouched temporal holdout |

## Existing knowledge import

```powershell
npm run data:process
npx prisma migrate deploy
npm run data:import
```

The imported tables are `MedicationTerminology`, `DrugInteractionKnowledge`, `DrugDiseaseKnowledge`, and `DrugIndicationKnowledge`.

## FAERS preprocessing

`vitanexus_ml.data` recursively discovers ZIPs or extracted ASCII files, ignores `.crdownload` files, audits logical tables and headers, records malformed rows, and hashes ZIPs with SHA-256. It supports DEMO, DRUG, REAC, INDI, OUTC, THER, and RPSR naming across discovered quarters.

Case history is built globally before temporal assignment. For each CASEID, the highest CASEVERSION is retained; date and PRIMARYID provide deterministic tie-breaking. The primary cohort requires:

- usable CASEID/PRIMARYID;
- at least one REAC term;
- exactly one `ROLE_COD=PS` drug;
- active ingredient (`PROD_AI`) preferred over drug name.

Concomitant medicines use `ROLE_COD=C`. Indications link by `INDI_DRUG_SEQ = DRUG_SEQ`. Serious outcome codes observed/mapped are `DE`, `LT`, `HO`, `DS`, `CA`, `RI`, and `OT`.

Outputs:

- `data/processed/faers/cohort.parquet` (full) or `cohort_fast.parquet`
- `case_history.sqlite3`
- `dataset_manifest.json`
- `data_quality.json`

## Temporal design

| Purpose | Quarters |
| --- | --- |
| Development fit | 2022Q1–2024Q4 |
| Tuning validation | 2025Q1–2025Q2 |
| Final base fit | 2022Q1–2025Q2 |
| Isotonic calibration | 2025Q3 |
| Split conformal calibration | 2025Q4 |
| Untouched evaluation | 2026Q1–2026Q2 |

No CASEID can cross these partitions because the retained latest case is assigned once after global deduplication.

## Full versus smoke execution

```powershell
# Full corpus (publication candidate)
npm run ml:preprocess
npm run ml:train:lightgbm
npm run ml:train:hgnn

# Explicit resource-bounded smoke execution
npm run ml:preprocess -- --fast
npm run ml:train:lightgbm -- --fast
npm run ml:train:hgnn -- --fast
```

Full mode does not silently sample. Fast mode caps table reads and model replicas/labels and writes `-fast-smoke` versions. Its metrics are diagnostic only.
