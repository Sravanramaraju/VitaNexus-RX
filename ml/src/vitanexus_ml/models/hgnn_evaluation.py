from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    hamming_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)


@dataclass(frozen=True)
class ThresholdChoice:
    threshold: float
    f1: float
    precision: float
    recall: float


def _arrays(targets, probabilities) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(targets, dtype=np.int8)
    p = np.asarray(probabilities, dtype=np.float64)
    if y.ndim != 2 or p.ndim != 2 or y.shape != p.shape:
        raise ValueError("HGNN targets and probabilities must be equally shaped two-dimensional arrays")
    if y.size == 0 or not np.isin(y, (0, 1)).all():
        raise ValueError("HGNN targets must be a non-empty binary matrix")
    if not np.isfinite(p).all() or np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("HGNN probabilities must be finite and within [0, 1]")
    return y, p


def apply_thresholds(probabilities, thresholds) -> np.ndarray:
    p = np.asarray(probabilities, dtype=np.float64)
    values = np.asarray(thresholds, dtype=np.float64)
    if values.ndim == 0:
        values = np.full(p.shape[1], float(values))
    if values.shape != (p.shape[1],):
        raise ValueError("Thresholds must be scalar or contain exactly one value per ADR label")
    if np.any((values < 0.0) | (values > 1.0)):
        raise ValueError("Thresholds must be within [0, 1]")
    return p >= values[None, :]


def expected_calibration_error(targets, probabilities, bins: int = 15) -> float:
    y = np.asarray(targets, dtype=np.int8).ravel()
    p = np.asarray(probabilities, dtype=np.float64).ravel()
    edges = np.linspace(0.0, 1.0, bins + 1)
    indexes = np.minimum(np.digitize(p, edges[1:-1], right=False), bins - 1)
    result = 0.0
    for index in range(bins):
        mask = indexes == index
        if mask.any():
            result += float(mask.mean()) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(result)


def multilabel_metrics(targets, probabilities, thresholds=0.5) -> dict:
    y, p = _arrays(targets, probabilities)
    predictions = apply_thresholds(p, thresholds)
    positives = y.sum(axis=0)
    valid_ap = positives > 0
    valid_auc = valid_ap & (positives < len(y))
    true_positive = int(np.logical_and(predictions, y == 1).sum())
    false_positive = int(np.logical_and(predictions, y == 0).sum())
    false_negative = int(np.logical_and(~predictions, y == 1).sum())
    true_negative = int(np.logical_and(~predictions, y == 0).sum())
    return {
        "microAUPRC": float(average_precision_score(y, p, average="micro")),
        "macroAUPRC": float(average_precision_score(y[:, valid_ap], p[:, valid_ap], average="macro")),
        "microAUROC": float(roc_auc_score(y, p, average="micro")),
        "macroAUROC": float(roc_auc_score(y[:, valid_auc], p[:, valid_auc], average="macro")),
        "microF1": float(f1_score(y, predictions, average="micro", zero_division=0)),
        "macroF1": float(f1_score(y, predictions, average="macro", zero_division=0)),
        "weightedF1": float(f1_score(y, predictions, average="weighted", zero_division=0)),
        "microPrecision": float(precision_score(y, predictions, average="micro", zero_division=0)),
        "macroPrecision": float(precision_score(y, predictions, average="macro", zero_division=0)),
        "microRecall": float(recall_score(y, predictions, average="micro", zero_division=0)),
        "macroRecall": float(recall_score(y, predictions, average="macro", zero_division=0)),
        "hammingLoss": float(hamming_loss(y, predictions)),
        "averageActualLabelsPerCase": float(y.sum(axis=1).mean()),
        "averagePredictedLabelsPerCase": float(predictions.sum(axis=1).mean()),
        "brier": float(np.mean((p - y) ** 2)),
        "ece": expected_calibration_error(y, p),
        "confusion": {
            "truePositive": true_positive,
            "falsePositive": false_positive,
            "falseNegative": false_negative,
            "trueNegative": true_negative,
        },
    }


def per_label_metrics(targets, probabilities, vocabulary: list[dict], thresholds=0.5) -> list[dict]:
    y, p = _arrays(targets, probabilities)
    predictions = apply_thresholds(p, thresholds)
    rows = []
    for index, item in enumerate(vocabulary):
        labels = y[:, index]
        scores = p[:, index]
        predicted = predictions[:, index]
        support = int(labels.sum())
        both = 0 < support < len(labels)
        rows.append({
            "index": index,
            "term": item["term"],
            "support": support,
            "negatives": int(len(labels) - support),
            "prevalence": float(labels.mean()),
            "auprc": float(average_precision_score(labels, scores)) if support else None,
            "auroc": float(roc_auc_score(labels, scores)) if both else None,
            "precision": float(precision_score(labels, predicted, zero_division=0)),
            "recall": float(recall_score(labels, predicted, zero_division=0)),
            "f1": float(f1_score(labels, predicted, zero_division=0)),
            "threshold": float(np.asarray(thresholds).reshape(-1)[index]) if np.asarray(thresholds).ndim else float(thresholds),
            "auprcLiftOverPrevalence": float(average_precision_score(labels, scores) / labels.mean()) if support else None,
        })
    return rows


def score_distributions(targets, probabilities, vocabulary: list[dict]) -> list[dict]:
    y, p = _arrays(targets, probabilities)
    rows = []
    quantile_points = [0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0]
    for index, item in enumerate(vocabulary):
        labels = y[:, index].astype(bool)
        scores = p[:, index]
        positive = scores[labels]
        negative = scores[~labels]
        rows.append({
            "index": index,
            "term": item["term"],
            "positives": int(labels.sum()),
            "negatives": int((~labels).sum()),
            "prevalence": float(labels.mean()),
            "positiveMean": float(positive.mean()) if len(positive) else None,
            "negativeMean": float(negative.mean()) if len(negative) else None,
            "positiveMedian": float(np.median(positive)) if len(positive) else None,
            "negativeMedian": float(np.median(negative)) if len(negative) else None,
            "scoreQuantiles": {str(value): float(result) for value, result in zip(quantile_points, np.quantile(scores, quantile_points))},
            "positiveQuantiles": {str(value): float(result) for value, result in zip((0.5, 0.9, 0.95, 0.99), np.quantile(positive, (0.5, 0.9, 0.95, 0.99)))} if len(positive) else {},
            "negativeQuantiles": {str(value): float(result) for value, result in zip((0.5, 0.9, 0.95, 0.99), np.quantile(negative, (0.5, 0.9, 0.95, 0.99)))} if len(negative) else {},
            "proportionAbovePointFive": float((scores >= 0.5).mean()),
        })
    return rows


def _counts_at_thresholds(labels: np.ndarray, scores: np.ndarray, thresholds: np.ndarray) -> tuple[np.ndarray, ...]:
    order = np.argsort(scores, kind="stable")
    ordered_labels = labels[order].astype(np.int64)
    cumulative = np.concatenate(([0], np.cumsum(ordered_labels)))
    starts = np.searchsorted(scores[order], thresholds, side="left")
    total_positive = int(ordered_labels.sum())
    predicted = len(labels) - starts
    true_positive = total_positive - cumulative[starts]
    false_positive = predicted - true_positive
    false_negative = total_positive - true_positive
    true_negative = len(labels) - total_positive - false_positive
    return true_positive, false_positive, false_negative, true_negative


def global_threshold_sweep(targets, probabilities, *, step: float = 0.001) -> list[dict]:
    y, p = _arrays(targets, probabilities)
    if step <= 0.0 or step > 1.0:
        raise ValueError("Threshold step must be within (0, 1]")
    thresholds = np.unique(np.append(np.arange(0.0, 1.0 + step / 2.0, step), 1.0))
    totals = [np.zeros(len(thresholds), dtype=np.int64) for _ in range(4)]
    macro_precision = np.zeros(len(thresholds), dtype=np.float64)
    macro_recall = np.zeros(len(thresholds), dtype=np.float64)
    macro_f1 = np.zeros(len(thresholds), dtype=np.float64)
    for index in range(y.shape[1]):
        counts = _counts_at_thresholds(y[:, index], p[:, index], thresholds)
        for total, values in zip(totals, counts):
            total += values
        tp, fp, fn, _ = counts
        precision = np.divide(tp, tp + fp, out=np.zeros_like(tp, dtype=float), where=(tp + fp) > 0)
        recall = np.divide(tp, tp + fn, out=np.zeros_like(tp, dtype=float), where=(tp + fn) > 0)
        label_f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(precision), where=(precision + recall) > 0)
        macro_precision += precision
        macro_recall += recall
        macro_f1 += label_f1
    tp, fp, fn, tn = totals
    micro_precision = np.divide(tp, tp + fp, out=np.zeros_like(tp, dtype=float), where=(tp + fp) > 0)
    micro_recall = np.divide(tp, tp + fn, out=np.zeros_like(tp, dtype=float), where=(tp + fn) > 0)
    micro_f1 = np.divide(2 * micro_precision * micro_recall, micro_precision + micro_recall, out=np.zeros_like(micro_precision), where=(micro_precision + micro_recall) > 0)
    labels = y.shape[1]
    rows = []
    for index, threshold in enumerate(thresholds):
        rows.append({
            "threshold": float(threshold),
            "microF1": float(micro_f1[index]),
            "macroF1": float(macro_f1[index] / labels),
            "microPrecision": float(micro_precision[index]),
            "macroPrecision": float(macro_precision[index] / labels),
            "microRecall": float(micro_recall[index]),
            "macroRecall": float(macro_recall[index] / labels),
            "hammingLoss": float((fp[index] + fn[index]) / y.size),
            "averagePredictedLabelsPerCase": float((tp[index] + fp[index]) / len(y)),
            "confusion": {
                "truePositive": int(tp[index]), "falsePositive": int(fp[index]),
                "falseNegative": int(fn[index]), "trueNegative": int(tn[index]),
            },
        })
    return rows


def global_candidates(sweep: list[dict]) -> dict:
    if not sweep:
        raise ValueError("Threshold sweep is empty")
    micro = max(sweep, key=lambda row: (row["microF1"], row["macroF1"], row["microPrecision"], row["threshold"]))
    macro = max(sweep, key=lambda row: (row["macroF1"], row["microF1"], row["microPrecision"], row["threshold"]))
    defensible = [row for row in sweep if row["microPrecision"] >= 0.25]
    recall = max(defensible or sweep, key=lambda row: (row["microRecall"], row["microF1"], row["threshold"]))
    balanced = max(sweep, key=lambda row: (min(row["microPrecision"], row["microRecall"]), row["microF1"], row["threshold"]))
    return {"G1MaximumMicroF1": micro, "G2MaximumMacroF1": macro, "G3RecallAtDefensiblePrecision": recall, "G4BalancedPrecisionRecall": balanced}


def precision_recall_frontier(sweep: list[dict], levels=(0.60, 0.50, 0.40, 0.30, 0.25)) -> list[dict]:
    rows = []
    for level in levels:
        eligible = [row for row in sweep if row["microPrecision"] >= level]
        if eligible:
            selected = max(eligible, key=lambda row: (row["microRecall"], row["microF1"], row["threshold"]))
            rows.append({"minimumPrecision": float(level), **selected})
    return rows


def _best_binary_threshold(labels: np.ndarray, scores: np.ndarray, fallback: float) -> ThresholdChoice:
    if labels.sum() == 0:
        return ThresholdChoice(float(fallback), 0.0, 0.0, 0.0)
    order = np.argsort(-scores, kind="stable")
    ordered_labels = labels[order].astype(np.int64)
    tp = np.cumsum(ordered_labels)
    fp = np.cumsum(1 - ordered_labels)
    distinct = np.r_[scores[order][1:] != scores[order][:-1], True]
    positions = np.flatnonzero(distinct)
    tp, fp = tp[positions], fp[positions]
    fn = int(labels.sum()) - tp
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(precision), where=(precision + recall) > 0)
    best = max(range(len(positions)), key=lambda index: (f1[index], precision[index], scores[order][positions[index]]))
    return ThresholdChoice(
        float(scores[order][positions[best]]), float(f1[best]), float(precision[best]), float(recall[best])
    )


def optimize_per_label_thresholds(
    targets,
    probabilities,
    vocabulary: list[dict],
    *,
    global_threshold: float,
    minimum_support: int,
) -> tuple[np.ndarray, list[dict]]:
    y, p = _arrays(targets, probabilities)
    thresholds = np.full(y.shape[1], float(global_threshold), dtype=np.float64)
    rows = []
    for index, item in enumerate(vocabulary):
        support = int(y[:, index].sum())
        choice = _best_binary_threshold(y[:, index], p[:, index], global_threshold)
        fallback = support < minimum_support or support == len(y)
        if not fallback:
            thresholds[index] = choice.threshold
        rows.append({
            "index": index,
            "term": item["term"],
            "support": support,
            "prevalence": float(y[:, index].mean()),
            "threshold": float(thresholds[index]),
            "unshrunkOptimalThreshold": choice.threshold,
            "precision": choice.precision if not fallback else None,
            "recall": choice.recall if not fallback else None,
            "f1": choice.f1 if not fallback else None,
            "fallback": "global threshold: insufficient support" if fallback else None,
        })
    return thresholds, rows


def top_k_metrics(targets, probabilities, values=(1, 3, 5)) -> dict:
    y, p = _arrays(targets, probabilities)
    actual = y.sum(axis=1)
    positive_cases = actual > 0
    result = {}
    for k in values:
        if k <= 0 or k > y.shape[1]:
            raise ValueError("Top-k values must be between one and the number of labels")
        indexes = np.argpartition(-p, kth=k - 1, axis=1)[:, :k]
        hits = np.take_along_axis(y, indexes, axis=1).sum(axis=1)
        result[f"precisionAt{k}"] = float((hits / k).mean())
        result[f"recallAt{k}"] = float(np.divide(hits, actual, out=np.zeros_like(hits, dtype=float), where=actual > 0).mean())
        result[f"hitAt{k}"] = float((hits[positive_cases] > 0).mean()) if positive_cases.any() else 0.0
    average_precisions = []
    for row in np.flatnonzero(positive_cases):
        order = np.argsort(-p[row], kind="stable")
        relevant = y[row, order]
        cumulative = np.cumsum(relevant)
        ranks = np.arange(1, len(relevant) + 1)
        average_precisions.append(float(((cumulative / ranks) * relevant).sum() / actual[row]))
    result["meanAveragePrecision"] = float(np.mean(average_precisions)) if average_precisions else 0.0
    result["positiveCases"] = int(positive_cases.sum())
    return result
