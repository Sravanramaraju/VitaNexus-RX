from __future__ import annotations

import hashlib

import numpy as np

from vitanexus_ml.models.hgnn_evaluation import (
    global_candidates,
    global_threshold_sweep,
    multilabel_decision_metrics,
    probability_metrics,
    optimize_per_label_thresholds,
)


DEFAULT_STABILITY_SEED = 20260824


def deterministic_group_folds(
    caseids,
    *,
    folds: int = 5,
    seed: int = DEFAULT_STABILITY_SEED,
) -> np.ndarray:
    """Assign a CASEID to one deterministic fold without splitting duplicate cases."""
    if folds < 2:
        raise ValueError("At least two stability folds are required")
    values = np.asarray(caseids)
    result = np.empty(len(values), dtype=np.int8)
    memo: dict[bytes, int] = {}
    prefix = f"{seed}:".encode("ascii")
    for index, raw in enumerate(values):
        value = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
        value = value.rstrip(b"\x00")
        if value not in memo:
            digest = hashlib.sha256(prefix + value).digest()
            memo[value] = int.from_bytes(digest[:8], "big") % folds
        result[index] = memo[value]
    return result


def global_threshold_stability(
    targets,
    probabilities,
    fold_assignments,
    *,
    step: float = 0.001,
) -> dict:
    y = np.asarray(targets)
    p = np.asarray(probabilities)
    assignments = np.asarray(fold_assignments)
    rows = []
    for fold in sorted(np.unique(assignments).tolist()):
        train = assignments != fold
        test = ~train
        selected = global_candidates(global_threshold_sweep(y[train], p[train], step=step))["G1MaximumMicroF1"]
        metrics = multilabel_decision_metrics(y[test], p[test], selected["threshold"])
        rows.append({"fold": int(fold), "selectedThreshold": selected["threshold"], "heldOut": metrics})
    thresholds = np.asarray([row["selectedThreshold"] for row in rows])
    return {
        "folds": rows,
        "summary": {
            "meanThreshold": float(thresholds.mean()),
            "medianThreshold": float(np.median(thresholds)),
            "standardDeviationThreshold": float(thresholds.std()),
            "rangeThreshold": float(thresholds.max() - thresholds.min()),
            **{
                f"{name}Mean": float(np.mean([row["heldOut"][name] for row in rows]))
                for name in ("microF1", "macroF1", "microPrecision", "microRecall")
            },
            **{
                f"{name}StandardDeviation": float(np.std([row["heldOut"][name] for row in rows]))
                for name in ("microF1", "macroF1", "microPrecision", "microRecall")
            },
        },
    }


def stable_per_label_thresholds(
    targets,
    probabilities,
    vocabulary: list[dict],
    fold_assignments,
    *,
    global_threshold: float,
    minimum_support: int,
    maximum_standard_deviation: float = 0.075,
    maximum_range: float = 0.15,
) -> tuple[np.ndarray, list[dict], dict]:
    """Select per-label thresholds using fold medians and conservative shrinkage."""
    y = np.asarray(targets)
    p = np.asarray(probabilities)
    assignments = np.asarray(fold_assignments)
    fold_values: list[np.ndarray] = []
    fold_precision: list[np.ndarray] = []
    fold_recall: list[np.ndarray] = []
    fold_f1: list[np.ndarray] = []
    for fold in sorted(np.unique(assignments).tolist()):
        train = assignments != fold
        test = ~train
        values, _ = optimize_per_label_thresholds(
            y[train], p[train], vocabulary,
            global_threshold=global_threshold,
            minimum_support=max(1, int(minimum_support * float(train.mean()))),
        )
        fold_values.append(values)
        predictions = p[test] >= values[None, :]
        labels = y[test].astype(bool)
        tp = np.logical_and(predictions, labels).sum(axis=0)
        fp = np.logical_and(predictions, ~labels).sum(axis=0)
        fn = np.logical_and(~predictions, labels).sum(axis=0)
        precision = np.divide(tp, tp + fp, out=np.zeros_like(tp, dtype=float), where=(tp + fp) > 0)
        recall = np.divide(tp, tp + fn, out=np.zeros_like(tp, dtype=float), where=(tp + fn) > 0)
        f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(precision), where=(precision + recall) > 0)
        fold_precision.append(precision)
        fold_recall.append(recall)
        fold_f1.append(f1)
    matrix = np.vstack(fold_values)
    precision_matrix = np.vstack(fold_precision)
    recall_matrix = np.vstack(fold_recall)
    f1_matrix = np.vstack(fold_f1)
    thresholds = np.full(y.shape[1], float(global_threshold), dtype=np.float64)
    rows = []
    for index, item in enumerate(vocabulary):
        support = int(y[:, index].sum())
        values = matrix[:, index]
        standard_deviation = float(values.std())
        value_range = float(values.max() - values.min())
        fallback = None
        if support < minimum_support or support == len(y):
            selected = float(global_threshold)
            fallback = "global threshold: insufficient positive or negative support"
        else:
            median = float(np.median(values))
            if standard_deviation > maximum_standard_deviation or value_range > maximum_range:
                selected = float((median + global_threshold) / 2.0)
                fallback = "50% shrinkage toward global threshold: unstable resampling estimate"
            else:
                selected = median
        thresholds[index] = selected
        rows.append({
            "index": index,
            "term": item["term"],
            "support": support,
            "prevalence": float(y[:, index].mean()),
            "threshold": selected,
            "foldThresholds": [float(value) for value in values],
            "meanThreshold": float(values.mean()),
            "medianThreshold": float(np.median(values)),
            "standardDeviationThreshold": standard_deviation,
            "rangeThreshold": value_range,
            "heldOutPrecisionByFold": [float(value) for value in precision_matrix[:, index]],
            "heldOutRecallByFold": [float(value) for value in recall_matrix[:, index]],
            "heldOutF1ByFold": [float(value) for value in f1_matrix[:, index]],
            "meanHeldOutPrecision": float(precision_matrix[:, index].mean()),
            "standardDeviationHeldOutPrecision": float(precision_matrix[:, index].std()),
            "meanHeldOutRecall": float(recall_matrix[:, index].mean()),
            "standardDeviationHeldOutRecall": float(recall_matrix[:, index].std()),
            "meanHeldOutF1": float(f1_matrix[:, index].mean()),
            "standardDeviationHeldOutF1": float(f1_matrix[:, index].std()),
            "fallback": fallback,
        })
    return thresholds, rows, {
        "foldCount": int(matrix.shape[0]),
        "minimumSupport": int(minimum_support),
        "maximumStandardDeviation": maximum_standard_deviation,
        "maximumRange": maximum_range,
        "fallbackLabels": int(sum(row["fallback"] is not None for row in rows)),
    }


def local_threshold_sensitivity(targets, probabilities, threshold: float) -> list[dict]:
    values = sorted(set(max(0.0, min(1.0, threshold + delta)) for delta in (-0.005, -0.001, 0, 0.001, 0.005)))
    quality = probability_metrics(targets, probabilities)
    return [{"threshold": value, **quality, **multilabel_decision_metrics(targets, probabilities, value)} for value in values]
