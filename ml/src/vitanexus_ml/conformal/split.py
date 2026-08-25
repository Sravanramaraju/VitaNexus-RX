from __future__ import annotations

import math

import numpy as np

from vitanexus_ml.config import NO_SERIOUS, SERIOUS


def conformal_quantile(probabilities: np.ndarray, labels: np.ndarray, alpha: float = 0.10) -> float:
    probabilities = np.asarray(probabilities, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if len(labels) == 0:
        raise ValueError("Conformal calibration requires at least one observation")
    true_probabilities = np.where(labels == 1, probabilities, 1.0 - probabilities)
    scores = 1.0 - true_probabilities
    rank = min(len(scores), math.ceil((len(scores) + 1) * (1.0 - alpha)))
    return float(np.sort(scores)[rank - 1])


def prediction_set(probability: float, q_hat: float) -> list[str]:
    result = []
    if 1.0 - (1.0 - probability) <= q_hat:
        result.append(NO_SERIOUS)
    if 1.0 - probability <= q_hat:
        result.append(SERIOUS)
    return result


def conformal_metrics(probabilities: np.ndarray, labels: np.ndarray, q_hat: float) -> dict:
    sets = [prediction_set(float(value), q_hat) for value in probabilities]
    expected = [SERIOUS if value else NO_SERIOUS for value in labels]
    coverage = np.mean([target in values for target, values in zip(expected, sets)]) if sets else float("nan")
    sizes = np.array([len(values) for values in sets], dtype=float)
    metrics = {
        "empiricalCoverage": float(coverage),
        "averageSetSize": float(sizes.mean()),
        "singletonRate": float(np.mean(sizes == 1)),
        "ambiguousRate": float(np.mean(sizes == 2)),
        "emptyRate": float(np.mean(sizes == 0)),
    }
    for label, name in ((0, NO_SERIOUS), (1, SERIOUS)):
        indices = np.where(np.asarray(labels) == label)[0]
        metrics[f"classConditionalCoverage_{name}"] = float(np.mean([expected[index] in sets[index] for index in indices])) if len(indices) else None
    return metrics
