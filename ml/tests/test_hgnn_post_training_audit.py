import numpy as np

from vitanexus_ml.models.hgnn_post_training_audit import select_configuration


def _candidate(name, f1, precision, recall, macro, actual=2.0, predicted=2.0):
    return {
        "name": name,
        "metrics": {
            "microF1": f1,
            "macroF1": macro,
            "microPrecision": precision,
            "microRecall": recall,
            "averageActualLabelsPerCase": actual,
            "averagePredictedLabelsPerCase": predicted,
        },
    }


def test_configuration_selection_rejects_unusable_precision_and_alert_volume():
    candidates = [
        _candidate("existing", .07, .62, .04, .05),
        _candidate("useful", .20, .30, .15, .06),
        _candidate("low-precision", .40, .10, .90, .10),
        _candidate("alert-flood", .30, .40, .25, .08, predicted=20),
    ]
    selected, constraints = select_configuration(candidates)
    assert selected["name"] == "useful"
    assert constraints["minimumMicroPrecision"] == .25
    assert not candidates[2]["passesConstraints"]
    assert not candidates[3]["passesConstraints"]


def test_threshold_configuration_remains_json_friendly():
    candidates = [_candidate("existing", .07, .62, .04, .05)]
    candidates[0]["thresholds"] = np.asarray([.1, .2]).tolist()
    selected, _ = select_configuration(candidates)
    assert selected["thresholds"] == [.1, .2]
