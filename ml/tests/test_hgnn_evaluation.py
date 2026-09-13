import numpy as np
import pytest

from vitanexus_ml.models.hgnn_evaluation import (
    apply_thresholds,
    global_candidates,
    global_threshold_sweep,
    multilabel_metrics,
    optimize_per_label_thresholds,
    per_label_metrics,
    precision_recall_frontier,
    top_k_metrics,
)


VOCABULARY = [
    {"term": "alpha", "index": 0},
    {"term": "beta", "index": 1},
    {"term": "gamma", "index": 2},
]


def test_multilabel_metrics_and_per_label_prevalence_lift():
    targets = np.array([[1, 0, 1], [0, 1, 0], [1, 0, 0], [0, 1, 1]], dtype=np.int8)
    probabilities = np.array([[0.9, 0.1, 0.8], [0.2, 0.7, 0.1], [0.6, 0.2, 0.4], [0.1, 0.8, 0.9]])
    metrics = multilabel_metrics(targets, probabilities, 0.5)
    assert metrics["microF1"] == pytest.approx(1.0)
    assert metrics["macroF1"] == pytest.approx(1.0)
    assert metrics["hammingLoss"] == 0.0
    assert metrics["averageActualLabelsPerCase"] == 1.5
    assert metrics["averagePredictedLabelsPerCase"] == 1.5
    rows = per_label_metrics(targets, probabilities, VOCABULARY)
    assert rows[0]["prevalence"] == 0.5
    assert rows[0]["auprcLiftOverPrevalence"] == pytest.approx(2.0)


def test_global_threshold_search_and_frontier_are_deterministic():
    targets = np.array([[1, 0], [1, 0], [0, 1], [0, 1]], dtype=np.int8)
    probabilities = np.array([[0.20, 0.01], [0.30, 0.02], [0.10, 0.25], [0.05, 0.35]])
    first = global_threshold_sweep(targets, probabilities, step=0.01)
    second = global_threshold_sweep(targets, probabilities, step=0.01)
    assert first == second
    candidates = global_candidates(first)
    assert candidates["G1MaximumMicroF1"]["threshold"] == pytest.approx(0.20)
    assert candidates["G1MaximumMicroF1"]["microF1"] == pytest.approx(1.0)
    frontier = precision_recall_frontier(first)
    assert frontier
    assert all(row["microPrecision"] >= row["minimumPrecision"] for row in frontier)


def test_per_label_thresholds_use_global_fallback_for_rare_labels():
    targets = np.array([[1, 0], [0, 0], [0, 0], [0, 1], [0, 1]], dtype=np.int8)
    probabilities = np.array([[0.2, 0.1], [0.1, 0.2], [0.05, 0.1], [0.1, 0.4], [0.1, 0.5]])
    thresholds, rows = optimize_per_label_thresholds(
        targets,
        probabilities,
        [{"term": "rare", "index": 0}, {"term": "supported", "index": 1}],
        global_threshold=0.3,
        minimum_support=2,
    )
    assert thresholds[0] == 0.3
    assert rows[0]["fallback"] == "global threshold: insufficient support"
    assert thresholds[1] == pytest.approx(0.4)
    assert apply_thresholds(probabilities, thresholds).shape == targets.shape


def test_top_k_metrics_use_ranked_predictions():
    targets = np.array([[1, 0, 1], [0, 1, 0]], dtype=np.int8)
    probabilities = np.array([[0.9, 0.1, 0.8], [0.2, 0.7, 0.1]])
    metrics = top_k_metrics(targets, probabilities, values=(1, 2))
    assert metrics["precisionAt1"] == 1.0
    assert metrics["hitAt1"] == 1.0
    assert metrics["recallAt2"] == 1.0
    assert metrics["meanAveragePrecision"] == 1.0
