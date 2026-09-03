# VitaNexus-RX ML subsystem

Source package: `ml/src/vitanexus_ml`.

## Modules

- `data/discovery.py`: ZIP/extracted-quarter discovery and SHA-256.
- `data/faers.py`: schema audit, streaming parse, global CASEID/CASEVERSION deduplication, single-PS cohort, Parquet output.
- `normalization.py`: drug, indication, sex, age-unit, and MedDRA text normalization.
- `features/builder.py`: persisted train-only sparse FeatureBuilder with explicit UNKNOWN buckets.
- `models/lightgbm_pipeline.py`: explicit smoke-mode compatibility and full laptop-pipeline entry point.
- `models/laptop_lightgbm_pipeline.py`: benchmark-gated, resumable full-data LightGBM, scalable full-development baselines, isotonic calibration, weighted CASEID bootstrap, conformal and temporal evaluation.
- `models/feature_cache.py`: immutable-input fingerprinting and one development-vocabulary sparse representation reused by every stage.
- `training_runtime.py`: atomic checkpoints, stage state, elapsed/ETA progress, and peak-memory measurement.
- `portable_state.py`: path-independent, checksum-manifested Windows/Colab checkpoint export, verification, and import.
- `artifact_bundle.py`: validated full-model inference bundle export/import; smoke artifacts are rejected.
- `models/hgnn_colab_pipeline.py`: streaming, CUDA-aware, temporally valid, epoch-resumable full HGNN training.
- `colab/`: shared Drive/local-disk preflight code and numbered LightGBM/HGNN notebooks.
- `conformal/split.py`: finite-sample-corrected split conformal classification.
- `models/hgnn.py`: minibatched PyG HeteroData graphs, prevalence/OvR/MLP baselines, HGNN, per-label calibration.
- `inference/predictor.py`: single and batch artifact-backed inference.
- `api/app.py`: FastAPI internal service.

## CLI

```powershell
$env:PYTHONPATH=(Resolve-Path 'ml\src').Path
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli preprocess
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli benchmark-lightgbm
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli train-lightgbm
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli training-status
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli train-hgnn
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli evaluate
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli serve
ml\.venv\Scripts\python.exe -m vitanexus_ml.cli all
```

Add `--fast` only for development smoke testing.

Full training requires a matching benchmark and uses every final-fit row. Only hyperparameter tuning uses a deterministic quarter/class-stratified subset. Checkpoints are bound to SHA-256 identities for `cohort.parquet`, `dataset_manifest.json`, and `data_quality.json`; a mismatch stops execution instead of reusing stale data. The active smoke artifacts are not replaced until all 20 full bootstrap replicas and final temporal evaluation have completed.

Absolute filesystem paths are informational only and no longer participate in dataset, feature-cache, or run identity. Separate environment overrides for cache, run, artifact, report, and processed-data roots support Colab `/content` performance storage with persistent Google Drive checkpoints and outputs.

Read `docs/COLAB_ML_TRAINING.md` before moving or resuming a full run.

## Artifacts

Heavy Parquet/model/cache/checkpoint artifacts are ignored by Git. JSON manifests, CSV metrics, and Markdown reports remain reviewable. Full-mode default bootstrap replicas: 20. ADR vocabulary: training-only PTs with frequency ≥500, capped at 100.

## Tests

```powershell
npm run ml:test
```

Fixtures cover discovery, parsing, deduplication, normalization, serious outcomes, train-serving parity, unknown categories, bootstrap quantiles, conformal construction, HGNN target-leakage safeguards, and API validation.
