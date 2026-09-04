# VitaNexus-RX Google Colab ML training

## Purpose and scientific invariants

Google Colab is the execution environment for the remaining full LightGBM bootstrap/evaluation work and the corrected full HGNN workflow. Google Drive is persistent storage; `/content` is temporary high-speed storage. FAERS preprocessing is complete and must not be rerun.

- Immutable input: the existing 6,309,764-row cohort plus its manifest and quality report.
- Development/vocabulary: 2022Q1–2024Q4.
- Validation/model selection: 2025Q1–2025Q2.
- Final fit after selection: 2022Q1–2025Q2.
- Isotonic calibration: 2025Q3.
- Serious-outcome conformal calibration: 2025Q4.
- Final untouched holdout: 2026Q1–2026Q2.
- No automatic fast mode, reduced final data, partial promotion, or 2026 leakage.

LightGBM remains on CPU because the completed selected-model and first eight bootstrap checkpoints used CPU LightGBM 4.6.0. HGNN automatically uses CUDA when available.

## Google Drive layout

```text
MyDrive/VitaNexus-RX-ML/
  data/processed/faers/
    cohort.parquet
    dataset_manifest.json
    data_quality.json
  training_state/
    imports/lightgbm_state/
      portable_state_manifest.json
      feature_cache/
      training_run/
      input_metadata/
    training_runs/
  models/runtime/
  reports/
  exports/
```

Both notebooks expose one Drive setting near the beginning:

```python
DRIVE_ROOT = "/content/drive/MyDrive/VitaNexus-RX-ML"
```

## Export the Windows LightGBM state

From `D:\Projects\VitaNexus-RX DDI Major Project`, inspect the state without copying:

```powershell
npm run ml:state:plan -- --source-root "C:\Users\srava\AppData\Local\VitaNexus-RX\ml-training\0eea994c4b72" --run-key "7cf62b58be44b03e635e" --cohort "D:\Projects\VitaNexus-RX DDI Major Project\data\processed\faers\cohort.parquet"
```

Create the portable directory once:

```powershell
npm run ml:state:export -- --source-root "C:\Users\srava\AppData\Local\VitaNexus-RX\ml-training\0eea994c4b72" --run-key "7cf62b58be44b03e635e" --cohort "D:\Projects\VitaNexus-RX DDI Major Project\data\processed\faers\cohort.parquet" --output "D:\Projects\VitaNexus-RX Colab Transfer\lightgbm_state"
```

Verify before upload:

```powershell
npm run ml:state:verify -- --bundle "D:\Projects\VitaNexus-RX Colab Transfer\lightgbm_state" --cohort "D:\Projects\VitaNexus-RX DDI Major Project\data\processed\faers\cohort.parquet"
```

The exporter never modifies or deletes AppData. It excludes reconstructable cache chunks and does not duplicate `cohort.parquet`. Copy the exported directory into Drive as `training_state/imports/lightgbm_state`. Upload the three immutable processed files separately to `data/processed/faers` without renaming them.

Actual transfer inventory from the recovered run:

| Item | Bytes | Approximate size |
| --- | ---: | ---: |
| `cohort.parquet` | 114,305,663 | 109.0 MiB |
| Finalized sparse feature cache inside the bundle | 443,736,086 | 423.2 MiB |
| Portable bundle, including cache/checkpoints/metadata | 490,191,644 | 467.5 MiB |
| Eight completed bootstrap artifacts inside the bundle | 26,452,192 | 25.2 MiB |
| Bundle plus all three immutable inputs | 604,561,337 | 576.6 MiB (0.605 GB) |

The complete `lightgbm_state` directory and all three immutable input files are required. The finalized sparse cache and replicas 0–7 are already inside that directory, so do not upload them separately. Disposable cache chunks and the committed benchmark report can be recreated/copied cheaply. The cohort, finalized cache, selected model/calibrator and eight completed replicas must not be regenerated.

## Resume LightGBM

Open `ml/colab/VitaNexus_LightGBM_Resume_Colab.ipynb`. A CPU runtime is sufficient. Run all numbered cells.

Drive authorization appears in section 2. The notebook clones the committed branch, installs constrained dependencies, prints resolved paths, verifies file hashes and 6,309,764 rows, checks free disk/RAM, stages data and the finalized sparse cache to `/content`, and imports the run into persistent Drive state. Preflight requires exactly 8/20 completed replicas.

On a fresh Colab runtime, the constrained dependency cell intentionally restarts the Python process once when package versions change. It also runs a clean subprocess import probe and force-reinstalls the pinned NumPy/Pandas/PyArrow/SciPy/scikit-learn/LightGBM wheels when version metadata matches but binary files are inconsistent. This prevents a partially upgraded in-memory or on-disk scientific stack. Wait for Colab to reconnect and choose **Runtime -> Run all** again; the second pass detects the exact installed versions, verifies the imports, and continues without another restart. This restart does not affect Drive checkpoints.

Replica 9 (`bootstrap_08`) restarts; replicas 0–7 are skipped. Every new replica is saved directly to Drive. After 20/20, the pipeline automatically runs 2025Q4 split-conformal calibration, evaluates 2026Q1–Q2, and promotes full LightGBM artifacts.

Success requires:

```text
training status = COMPLETE
bootstrap completed = 20, total = 20
models/runtime/training_manifest.json: fastMode=false, fullFinalData=true
reports/conformal_metrics.json exists
reports/final_temporal_evaluation.json exists
```

## Train the corrected HGNN

Only after LightGBM succeeds, open `ml/colab/VitaNexus_HGNN_Full_Training_Colab.ipynb`. Select **Runtime → Change runtime type → T4 GPU**, L4, A100, or another available GPU. Run all cells.

Preflight refuses smoke/partial LightGBM dependencies. The corrected pipeline:

1. streams Parquet batches instead of loading 6.31 million rows at once;
2. builds the maximum-100-label, minimum-frequency-500 vocabulary from development only;
3. builds selection associations from development only;
4. selects the two-layer HeteroConv/SAGEConv model on development→validation;
5. stores separate selection `latest` and `best` checkpoints;
6. refits a fresh final model on 2022Q1–2025Q2 for the selected epoch count;
7. calibrates each eligible label on 2025Q3;
8. evaluates only at the end on the 2026 holdout;
9. delays promotion until all stages succeed.

The original full liblinear/MLP baseline setup is not feasible at this scale. The Colab pipeline preserves the baseline families but explicitly uses a deterministic quarter-balanced 400,000-row development subset. Logistic regression uses SGD log-loss; the MLP retains one 64-unit hidden layer, up to 80 iterations and early stopping. Reports label this methodology explicitly.

HGNN success requires:

```text
models/runtime/hgnn_training_manifest.json: fastMode=false, fullFinalData=true
models/runtime/hgnn_metadata.joblib exists
models/runtime/hgnn_state.pt exists
models/runtime/adr_vocabulary.json is development-derived
reports/hgnn_metrics.json contains holdout2026
exports/vitanexus_full_inference/inference_bundle_manifest.json exists
```

## If Colab disconnects

1. Reconnect and select the same runtime type; select a GPU again for HGNN.
2. Open the same notebook and choose **Runtime → Run all**.
3. Authorize Drive again when prompted.
4. Dataset/cache files are recopied and checksum-verified in the new `/content` session.
5. Existing Drive run state is not overwritten by the original import bundle.
6. LightGBM skips completed replicas and restarts only the incomplete replica.
7. HGNN restores the latest model, optimizer, AMP scaler and RNG state, then continues at the next epoch. The separate best checkpoint remains intact.

Never leave the only valuable checkpoint under `/content`.

## Import final models locally

After both notebooks complete, sync or download:

```text
MyDrive/VitaNexus-RX-ML/exports/vitanexus_full_inference
```

From the local project root:

```powershell
npm run ml:bundle:verify -- --bundle "D:\Path\To\vitanexus_full_inference"
npm run ml:bundle:import -- --bundle "D:\Path\To\vitanexus_full_inference"
npm run ml:serve
```

In another PowerShell window:

```powershell
$health = Invoke-RestMethod http://127.0.0.1:8000/health
$health | ConvertTo-Json -Depth 5

$predictionBody = @{
  requestId = "local-full-model-smoke-1"
  patient = @{
    age = 52
    sex = "F"
    currentMedications = @("warfarin")
  }
  candidateDrug = @{
    canonicalName = "aspirin"
    ingredients = @("aspirin")
  }
  indication = @{
    id = "local-smoke-indication"
    name = "pain"
    source = "DrugCentral"
  }
} | ConvertTo-Json -Depth 6

$prediction = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/predict -ContentType 'application/json' -Body $predictionBody
$prediction | ConvertTo-Json -Depth 10

$batchBody = @{ requests = @($predictionBody | ConvertFrom-Json) } | ConvertTo-Json -Depth 8
$batch = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/predict-batch -ContentType 'application/json' -Body $batchBody
$batch | ConvertTo-Json -Depth 10
```

The importer validates all checksums and both full-mode manifests before staging replacements. Health must show `artifactsLoaded: true`. The single prediction must show `artifactMode: FULL` and `overall.uncertainty.replicas: 20`; the batch must show `status: ok`. Neither response may contain a `-fast-smoke` version.

## Do not do these things

- Do not rerun FAERS preprocessing.
- Do not delete old AppData checkpoints.
- Do not restart LightGBM from scratch.
- Do not add `--fast` to full training.
- Do not tune, select or calibrate with 2026 rows.
- Do not promote partial models.
- Do not run the old leaking HGNN full implementation.
- Do not switch remaining LightGBM replicas to GPU.
- Do not assume Colab automatically updates the local project.
- Do not describe high metrics as causal, state-of-the-art or publication-grade without valid evidence.
