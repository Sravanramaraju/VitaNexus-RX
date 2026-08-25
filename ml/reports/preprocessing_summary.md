# FAERS preprocessing summary

**Execution mode:** FAST SMOKE — non-final, table reads capped at 50,000 rows per logical table and quarter.
**Executed:** 2026-08-24
**Preprocessing version:** `faers-case-cohort-1.0.0`

## Discovery

All 18 required ZIP quarters were discovered: 2022Q1–2025Q4 for development and 2026Q1–2026Q2 for temporal holdout. Three `.crdownload` files were ignored. DEMO, DRUG, REAC, INDI, OUTC, THER, and RPSR entries were present. Required columns were present and no cross-quarter schema difference was detected for the five parsed cohort tables.

SHA-256 values and raw entry names are in `data/processed/faers/dataset_manifest.json`. The raw ZIPs were not modified.

## Smoke-run counts

- DEMO rows visited before global deduplication: 900,018
- Unique CASEIDs/retained latest cases: 656,011
- Older versions removed: 244,007
- Single-primary-suspect cohort rows retained: 45,266
- SERIOUS_OUTCOME: 31,329
- NO_DOCUMENTED_SERIOUS_OUTCOME: 13,937
- Malformed rows in the capped sections: 0

These are smoke-run counts, not full-corpus cohort statistics. Independent per-table row caps deliberately make component coverage incomplete and therefore inflate the multi/missing-primary-suspect exclusion count. Use the uncapped command below for final statistics:

```powershell
npm run ml:preprocess
```

The detailed per-quarter source names, schemas, parsed row counts, and exclusions are in `data/processed/faers/data_quality.json`.
