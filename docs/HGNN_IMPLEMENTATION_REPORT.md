# HGNN Baseline Integration — Implementation Report

1. **Model choice:** The active supplementary model is the already-trained `faers-specific-adr-hgnn-1.0.0` baseline HGNN. No retraining was performed.
2. **Checkpoint selection:** Runtime uses `hgnn_selection_best.pt`, the protected selection checkpoint identified by the post-training integrity manifest.
3. **Selection evidence:** The manifest records training epoch 20; the checkpoint stores zero-based epoch 19. The partial five-epoch final-refit artifact remains experimental and was not promoted.
4. **Checkpoint integrity:** SHA-256 `7ca91da8449c87e65c08550083eab12cf3e267faa9e44284c496853de7fa5420` is verified before model loading.
5. **Artifact immutability:** The runtime reads protected artifacts and does not write beneath the saved training snapshot.
6. **Architecture preservation:** Inference reconstructs the existing `HeterogeneousAdrNetwork` unchanged with 96 hidden channels and 100 outputs.
7. **Node types:** The graph contains `report`, `drug`, `indication`, and `adr` nodes.
8. **Edge schema:** All ten original directed/reverse relations are reconstructed through the shared `build_heterodata` implementation.
9. **Message passing:** Two `HeteroConv` layers retain `SAGEConv`, sum aggregation, residual addition, and ReLU behavior from training.
10. **Output layer:** The original linear 100-logit output layer is strictly loaded; architecture or output-shape mismatches fail closed.
11. **Vocabulary:** The ordered `adr_vocabulary.json` contains 100 actual training labels with contiguous indices.
12. **Vocabulary identity:** Checkpoint vocabulary identity and vocabulary artifact identity must match before inference starts.
13. **Historical associations:** Runtime uses the selection model’s `development_associations.joblib`, not the experimental final-refit associations.
14. **Leakage safeguard:** Checkpoint metadata must assert that report-to-target ADR edges were excluded from the encoder.
15. **Supported inputs:** Only age, sex, candidate drug, indication, and active/current medication names are consumed.
16. **Feature parity:** Runtime reuses original normalization, report feature scaling/missingness, hashed entity features, graph construction, and association mapping.
17. **Unsupported data:** Dose, route, laboratory values, allergies, genetics, organ function, and free-form notes are not invented as model features.
18. **Activation:** The model produces logits and the runtime applies sigmoid exactly once. No softmax, threshold, or additional calibration is applied.
19. **Score semantics:** Returned values are `BASELINE_MODEL_SCORE` event-label association scores, not patient-incidence probabilities.
20. **Determinism:** Scores are sorted descending, event name is the tie-breaker, and repeated identical input returns the same ranked values and input identity.
21. **Device behavior:** Artifacts load on CPU first; inference uses CUDA when available and CPU otherwise. The verified integration test explicitly exercises CPU.
22. **Cached loading:** FastAPI constructs and loads the HGNN once in application lifespan, sets evaluation mode, and uses inference/no-gradient execution.
23. **FastAPI status endpoint:** `GET /v1/hgnn/status` exposes readiness, model/checkpoint/vocabulary/schema identities, device, graph types, top K, stage, validation state, and ranking isolation.
24. **FastAPI inference endpoint:** `POST /v1/hgnn/predict-events` strictly validates the exact HGNN input contract and returns ranked event results or an explicit failure.
25. **Independent model startup:** LightGBM and HGNN load independently. Failure of one does not rewrite the other model’s result or semantics.
26. **Express orchestration:** The authenticated consultation route verifies record ownership, maps canonical persisted fields, calls HGNN status/inference, and validates every response with Zod.
27. **Response validation:** Model metadata, SHA shape, finite range-bounded scores, contiguous ranks, deterministic ordering, event count, and coverage/status consistency are validated before storage.
28. **Persistence:** `HgnnEventPrediction` stores result JSON plus model version, checkpoint version, model/validation stage, input hash, coverage, status, and generation time.
29. **Cache identity:** Consultation, model version, checkpoint hash, and stable exact-input/schema hash form the unique result identity. GET reuses; POST explicitly regenerates.
30. **Failure and OOV behavior:** Missing artifacts, mismatch, timeout, unreachable service, malformed output, and inference error return no events. Unknown graph entities produce typed `DEGRADED_COVERAGE`; zero is never substituted.
31. **Clinical isolation:** HGNN does not affect LightGBM, bootstrap/conformal output, DDInter, DrugCentral, safety gates, candidate generation, recommendation weights, sorting, tie-breaking, or follow-up ranking.
32. **Interface and verification:** The responsive, dark-mode-compatible Event Profile adds wizard navigation, context, baseline/audit/coverage badges, accessible ranked score bars, explanations, model details, loading/empty/unavailable states, and retry. Verification completed with ESLint, Vite production build, Prisma validate/generate/deploy, 42 server tests, 66 ML tests, actual CPU inference, and persisted GET/POST end-to-end checks.

For the detailed architecture, input semantics, pipeline, and remaining audit work, see `HGNN_EVENT_PROFILE.md`.
