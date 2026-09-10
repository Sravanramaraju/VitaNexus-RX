from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pyarrow.parquet as pq

from vitanexus_ml.conformal.split import conformal_metrics, conformal_quantile
from vitanexus_ml.models.metrics import operating_metrics, select_specificity_threshold
from vitanexus_ml.training_runtime import atomic_json, atomic_replace


OPERATING_THRESHOLD_VERSION = "faers-calibrated-operating-threshold-1.0.0"
SENSITIVITY_SCENARIOS = (0.92, 0.90, 0.89, 0.88, 0.85)


def assert_operating_cohort_is_pre_holdout(quarters, *, required_quarter: str = "2025Q4") -> None:
    values = {str(value) for value in np.asarray(quarters).tolist()}
    if not values:
        raise ValueError("Operating-threshold cohort is empty")
    if any(value >= "2026Q1" for value in values):
        raise ValueError("The locked 2026 holdout cannot participate in threshold selection")
    if values != {required_quarter}:
        raise ValueError(
            f"Operating-threshold selection requires only {required_quarter}; observed {sorted(values)}"
        )


def deterministic_group_stratified_split(
    labels,
    group_ids,
    *,
    selection_fraction: float = 0.5,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Split groups into disjoint conformal and threshold-selection positions."""
    labels = np.asarray(labels, dtype=np.int8)
    group_ids = np.asarray(group_ids).astype(str)
    if labels.ndim != 1 or group_ids.ndim != 1 or len(labels) != len(group_ids):
        raise ValueError("Labels and group IDs must be equally sized one-dimensional arrays")
    if not 0.0 < selection_fraction < 1.0:
        raise ValueError("Selection fraction must be in (0, 1)")
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError("Both classes are required before cohort partitioning")

    group_labels: dict[str, int] = {}
    for group_id, label in zip(group_ids, labels):
        previous = group_labels.setdefault(group_id, int(label))
        if previous != int(label):
            raise ValueError(f"Group {group_id} spans multiple target classes")

    selection_groups: set[str] = set()
    for label in (0, 1):
        members = [group_id for group_id, group_label in group_labels.items() if group_label == label]
        if len(members) < 2:
            raise ValueError("Each class requires at least two groups for a disjoint split")
        ordered = sorted(
            members,
            key=lambda value: hashlib.sha256(f"{seed}:{value}".encode("utf-8")).digest(),
        )
        count = min(len(ordered) - 1, max(1, int(round(len(ordered) * selection_fraction))))
        selection_groups.update(ordered[:count])

    selection_mask = np.fromiter((value in selection_groups for value in group_ids), dtype=bool)
    selection_positions = np.flatnonzero(selection_mask)
    conformal_positions = np.flatnonzero(~selection_mask)
    if np.intersect1d(selection_positions, conformal_positions).size:
        raise RuntimeError("Conformal and threshold-selection cohorts overlap")
    if set(np.unique(labels[selection_positions])) != {0, 1} or set(np.unique(labels[conformal_positions])) != {0, 1}:
        raise RuntimeError("Disjoint cohorts did not retain both target classes")
    return conformal_positions.astype(np.int64), selection_positions.astype(np.int64)


def _class_counts(labels) -> dict:
    labels = np.asarray(labels, dtype=np.int8)
    negative = int(np.sum(labels == 0))
    positive = int(np.sum(labels == 1))
    return {"negative": negative, "positive": positive, "total": negative + positive}


def evaluate_calibrated_operating_threshold(
    *,
    pool_labels,
    pool_probabilities,
    pool_caseids,
    pool_quarters,
    holdout_labels,
    holdout_probabilities,
    legacy_threshold: float,
    seed: int,
    selection_fraction: float = 0.5,
    sensitivity_constraint: float = 0.90,
    threshold_step: float = 0.001,
) -> tuple[dict, list[dict]]:
    """Select on pre-holdout calibrated scores and evaluate once on holdout."""
    assert_operating_cohort_is_pre_holdout(pool_quarters)
    pool_labels = np.asarray(pool_labels, dtype=np.int8)
    pool_probabilities = np.asarray(pool_probabilities, dtype=float)
    holdout_labels = np.asarray(holdout_labels, dtype=np.int8)
    holdout_probabilities = np.asarray(holdout_probabilities, dtype=float)
    conformal_positions, selection_positions = deterministic_group_stratified_split(
        pool_labels,
        pool_caseids,
        selection_fraction=selection_fraction,
        seed=seed,
    )
    selection_labels = pool_labels[selection_positions]
    selection_probabilities = pool_probabilities[selection_positions]
    selected, sweep = select_specificity_threshold(
        selection_labels,
        selection_probabilities,
        sensitivity_floor=sensitivity_constraint,
        probability_scale="calibrated",
        step=threshold_step,
    )
    scenarios = {}
    for floor in SENSITIVITY_SCENARIOS:
        scenario, _ = select_specificity_threshold(
            selection_labels,
            selection_probabilities,
            sensitivity_floor=floor,
            probability_scale="calibrated",
            step=threshold_step,
        )
        scenarios[f"sensitivityAtLeast{int(round(floor * 100))}"] = scenario

    conformal_labels = pool_labels[conformal_positions]
    conformal_probabilities = pool_probabilities[conformal_positions]
    q_hat = conformal_quantile(conformal_probabilities, conformal_labels, alpha=0.10)
    legacy_selection = operating_metrics(selection_labels, selection_probabilities, legacy_threshold)
    legacy_holdout = operating_metrics(holdout_labels, holdout_probabilities, legacy_threshold)
    selected_holdout = operating_metrics(holdout_labels, holdout_probabilities, selected["threshold"])
    report = {
        "experimentVersion": OPERATING_THRESHOLD_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "methodology": "maximum specificity subject to sensitivity >= 0.90 on calibrated probabilities",
        "probabilityCalibration": "isotonic",
        "probabilityScale": "calibrated",
        "sensitivityConstraint": float(sensitivity_constraint),
        "thresholdSweep": {"lower": 0.0, "upper": 1.0, "step": float(threshold_step), "rows": len(sweep)},
        "cohortAllocation": {
            "source": "2025Q4",
            "groupKey": "CASEID",
            "method": "deterministic class-stratified SHA-256 group ordering",
            "seed": int(seed),
            "selectionFraction": float(selection_fraction),
            "conformal": {"rows": len(conformal_positions), "classCounts": _class_counts(conformal_labels)},
            "operatingThreshold": {"rows": len(selection_positions), "classCounts": _class_counts(selection_labels)},
            "overlapRows": int(np.intersect1d(conformal_positions, selection_positions).size),
        },
        "selection": {
            "holdoutUsedForSelection": False,
            "selectedOperatingPoint": selected,
            "legacyOperatingPoint": legacy_selection,
            "comparisonScenarios": scenarios,
        },
        "conformal": {
            "calibrationSubset": "2025Q4 deterministic conformal half",
            "targetCoverage": 0.90,
            "qHat": float(q_hat),
            "holdout2026": conformal_metrics(holdout_probabilities, holdout_labels, q_hat),
        },
        "lockedHoldout2026": {
            "usedForThresholdSelection": False,
            "rows": len(holdout_labels),
            "classCounts": _class_counts(holdout_labels),
            "legacyThreshold": legacy_holdout,
            "frozenSelectedThreshold": selected_holdout,
            "specificityPercentagePointImprovement": float(
                100.0 * (selected_holdout["specificity"] - legacy_holdout["specificity"])
            ),
        },
        "metricSemantics": {
            "thresholdDependent": [
                "recallSensitivity", "specificity", "precision", "f1", "accuracy",
                "balancedAccuracy", "negativePredictiveValue", "confusionMatrix",
            ],
            "thresholdIndependent": ["auroc", "auprc", "brier", "ece", "calibrated probabilities"],
        },
    }
    return report, sweep


def _write_threshold_sweep(path: Path, sweep: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    fields = [
        "threshold", "recallSensitivity", "specificity", "precision", "f1", "accuracy",
        "balancedAccuracy", "negativePredictiveValue", "tn", "fp", "fn", "tp",
        "auroc", "auprc", "brier", "ece",
    ]
    with temporary.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for row in sweep:
            writer.writerow({
                **{key: row[key] for key in fields if key not in {"tn", "fp", "fn", "tp"}},
                **row["confusionMatrix"],
            })
    atomic_replace(temporary, path)


def optimize_existing_lightgbm_threshold(
    *,
    cohort_path: Path,
    serious_artifact_path: Path,
    report_root: Path,
    seed: int,
    sensitivity_constraint: float = 0.90,
    threshold_step: float = 0.001,
) -> dict:
    """Evaluate an existing frozen LightGBM without retraining or mutating it."""
    artifact = joblib.load(serious_artifact_path)
    if artifact.get("fastMode"):
        raise RuntimeError("Operating-threshold optimization requires the full LightGBM artifact")
    expected_windows = {"calibration": "2025Q3", "conformal": "2025Q4", "holdout": "2026Q1-2026Q2"}
    if any(artifact.get("dataWindow", {}).get(key) != value for key, value in expected_windows.items()):
        raise RuntimeError("LightGBM artifact temporal windows do not match the locked evaluation design")

    columns = pq.ParquetFile(cohort_path).schema.names
    pool = pq.read_table(cohort_path, columns=columns, filters=[("quarter", "=", "2025Q4")]).to_pandas()
    holdout = pq.read_table(
        cohort_path,
        columns=columns,
        filters=[("quarter", ">=", "2026Q1"), ("quarter", "<=", "2026Q2")],
    ).to_pandas()
    builder = artifact["featureBuilder"]
    model = artifact["model"]
    calibrator = artifact["calibrator"]
    pool_probabilities = calibrator.predict(model.predict_proba(builder.transform(pool))[:, 1])
    holdout_probabilities = calibrator.predict(model.predict_proba(builder.transform(holdout))[:, 1])
    report, sweep = evaluate_calibrated_operating_threshold(
        pool_labels=pool["has_serious_outcome"].to_numpy(dtype=np.int8),
        pool_probabilities=pool_probabilities,
        pool_caseids=pool["caseid"].astype(str).to_numpy(),
        pool_quarters=pool["quarter"].astype(str).to_numpy(),
        holdout_labels=holdout["has_serious_outcome"].to_numpy(dtype=np.int8),
        holdout_probabilities=holdout_probabilities,
        legacy_threshold=float(artifact.get("threshold", 0.35)),
        seed=seed,
        sensitivity_constraint=sensitivity_constraint,
        threshold_step=threshold_step,
    )
    report_root.mkdir(parents=True, exist_ok=True)
    report_path = report_root / "lightgbm_operating_threshold.json"
    sweep_path = report_root / "lightgbm_threshold_sweep.csv"
    report["thresholdSweep"]["artifact"] = sweep_path.name
    atomic_json(report_path, report)
    _write_threshold_sweep(sweep_path, sweep)
    return {"report": str(report_path), "sweep": str(sweep_path), **report}
