import joblib
import numpy as np

from vitanexus_ml.models.hgnn_calibration import (
    apply_calibration,
    calibration_diagnostics,
    choose_calibration,
    fit_calibration_candidates,
)


def test_calibration_candidates_are_serializable_and_preserve_shape(tmp_path):
    rng = np.random.default_rng(20260824)
    logits = rng.normal(size=(500, 3))
    probabilities = 1.0 / (1.0 + np.exp(-logits))
    targets = (rng.random((500, 3)) < np.array([0.3, 0.2, 0.1])).astype(np.int8)
    candidates = fit_calibration_candidates(targets, logits, probabilities, minimum_support=10)
    path = tmp_path / "calibrators.joblib"
    joblib.dump(candidates, path)
    restored = joblib.load(path)
    for bundle in restored.values():
        calibrated = apply_calibration(bundle, logits, probabilities)
        assert calibrated.shape == targets.shape
        assert np.isfinite(calibrated).all()
        assert np.all((calibrated >= 0.0) & (calibrated <= 1.0))


def test_rare_label_uses_identity_fallback():
    probabilities = np.array([[0.1, 0.2], [0.2, 0.3], [0.3, 0.4], [0.4, 0.5]])
    logits = np.log(probabilities / (1 - probabilities))
    targets = np.array([[1, 0], [0, 0], [0, 1], [0, 1]], dtype=np.int8)
    candidates = fit_calibration_candidates(targets, logits, probabilities, minimum_support=2)
    assert candidates["platt"].fallback_labels == [0]
    assert candidates["isotonic"].fallback_labels == [0]
    calibrated = apply_calibration(candidates["isotonic"], logits, probabilities)
    np.testing.assert_array_equal(calibrated[:, 0], probabilities[:, 0])


def test_calibration_adoption_requires_material_joint_improvement():
    diagnostics = {
        "identity": {"brier": 0.10, "ece": 0.05, "microAUPRC": 0.15, "macroAUPRC": 0.12},
        "weak": {"brier": 0.0999, "ece": 0.049, "microAUPRC": 0.15, "macroAUPRC": 0.12},
        "useful": {"brier": 0.09, "ece": 0.03, "microAUPRC": 0.15, "macroAUPRC": 0.12},
    }
    selected = choose_calibration(diagnostics)
    assert selected["method"] == "useful"
    assert selected["adopted"] is True
    unchanged = choose_calibration({key: value for key, value in diagnostics.items() if key != "useful"})
    assert unchanged["method"] == "identity"
    assert unchanged["adopted"] is False


def test_calibration_diagnostics_include_probability_quality():
    targets = np.array([[1, 0], [0, 1], [1, 0], [0, 1]], dtype=np.int8)
    probabilities = np.array([[0.8, 0.2], [0.2, 0.8], [0.7, 0.3], [0.3, 0.7]])
    result = calibration_diagnostics(targets, probabilities)
    assert result["brier"] < 0.1
    assert result["microAUPRC"] == 1.0
    assert len(result["perLabel"]) == 2
