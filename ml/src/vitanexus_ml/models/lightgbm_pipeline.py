from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import sklearn
import xgboost
from lightgbm import LGBMClassifier
from sklearn.calibration import calibration_curve
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

from vitanexus_ml.config import (
    ARTIFACT_ROOT, BOOTSTRAP_VERSION, CONFORMAL_VERSION, FEATURE_SCHEMA_VERSION,
    LIGHTGBM_VERSION, PREPROCESSING_VERSION, REPORT_ROOT, TrainConfig, ensure_output_directories,
)
from vitanexus_ml.conformal.split import conformal_metrics, conformal_quantile
from vitanexus_ml.features.builder import FeatureBuilder
from vitanexus_ml.models.metrics import binary_metrics, expected_calibration_error, select_threshold


TUNING_PARAMS = [
    {"num_leaves": 31, "max_depth": -1, "min_child_samples": 30, "learning_rate": 0.05, "feature_fraction": 0.9, "bagging_fraction": 0.9, "lambda_l1": 0.0, "lambda_l2": 1.0},
    {"num_leaves": 63, "max_depth": 10, "min_child_samples": 50, "learning_rate": 0.04, "feature_fraction": 0.8, "bagging_fraction": 0.8, "lambda_l1": 0.1, "lambda_l2": 2.0},
    {"num_leaves": 24, "max_depth": 7, "min_child_samples": 75, "learning_rate": 0.07, "feature_fraction": 1.0, "bagging_fraction": 0.85, "lambda_l1": 0.0, "lambda_l2": 4.0},
]


def _quarter_mask(frame: pd.DataFrame, start: str, end: str):
    return (frame["quarter"] >= start) & (frame["quarter"] <= end)


def _classifier(params: dict, seed: int, *, estimators: int) -> LGBMClassifier:
    return LGBMClassifier(
        objective="binary", n_estimators=estimators, random_state=seed, n_jobs=-1,
        class_weight="balanced", verbosity=-1, deterministic=True, force_col_wise=True,
        **params,
    )


def _fit_lgbm(model, x_train, y_train, x_validation=None, y_validation=None):
    kwargs = {}
    if x_validation is not None and len(y_validation):
        kwargs = {"eval_set": [(x_validation, y_validation)], "callbacks": [lgb.early_stopping(40, verbose=False)]}
    return model.fit(x_train, y_train, **kwargs)


def _probability(model, matrix) -> np.ndarray:
    return np.asarray(model.predict_proba(matrix)[:, 1], dtype=float)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def train_lightgbm_pipeline(cohort_path: Path, *, fast: bool = False, config: TrainConfig | None = None) -> dict:
    config = config or TrainConfig()
    version_suffix = "-fast-smoke" if fast else ""
    ensure_output_directories()
    frame = pd.read_parquet(cohort_path)
    if frame.empty:
        raise RuntimeError("The processed FAERS cohort is empty")
    development_train = frame[_quarter_mask(frame, "2022Q1", "2024Q4")].reset_index(drop=True)
    tuning_validation = frame[_quarter_mask(frame, "2025Q1", "2025Q2")].reset_index(drop=True)
    final_fit = frame[_quarter_mask(frame, "2022Q1", "2025Q2")].reset_index(drop=True)
    calibration = frame[frame["quarter"] == "2025Q3"].reset_index(drop=True)
    conformal = frame[frame["quarter"] == "2025Q4"].reset_index(drop=True)
    holdout = frame[_quarter_mask(frame, "2026Q1", "2026Q2")].reset_index(drop=True)
    required = {"developmentTrain": development_train, "tuningValidation": tuning_validation, "calibration": calibration, "conformal": conformal, "holdout": holdout}
    empty = [name for name, values in required.items() if values.empty]
    if empty:
        raise RuntimeError(f"Temporal partitions are empty: {', '.join(empty)}")

    development_builder = FeatureBuilder(config).fit(development_train)
    x_development = development_builder.transform(development_train)
    y_development = development_train["has_serious_outcome"].to_numpy(dtype=int)
    x_tuning = development_builder.transform(tuning_validation)
    y_tuning = tuning_validation["has_serious_outcome"].to_numpy(dtype=int)
    estimators = 120 if fast else 800
    tuning_results = []
    for index, params in enumerate(TUNING_PARAMS[:1] if fast else TUNING_PARAMS):
        model = _fit_lgbm(_classifier(params, config.seed + index, estimators=estimators), x_development, y_development, x_tuning, y_tuning)
        probabilities = _probability(model, x_tuning)
        tuning_results.append({"params": params, "auprc": float(binary_metrics(y_tuning, probabilities, select_threshold(y_tuning, probabilities))["auprc"]), "bestIteration": int(model.best_iteration_ or estimators)})
    best = max(tuning_results, key=lambda item: item["auprc"])

    baseline_models = {
        "Logistic Regression": LogisticRegression(max_iter=500, class_weight="balanced", random_state=config.seed, n_jobs=-1),
        "Random Forest": RandomForestClassifier(n_estimators=50 if fast else 300, class_weight="balanced_subsample", min_samples_leaf=3, random_state=config.seed, n_jobs=-1),
        "XGBoost": XGBClassifier(n_estimators=80 if fast else 400, max_depth=6, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, eval_metric="logloss", random_state=config.seed, n_jobs=-1),
        "LightGBM": _classifier(best["params"], config.seed, estimators=best["bestIteration"]),
    }
    baseline_rows = []
    threshold_by_model = {}
    for name, model in baseline_models.items():
        model.fit(x_development, y_development)
        probabilities = _probability(model, x_tuning)
        threshold = select_threshold(y_tuning, probabilities)
        threshold_by_model[name] = threshold
        baseline_rows.append({"model": name, "fastMode": fast, **binary_metrics(y_tuning, probabilities, threshold)})
    pd.DataFrame(baseline_rows).to_csv(REPORT_ROOT / "lightgbm_baselines.csv", index=False)

    builder = FeatureBuilder(config).fit(final_fit)
    x_final = builder.transform(final_fit)
    y_final = final_fit["has_serious_outcome"].to_numpy(dtype=int)
    x_calibration = builder.transform(calibration)
    y_calibration = calibration["has_serious_outcome"].to_numpy(dtype=int)
    final_model = _classifier(best["params"], config.seed, estimators=best["bestIteration"])
    final_model.fit(x_final, y_final)
    raw_calibration = _probability(final_model, x_calibration)
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(raw_calibration, y_calibration)
    calibrated_calibration = calibrator.predict(raw_calibration)
    calibration_report = {
        "cohort": "2025Q3", "method": "isotonic", "fastMode": fast,
        "brierBefore": float(np.mean((raw_calibration - y_calibration) ** 2)),
        "brierAfter": float(np.mean((calibrated_calibration - y_calibration) ** 2)),
        "eceBefore": expected_calibration_error(y_calibration, raw_calibration),
        "eceAfter": expected_calibration_error(y_calibration, calibrated_calibration),
    }
    fraction_positive, mean_predicted = calibration_curve(y_calibration, calibrated_calibration, n_bins=10, strategy="quantile")
    calibration_report["reliabilityPlotData"] = [{"meanPredicted": float(x), "fractionPositive": float(y)} for x, y in zip(mean_predicted, fraction_positive)]
    _write_json(REPORT_ROOT / "calibration_metrics.json", calibration_report)

    replicas = 2 if fast else config.bootstrap_replicas
    bootstrap_models = []
    rng = np.random.default_rng(config.seed)
    unique_caseids = final_fit["caseid"].drop_duplicates().to_numpy()
    bootstrap_dir = ARTIFACT_ROOT / "bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    for index in range(replicas):
        artifact_path = bootstrap_dir / f"replica_{index:02d}.joblib"
        sampled_ids = rng.choice(unique_caseids, size=len(unique_caseids), replace=True)
        multiplicities = pd.Series(sampled_ids).value_counts()
        sampled = final_fit.merge(multiplicities.rename("_copies"), left_on="caseid", right_index=True)
        sampled = sampled.loc[sampled.index.repeat(sampled["_copies"])].drop(columns="_copies").reset_index(drop=True)
        replica = _classifier(best["params"], config.seed + index + 1, estimators=best["bestIteration"])
        replica.fit(builder.transform(sampled), sampled["has_serious_outcome"].to_numpy(dtype=int))
        replica_calibrator = IsotonicRegression(out_of_bounds="clip").fit(_probability(replica, x_calibration), y_calibration)
        payload = {"model": replica, "calibrator": replica_calibrator}
        joblib.dump(payload, artifact_path)
        bootstrap_models.append(payload)
    bootstrap_report = {"version": f"{BOOTSTRAP_VERSION}{version_suffix}", "replicas": replicas, "resamplingUnit": "CASEID", "intervalLevel": 0.90, "lowerPercentile": 5, "upperPercentile": 95, "fastMode": fast}
    _write_json(REPORT_ROOT / "bootstrap_summary.json", bootstrap_report)

    x_conformal = builder.transform(conformal)
    y_conformal = conformal["has_serious_outcome"].to_numpy(dtype=int)
    conformal_probabilities = calibrator.predict(_probability(final_model, x_conformal))
    q_hat = conformal_quantile(conformal_probabilities, y_conformal, config.conformal_alpha)

    x_holdout = builder.transform(holdout)
    y_holdout = holdout["has_serious_outcome"].to_numpy(dtype=int)
    raw_holdout = _probability(final_model, x_holdout)
    calibrated_holdout = calibrator.predict(raw_holdout)
    threshold = select_threshold(y_tuning, _probability(baseline_models["LightGBM"], x_tuning))
    holdout_metrics = binary_metrics(y_holdout, calibrated_holdout, threshold)
    holdout_conformal = conformal_metrics(calibrated_holdout, y_holdout, q_hat)
    conformal_report = {"version": f"{CONFORMAL_VERSION}{version_suffix}", "calibrationCohort": "2025Q4", "alpha": config.conformal_alpha, "targetCoverage": 1.0 - config.conformal_alpha, "qHat": q_hat, "holdout2026": holdout_conformal, "fastMode": fast}
    _write_json(REPORT_ROOT / "conformal_metrics.json", conformal_report)
    _write_json(REPORT_ROOT / "final_temporal_evaluation.json", {"lightgbm": holdout_metrics, "conformal": holdout_conformal, "holdoutRows": len(holdout), "fastMode": fast})

    artifact = {
        "featureBuilder": builder, "model": final_model, "calibrator": calibrator,
        "qHat": q_hat, "threshold": threshold,
        "versions": {"preprocessing": f"{PREPROCESSING_VERSION}{version_suffix}", "features": FEATURE_SCHEMA_VERSION, "lightgbm": f"{LIGHTGBM_VERSION}{version_suffix}", "bootstrap": f"{BOOTSTRAP_VERSION}{version_suffix}", "conformal": f"{CONFORMAL_VERSION}{version_suffix}"},
        "dataWindow": {"fit": "2022Q1-2025Q2", "calibration": "2025Q3", "conformal": "2025Q4", "holdout": "2026Q1-2026Q2"},
        "fastMode": fast,
    }
    joblib.dump(artifact, ARTIFACT_ROOT / "serious_outcome.joblib")
    runtime_manifest = {
        "python": sys.version, "platform": platform.platform(), "lightgbm": lgb.__version__, "xgboost": xgboost.__version__, "scikitLearn": sklearn.__version__,
        "config": asdict(config), "fastMode": fast, "temporalRows": {name: len(values) for name, values in required.items()}, "tuning": tuning_results,
        "featureBuilder": builder.metadata(), "gitCommit": _git_commit(),
    }
    _write_json(ARTIFACT_ROOT / "training_manifest.json", runtime_manifest)
    _write_json(REPORT_ROOT / "lightgbm_metrics.json", {"validationTuning": tuning_results, "holdout2026": holdout_metrics, "fastMode": fast})
    return {"baselines": baseline_rows, "calibration": calibration_report, "bootstrap": bootstrap_report, "conformal": conformal_report, "holdout": holdout_metrics}


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
