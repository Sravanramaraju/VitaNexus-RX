# VitaNexus-RX ML subsystem

Source package: `ml/src/vitanexus_ml`.

## Modules

- `data/discovery.py`: ZIP/extracted-quarter discovery and SHA-256.
- `data/faers.py`: schema audit, streaming parse, global CASEID/CASEVERSION deduplication, single-PS cohort, Parquet output.
- `normalization.py`: drug, indication, sex, age-unit, and MedDRA text normalization.
- `features/builder.py`: persisted train-only sparse FeatureBuilder with explicit UNKNOWN buckets.
- `models/lightgbm_pipeline.py`: Logistic Regression, Random Forest, XGBoost, LightGBM, isotonic calibration, CASEID bootstrap, temporal evaluation.
- `conformal/split.py`: finite-sample-corrected split conformal classification.
- `models/hgnn.py`: minibatched PyG HeteroData graphs, prevalence/OvR/MLP baselines, HGNN, per-label calibration.
- `inference/predictor.py`: single and batch artifact-backed inference.
- `api/app.py`: FastAPI internal service.

## CLI

```powershell
$env:PYTHONPATH=(Resolve-Path 'ml\src').Path
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli preprocess
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli train-lightgbm
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli train-hgnn
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli evaluate
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli serve
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli all
```

Add `--fast` only for development smoke testing.

## Artifacts

Heavy Parquet/model artifacts are ignored by Git. JSON manifests, CSV metrics, and Markdown reports remain reviewable. Full-mode default bootstrap replicas: 20. ADR vocabulary: training-only PTs with frequency ≥500, capped at 100.

## Tests

```powershell
npm run ml:test
```

Fixtures cover discovery, parsing, deduplication, normalization, serious outcomes, train-serving parity, unknown categories, bootstrap quantiles, conformal construction, HGNN target-leakage safeguards, and API validation.
