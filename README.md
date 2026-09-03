# VitaNexus-RX

VitaNexus-RX is a B.Tech CSE clinical decision-support project that combines Indian medicine terminology, DDInter 2.0, DrugCentral, and a reproducible FAERS modelling subsystem. It is a research/demo system, not an autonomous prescriber or validated medical device.

## Runtime workflow

1. Select an Indian brand/generic medicine and a required DrugCentral-backed indication.
2. Evaluate the candidate against active medicines (DDInter) and resolved conditions (DrugCentral).
3. Open the dedicated Adverse Risk Assessment page.
4. Obtain a calibrated LightGBM serious-outcome estimate, 90% bootstrap model-uncertainty interval, split-conformal set, and HGNN-specific ADR scores.
5. Rank same-indication alternatives lexicographically: P1 known safety evidence, P2 lower bootstrap upper bound, P3 conformal set, P4 canonical name.
6. Persist notes, analyses, recommendations, and follow-up in PostgreSQL.

FAERS probabilities are conditional on the learned adverse-event reporting task. They are not population incidence.

## Windows setup and run order

Prerequisites: Node.js, PostgreSQL, and Python 3.12 (CPU execution is supported).

```powershell
# 1. JavaScript dependencies and Prisma client
npm install

# 2. Database schema and clinical knowledge
npx prisma migrate deploy
npm run data:process
npm run data:import

# 3. Isolated Python environment
py -3.12 -m venv ml\.venv
ml\.venv\Scripts\python.exe -m pip install -r ml\requirements.txt

# 4. Create processed FAERS data only when cohort.parquet does not already exist
# npm run ml:preprocess

# 5. Required laptop benchmark, then resumable full-data training
npm run ml:benchmark
npm run ml:train:lightgbm
npm run ml:status
npm run ml:train:hgnn
npm run ml:evaluate

# 6. Terminal A: internal model service
npm run ml:serve

# 7. Terminal B: Express API + Vite
npm run dev
```

Development-only smoke runs are explicit and produce `-fast-smoke` artifact versions:

```powershell
npm run ml:preprocess -- --fast
npm run ml:train:lightgbm -- --fast
npm run ml:train:hgnn -- --fast
```

Never report fast-mode metrics as final research results.

The full LightGBM command refuses to start without a benchmark matching the immutable processed cohort and current configuration. Full training is checkpointed and resumes completed stages/replicas. It never silently switches to `--fast` or reduces the final 2022Q1–2025Q2 fit. See [ML_TRAINING_OPERATIONS.md](docs/ML_TRAINING_OPERATIONS.md) and the exact [Google Colab migration guide](docs/COLAB_ML_TRAINING.md).

## Environment

Copy `.env.example` to `.env`. The important ML keys are:

```dotenv
ADR_ML_BASE_URL=http://127.0.0.1:8000
ADR_ML_TIMEOUT_MS=30000
```

The browser uses the same-origin `/api/v1` path. Vite proxies it to Express during development.

## Verification

```powershell
npm run ml:test
npm run api:test
npm run lint
npm run build
npx prisma validate
$env:PYTHONPATH=(Resolve-Path 'ml\src').Path
ml\.venv\Scripts\python.exe ml\scripts\smoke_inference.py
node scripts\smokeEndToEnd.js
```

See [CURRENT_SYSTEM_ARCHITECTURE.md](docs/CURRENT_SYSTEM_ARCHITECTURE.md), [DATASET_INTEGRATION.md](docs/DATASET_INTEGRATION.md), and [FINAL_ML_IMPLEMENTATION_REPORT.md](ml/reports/FINAL_ML_IMPLEMENTATION_REPORT.md).
