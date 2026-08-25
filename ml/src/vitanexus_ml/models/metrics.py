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


def bootstrap_interval(probabilities: np.ndarray, level: float = 0.90) -> tuple[float, float]:
    values = np.asarray(probabilities, dtype=float)
    if values.size == 0:
        raise ValueError("At least one bootstrap probability is required")
    tail = (1.0 - level) / 2.0
    return float(np.quantile(values, tail)), float(np.quantile(values, 1.0 - tail))
