import numpy as np

from vitanexus_ml.models.hgnn_thresholds import (
    deterministic_group_folds,
    global_threshold_stability,
    stable_per_label_thresholds,
)


VOCABULARY = [{"index": 0, "term": "a"}, {"index": 1, "term": "b"}]


def test_group_folds_are_deterministic_and_keep_cases_together():
    caseids = np.asarray([b"10", b"20", b"10", b"30"])
    first = deterministic_group_folds(caseids, folds=3)
    second = deterministic_group_folds(caseids, folds=3)
    assert np.array_equal(first, second)
    assert first[0] == first[2]


def test_global_threshold_stability_reports_every_fold():
    y = np.asarray([[1, 0], [0, 1], [1, 0], [0, 1], [1, 0], [0, 1]])
    p = np.asarray([[.9, .1], [.1, .9], [.8, .2], [.2, .8], [.7, .3], [.3, .7]])
    folds = np.asarray([0, 0, 1, 1, 2, 2])
    result = global_threshold_stability(y, p, folds, step=.1)
    assert len(result["folds"]) == 3
    assert result["summary"]["microF1Mean"] > 0.5
    assert result["summary"]["standardDeviationThreshold"] >= 0.0


def test_rare_labels_fall_back_and_unstable_labels_shrink():
    y = np.asarray([[1, 0], [0, 0], [1, 0], [0, 1], [1, 0], [0, 0]])
    p = np.asarray([[.9, .1], [.2, .1], [.8, .1], [.1, .8], [.7, .1], [.3, .1]])
    folds = np.asarray([0, 0, 1, 1, 2, 2])
    thresholds, rows, summary = stable_per_label_thresholds(
        y, p, VOCABULARY, folds, global_threshold=.5, minimum_support=2,
    )
    assert thresholds[1] == .5
    assert rows[1]["fallback"].startswith("global threshold")
    assert summary["fallbackLabels"] >= 1
