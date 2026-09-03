# FAERS preprocessing summary

**Execution mode:** FULL — uncapped, final processed input

**Completed:** 2026-08-25

**Preprocessing version:** `faers-case-cohort-1.0.0`

## Immutable full-corpus result

All 18 required ZIP quarters were discovered: 2022Q1–2025Q4 for development/calibration and 2026Q1–2026Q2 for temporal holdout. Three incomplete `.crdownload` files were ignored. DEMO, DRUG, REAC, INDI, OUTC, THER, and RPSR entries were present. Required columns were present and `schemaDifferences` is empty.

- DEMO records before global deduplication: **7,557,824**
- Unique CASEIDs/latest cases retained: **6,469,677**
- Older CASEVERSION records removed: **1,088,147**
- Exact-one-primary-suspect cohort rows: **6,309,764**
- `SERIOUS_OUTCOME`: **3,498,823**
- `NO_DOCUMENTED_SERIOUS_OUTCOME`: **2,810,941**

The immutable full inputs are:

- `data/processed/faers/cohort.parquet`
- `data/processed/faers/dataset_manifest.json`
- `data/processed/faers/data_quality.json`

Do not rerun preprocessing for the current experiment. The laptop training pipeline fingerprints all three files and refuses stale/mismatched checkpoints. Detailed per-quarter source names, schemas, parsed row counts, malformed-row counts, exclusions, and SHA-256 provenance are retained in the manifest and quality report.

## Temporal contract

| Purpose | Quarters | Rows |
| --- | --- | ---: |
| Development fit | 2022Q1–2024Q4 | 4,271,984 |
| Tuning validation | 2025Q1–2025Q2 | 638,284 |
| Selected final fit | 2022Q1–2025Q2 | 4,910,268 |
| Isotonic calibration | 2025Q3 | 375,893 |
| Split conformal calibration | 2025Q4 | 326,999 |
| Untouched final evaluation | 2026Q1–2026Q2 | 696,604 |

Counts were verified by the immutable-input laptop benchmark. The benchmark skipped 2026 row groups before loading label or feature columns.
