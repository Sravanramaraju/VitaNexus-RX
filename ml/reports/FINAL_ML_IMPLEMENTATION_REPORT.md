# VitaNexus-RX ML implementation report

**Implementation status:** end-to-end code complete and smoke-validated
**Research metric status:** FAST SMOKE ONLY — not publication/final results
**Date:** 2026-08-24

## What existed before modification

The repository already had working React/Express/PostgreSQL persistence, Indian medicine resolution, DDInter pairwise DDI lookup, DrugCentral disease/indication knowledge, ADR JSON persistence, and an ADR provider seam. The active ADR provider generated deterministic placeholder numbers; the frontend also retained a static ADR adapter. Recommendations used known datasets only and an ordinal sort. Indication text was searchable but free text remained submittable. The actual knowledge engine constant was `vitanexus-knowledge-2.2.0`, despite stale documentation mentioning 2.1.0.

## Implemented architecture

- Streaming FAERS ZIP/extracted-file discovery, schema audit, SHA-256 manifest, global CASEID/CASEVERSION deduplication, latest PRIMARYID joins, exact-one-PS cohort, Parquet caching, and temporal partitions.
- Persisted train-serving FeatureBuilder with explicit unknown categories and train-only concomitant-medication vocabulary.
- Logistic Regression, Random Forest, XGBoost, and LightGBM serious-outcome classifiers.
- Isotonic calibration on 2025Q3.
- CASEID bootstrap ensemble (20 full-mode replicas; 2 smoke replicas), 90% percentile interval, conservative upper bound.
- Finite-sample-corrected split conformal calibration on 2025Q4.
- Training-only MedDRA vocabulary, prevalence/OvR Logistic/MLP baselines, PyG heterogeneous graph model, target-edge leakage safeguards, and label calibration.
- FastAPI `/health`, `/v1/predict`, and `/v1/predict-batch`.
- Express Python provider with timeout, request-ID propagation, Zod validation, explicit failure semantics, persistence, and model-version hashing.
- Lexicographic P1/P2/P3/P4 recommendation ranking; no weighted score and no HGNN double-counting.
- Required DrugCentral indication provenance and server-side verification.
- Dedicated persisted ADR route/page with loading/success/degraded/unavailable/failed states.

## Raw data and smoke cohort

18 ZIPs were discovered: 2022Q1–2026Q2. Three incomplete browser downloads were ignored. Smoke preprocessing visited 900,018 capped DEMO rows, retained 656,011 latest CASEIDs, removed 244,007 older versions, and produced 45,266 cohort rows. Smoke class distribution: 31,329 serious and 13,937 no documented serious outcome.

These counts are not full-corpus counts because `--fast` independently caps component tables. Full preprocessing must be run for research reporting.

## LightGBM/baseline smoke metrics

2025Q1–Q2 tuning-validation metrics:

| Model | AUROC | AUPRC | F1 | Brier | ECE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Logistic Regression | 0.8512 | 0.9661 | 0.9272 | 0.1416 | 0.1498 |
| Random Forest | 0.8298 | 0.9589 | 0.9294 | 0.1452 | 0.2054 |
| XGBoost | 0.8032 | 0.9477 | 0.9289 | 0.1002 | 0.0423 |
| LightGBM | 0.8322 | 0.9605 | 0.9284 | 0.1493 | 0.1946 |

The baseline result is reported honestly: Logistic Regression had higher AUROC/AUPRC than LightGBM in this capped smoke cohort. The locked deployed architecture remains LightGBM pending full-corpus evaluation.

Isotonic smoke calibration on 2025Q3 changed Brier 0.0927 → 0.0325 and ECE 0.2061 → approximately 0 on the calibration cohort. This in-sample calibration improvement must not be mistaken for temporal generalization.

## Conformal and 2026 smoke evaluation

Target coverage was 0.90; smoke `qHat=0.3261`. Empirical 2026 coverage was only 0.2865, average set size 0.9948, singleton rate 0.9948, ambiguous rate 0, and empty rate 0.0052. The target was not achieved. The result is deliberately reported without a false confidence claim.

LightGBM smoke 2026 holdout: AUROC 0.7397, AUPRC 0.6355, F1 0.4362, Brier 0.6364, ECE 0.6587. The very poor calibration/coverage shift makes the smoke artifacts unsuitable for clinical or final research use.

## HGNN smoke metrics

The smoke vocabulary contains 15 training-derived labels (full default cap: 100; minimum full training frequency: 500).

| Model | Validation micro-AUPRC | Validation macro-AUPRC | micro-F1 |
| --- | ---: | ---: | ---: |
| Training prevalence | 0.0823 | 0.0649 | 0.0000 |
| One-vs-Rest Logistic | 0.2771 | 0.3143 | 0.3027 |
| Multi-label MLP | 0.3249 | 0.3465 | 0.2083 |
| HGNN | 0.2853 | 0.3105 | 0.0894 |

HGNN smoke 2026 holdout: micro-AUPRC 0.1385, macro-AUPRC 0.2101, micro-F1 0.0594. The MLP baseline exceeded HGNN on capped validation micro-AUPRC; this is not hidden or relabeled.

## Runtime validation

The smoke artifacts are versioned with `-fast-smoke`, return `artifactMode: FAST_SMOKE`, and force `DEGRADED_COVERAGE`. A real HTTP end-to-end test completed:

DrugCentral indication → consultation → DDInter/DrugCentral safety → Express → FastAPI → persisted ADR reload → batch alternative inference → lexicographic ranking → follow-up persistence.

The ADR direct route was verified after an authentication hydration fix. Desktop and 390×844 mobile layouts were visually checked.

Final regression validation passed: 9 Python tests, 32 backend tests across 7 files, ESLint, the Vite production build (2,228 transformed modules), Prisma schema validation/migration deployment, direct model-artifact smoke inference, FastAPI health, and the real HTTP end-to-end workflow. No frontend unit-test runner exists in this repository, so browser visual/navigation QA and the production build are the frontend gates.

## Remaining research limitation and exact resume commands

Full uncapped training was not completed in this execution session because it requires reading the entire ~1.2 GB compressed FAERS corpus, fitting four full baselines, 20 independently calibrated LightGBM replicas, and the full HGNN vocabulary/epochs. No full metrics were fabricated.

Run:

```powershell
npm run ml:preprocess
npm run ml:train:lightgbm
npm run ml:train:hgnn
npm run ml:evaluate
```

Then restart `npm run ml:serve` so the service loads full artifacts. Confirm that returned versions no longer contain `-fast-smoke` and review actual 2026 calibration/conformal coverage before using the results in the final report.

## Interpretation

FAERS reporting bias, missing denominator, temporal drift, and indication/drug vocabulary coverage remain material limitations. Outputs are decision support only. No documented interaction is not proof of safety. Known HIGH evidence always dominates ML. Specific ADR scores are explanatory and are not another ranking weight. No online patient-feedback retraining is active.
