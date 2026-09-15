from __future__ import annotations

import gc
import json
import os
import platform
import shutil
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import sklearn
import torch
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.multiclass import OneVsRestClassifier
from sklearn.neural_network import MLPClassifier

from vitanexus_ml.config import (
    ARTIFACT_ROOT,
    HGNN_TRAINING_PIPELINE_VERSION,
    HGNN_VERSION,
    REPORT_ROOT,
    TRAINING_RUN_ROOT,
    TrainConfig,
    ensure_output_directories,
)
from vitanexus_ml.models.feature_cache import processed_input_identity, processed_input_location
from vitanexus_ml.models.hgnn import (
    HeterogeneousAdrNetwork,
    RELATIONS,
    _items,
    _multilabel_metrics,
    _targets,
    build_heterodata,
)
from vitanexus_ml.normalization import normalize_drug, normalize_indication, normalize_reaction
from vitanexus_ml.training_runtime import (
    ProgressReporter,
    StageStore,
    atomic_joblib,
    atomic_json,
    atomic_replace,
    atomic_torch,
    stable_hash,
    file_sha256,
    utc_now,
)


PARTITIONS = {
    "developmentTrain": ("2022Q1", "2024Q4"),
    "validation": ("2025Q1", "2025Q2"),
    "finalFit": ("2022Q1", "2025Q2"),
    "calibration": ("2025Q3", "2025Q3"),
    "holdout": ("2026Q1", "2026Q2"),
}
EXPECTED_ROWS = {
    "developmentTrain": 4_271_984,
    "validation": 638_284,
    "finalFit": 4_910_268,
    "calibration": 375_893,
    "holdout": 696_604,
}
ROW_COLUMNS = ["caseid", "quarter", "age_years", "sex", "candidate_drug", "indication", "current_medications", "reactions"]


@dataclass(frozen=True)
class HgnnTrainConfig:
    hidden_channels: int = 96
    epochs: int = 20
    batch_size: int = 2048
    learning_rate: float = 0.002
    weight_decay: float = 0.0001
    association_minimum: int = 5
    baseline_sample_rows: int = 400_000
    baseline_mlp_max_iter: int = 80
    use_amp: bool = True


def assert_hgnn_temporal_integrity(partitions: dict = PARTITIONS) -> None:
    development = set(_quarters(*partitions["developmentTrain"]))
    validation = set(_quarters(*partitions["validation"]))
    final_fit = set(_quarters(*partitions["finalFit"]))
    calibration = set(_quarters(*partitions["calibration"]))
    holdout = set(_quarters(*partitions["holdout"]))
    if development & validation or development & calibration or validation & calibration:
        raise RuntimeError("HGNN development, validation and calibration windows overlap.")
    if final_fit != development | validation:
        raise RuntimeError("HGNN final-fit window must equal development plus validation after selection.")
    if any(quarter.startswith("2026") for quarter in development | validation | final_fit | calibration):
        raise RuntimeError("2026 holdout leakage detected in an HGNN fitting/selection/calibration stage.")
    if holdout != {"2026Q1", "2026Q2"}:
        raise RuntimeError("HGNN temporal holdout must remain exactly 2026Q1-2026Q2.")


def assert_hgnn_target_edge_integrity() -> None:
    forbidden = [relation for relation in RELATIONS if relation[0] == "report" and relation[2] == "adr"]
    if forbidden:
        raise RuntimeError(f"HGNN target-edge leakage detected in encoder relations: {forbidden}")


def _quarters(start: str, end: str) -> list[str]:
    values = [f"{year}Q{quarter}" for year in range(2022, 2027) for quarter in range(1, 5)]
    return [value for value in values if start <= value <= end]


def _iter_frames(parquet: pq.ParquetFile, window: tuple[str, str], batch_size: int, columns=ROW_COLUMNS):
    start, end = window
    requested = list(dict.fromkeys(["quarter", *columns]))
    for record_batch in parquet.iter_batches(batch_size=batch_size, columns=requested):
        frame = record_batch.to_pandas()
        frame = frame[(frame["quarter"] >= start) & (frame["quarter"] <= end)]
        if len(frame):
            yield frame.reset_index(drop=True)


def _partition_counts(parquet: pq.ParquetFile) -> dict[str, int]:
    counts = Counter()
    for batch in parquet.iter_batches(batch_size=250_000, columns=["quarter"]):
        counts.update(batch.column(0).to_pylist())
    result = {
        name: sum(counts[quarter] for quarter in _quarters(*window))
        for name, window in PARTITIONS.items()
    }
    if result != EXPECTED_ROWS:
        raise RuntimeError(f"HGNN temporal row counts differ from the immutable scientific contract: {result}")
    return result


def _streaming_vocabulary(parquet: pq.ParquetFile, config: TrainConfig) -> list[dict]:
    counts: Counter = Counter()
    progress = ProgressReporter("hgnn-adr-vocabulary", EXPECTED_ROWS["developmentTrain"])
    rows = 0
    for frame in _iter_frames(parquet, PARTITIONS["developmentTrain"], 100_000, ["quarter", "reactions"]):
        for values in frame["reactions"]:
            counts.update(term for term in (normalize_reaction(value) for value in _items(values)) if term)
        rows += len(frame)
        progress.update(rows, f"unique ADR terms={len(counts):,}")
    ordered = sorted(
        ((term, count) for term, count in counts.items() if count >= config.adr_min_frequency),
        key=lambda item: (-item[1], item[0]),
    )[:config.adr_max_labels]
    vocabulary = [
        {"term": term, "trainingFrequency": count, "index": index, "version": HGNN_VERSION}
        for index, (term, count) in enumerate(ordered)
    ]
    progress.finish(f"labels={len(vocabulary)}")
    return vocabulary


def _streaming_associations(parquet: pq.ParquetFile, vocabulary: list[dict], window: tuple[str, str], minimum: int) -> dict:
    labels = {item["term"]: item["index"] for item in vocabulary}
    drug_counts: dict[str, Counter] = defaultdict(Counter)
    indication_counts: dict[str, Counter] = defaultdict(Counter)
    expected = EXPECTED_ROWS["developmentTrain"] if window == PARTITIONS["developmentTrain"] else EXPECTED_ROWS["finalFit"]
    progress = ProgressReporter("hgnn-development-associations" if window == PARTITIONS["developmentTrain"] else "hgnn-final-associations", expected)
    rows = 0
    for frame in _iter_frames(parquet, window, 100_000, ["quarter", "candidate_drug", "indication", "reactions"]):
        for candidate, indication, reactions in frame[["candidate_drug", "indication", "reactions"]].itertuples(index=False, name=None):
            present = {labels[term] for term in (normalize_reaction(value) for value in _items(reactions)) if term in labels}
            for index in present:
                drug_counts[normalize_drug(candidate)][index] += 1
                indication_counts[normalize_indication(indication)][index] += 1
        rows += len(frame)
        progress.update(rows, f"drugs={len(drug_counts):,}; indications={len(indication_counts):,}")
    result = {
        "drug": {key: sorted(index for index, count in values.items() if count >= minimum) for key, values in drug_counts.items()},
        "indication": {key: sorted(index for index, count in values.items() if count >= minimum) for key, values in indication_counts.items()},
    }
    progress.finish(f"drug nodes={len(result['drug']):,}; indication nodes={len(result['indication']):,}")
    return result


def _first_frame(parquet: pq.ParquetFile, window: tuple[str, str]) -> pd.DataFrame:
    return next(_iter_frames(parquet, window, 2, ROW_COLUMNS))


def _new_model(config: HgnnTrainConfig, vocabulary: list[dict], associations: dict, sample: pd.DataFrame, device: torch.device):
    model = HeterogeneousAdrNetwork(config.hidden_channels, len(vocabulary)).to(device)
    graph = build_heterodata(sample, vocabulary, associations, include_targets=False).to(device)
    with torch.no_grad():
        model(graph)
    return model


def _evaluate_streaming(model, parquet, window, vocabulary, associations, batch_size, device) -> tuple[dict, np.ndarray, np.ndarray]:
    probabilities, targets = [], []
    model.eval()
    with torch.no_grad():
        for frame in _iter_frames(parquet, window, batch_size, ROW_COLUMNS):
            graph = build_heterodata(frame, vocabulary, associations, include_targets=True).to(device)
            probabilities.append(torch.sigmoid(model(graph)).detach().cpu().numpy().astype(np.float32))
            targets.append(graph["report"].y.detach().cpu().numpy().astype(np.int8))
    probability_matrix = np.vstack(probabilities)
    target_matrix = np.vstack(targets)
    return _multilabel_metrics(target_matrix, probability_matrix), target_matrix, probability_matrix


def _restore_cuda_rng_state_all(states) -> None:
    """Restore CUDA RNG states after a checkpoint was loaded onto a CUDA device.

    ``torch.load(..., map_location=cuda)`` also moves the serialized RNG byte
    tensors to CUDA.  PyTorch's RNG restoration API intentionally accepts CPU
    ByteTensors only, so normalize those tensors before handing them back.
    """
    cpu_states = []
    for state in states:
        if not isinstance(state, torch.Tensor):
            state = torch.as_tensor(state, dtype=torch.uint8)
        state = state.detach().cpu().contiguous()
        if state.dtype != torch.uint8:
            raise RuntimeError(f"CUDA RNG checkpoint state must use torch.uint8, found {state.dtype}.")
        cpu_states.append(state)
    torch.cuda.set_rng_state_all(cpu_states)


def _train_epochs(
    *,
    stage: str,
    model,
    parquet,
    window,
    vocabulary,
    associations,
    device,
    config: HgnnTrainConfig,
    run_root: Path,
    state: StageStore,
    validation_window: tuple[str, str] | None,
    start_epoch: int = 0,
    history: list | None = None,
    best_score: float = -1.0,
    best_epoch: int = -1,
    checkpoint_metadata: dict | None = None,
) -> tuple[list, int, float]:
    history = list(history or [])
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    amp_enabled = bool(config.use_amp and device.type == "cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled)
    latest_path = run_root / f"{stage}_latest.pt"
    if start_epoch:
        checkpoint = torch.load(latest_path, map_location=device, weights_only=False)
        optimizer.load_state_dict(checkpoint["optimizerState"])
        scaler.load_state_dict(checkpoint.get("scalerState", {}))
        if checkpoint.get("torchRngState") is not None:
            torch.set_rng_state(checkpoint["torchRngState"].cpu())
        if device.type == "cuda" and checkpoint.get("cudaRngState") is not None:
            _restore_cuda_rng_state_all(checkpoint["cudaRngState"])
    state.start(stage, resumedEpoch=start_epoch, totalEpochs=config.epochs)
    for epoch in range(start_epoch, config.epochs):
        model.train()
        processed = 0
        loss_sum = 0.0
        batches = 0
        started = time.perf_counter()
        for batch_index, frame in enumerate(_iter_frames(parquet, window, config.batch_size, ROW_COLUMNS)):
            frame = frame.sample(frac=1.0, random_state=20260824 + epoch + batch_index).reset_index(drop=True)
            graph = build_heterodata(frame, vocabulary, associations, include_targets=True).to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=amp_enabled):
                logits = model(graph)
                loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, graph["report"].y)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            processed += len(frame)
            batches += 1
            loss_sum += float(loss.detach().cpu())
            if batches == 1 or batches % 100 == 0:
                print(f"[{stage}] epoch {epoch + 1}/{config.epochs}; rows={processed:,}; meanLoss={loss_sum / batches:.6f}", flush=True)
            del graph, logits, loss
        validation_metrics = None
        if validation_window is not None:
            validation_metrics, validation_targets, validation_probabilities = _evaluate_streaming(
                model, parquet, validation_window, vocabulary, associations, config.batch_size, device
            )
            del validation_targets, validation_probabilities
            score = float(validation_metrics["microAUPRC"])
            if score > best_score:
                best_score, best_epoch = score, epoch
                atomic_torch(run_root / f"{stage}_best.pt", {
                    "modelState": model.state_dict(), "epoch": epoch, "score": score,
                    "checkpointMetadata": checkpoint_metadata,
                })
        history.append({
            "epoch": epoch + 1,
            "trainingRows": processed,
            "meanLoss": loss_sum / max(batches, 1),
            "validation": validation_metrics,
            "elapsedSeconds": time.perf_counter() - started,
        })
        checkpoint = {
            "stage": stage,
            "epoch": epoch,
            "nextEpoch": epoch + 1,
            "modelState": model.state_dict(),
            "optimizerState": optimizer.state_dict(),
            "scalerState": scaler.state_dict(),
            "torchRngState": torch.get_rng_state(),
            "cudaRngState": torch.cuda.get_rng_state_all() if device.type == "cuda" else None,
            "history": history,
            "bestValidationMicroAUPRC": best_score,
            "bestEpoch": best_epoch,
            "config": asdict(config),
            "checkpointMetadata": checkpoint_metadata,
        }
        atomic_torch(latest_path, checkpoint)
        state.start(stage, completedEpoch=epoch + 1, totalEpochs=config.epochs, bestEpoch=best_epoch + 1, bestValidationMicroAUPRC=best_score)
    state.complete(stage, epochs=config.epochs, bestEpoch=best_epoch + 1, bestValidationMicroAUPRC=best_score, history=history)
    return history, best_epoch, best_score


def _resume_model(stage: str, model, run_root: Path, device, expected_metadata: dict) -> tuple[int, list, float, int]:
    path = run_root / f"{stage}_latest.pt"
    if not path.exists():
        return 0, [], -1.0, -1
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    if checkpoint.get("checkpointMetadata") != expected_metadata:
        raise RuntimeError(f"{stage} checkpoint identity differs from dataset/vocabulary/split/graph configuration.")
    model.load_state_dict(checkpoint["modelState"])
    return (
        int(checkpoint["nextEpoch"]),
        checkpoint.get("history", []),
        float(checkpoint.get("bestValidationMicroAUPRC", -1.0)),
        int(checkpoint.get("bestEpoch", -1)),
    )


def _sample_development(parquet: pq.ParquetFile, target: int) -> pd.DataFrame:
    quarters = _quarters(*PARTITIONS["developmentTrain"])
    quotas = {quarter: target // len(quarters) for quarter in quarters}
    for quarter in quarters[: target % len(quarters)]:
        quotas[quarter] += 1
    counts = Counter()
    count_progress = ProgressReporter("hgnn-baseline-sample-count", EXPECTED_ROWS["developmentTrain"])
    counted = 0
    for frame in _iter_frames(parquet, PARTITIONS["developmentTrain"], 250_000, ["quarter"]):
        counts.update(frame["quarter"].value_counts().to_dict())
        counted += len(frame)
        count_progress.update(counted)
    count_progress.finish()

    # Deterministic CASEID hashing avoids selecting only the first physical Parquet
    # batches in each quarter. A 25% oversample is sorted down to the exact quota.
    candidates = []
    maximum_hash = float(np.iinfo(np.uint64).max)
    sample_progress = ProgressReporter("hgnn-baseline-sample-select", EXPECTED_ROWS["developmentTrain"])
    processed = 0
    for frame in _iter_frames(parquet, PARTITIONS["developmentTrain"], 100_000, ROW_COLUMNS):
        hashes = pd.util.hash_pandas_object(frame[["caseid", "quarter"]], index=False).to_numpy(dtype=np.uint64)
        fractions = hashes.astype(np.float64) / maximum_hash
        limits = frame["quarter"].map(
            lambda quarter: min(1.0, (quotas[str(quarter)] * 1.25) / max(counts[str(quarter)], 1))
        ).to_numpy(dtype=np.float64)
        selected = frame.loc[fractions < limits].copy()
        if len(selected):
            selected["_sample_hash"] = hashes[fractions < limits]
            candidates.append(selected)
        processed += len(frame)
        sample_progress.update(processed, f"candidates={sum(len(value) for value in candidates):,}")
    if not candidates:
        raise RuntimeError("Deterministic development baseline sampling produced no rows.")
    candidate_frame = pd.concat(candidates, ignore_index=True)
    selected_frames = []
    for quarter in quarters:
        quarter_rows = candidate_frame[candidate_frame["quarter"] == quarter].nsmallest(quotas[quarter], "_sample_hash")
        if len(quarter_rows) != quotas[quarter]:
            raise RuntimeError(
                f"Development baseline sample for {quarter} contains {len(quarter_rows):,} rows; "
                f"expected {quotas[quarter]:,}. Increase the deterministic oversampling margin."
            )
        selected_frames.append(quarter_rows)
    result = pd.concat(selected_frames, ignore_index=True).drop(columns=["_sample_hash"])
    if len(result) != target:
        raise RuntimeError(f"Expected an exact {target:,}-row development baseline sample, found {len(result):,}.")
    sample_progress.finish(f"selected={len(result):,}")
    return result


def _per_label_metrics(targets: np.ndarray, probabilities: np.ndarray, vocabulary: list[dict]) -> list[dict]:
    rows = []
    for index, item in enumerate(vocabulary):
        labels = targets[:, index]
        both = len(np.unique(labels)) == 2
        predictions = probabilities[:, index] >= 0.5
        rows.append({
            "term": item["term"],
            "trainingFrequency": item["trainingFrequency"],
            "holdoutPositives": int(labels.sum()),
            "auprc": float(average_precision_score(labels, probabilities[:, index])) if labels.any() else None,
            "f1": float(f1_score(labels, predictions, zero_division=0)),
            "precision": float(precision_score(labels, predictions, zero_division=0)),
            "recall": float(recall_score(labels, predictions, zero_division=0)),
            "calibratable": both,
        })
    return rows


def _run_scalable_baselines(parquet, vocabulary, serious, config, run_root, state, device) -> list[dict]:
    path = run_root / "hgnn_baselines.joblib"
    if state.is_complete("baselines") and path.exists():
        return joblib.load(path)["rows"]
    state.start("baselines", trainingMethod="deterministic quarter-balanced development subset")
    sample = _sample_development(parquet, config.baseline_sample_rows)
    builder = serious["featureBuilder"]
    x_train = builder.transform(sample)
    y_train = _targets(sample, vocabulary)
    prevalence = y_train.mean(axis=0)
    model_specs = [
        ("hgnn_baseline_logistic", "One-vs-Rest Logistic (SGD scalable equivalent)", lambda: OneVsRestClassifier(SGDClassifier(
            loss="log_loss", class_weight="balanced", max_iter=20, tol=None, average=True, random_state=20260824
        ), n_jobs=1)),
        ("hgnn_baseline_mlp", "Multi-label MLP", lambda: MLPClassifier(
            hidden_layer_sizes=(64,), max_iter=config.baseline_mlp_max_iter, early_stopping=True, random_state=20260824
        )),
    ]
    trained = []
    for stage, name, factory in model_specs:
        model_path = run_root / f"{stage}.joblib"
        if state.is_complete(stage) and model_path.exists():
            model = joblib.load(model_path)
        else:
            state.start(stage, modelName=name, trainingRows=len(sample))
            model = factory()
            model.fit(x_train, y_train)
            atomic_joblib(model_path, model)
            state.complete(stage, modelName=name, trainingRows=len(sample))
        trained.append((name, model))
    result_buffers = {"Training prevalence": []}
    target_buffers = []
    for name, _ in trained:
        result_buffers[name] = []
    for frame in _iter_frames(parquet, PARTITIONS["validation"], 25_000, ROW_COLUMNS):
        x = builder.transform(frame)
        y = _targets(frame, vocabulary)
        target_buffers.append(y)
        result_buffers["Training prevalence"].append(np.tile(prevalence, (len(frame), 1)))
        for name, model in trained:
            result_buffers[name].append(np.asarray(model.predict_proba(x)))
    targets = np.vstack(target_buffers)
    rows = []
    for name, values in result_buffers.items():
        rows.append({
            "model": name,
            "trainingRows": len(sample),
            "validationRows": len(targets),
            "trainingMethod": "deterministic quarter-balanced development subset; explicitly used because full liblinear/MLP baselines are infeasible",
            **_multilabel_metrics(targets, np.vstack(values)),
        })
    atomic_joblib(path, {"rows": rows, "models": trained, "prevalence": prevalence})
    state.complete("baselines", rows=rows)
    return rows


def _promote(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    shutil.copy2(source, temporary)
    atomic_replace(temporary, target)


def train_hgnn_colab(cohort_path: Path, config: HgnnTrainConfig | None = None, train_config: TrainConfig | None = None) -> dict:
    config = config or HgnnTrainConfig()
    train_config = train_config or TrainConfig()
    ensure_output_directories()
    assert_hgnn_temporal_integrity()
    assert_hgnn_target_edge_integrity()
    input_identity = processed_input_identity(cohort_path)
    serious_manifest_path = ARTIFACT_ROOT / "training_manifest.json"
    serious_path = ARTIFACT_ROOT / "serious_outcome.joblib"
    if not serious_manifest_path.exists() or not serious_path.exists():
        raise RuntimeError("Full serious-outcome artifacts must be promoted before full HGNN training.")
    serious_manifest = json.loads(serious_manifest_path.read_text(encoding="utf-8"))
    if serious_manifest.get("fastMode") is not False or serious_manifest.get("fullFinalData") is not True:
        raise RuntimeError("Refusing full HGNN training with smoke or partial serious-outcome artifacts.")
    if serious_manifest.get("input") != input_identity:
        raise RuntimeError("Serious-outcome artifact and HGNN immutable dataset identities differ.")
    serious = joblib.load(serious_path)
    if serious.get("fastMode") is not False:
        raise RuntimeError("Serious-outcome model payload is still smoke-mode.")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[hgnn] device={device}; cuda={torch.cuda.is_available()}; batchSize={config.batch_size}", flush=True)
    identity = {
        "pipelineVersion": HGNN_TRAINING_PIPELINE_VERSION,
        "modelVersion": HGNN_VERSION,
        "input": input_identity,
        "trainConfig": asdict(train_config),
        "hgnnConfig": asdict(config),
        "temporalPartitions": {key: list(value) for key, value in PARTITIONS.items()},
        "mode": "FULL",
    }
    run_key = stable_hash(identity)[:20]
    run_root = TRAINING_RUN_ROOT / "hgnn" / run_key
    state = StageStore(run_root / "state.json", identity)
    if state.is_complete("promoted") and (ARTIFACT_ROOT / "hgnn_training_manifest.json").exists():
        manifest = json.loads((ARTIFACT_ROOT / "hgnn_training_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("pipelineVersion") == HGNN_TRAINING_PIPELINE_VERSION and manifest.get("input") == input_identity:
            report = json.loads((REPORT_ROOT / "hgnn_metrics.json").read_text(encoding="utf-8"))
            return {"status": "COMPLETE", "runKey": run_key, "device": manifest["device"], "holdout2026": report["holdout2026"], "resumed": True}
    parquet = pq.ParquetFile(cohort_path)
    counts = _partition_counts(parquet)
    state.complete("temporal_preflight", counts=counts, holdoutUsedBeforeFinalEvaluation=False)

    vocabulary_path = run_root / "adr_vocabulary.json"
    if state.is_complete("vocabulary") and vocabulary_path.exists():
        vocabulary = json.loads(vocabulary_path.read_text(encoding="utf-8"))
    else:
        vocabulary = _streaming_vocabulary(parquet, train_config)
        vocabulary_hash = stable_hash({"items": vocabulary, "window": list(PARTITIONS["developmentTrain"])})
        atomic_json(vocabulary_path, {"items": vocabulary, "identity": vocabulary_hash, "sourceWindow": list(PARTITIONS["developmentTrain"])})
        state.complete("vocabulary", labels=len(vocabulary), identity=vocabulary_hash, sourceWindow=list(PARTITIONS["developmentTrain"]))
    if isinstance(vocabulary, dict):
        vocabulary = vocabulary["items"]
    vocabulary_hash = stable_hash({"items": vocabulary, "window": list(PARTITIONS["developmentTrain"])})

    development_associations_path = run_root / "development_associations.joblib"
    if state.is_complete("development_associations") and development_associations_path.exists():
        development_associations = joblib.load(development_associations_path)
    else:
        development_associations = _streaming_associations(
            parquet, vocabulary, PARTITIONS["developmentTrain"], config.association_minimum
        )
        atomic_joblib(development_associations_path, development_associations)
        state.complete("development_associations", sourceWindow=list(PARTITIONS["developmentTrain"]), validationRowsUsed=False)

    sample = _first_frame(parquet, PARTITIONS["developmentTrain"])
    selection_checkpoint_metadata = {
        "runIdentity": identity,
        "vocabularyIdentity": vocabulary_hash,
        "temporalWindow": list(PARTITIONS["developmentTrain"]),
        "validationWindow": list(PARTITIONS["validation"]),
        "graphAssociationSha256": file_sha256(development_associations_path),
        "targetEdgesExcluded": True,
    }
    selection_model = _new_model(config, vocabulary, development_associations, sample, device)
    start_epoch, history, best_score, best_epoch = _resume_model(
        "hgnn_selection", selection_model, run_root, device, selection_checkpoint_metadata
    )
    if not state.is_complete("hgnn_selection"):
        history, best_epoch, best_score = _train_epochs(
            stage="hgnn_selection", model=selection_model, parquet=parquet,
            window=PARTITIONS["developmentTrain"], validation_window=PARTITIONS["validation"],
            vocabulary=vocabulary, associations=development_associations, device=device,
            config=config, run_root=run_root, state=state, start_epoch=start_epoch,
            history=history, best_score=best_score, best_epoch=best_epoch,
            checkpoint_metadata=selection_checkpoint_metadata,
        )
    best = torch.load(run_root / "hgnn_selection_best.pt", map_location=device, weights_only=False)
    selection_model.load_state_dict(best["modelState"])
    selection_evaluation_path = run_root / "hgnn_selection_evaluation.json"
    if state.is_complete("selection_evaluation") and selection_evaluation_path.exists():
        selection_evaluation = json.loads(selection_evaluation_path.read_text(encoding="utf-8"))
        if selection_evaluation.get("checkpointIdentity") != selection_checkpoint_metadata:
            raise RuntimeError("Cached HGNN selection evaluation has a different scientific identity.")
        validation_metrics = selection_evaluation["validation"]
    else:
        validation_metrics, selection_targets, selection_probabilities = _evaluate_streaming(
            selection_model, parquet, PARTITIONS["validation"], vocabulary,
            development_associations, config.batch_size, device,
        )
        del selection_targets, selection_probabilities
        atomic_json(selection_evaluation_path, {
            "checkpointIdentity": selection_checkpoint_metadata,
            "bestEpoch": int(best["epoch"]) + 1,
            "validation": validation_metrics,
        })
        state.complete("selection_evaluation", bestEpoch=int(best["epoch"]) + 1, validation=validation_metrics)

    baseline_rows = _run_scalable_baselines(parquet, vocabulary, serious, config, run_root, state, device)

    final_associations_path = run_root / "final_associations.joblib"
    if state.is_complete("final_associations") and final_associations_path.exists():
        final_associations = joblib.load(final_associations_path)
    else:
        final_associations = _streaming_associations(parquet, vocabulary, PARTITIONS["finalFit"], config.association_minimum)
        atomic_joblib(final_associations_path, final_associations)
        state.complete("final_associations", sourceWindow=list(PARTITIONS["finalFit"]), createdAfterSelection=True)

    final_epochs = int(best["epoch"]) + 1
    final_config = HgnnTrainConfig(**{**asdict(config), "epochs": final_epochs})
    final_checkpoint_metadata = {
        "runIdentity": identity,
        "vocabularyIdentity": vocabulary_hash,
        "temporalWindow": list(PARTITIONS["finalFit"]),
        "graphAssociationSha256": file_sha256(final_associations_path),
        "selectedEpochs": final_epochs,
        "targetEdgesExcluded": True,
    }
    final_model = _new_model(final_config, vocabulary, final_associations, sample, device)
    final_start, final_history, _, _ = _resume_model(
        "hgnn_final_refit", final_model, run_root, device, final_checkpoint_metadata
    )
    if not state.is_complete("hgnn_final_refit"):
        final_history, _, _ = _train_epochs(
            stage="hgnn_final_refit", model=final_model, parquet=parquet,
            window=PARTITIONS["finalFit"], validation_window=None,
            vocabulary=vocabulary, associations=final_associations, device=device,
            config=final_config, run_root=run_root, state=state, start_epoch=final_start,
            history=final_history,
            checkpoint_metadata=final_checkpoint_metadata,
        )

    calibration_path = run_root / "hgnn_calibration.joblib"
    if state.is_complete("calibration") and calibration_path.exists():
        calibrators = joblib.load(calibration_path)
    else:
        _, calibration_targets, calibration_raw = _evaluate_streaming(
            final_model, parquet, PARTITIONS["calibration"], vocabulary, final_associations, config.batch_size, device
        )
        calibrators = []
        uncalibrated = []
        for index in range(len(vocabulary)):
            labels = calibration_targets[:, index]
            if len(np.unique(labels)) == 2:
                calibrators.append(IsotonicRegression(out_of_bounds="clip").fit(calibration_raw[:, index], labels))
            else:
                calibrators.append(None)
                uncalibrated.append(vocabulary[index]["term"])
        atomic_joblib(calibration_path, calibrators)
        state.complete("calibration", sourceWindow=list(PARTITIONS["calibration"]), uncalibratedLabels=uncalibrated)
        del calibration_targets, calibration_raw
        gc.collect()

    holdout_path = run_root / "hgnn_holdout.joblib"
    if state.is_complete("holdout_evaluation") and holdout_path.exists():
        holdout_payload = joblib.load(holdout_path)
        raw_metrics = holdout_payload["rawMetrics"]
        holdout_metrics = holdout_payload["metrics"]
        per_label = holdout_payload["perLabel"]
    else:
        raw_metrics, holdout_targets, holdout_raw = _evaluate_streaming(
            final_model, parquet, PARTITIONS["holdout"], vocabulary, final_associations, config.batch_size, device
        )
        calibrated = np.column_stack([
            calibrator.predict(holdout_raw[:, index]) if calibrator else holdout_raw[:, index]
            for index, calibrator in enumerate(calibrators)
        ])
        holdout_metrics = _multilabel_metrics(holdout_targets, calibrated)
        per_label = _per_label_metrics(holdout_targets, calibrated, vocabulary)
        atomic_joblib(holdout_path, {"rawMetrics": raw_metrics, "metrics": holdout_metrics, "perLabel": per_label})
        state.complete("holdout_evaluation", holdoutRows=counts["holdout"], metrics=holdout_metrics)
        del holdout_targets, holdout_raw, calibrated
    report = {
        "version": HGNN_VERSION,
        "pipelineVersion": HGNN_TRAINING_PIPELINE_VERSION,
        "fastMode": False,
        "fullFinalData": True,
        "device": str(device),
        "validationBeforeFinalRefit": validation_metrics,
        "holdout2026": holdout_metrics,
        "rawHoldout2026": raw_metrics,
        "perLabelHoldout2026": per_label,
        "targetLeakageSafeguard": "report-to-ADR target edges are never passed to the encoder",
    }
    staged_artifacts = run_root / "final_artifacts"
    staged_reports = run_root / "reports"
    staged_artifacts.mkdir(parents=True, exist_ok=True)
    staged_reports.mkdir(parents=True, exist_ok=True)
    atomic_joblib(staged_artifacts / "hgnn_metadata.joblib", {
        "associations": final_associations,
        "calibrators": calibrators,
        "vocabulary": vocabulary,
        "hiddenChannels": config.hidden_channels,
        "version": HGNN_VERSION,
        "pipelineVersion": HGNN_TRAINING_PIPELINE_VERSION,
        "fastMode": False,
    })
    atomic_torch(staged_artifacts / "hgnn_state.pt", final_model.state_dict())
    atomic_json(staged_artifacts / "adr_vocabulary.json", {
        "version": HGNN_VERSION,
        "sourceWindow": list(PARTITIONS["developmentTrain"]),
        "identity": vocabulary_hash,
        "items": vocabulary,
    })
    hgnn_manifest = {
        "pipelineVersion": HGNN_TRAINING_PIPELINE_VERSION,
        "version": HGNN_VERSION,
        "input": input_identity,
        "inputLocation": processed_input_location(cohort_path),
        "fastMode": False,
        "fullFinalData": True,
        "temporalRows": counts,
        "selectionTrainWindow": list(PARTITIONS["developmentTrain"]),
        "validationWindow": list(PARTITIONS["validation"]),
        "finalFitWindow": list(PARTITIONS["finalFit"]),
        "calibrationWindow": list(PARTITIONS["calibration"]),
        "holdoutWindow": list(PARTITIONS["holdout"]),
        "bestEpoch": final_epochs,
        "vocabularyIdentity": vocabulary_hash,
        "configuration": asdict(config),
        "device": str(device),
        "python": sys.version,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "scikitLearn": sklearn.__version__,
        "completedAt": utc_now(),
    }
    atomic_json(staged_artifacts / "hgnn_training_manifest.json", hgnn_manifest)
    atomic_json(staged_reports / "hgnn_metrics.json", report)
    pd.DataFrame(baseline_rows + [{"model": "HGNN", **validation_metrics}]).to_csv(staged_reports / "hgnn_baselines.csv", index=False)
    state.complete("staged_final_artifacts")

    for name in ("hgnn_metadata.joblib", "hgnn_state.pt", "adr_vocabulary.json", "hgnn_training_manifest.json"):
        _promote(staged_artifacts / name, ARTIFACT_ROOT / name)
    for name in ("hgnn_metrics.json", "hgnn_baselines.csv"):
        _promote(staged_reports / name, REPORT_ROOT / name)
    state.complete("promoted", artifacts=6)
    return {"status": "COMPLETE", "runKey": run_key, "device": str(device), "holdout2026": holdout_metrics}
