from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score


def expected_calibration_error(labels, probabilities, bins: int = 10) -> float:
    labels = np.asarray(labels)
    probabilities = np.asarray(probabilities)
    edges = np.linspace(0.0, 1.0, bins + 1)
    result = 0.0
    for lower, upper in zip(edges[:-1], edges[1:]):
        mask = (probabilities >= lower) & (probabilities < upper if upper < 1 else probabilities <= upper)
        if mask.any():
            result += mask.mean() * abs(labels[mask].mean() - probabilities[mask].mean())
    return float(result)


def select_threshold(labels, probabilities) -> float:
    candidates = np.linspace(0.05, 0.95, 91)
    scores = [(f1_score(labels, probabilities >= threshold, zero_division=0), threshold) for threshold in candidates]
    return float(max(scores, key=lambda item: (item[0], -item[1]))[1])


def binary_metrics(labels, probabilities, threshold: float) -> dict:
    labels = np.asarray(labels, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    predictions = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "auroc": float(roc_auc_score(labels, probabilities)),
        "auprc": float(average_precision_score(labels, probabilities)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recallSensitivity": float(recall_score(labels, predictions, zero_division=0)),
        "specificity": float(tn / (tn + fp)) if tn + fp else None,
        "brier": float(brier_score_loss(labels, probabilities)),
        "ece": expected_calibration_error(labels, probabilities),
        "threshold": float(threshold),
        "confusionMatrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def operating_metrics(labels, probabilities, threshold: float) -> dict:
    """Return threshold-dependent and probability-level binary metrics."""
    metrics = binary_metrics(labels, probabilities, threshold)
    matrix = metrics["confusionMatrix"]
    tn, fp, fn, tp = (matrix[key] for key in ("tn", "fp", "fn", "tp"))
    total = tn + fp + fn + tp
    negative_predictions = tn + fn
    specificity = metrics["specificity"]
    sensitivity = metrics["recallSensitivity"]
    metrics.update({
        "accuracy": float((tp + tn) / total) if total else None,
        "balancedAccuracy": float((sensitivity + specificity) / 2.0) if sensitivity is not None and specificity is not None else None,
        "negativePredictiveValue": float(tn / negative_predictions) if negative_predictions else None,
    })
    return metrics


def threshold_sweep(
    labels,
    probabilities,
    *,
    lower: float = 0.0,
    upper: float = 1.0,
    step: float = 0.001,
) -> list[dict]:
    """Evaluate a deterministic threshold grid without changing probabilities."""
    labels = np.asarray(labels, dtype=np.int8)
    probabilities = np.asarray(probabilities, dtype=float)
    if labels.ndim != 1 or probabilities.ndim != 1 or len(labels) != len(probabilities):
        raise ValueError("Labels and probabilities must be equally sized one-dimensional arrays")
    if not len(labels) or set(np.unique(labels)) != {0, 1}:
        raise ValueError("Threshold selection requires both binary classes")
    if not np.isfinite(probabilities).all() or np.any((probabilities < 0.0) | (probabilities > 1.0)):
        raise ValueError("Probabilities must be finite values in [0, 1]")
    if not 0.0 <= lower < upper <= 1.0 or not 0.0 < step <= 0.001:
        raise ValueError("Threshold range must be within [0, 1] and step must be in (0, 0.001]")
    thresholds = np.round(np.minimum(np.arange(lower, upper + step / 2.0, step, dtype=float), upper), 12)
    order = np.argsort(probabilities, kind="stable")
    sorted_probabilities = probabilities[order]
    sorted_labels = labels[order]
    cumulative_positive = np.concatenate(([0], np.cumsum(sorted_labels == 1, dtype=np.int64)))
    cumulative_negative = np.concatenate(([0], np.cumsum(sorted_labels == 0, dtype=np.int64)))
    positions = np.searchsorted(sorted_probabilities, thresholds, side="left")
    fn_values = cumulative_positive[positions]
    tn_values = cumulative_negative[positions]
    total_positive = int(cumulative_positive[-1])
    total_negative = int(cumulative_negative[-1])
    tp_values = total_positive - fn_values
    fp_values = total_negative - tn_values
    auroc = float(roc_auc_score(labels, probabilities))
    auprc = float(average_precision_score(labels, probabilities))
    brier = float(brier_score_loss(labels, probabilities))
    ece = expected_calibration_error(labels, probabilities)
    rows = []
    for threshold, tn, fp, fn, tp in zip(thresholds, tn_values, fp_values, fn_values, tp_values):
        tn, fp, fn, tp = map(int, (tn, fp, fn, tp))
        sensitivity = float(tp / total_positive)
        specificity = float(tn / total_negative)
        precision = float(tp / (tp + fp)) if tp + fp else 0.0
        negative_predictions = tn + fn
        f1 = float(2 * precision * sensitivity / (precision + sensitivity)) if precision + sensitivity else 0.0
        rows.append({
            "auroc": auroc,
            "auprc": auprc,
            "f1": f1,
            "precision": precision,
            "recallSensitivity": sensitivity,
            "specificity": specificity,
            "brier": brier,
            "ece": ece,
            "threshold": float(threshold),
            "confusionMatrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
            "accuracy": float((tp + tn) / len(labels)),
            "balancedAccuracy": float((sensitivity + specificity) / 2.0),
            "negativePredictiveValue": float(tn / negative_predictions) if negative_predictions else None,
        })
    return rows


def select_specificity_threshold(
    labels,
    probabilities,
    *,
    sensitivity_floor: float = 0.90,
    probability_scale: str,
    lower: float = 0.0,
    upper: float = 1.0,
    step: float = 0.001,
) -> tuple[dict, list[dict]]:
    """Maximize specificity while enforcing sensitivity on calibrated scores."""
    if probability_scale != "calibrated":
        raise ValueError("Operating-threshold selection requires calibrated probabilities")
    if not 0.0 < sensitivity_floor <= 1.0:
        raise ValueError("Sensitivity floor must be in (0, 1]")
    sweep = threshold_sweep(labels, probabilities, lower=lower, upper=upper, step=step)
    eligible = [row for row in sweep if row["recallSensitivity"] >= sensitivity_floor]
    if not eligible:
        raise RuntimeError(f"No threshold satisfies sensitivity >= {sensitivity_floor:.3f}")

    best_specificity = max(row["specificity"] for row in eligible)
    finalists = [row for row in eligible if np.isclose(row["specificity"], best_specificity, rtol=0.0, atol=1e-12)]
    positions = {round(row["threshold"], 12): index for index, row in enumerate(sweep)}

    def stability(row: dict) -> float:
        index = positions[round(row["threshold"], 12)]
        neighbors = sweep[max(0, index - 1):min(len(sweep), index + 2)]
        return -max(
            abs(row[metric] - neighbor[metric])
            for neighbor in neighbors
            for metric in ("recallSensitivity", "specificity")
        )

    selected = max(
        finalists,
        key=lambda row: (
            row["recallSensitivity"],
            row["balancedAccuracy"],
            row["precision"],
            stability(row),
            row["threshold"],
        ),
    ).copy()
    selected["selectionRule"] = "maximum specificity subject to sensitivity floor"
    selected["sensitivityConstraint"] = float(sensitivity_floor)
    selected["probabilityScale"] = probability_scale
    selected["thresholdStep"] = float(step)
    selected["neighborStability"] = float(stability(selected))
    return selected, sweep


def bootstrap_interval(probabilities: np.ndarray, level: float = 0.90) -> tuple[float, float]:
    values = np.asarray(probabilities, dtype=float)
    if values.size == 0:
        raise ValueError("At least one bootstrap probability is required")
    tail = (1.0 - level) / 2.0
    return float(np.quantile(values, tail)), float(np.quantile(values, 1.0 - tail))
