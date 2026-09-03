from __future__ import annotations

import gc
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
import warnings
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import sklearn
from lightgbm import LGBMClassifier
from scipy import sparse
from sklearn.calibration import calibration_curve
from sklearn.dummy import DummyClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import SGDClassifier
from sklearn.naive_bayes import ComplementNB

from vitanexus_ml.config import (
    ARTIFACT_ROOT,
    BOOTSTRAP_VERSION,
    CONFORMAL_VERSION,
    FEATURE_SCHEMA_VERSION,
    LIGHTGBM_VERSION,
    PREPROCESSING_VERSION,
    REPORT_ROOT,
    FEATURE_CACHE_ROOT,
    TRAINING_RUN_ROOT,
    TRAINING_PIPELINE_VERSION,
    TrainConfig,
    ensure_output_directories,
)
from vitanexus_ml.conformal.split import conformal_metrics, conformal_quantile
from vitanexus_ml.features.builder import FeatureBuilder
from vitanexus_ml.models.feature_cache import (
    CACHE_COLUMNS,
    QUARTER_TO_CODE,
    FeatureCache,
    assert_input_identity,
    build_or_load_feature_cache,
    normalize_processed_input_identity,
    processed_input_identity,
    processed_input_location,
)
from vitanexus_ml.models.metrics import binary_metrics, expected_calibration_error, select_threshold
from vitanexus_ml.training_runtime import (
    PeakMemoryMonitor,
    ProgressReporter,
    StageStore,
    atomic_joblib,
    atomic_json,
    atomic_replace,
    format_duration,
    stable_hash,
    utc_now,
)


TUNING_PARAMS = [
    {"num_leaves": 31, "max_depth": -1, "min_child_samples": 30, "learning_rate": 0.05, "feature_fraction": 0.9, "bagging_fraction": 0.9, "lambda_l1": 0.0, "lambda_l2": 1.0},
    {"num_leaves": 63, "max_depth": 10, "min_child_samples": 50, "learning_rate": 0.04, "feature_fraction": 0.8, "bagging_fraction": 0.8, "lambda_l1": 0.1, "lambda_l2": 2.0},
    {"num_leaves": 24, "max_depth": 7, "min_child_samples": 75, "learning_rate": 0.07, "feature_fraction": 1.0, "bagging_fraction": 0.85, "lambda_l1": 0.0, "lambda_l2": 4.0},
]

PARTITIONS = {
    "developmentTrain": ("2022Q1", "2024Q4"),
    "tuningValidation": ("2025Q1", "2025Q2"),
    "finalFit": ("2022Q1", "2025Q2"),
    "calibration": ("2025Q3", "2025Q3"),
    "conformal": ("2025Q4", "2025Q4"),
    "holdout": ("2026Q1", "2026Q2"),
}


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _classifier(params: dict, seed: int, estimators: int, threads: int) -> LGBMClassifier:
    return LGBMClassifier(
        objective="binary",
        n_estimators=int(estimators),
        random_state=seed,
        n_jobs=threads,
        verbosity=-1,
        deterministic=True,
        force_col_wise=True,
        **params,
    )


def _iteration_callback(label: str, total_iterations: int, every: int = 25):
    started = time.perf_counter()

    def callback(environment) -> None:
        completed = environment.iteration + 1
        if completed == 1 or completed % every == 0 or completed >= total_iterations:
            elapsed = time.perf_counter() - started
            eta = elapsed / completed * max(total_iterations - completed, 0)
            print(
                f"[{label}] iteration {completed}/{total_iterations} | elapsed {format_duration(elapsed)} | ETA <= {format_duration(eta)}",
                flush=True,
            )

    callback.order = 50
    callback.before_iteration = False
    return callback


def _fit_lgbm(
    model,
    x_train,
    y_train,
    sample_weight,
    x_validation=None,
    y_validation=None,
    early_stopping: int | None = 40,
    progress_label: str = "lightgbm",
):
    kwargs = {"sample_weight": sample_weight}
    callbacks = [_iteration_callback(progress_label, int(model.n_estimators))]
    if x_validation is not None and len(y_validation):
        kwargs["eval_set"] = [(x_validation, y_validation)]
        if early_stopping:
            callbacks.insert(0, lgb.early_stopping(early_stopping, verbose=False))
    kwargs["callbacks"] = callbacks
    return model.fit(x_train, y_train, **kwargs)


def _probability(model, matrix) -> np.ndarray:
    # LightGBM's sklearn wrapper assigns synthetic feature names to CSR fits and
    # sklearn warns when the same ordered CSR schema is used for prediction.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names, but LGBMClassifier was fitted with feature names")
        return np.asarray(model.predict_proba(matrix)[:, 1], dtype=float)


def _balanced_weights(labels: np.ndarray, multiplicities: np.ndarray | None = None) -> np.ndarray:
    labels = np.asarray(labels, dtype=np.int8)
    counts = np.ones(len(labels), dtype=np.float32) if multiplicities is None else np.asarray(multiplicities, dtype=np.float32)
    negative = float(counts[labels == 0].sum())
    positive = float(counts[labels == 1].sum())
    if not negative or not positive:
        raise RuntimeError("Both serious-outcome classes are required for balanced training")
    total = negative + positive
    class_weights = np.asarray([total / (2.0 * negative), total / (2.0 * positive)], dtype=np.float32)
    return counts * class_weights[labels]


def _bootstrap_multiplicities(rows: int, seed: int) -> np.ndarray:
    """Return deterministic bootstrap row counts without copying the feature matrix."""
    rng = np.random.default_rng(seed)
    sampled_indices = rng.integers(0, rows, size=rows, dtype=np.int64)
    return np.bincount(sampled_indices, minlength=rows).astype(np.float32, copy=False)


def _pending_bootstrap_indices(state: StageStore, replica_root: Path, total: int) -> list[int]:
    return [
        index for index in range(total)
        if not (
            state.is_complete(f"bootstrap_{index:02d}")
            and (replica_root / f"replica_{index:02d}.joblib").exists()
        )
    ]


def _partition_indices(cache: FeatureCache, start: str, end: str) -> np.ndarray:
    lower = QUARTER_TO_CODE[start]
    upper = QUARTER_TO_CODE[end]
    return np.flatnonzero((cache.quarter_codes >= lower) & (cache.quarter_codes <= upper))


def _temporal_stratified_sample(indices: np.ndarray, cache: FeatureCache, target: int, seed: int) -> np.ndarray:
    if len(indices) <= target:
        return np.asarray(indices, dtype=np.int64)
    labels = np.asarray(cache.labels[indices])
    quarters = np.asarray(cache.quarter_codes[indices])
    rng = np.random.default_rng(seed)
    selected: list[np.ndarray] = []
    groups = [(quarter, label) for quarter in np.unique(quarters) for label in (0, 1)]
    remaining = target
    for group_index, (quarter, label) in enumerate(groups):
        members = indices[(quarters == quarter) & (labels == label)]
        if not len(members):
            continue
        if group_index == len(groups) - 1:
            quota = min(len(members), remaining)
        else:
            quota = max(1, int(round(target * len(members) / len(indices))))
            quota = min(len(members), quota, remaining)
        selected.append(rng.choice(members, size=quota, replace=False))
        remaining -= quota
    combined = np.concatenate(selected)
    if len(combined) < target:
        available = np.setdiff1d(indices, combined, assume_unique=False)
        combined = np.concatenate([combined, rng.choice(available, size=target - len(combined), replace=False)])
    elif len(combined) > target:
        combined = rng.choice(combined, size=target, replace=False)
    return np.sort(combined.astype(np.int64, copy=False))


def _atomic_npy(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as target:
        np.save(target, values)
    atomic_replace(temporary, path)


def _sample_checkpoint(path: Path, indices: np.ndarray, cache: FeatureCache, target: int, seed: int) -> np.ndarray:
    if path.exists():
        return np.load(path, mmap_mode="r")
    selected = _temporal_stratified_sample(indices, cache, target, seed)
    _atomic_npy(path, selected)
    return np.load(path, mmap_mode="r")


def _require_benchmark(cohort_path: Path, config: TrainConfig) -> dict:
    path = REPORT_ROOT / "lightgbm_benchmark.json"
    if not path.exists():
        raise RuntimeError("A matching laptop benchmark is required before full training. Run: npm run ml:benchmark")
    report = json.loads(path.read_text(encoding="utf-8"))
    expected_input = processed_input_identity(cohort_path)
    reported_input = normalize_processed_input_identity(report.get("input", {}))
    if report.get("pipelineVersion") != TRAINING_PIPELINE_VERSION or reported_input != expected_input or report.get("config") != asdict(config):
        raise RuntimeError("The existing benchmark does not match this immutable cohort and training configuration. Run: npm run ml:benchmark")
    if not report.get("approvedForFullRun"):
        raise RuntimeError("The benchmark projected unsafe RAM use for a 16 GB laptop. Full training is blocked until the pipeline is revised.")
    return report


def _stage_payload(path: Path, state: StageStore, stage: str):
    if state.is_complete(stage) and path.exists():
        print(f"[{stage}] resumed from checkpoint", flush=True)
        return joblib.load(path)
    return None


def _model_metrics(model, x_validation, y_validation) -> tuple[dict, float]:
    probabilities = _probability(model, x_validation)
    threshold = select_threshold(y_validation, probabilities)
    return binary_metrics(y_validation, probabilities, threshold), threshold


def _promote_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    shutil.copyfile(source, temporary)
    atomic_replace(temporary, target)


def train_resumable_lightgbm(cohort_path: Path, config: TrainConfig) -> dict:
    ensure_output_directories()
    benchmark = _require_benchmark(cohort_path, config)
    input_identity = normalize_processed_input_identity(benchmark["input"])
    run_identity = {
        "pipelineVersion": TRAINING_PIPELINE_VERSION,
        "input": input_identity,
        "config": asdict(config),
        "mode": "FULL",
        "temporalPartitions": {name: list(window) for name, window in PARTITIONS.items()},
    }
    run_key = stable_hash(run_identity)[:20]
    run_root = TRAINING_RUN_ROOT / run_key
    checkpoint_root = run_root / "checkpoints"
    staged_report_root = run_root / "reports"
    state = StageStore(run_root / "state.json", run_identity)
    print(f"[training] resumable run={run_key}; benchmark estimate={benchmark['estimatedFullRuntime']['likely']}", flush=True)
    if state.is_complete("promoted") and (ARTIFACT_ROOT / "training_manifest.json").exists() and (REPORT_ROOT / "final_temporal_evaluation.json").exists():
        manifest = json.loads((ARTIFACT_ROOT / "training_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("pipelineVersion") == TRAINING_PIPELINE_VERSION and manifest.get("input") == input_identity:
            print("[training] complete FULL run resumed; nothing to retrain", flush=True)
            return {
                "mode": "FULL",
                "runKey": run_key,
                "temporalRows": manifest["temporalRows"],
                "holdout": json.loads((REPORT_ROOT / "final_temporal_evaluation.json").read_text(encoding="utf-8"))["lightgbm"],
                "resumed": True,
            }

    cache = build_or_load_feature_cache(cohort_path, config, FEATURE_CACHE_ROOT)
    state.complete("feature_cache", cacheKey=cache.metadata["cacheKey"], rows=cache.rows, nnz=cache.features.nnz)
    assert_input_identity(cohort_path, input_identity)

    partition_indices = {name: _partition_indices(cache, *window) for name, window in PARTITIONS.items()}
    partition_counts = {name: int(len(values)) for name, values in partition_indices.items()}
    empty = [name for name, count in partition_counts.items() if count == 0]
    if empty:
        raise RuntimeError(f"Temporal partitions are empty: {', '.join(empty)}")
    if partition_counts["finalFit"] != partition_counts["developmentTrain"] + partition_counts["tuningValidation"]:
        raise RuntimeError("Final-fit partition does not exactly equal development plus tuning-validation rows")
    state.complete("temporal_partitions", counts=partition_counts)

    tuning_train_indices = _sample_checkpoint(
        checkpoint_root / "tuning_train_indices.npy",
        partition_indices["developmentTrain"], cache, config.tuning_train_rows, config.seed,
    )
    tuning_validation_indices = _sample_checkpoint(
        checkpoint_root / "tuning_validation_indices.npy",
        partition_indices["tuningValidation"], cache, config.tuning_validation_rows, config.seed + 1,
    )
    state.complete(
        "tuning_samples",
        developmentRows=int(len(tuning_train_indices)), validationRows=int(len(tuning_validation_indices)),
        method="deterministic quarter-and-class stratified sample; final model remains full-data",
    )
    x_tune_train = cache.features[tuning_train_indices]
    y_tune_train = np.asarray(cache.labels[tuning_train_indices], dtype=np.int8)
    x_tune_validation = cache.features[tuning_validation_indices]
    y_tune_validation = np.asarray(cache.labels[tuning_validation_indices], dtype=np.int8)
    tune_weights = _balanced_weights(y_tune_train)
    tuning_results = []
    tuning_progress = ProgressReporter("lightgbm-tuning", len(TUNING_PARAMS))
    for index, params in enumerate(TUNING_PARAMS):
        stage = f"tuning_{index:02d}"
        path = checkpoint_root / f"{stage}.joblib"
        payload = _stage_payload(path, state, stage)
        if payload is None:
            state.start(stage, params=params, sampleRows={"train": len(y_tune_train), "validation": len(y_tune_validation)})
            started = time.perf_counter()
            model = _fit_lgbm(
                _classifier(params, config.seed + index, config.lightgbm_estimators, config.training_threads),
                x_tune_train, y_tune_train, tune_weights, x_tune_validation, y_tune_validation,
                config.tuning_early_stopping_rounds, stage,
            )
            metrics, threshold = _model_metrics(model, x_tune_validation, y_tune_validation)
            payload = {
                "params": params,
                "metrics": metrics,
                "threshold": threshold,
                "bestIteration": int(model.best_iteration_ or config.lightgbm_estimators),
                "sampleRows": {"train": len(y_tune_train), "validation": len(y_tune_validation)},
                "elapsedSeconds": time.perf_counter() - started,
                "model": model,
            }
            atomic_joblib(path, payload)
            state.complete(stage, elapsedSeconds=payload["elapsedSeconds"], bestIteration=payload["bestIteration"])
        tuning_results.append({key: value for key, value in payload.items() if key != "model"})
        tuning_progress.update(index + 1, f"AUPRC={payload['metrics']['auprc']:.4f}; best_iteration={payload['bestIteration']}")
        payload = None
        model = None
    tuning_progress.finish()
    best = max(tuning_results, key=lambda item: item["metrics"]["auprc"])
    state.complete("tuning", bestParams=best["params"], bestIteration=best["bestIteration"], results=tuning_results)
    del x_tune_train, x_tune_validation, y_tune_train, y_tune_validation, tune_weights
    gc.collect()

    development_indices = partition_indices["developmentTrain"]
    validation_indices = partition_indices["tuningValidation"]
    x_development = cache.features[development_indices]
    y_development = np.asarray(cache.labels[development_indices], dtype=np.int8)
    x_validation = cache.features[validation_indices]
    y_validation = np.asarray(cache.labels[validation_indices], dtype=np.int8)
    development_weights = _balanced_weights(y_development)
    baseline_specs = [
        ("Prior Dummy", lambda: DummyClassifier(strategy="prior"), False),
        ("Linear Logistic (SGD)", lambda: SGDClassifier(
            loss="log_loss", penalty="l2", alpha=1e-4, max_iter=20, tol=None,
            class_weight="balanced", average=True, random_state=config.seed, n_jobs=config.training_threads,
        ), False),
        ("Complement Naive Bayes", lambda: ComplementNB(alpha=1.0), False),
        ("LightGBM", lambda: _classifier(best["params"], config.seed, best["bestIteration"], config.training_threads), True),
    ]
    baseline_rows = []
    baseline_payloads = {}
    baseline_progress = ProgressReporter("full-development-baselines", len(baseline_specs))
    for index, (name, factory, weighted) in enumerate(baseline_specs):
        stage = f"baseline_{index:02d}"
        path = checkpoint_root / f"{stage}.joblib"
        payload = _stage_payload(path, state, stage)
        if payload is None:
            state.start(stage, modelName=name, trainingRows=len(y_development), validationRows=len(y_validation))
            started = time.perf_counter()
            model = factory()
            if weighted:
                _fit_lgbm(
                    model, x_development, y_development, development_weights,
                    progress_label="baseline-lightgbm", early_stopping=None,
                )
            else:
                model.fit(x_development, y_development)
            metrics, threshold = _model_metrics(model, x_validation, y_validation)
            payload = {"name": name, "model": model, "metrics": metrics, "threshold": threshold, "elapsedSeconds": time.perf_counter() - started}
            atomic_joblib(path, payload)
            state.complete(stage, modelName=name, elapsedSeconds=payload["elapsedSeconds"], metrics=metrics)
        baseline_payloads[name] = payload
        baseline_rows.append({"model": name, "trainingRows": len(y_development), "validationRows": len(y_validation), "fastMode": False, **payload["metrics"]})
        baseline_progress.update(index + 1, f"{name}; AUPRC={payload['metrics']['auprc']:.4f}")
        payload = None
        model = None
    baseline_progress.finish()
    staged_report_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(baseline_rows).to_csv(staged_report_root / "lightgbm_baselines.csv", index=False)
    state.complete("baselines", models=[row["model"] for row in baseline_rows])
    selected_threshold = float(baseline_payloads["LightGBM"]["threshold"])
    del x_development, y_development, x_validation, y_validation, development_weights, baseline_payloads
    gc.collect()

    final_indices = partition_indices["finalFit"]
    x_final = cache.features[final_indices]
    y_final = np.asarray(cache.labels[final_indices], dtype=np.int8)
    final_weights = _balanced_weights(y_final)
    final_path = checkpoint_root / "final_model.joblib"
    final_payload = _stage_payload(final_path, state, "final_model")
    if final_payload is None:
        state.start("final_model", rows=len(y_final), bestIteration=best["bestIteration"])
        progress = ProgressReporter("final-lightgbm-full-data", 1)
        started = time.perf_counter()
        final_model = _classifier(best["params"], config.seed, best["bestIteration"], config.training_threads)
        _fit_lgbm(final_model, x_final, y_final, final_weights, progress_label="final-lightgbm", early_stopping=None)
        final_payload = {"model": final_model, "elapsedSeconds": time.perf_counter() - started, "rows": len(y_final)}
        atomic_joblib(final_path, final_payload)
        state.complete("final_model", elapsedSeconds=final_payload["elapsedSeconds"], rows=len(y_final), bestIteration=best["bestIteration"])
        progress.update(1, f"rows={len(y_final):,}")
        progress.finish()
    final_model = final_payload["model"]
    del final_weights
    gc.collect()

    calibration_indices = partition_indices["calibration"]
    x_calibration = cache.features[calibration_indices]
    y_calibration = np.asarray(cache.labels[calibration_indices], dtype=np.int8)
    calibration_path = checkpoint_root / "calibration.joblib"
    calibration_payload = _stage_payload(calibration_path, state, "calibration")
    if calibration_payload is None:
        state.start("calibration", rows=len(y_calibration), cohort="2025Q3")
        raw_calibration = _probability(final_model, x_calibration)
        calibrator = IsotonicRegression(out_of_bounds="clip").fit(raw_calibration, y_calibration)
        calibrated = calibrator.predict(raw_calibration)
        report = {
            "cohort": "2025Q3", "method": "isotonic", "fastMode": False,
            "brierBefore": float(np.mean((raw_calibration - y_calibration) ** 2)),
            "brierAfter": float(np.mean((calibrated - y_calibration) ** 2)),
            "eceBefore": expected_calibration_error(y_calibration, raw_calibration),
            "eceAfter": expected_calibration_error(y_calibration, calibrated),
        }
        fraction_positive, mean_predicted = calibration_curve(y_calibration, calibrated, n_bins=10, strategy="quantile")
        report["reliabilityPlotData"] = [
            {"meanPredicted": float(x), "fractionPositive": float(y)}
            for x, y in zip(mean_predicted, fraction_positive)
        ]
        calibration_payload = {"calibrator": calibrator, "report": report}
        atomic_joblib(calibration_path, calibration_payload)
        state.complete("calibration", report=report)
    calibrator = calibration_payload["calibrator"]
    atomic_json(staged_report_root / "calibration_metrics.json", calibration_payload["report"])

    caseids = np.asarray(cache.caseids[final_indices], dtype=np.int64)
    if len(np.unique(caseids)) != len(caseids):
        raise RuntimeError("Final-fit cohort contains duplicate CASEIDs; row-level bootstrap would violate the CASEID bootstrap contract.")
    state.complete("bootstrap_unit_audit", rows=len(caseids), uniqueCaseIds=len(caseids))
    replica_root = run_root / "bootstrap"
    replica_root.mkdir(parents=True, exist_ok=True)
    pending = _pending_bootstrap_indices(state, replica_root, config.bootstrap_replicas)
    bootstrap_progress = ProgressReporter("caseid-bootstrap", max(1, len(pending)))
    completed_now = 0
    for index in range(config.bootstrap_replicas):
        stage = f"bootstrap_{index:02d}"
        artifact_path = replica_root / f"replica_{index:02d}.joblib"
        if state.is_complete(stage) and artifact_path.exists():
            print(f"[{stage}] resumed from checkpoint", flush=True)
            continue
        state.start(stage, replica=index + 1, total=config.bootstrap_replicas)
        started = time.perf_counter()
        multiplicities = _bootstrap_multiplicities(len(y_final), config.seed + index + 1)
        weights = _balanced_weights(y_final, multiplicities)
        del multiplicities
        replica = _classifier(best["params"], config.seed + index + 1, best["bestIteration"], config.training_threads)
        _fit_lgbm(replica, x_final, y_final, weights, progress_label=stage, early_stopping=None)
        del weights
        replica_calibrator = IsotonicRegression(out_of_bounds="clip").fit(_probability(replica, x_calibration), y_calibration)
        payload = {"model": replica, "calibrator": replica_calibrator, "bootstrapUnit": "CASEID", "seed": config.seed + index + 1}
        atomic_joblib(artifact_path, payload)
        elapsed = time.perf_counter() - started
        state.complete(stage, elapsedSeconds=elapsed, seed=config.seed + index + 1)
        completed_now += 1
        bootstrap_progress.update(completed_now, f"overall replica {index + 1}/{config.bootstrap_replicas}")
        payload = None
        replica = None
        gc.collect()
    bootstrap_progress.finish(f"replicas={config.bootstrap_replicas}")
    bootstrap_report = {
        "version": BOOTSTRAP_VERSION,
        "replicas": config.bootstrap_replicas,
        "resamplingUnit": "CASEID",
        "implementation": "deterministic row-index multiplicities passed as sample weights; feature rows are never copied",
        "intervalLevel": 0.90,
        "lowerPercentile": 5,
        "upperPercentile": 95,
        "fastMode": False,
    }
    atomic_json(staged_report_root / "bootstrap_summary.json", bootstrap_report)
    state.complete("bootstrap", replicas=config.bootstrap_replicas)

    conformal_path = staged_report_root / "conformal_metrics.json"
    temporal_path = staged_report_root / "final_temporal_evaluation.json"
    if state.is_complete("temporal_evaluation") and conformal_path.exists() and temporal_path.exists():
        print("[temporal_evaluation] resumed from checkpoint", flush=True)
        conformal_report = json.loads(conformal_path.read_text(encoding="utf-8"))
        temporal_report = json.loads(temporal_path.read_text(encoding="utf-8"))
        q_hat = float(conformal_report["qHat"])
        holdout_metrics = temporal_report["lightgbm"]
        holdout_conformal = temporal_report["conformal"]
    else:
        state.start("temporal_evaluation", conformalCohort="2025Q4", holdout="2026Q1-2026Q2")
        conformal_indices = partition_indices["conformal"]
        holdout_indices = partition_indices["holdout"]
        x_conformal = cache.features[conformal_indices]
        y_conformal = np.asarray(cache.labels[conformal_indices], dtype=np.int8)
        conformal_probabilities = calibrator.predict(_probability(final_model, x_conformal))
        q_hat = conformal_quantile(conformal_probabilities, y_conformal, config.conformal_alpha)
        del x_conformal, y_conformal, conformal_probabilities
        x_holdout = cache.features[holdout_indices]
        y_holdout = np.asarray(cache.labels[holdout_indices], dtype=np.int8)
        calibrated_holdout = calibrator.predict(_probability(final_model, x_holdout))
        holdout_metrics = binary_metrics(y_holdout, calibrated_holdout, selected_threshold)
        holdout_conformal = conformal_metrics(calibrated_holdout, y_holdout, q_hat)
        conformal_report = {
            "version": CONFORMAL_VERSION,
            "calibrationCohort": "2025Q4",
            "alpha": config.conformal_alpha,
            "targetCoverage": 1.0 - config.conformal_alpha,
            "qHat": q_hat,
            "holdout2026": holdout_conformal,
            "fastMode": False,
        }
        temporal_report = {"lightgbm": holdout_metrics, "conformal": holdout_conformal, "holdoutRows": len(y_holdout), "fastMode": False}
        atomic_json(conformal_path, conformal_report)
        atomic_json(temporal_path, temporal_report)
        state.complete("temporal_evaluation", qHat=q_hat, holdoutRows=len(y_holdout), metrics=holdout_metrics, conformal=holdout_conformal)

    serious_payload = {
        "featureBuilder": cache.builder,
        "model": final_model,
        "calibrator": calibrator,
        "qHat": q_hat,
        "threshold": selected_threshold,
        "versions": {
            "preprocessing": PREPROCESSING_VERSION,
            "features": FEATURE_SCHEMA_VERSION,
            "lightgbm": LIGHTGBM_VERSION,
            "bootstrap": BOOTSTRAP_VERSION,
            "conformal": CONFORMAL_VERSION,
        },
        "dataWindow": {"fit": "2022Q1-2025Q2", "calibration": "2025Q3", "conformal": "2025Q4", "holdout": "2026Q1-2026Q2"},
        "fastMode": False,
    }
    staged_serious = run_root / "serious_outcome.joblib"
    atomic_joblib(staged_serious, serious_payload)
    runtime_manifest = {
        "pipelineVersion": TRAINING_PIPELINE_VERSION,
        "python": sys.version,
        "platform": platform.platform(),
        "lightgbm": lgb.__version__,
        "scikitLearn": sklearn.__version__,
        "config": asdict(config),
        "fastMode": False,
        "fullFinalData": True,
        "input": input_identity,
        "inputLocation": processed_input_location(cohort_path),
        "temporalRows": partition_counts,
        "tuningSubset": {"developmentTrain": len(tuning_train_indices), "tuningValidation": len(tuning_validation_indices)},
        "tuning": tuning_results,
        "featureBuilder": cache.builder.metadata(),
        "featureCache": {key: value for key, value in cache.metadata.items() if key != "identity"},
        "gitCommit": _git_commit(),
        "completedAt": utc_now(),
    }
    staged_manifest = run_root / "training_manifest.json"
    atomic_json(staged_manifest, runtime_manifest)
    atomic_json(staged_report_root / "lightgbm_metrics.json", {"validationTuning": tuning_results, "holdout2026": holdout_metrics, "fastMode": False})
    state.complete("staged_final_artifacts")
    assert_input_identity(cohort_path, input_identity)

    _promote_file(staged_serious, ARTIFACT_ROOT / "serious_outcome.joblib")
    _promote_file(staged_manifest, ARTIFACT_ROOT / "training_manifest.json")
    for index in range(config.bootstrap_replicas):
        _promote_file(replica_root / f"replica_{index:02d}.joblib", ARTIFACT_ROOT / "bootstrap" / f"replica_{index:02d}.joblib")
    for report_path in staged_report_root.iterdir():
        _promote_file(report_path, REPORT_ROOT / report_path.name)
    state.complete("promoted", artifacts=config.bootstrap_replicas + 2)
    print("[training] FULL artifacts promoted atomically; no fast-mode fallback occurred", flush=True)
    return {
        "mode": "FULL",
        "runKey": run_key,
        "temporalRows": partition_counts,
        "baselines": baseline_rows,
        "holdout": holdout_metrics,
        "conformal": conformal_report,
        "bootstrap": bootstrap_report,
    }


def _benchmark_sample(cohort_path: Path, target_rows: int, batch_rows: int) -> tuple[pd.DataFrame, dict, dict, float]:
    started = time.perf_counter()
    parquet = pq.ParquetFile(cohort_path)
    counts: Counter = Counter()
    quarter_counts: Counter = Counter()
    row_group_quarters: dict[int, set[str]] = {}
    for row_group in range(parquet.metadata.num_row_groups):
        quarter_frame = parquet.read_row_group(row_group, columns=["quarter"]).to_pandas()
        quarters = set(str(value) for value in quarter_frame["quarter"].unique())
        row_group_quarters[row_group] = quarters
        quarter_counts.update(str(value) for value in quarter_frame["quarter"])
        if all(quarter > "2025Q4" for quarter in quarters):
            continue
        # The label column is never loaded for a row group containing only the
        # untouched 2026 holdout.
        for batch in parquet.iter_batches(row_groups=[row_group], batch_size=batch_rows, columns=["quarter", "has_serious_outcome"]):
            frame = batch.to_pandas()
            frame = frame[frame["quarter"] <= "2025Q4"]
            counts.update(zip(frame["quarter"], frame["has_serious_outcome"].astype(int)))
    total = sum(counts.values())
    quotas = {key: max(2, int(round(target_rows * count / total))) for key, count in counts.items()}
    samples: dict[tuple[str, int], pd.DataFrame] = {}
    total_batches = sum(
        math.ceil(parquet.metadata.row_group(index).num_rows / batch_rows)
        for index in range(parquet.metadata.num_row_groups)
    )
    progress = ProgressReporter("benchmark-temporal-sample", total_batches)
    batch_index = 0
    for row_group in range(parquet.metadata.num_row_groups):
        row_group_batches = math.ceil(parquet.metadata.row_group(row_group).num_rows / batch_rows)
        if all(quarter > "2025Q4" for quarter in row_group_quarters[row_group]):
            batch_index += row_group_batches
            progress.update(batch_index, "2026 row group skipped before loading labels/features")
            continue
        for batch in parquet.iter_batches(row_groups=[row_group], batch_size=batch_rows, columns=CACHE_COLUMNS):
            batch_index += 1
            frame = batch.to_pandas()
            frame["_hash"] = pd.util.hash_pandas_object(frame["caseid"].astype(str), index=False).to_numpy(dtype=np.uint64)
            for key, group in frame.groupby(["quarter", "has_serious_outcome"], sort=False):
                key = (str(key[0]), int(key[1]))
                combined = pd.concat([samples[key], group], ignore_index=True) if key in samples else group
                samples[key] = combined.nsmallest(quotas[key], "_hash")
            progress.update(batch_index, f"retained={sum(len(value) for value in samples.values()):,}")
    sample = pd.concat(samples.values(), ignore_index=True).drop(columns="_hash")
    progress.finish(f"sample rows={len(sample):,}")
    return (
        sample,
        {f"{quarter}:{label}": count for (quarter, label), count in sorted(counts.items())},
        dict(sorted(quarter_counts.items())),
        time.perf_counter() - started,
    )


def benchmark_lightgbm(cohort_path: Path, config: TrainConfig, sample_rows: int | None = None) -> dict:
    ensure_output_directories()
    input_identity = processed_input_identity(cohort_path)
    requested_rows = int(sample_rows or config.benchmark_rows)
    if requested_rows < 20_000:
        raise ValueError("Benchmark sample must contain at least 20,000 rows for temporal/class coverage")
    with PeakMemoryMonitor() as memory:
        sample, stratum_counts, quarter_counts, scan_seconds = _benchmark_sample(cohort_path, requested_rows, config.cache_batch_rows)
        development = sample[(sample["quarter"] >= "2022Q1") & (sample["quarter"] <= "2024Q4")].reset_index(drop=True)
        tuning_validation = sample[(sample["quarter"] >= "2025Q1") & (sample["quarter"] <= "2025Q2")].reset_index(drop=True)
        final_fit = sample[(sample["quarter"] >= "2022Q1") & (sample["quarter"] <= "2025Q2")].reset_index(drop=True)
        calibration = sample[sample["quarter"] == "2025Q3"].reset_index(drop=True)
        required = {"development": development, "tuningValidation": tuning_validation, "finalFit": final_fit, "calibration": calibration}
        empty = [name for name, frame in required.items() if frame.empty or frame["has_serious_outcome"].nunique() < 2]
        if empty:
            raise RuntimeError(f"Benchmark sample lacks required temporal/class coverage: {', '.join(empty)}")
        builder = FeatureBuilder(config).fit(development)
        transform_started = time.perf_counter()
        matrix = builder.transform(sample)
        transform_seconds = time.perf_counter() - transform_started
        masks = {
            "development": (sample["quarter"] >= "2022Q1") & (sample["quarter"] <= "2024Q4"),
            "tuningValidation": (sample["quarter"] >= "2025Q1") & (sample["quarter"] <= "2025Q2"),
            "finalFit": (sample["quarter"] >= "2022Q1") & (sample["quarter"] <= "2025Q2"),
            "calibration": sample["quarter"] == "2025Q3",
        }
        positions = {name: np.flatnonzero(mask.to_numpy()) for name, mask in masks.items()}
        x_dev = matrix[positions["development"]]
        y_dev = sample.loc[masks["development"], "has_serious_outcome"].to_numpy(dtype=np.int8)
        x_val = matrix[positions["tuningValidation"]]
        y_val = sample.loc[masks["tuningValidation"], "has_serious_outcome"].to_numpy(dtype=np.int8)
        benchmark_estimators = min(200, config.lightgbm_estimators)
        fit_started = time.perf_counter()
        model = _fit_lgbm(
            _classifier(TUNING_PARAMS[0], config.seed, benchmark_estimators, config.training_threads),
            x_dev, y_dev, _balanced_weights(y_dev), x_val, y_val,
            min(20, config.tuning_early_stopping_rounds), "benchmark-lightgbm",
        )
        lightgbm_seconds = time.perf_counter() - fit_started
        best_iteration = int(model.best_iteration_ or benchmark_estimators)
        metrics, _ = _model_metrics(model, x_val, y_val)
        baseline_timings = {}
        for name, baseline in (
            ("Linear Logistic (SGD)", SGDClassifier(loss="log_loss", max_iter=5, tol=None, class_weight="balanced", average=True, random_state=config.seed, n_jobs=config.training_threads)),
            ("Complement Naive Bayes", ComplementNB(alpha=1.0)),
        ):
            baseline_started = time.perf_counter()
            baseline.fit(x_dev, y_dev)
            baseline_timings[name] = time.perf_counter() - baseline_started
        x_final = matrix[positions["finalFit"]]
        y_final = sample.loc[masks["finalFit"], "has_serious_outcome"].to_numpy(dtype=np.int8)
        x_calibration = matrix[positions["calibration"]]
        y_calibration = sample.loc[masks["calibration"], "has_serious_outcome"].to_numpy(dtype=np.int8)
        bootstrap_started = time.perf_counter()
        multiplicities = _bootstrap_multiplicities(len(y_final), config.seed + 1)
        replica = _classifier(TUNING_PARAMS[0], config.seed + 1, best_iteration, config.training_threads)
        _fit_lgbm(
            replica, x_final, y_final, _balanced_weights(y_final, multiplicities),
            progress_label="benchmark-bootstrap", early_stopping=None,
        )
        IsotonicRegression(out_of_bounds="clip").fit(_probability(replica, x_calibration), y_calibration)
        bootstrap_seconds = time.perf_counter() - bootstrap_started

    parquet_rows = pq.ParquetFile(cohort_path).metadata.num_rows
    partition_counts = {}
    for name, (start, end) in PARTITIONS.items():
        partition_counts[name] = sum(count for quarter, count in quarter_counts.items() if start <= quarter <= end)
    # stratum_counts are full-corpus counts collected during the benchmark scan.
    tune_ratio = config.tuning_train_rows / max(len(y_dev), 1)
    projected_iterations = max(best_iteration, config.lightgbm_estimators // 2)
    iteration_ratio = projected_iterations / benchmark_estimators
    validation_model_seconds = lightgbm_seconds * (partition_counts["developmentTrain"] / max(len(y_dev), 1)) * iteration_ratio
    final_model_seconds = lightgbm_seconds * (partition_counts["finalFit"] / max(len(y_dev), 1)) * iteration_ratio
    tuning_seconds = lightgbm_seconds * tune_ratio * len(TUNING_PARAMS) * iteration_ratio
    baseline_seconds = sum(baseline_timings.values()) * (partition_counts["developmentTrain"] / max(len(y_dev), 1)) * 4
    cache_seconds = scan_seconds + transform_seconds * (parquet_rows / max(len(sample), 1))
    bootstrap_total_seconds = bootstrap_seconds * (partition_counts["finalFit"] / max(len(y_final), 1)) * config.bootstrap_replicas * (projected_iterations / max(best_iteration, 1))
    likely_seconds = cache_seconds + tuning_seconds + baseline_seconds + validation_model_seconds + final_model_seconds + bootstrap_total_seconds
    nnz_per_row = matrix.nnz / max(matrix.shape[0], 1)
    sparse_bytes = parquet_rows * nnz_per_row * (4 + 4) + (parquet_rows + 1) * 8
    estimated_peak_bytes = max(memory.peak_bytes, int(1.5 * 1024**3 + sparse_bytes * 4.0))
    approved = estimated_peak_bytes <= int(12.5 * 1024**3)
    report = {
        "pipelineVersion": TRAINING_PIPELINE_VERSION,
        "benchmarkMode": True,
        "createdAt": utc_now(),
        "input": input_identity,
        "inputLocation": processed_input_location(cohort_path),
        "config": asdict(config),
        "sampleRows": len(sample),
        "fullRows": parquet_rows,
        "sampleTemporalRows": {name: len(frame) for name, frame in required.items()},
        "fullTemporalRows": partition_counts,
        "featureCount": matrix.shape[1],
        "nnzPerRow": nnz_per_row,
        "timingsSeconds": {
            "fullCohortScanAndSampling": scan_seconds,
            "sampleFeatureTransform": transform_seconds,
            "sampleLightGBM": lightgbm_seconds,
            "sampleWeightedBootstrapReplica": bootstrap_seconds,
            "sampleBaselines": baseline_timings,
        },
        "benchmarkLightGBM": {
            "estimators": benchmark_estimators,
            "bestIteration": best_iteration,
            "projectedFullIterations": projected_iterations,
            "metrics": metrics,
        },
        "measuredPeakRamGB": memory.peak_bytes / 1024**3,
        "estimatedFullPeakRamGB": estimated_peak_bytes / 1024**3,
        "estimatedFullRuntime": {
            "lower": format_duration(likely_seconds * 0.75),
            "likely": format_duration(likely_seconds),
            "upper": format_duration(likely_seconds * 3.0),
            "method": "hardware benchmark extrapolation by rows, fitted iterations and configured replicas; estimate, not a guarantee",
        },
        "approvedForFullRun": approved,
        "scientificGuards": {
            "fullFinalFitRequired": True,
            "tuningSubsetOnly": True,
            "holdout2026UsedForTraining": False,
            "silentFastFallback": False,
        },
    }
    atomic_json(REPORT_ROOT / "lightgbm_benchmark.json", report)
    markdown = "# LightGBM laptop benchmark\n\n"
    markdown += f"- Immutable cohort rows: **{parquet_rows:,}**\n- Benchmark rows: **{len(sample):,}**\n"
    markdown += f"- Measured benchmark peak RAM: **{report['measuredPeakRamGB']:.2f} GB**\n- Estimated full peak RAM: **{report['estimatedFullPeakRamGB']:.2f} GB**\n"
    markdown += f"- Estimated runtime: **{report['estimatedFullRuntime']['likely']}** (range {report['estimatedFullRuntime']['lower']}–{report['estimatedFullRuntime']['upper']})\n"
    markdown += f"- Full-run RAM gate: **{'PASS' if approved else 'BLOCKED'}**\n\n"
    markdown += "The benchmark uses a deterministic quarter/class-representative subset only for timing and tuning. Final training is required to use every 2022Q1–2025Q2 row. Calibration remains 2025Q3, conformal calibration remains 2025Q4, and 2026Q1–Q2 remains untouched until final evaluation. No fast-mode fallback is permitted.\n"
    (REPORT_ROOT / "lightgbm_benchmark.md").write_text(markdown, encoding="utf-8")
    assert_input_identity(cohort_path, input_identity)
    return report
