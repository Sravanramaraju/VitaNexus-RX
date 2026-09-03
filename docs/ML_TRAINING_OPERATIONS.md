# ML training operations

## Immutable input contract

The existing `data/processed/faers/cohort.parquet` contains 6,309,764 retained cases and is the full training/evaluation input. Do not rerun preprocessing for the current experiment. Full training fingerprints that file plus `dataset_manifest.json` and `data_quality.json`; any content change invalidates the benchmark and checkpoints and stops the run.

The training pipeline never writes under `data/processed/faers`.

## Required order

```powershell
# Measures this laptop on a deterministic temporal subset. It does not train or
# promote a final model and does not inspect 2026 labels.
npm run ml:benchmark

# Review the generated estimate before committing to the full run.
Get-Content .\ml\reports\lightgbm_benchmark.md

# Full, resumable training. There is no implicit fast or reduced-data fallback.
npm run ml:train:lightgbm

# Safe in another terminal; reports checkpoints and bootstrap ETA.
npm run ml:status
```

Running `npm run ml:train:lightgbm` again after interruption resumes completed cache chunks, tuning models, baselines, the final model, calibration, and individual bootstrap replicas. It does not repeat completed stages whose identity and checkpoint agree.

## Scientific split contract

| Stage | Data |
| --- | --- |
| Vocabulary fit | 2022Q1–2024Q4 only |
| Hyperparameter tuning fit | deterministic quarter/class subset of 2022Q1–2024Q4 |
| Hyperparameter validation | deterministic quarter/class subset of 2025Q1–2025Q2 |
| Fair baseline fit | all 2022Q1–2024Q4 rows |
| Fair baseline validation | all 2025Q1–2025Q2 rows |
| Selected final fit | all 2022Q1–2025Q2 rows |
| Isotonic calibration | 2025Q3 |
| Split conformal calibration | 2025Q4 |
| Final untouched evaluation | 2026Q1–2026Q2 |

The benchmark excludes 2026 records from sampling and label inspection. Frozen-feature transformation may cache their rows, but their labels are not used until final evaluation.

## Laptop memory controls

- One CSR feature representation is cached as memory-mapped arrays.
- Full pandas partitions are not retained.
- Training uses eight threads by default to control native-model memory on a 16 GB machine.
- Logistic Regression uses scalable SGD optimization; Complement Naive Bayes and a prior dummy provide additional full-development baselines. The earlier 300-tree Random Forest and full XGBoost baseline were removed because they made the comparison operationally infeasible on the target hardware.
- Each bootstrap draws deterministic CASEID row indices, converts them to multiplicity/sample-weight vectors, and reuses the same CSR matrix.
- Heavy feature caches and checkpoints default to `%LOCALAPPDATA%\VitaNexus-RX\ml-training` so OneDrive sync does not lock or repeatedly upload them. Set `VITANEXUS_ML_WORK_ROOT` to an absolute local path to override this location.

## Artifact safety

Partial full models live under the local training-work directory, under `training_runs/<identity>/`. Existing runtime artifacts remain unchanged while training is incomplete. Only after all full stages and the input-integrity recheck pass are the complete LightGBM artifact, manifest, 20 bootstrap models, and reports promoted to their runtime locations. Final promotion uses bounded atomic-replace retries to tolerate transient Windows sync/antivirus locks.

Explicit `--fast` commands remain development-only and are never selected automatically.

## Google Colab migration

Scientific identities are location-independent. They use immutable file hashes/sizes, preprocessing and pipeline versions, model configuration, temporal partitions, and mode. Absolute paths are informational provenance only. Cache, run, artifact, report, and processed-data roots can be configured independently.

Do not run full training locally after moving the repository. Export the existing Windows state with `npm run ml:state:export`, upload it to Drive, and let the LightGBM notebook verify/import it. The exporter includes the finalized CSR cache, completed checkpoints, eight completed bootstrap replicas, state metadata, and the two small provenance JSON files. It excludes disposable cache chunks and does not duplicate `cohort.parquet`.

Use the notebooks in this order:

1. `ml/colab/VitaNexus_LightGBM_Resume_Colab.ipynb`
2. `ml/colab/VitaNexus_HGNN_Full_Training_Colab.ipynb`

LightGBM remains on CPU for compatibility with completed checkpoints. Full HGNN now selects on development versus validation, builds selection associations from development only, final-refits only after selection, streams Parquet batches, uses CUDA when available, checkpoints every epoch with separate latest/best semantics, and promotes only after calibration plus untouched holdout evaluation.

The literal Drive layout, measured transfer sizes, export, disconnect recovery, final bundle import, and health/single/batch inference verification commands are documented in `docs/COLAB_ML_TRAINING.md`.
