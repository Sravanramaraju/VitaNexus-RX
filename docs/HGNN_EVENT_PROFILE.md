# Baseline HGNN Specific Event Profile

## Purpose and interpretation

The Specific Event Profile is a supplementary decision-support view. For the current patient context, medicine, indication, and active medicines, it ranks event labels by the association score produced by the saved baseline heterogeneous graph neural network (HGNN).

An event score is **not** the probability that this patient will experience the event. It is an uncalibrated sigmoid score from the protected baseline checkpoint. The feature may help a clinician decide what source evidence to review, but it does not diagnose an adverse reaction, estimate population incidence, or recommend a drug.

The interface therefore always displays:

- **Baseline HGNN** and **Audit Pending**;
- **model score**, never “patient probability”;
- full or limited graph-coverage status;
- no-ranking-influence language;
- explicit unavailable states without default or zero scores.

## Protected artifact selection

The runtime uses the selection checkpoint recorded in `ml/training_state/hgnn_post_training/checkpoint_integrity.json`:

- model version: `faers-specific-adr-hgnn-1.0.0`;
- selected training epoch: 20 (zero-based checkpoint field 19);
- checkpoint SHA-256: `7ca91da8449c87e65c08550083eab12cf3e267faa9e44284c496853de7fa5420`;
- checkpoint file: `hgnn_selection_best.pt`;
- ordered event vocabulary: 100 labels from `adr_vocabulary.json`;
- vocabulary identity: verified against checkpoint metadata;
- development associations: `development_associations.joblib`;
- target-event edges excluded: verified before serving.

The incomplete experimental final-refit artifact is not used. No retraining, architecture modification, post-hoc calibration, or threshold optimization occurs in this integration.

## Architecture preserved from training

The model is `HeterogeneousAdrNetwork(hidden_channels=96, output_channels=100)`. It has four node types:

1. `report`
2. `drug`
3. `indication`
4. `adr`

It uses ten directed edge types:

1. report → primary suspect → drug
2. drug → reverse primary suspect → report
3. report → concomitant → drug
4. drug → reverse concomitant → report
5. report → indication → indication
6. indication → reverse indication → report
7. drug → historically associated → ADR
8. ADR → reverse historically associated → drug
9. indication → historically associated → ADR
10. ADR → reverse indication associated → indication

Four lazy node projections feed two `HeteroConv` layers using `SAGEConv`, sum aggregation, residual connections, and ReLU. A linear output layer produces 100 logits. Runtime applies `torch.sigmoid` exactly once, sorts descending by score with the event name as deterministic tie-breaker, and returns the configured top K (default 10).

## Runtime input contract

Only features supported by training are accepted:

```text
age
sex
candidate drug canonical name
indication name
active/current medication canonical names
```

The graph builder uses the original normalization, hashed drug/indication features, report features, and development-only historical associations. Unsupported patient fields such as labs, dose, route, allergies, genetics, renal function, or free-form notes are neither invented nor consumed.

Unknown candidate drugs, indications, or current medicines are listed as typed unknown entities and produce `DEGRADED_COVERAGE`. They do not become zero risk. Invalid artifacts, vocabulary mismatch, architecture mismatch, inference errors, service timeouts, and non-finite output fail closed with no events.

## Service and persistence pipeline

```text
React Specific Event Profile
    │ authenticated GET / POST
    ▼
Express consultation route
    │ ownership check + exact input mapping
    ▼
FastAPI /v1/hgnn/predict-events
    │ cached verified model, eval + inference_mode
    ▼
Protected checkpoint + vocabulary + associations
    │ top-K event-label scores
    ▼
Express response validation + versioned Prisma persistence
    │
    └── UI display only (ranking influence: none)
```

FastAPI loads LightGBM and HGNN independently during application lifespan. The HGNN model loads once and runs on CUDA when available or CPU otherwise. Express validates metadata, finiteness, range, rank continuity, deterministic ordering, and coverage consistency before persistence. Results are keyed by consultation, model version, checkpoint hash, and a stable hash of exact supported inputs and schema identities. `GET` reuses a matching persisted result; `POST` forces regeneration and updates the versioned record.

Endpoints:

- `GET /v1/hgnn/status` — FastAPI model readiness and immutable provenance.
- `POST /v1/hgnn/predict-events` — FastAPI event-profile inference.
- `GET /api/v1/consultations/:consultationId/adverse-event-risks` — authenticated persisted-or-generate application endpoint.
- `POST /api/v1/consultations/:consultationId/adverse-event-risks` — authenticated explicit retry/regeneration.

## Isolation from existing clinical logic

The HGNN result is not imported by or passed into the LightGBM predictor, conformal reliability calculation, DDInter analysis, DrugCentral drug-disease analysis, candidate generator, safety gate, recommendation weighting formula, deterministic comparator, or follow-up re-ranking. The recommendation test suite compares results with unrelated HGNN/allergy context and confirms identical rankings and the absence of an HGNN scoring component.

## Interface behavior

The responsive page follows the existing VitaNexus-RX navy, clinical blue, teal, neutral-card, and dark-mode design system. Its visual hierarchy includes consultation context, wizard navigation, baseline/audit/coverage badges, ranked event rows, accessible score bars with numeric text alternatives, interpretation guidance, and expandable model provenance. Neutral blue-to-teal bars deliberately avoid clinical risk-category colors because the scores are not validated low/moderate/high risk classes.

The wizard remains usable even if the HGNN service is unavailable. Clinical Safety, Adverse Risk Assessment, Event Profile, and Recommendations are directly navigable according to the existing consultation workflow.

## Remaining audit work

Before any future claim of calibrated individual risk, the baseline requires a separately governed clinical/model audit, calibration study, subgroup and fairness review, temporal/external validation, event-label quality review, threshold/use-policy approval, monitoring plan, and clinical usability evaluation. Those activities are intentionally not represented as completed by this integration.
