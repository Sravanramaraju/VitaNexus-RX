import numpy as np
import pytest

from vitanexus_ml.models.metrics import operating_metrics, select_specificity_threshold, threshold_sweep


def test_operating_metrics_include_requested_confusion_derived_values():
    labels = np.array([0, 0, 0, 1, 1, 1])
    probabilities = np.array([0.1, 0.4, 0.8, 0.3, 0.7, 0.9])
    result = operating_metrics(labels, probabilities, 0.5)
    assert result["confusionMatrix"] == {"tn": 2, "fp": 1, "fn": 1, "tp": 2}
    assert result["accuracy"] == pytest.approx(4 / 6)
    assert result["balancedAccuracy"] == pytest.approx(2 / 3)
    assert result["negativePredictiveValue"] == pytest.approx(2 / 3)


def test_specificity_selection_enforces_sensitivity_before_specificity():
    labels = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    calibrated = np.array([0.1, 0.2, 0.4, 0.8, 0.3, 0.6, 0.7, 0.9])
    selected, sweep = select_specificity_threshold(
        labels,
        calibrated,
        sensitivity_floor=0.75,
        probability_scale="calibrated",
        step=0.001,
    )
    assert selected["recallSensitivity"] >= 0.75
    assert selected["threshold"] == pytest.approx(0.599)
    assert selected["specificity"] == pytest.approx(0.75)
    assert all(row["threshold"] <= 1.0 for row in sweep)


def test_specificity_selection_rejects_raw_or_unspecified_probability_scale():
    labels = np.array([0, 0, 1, 1])
    probabilities = np.array([0.1, 0.2, 0.8, 0.9])
    with pytest.raises(ValueError, match="calibrated probabilities"):
        select_specificity_threshold(labels, probabilities, sensitivity_floor=0.9, probability_scale="raw")
    with pytest.raises(TypeError):
        select_specificity_threshold(labels, probabilities, sensitivity_floor=0.9)


def test_threshold_sweep_requires_both_classes_and_fine_resolution():
    with pytest.raises(ValueError, match="both binary classes"):
        threshold_sweep(np.ones(4), np.full(4, 0.5))
    with pytest.raises(ValueError, match="step"):
        threshold_sweep(np.array([0, 1]), np.array([0.2, 0.8]), step=0.01)
