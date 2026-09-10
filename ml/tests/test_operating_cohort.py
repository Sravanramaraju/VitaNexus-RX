import numpy as np
import pytest

from vitanexus_ml.models.operating_threshold import (
    assert_operating_cohort_is_pre_holdout,
    deterministic_group_stratified_split,
    evaluate_calibrated_operating_threshold,
)


def test_operating_cohort_split_is_deterministic_disjoint_and_group_safe():
    labels = np.array([0, 0, 0, 0, 1, 1, 1, 1], dtype=np.int8)
    groups = np.array(["a", "a", "b", "c", "d", "d", "e", "f"])
    first = deterministic_group_stratified_split(labels, groups, selection_fraction=0.5, seed=42)
    second = deterministic_group_stratified_split(labels, groups, selection_fraction=0.5, seed=42)
    assert all(np.array_equal(left, right) for left, right in zip(first, second))
    conformal, selection = first
    assert not np.intersect1d(conformal, selection).size
    assert set(conformal) | set(selection) == set(range(len(labels)))
    assert not set(groups[conformal]) & set(groups[selection])
    assert set(labels[conformal]) == set(labels[selection]) == {0, 1}


def test_operating_cohort_accepts_only_the_designated_pre_holdout_quarter():
    assert_operating_cohort_is_pre_holdout(np.array(["2025Q4", "2025Q4"]))
    with pytest.raises(ValueError, match="requires only 2025Q4"):
        assert_operating_cohort_is_pre_holdout(np.array(["2025Q3", "2025Q4"]))
    with pytest.raises(ValueError, match="locked 2026 holdout"):
        assert_operating_cohort_is_pre_holdout(np.array(["2025Q4", "2026Q1"]))


def test_operating_cohort_split_rejects_cross_class_groups():
    with pytest.raises(ValueError, match="spans multiple target classes"):
        deterministic_group_stratified_split(
            np.array([0, 1, 0, 1]),
            np.array(["same", "same", "negative", "positive"]),
            seed=42,
        )


def test_calibrated_operating_evaluation_freezes_threshold_before_holdout():
    pool_labels = np.array([0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1], dtype=np.int8)
    pool_probabilities = np.array([0.05, 0.15, 0.25, 0.35, 0.65, 0.85, 0.30, 0.45, 0.55, 0.70, 0.80, 0.95])
    holdout_labels = np.array([0, 0, 0, 1, 1, 1], dtype=np.int8)
    holdout_probabilities = np.array([0.10, 0.40, 0.75, 0.35, 0.60, 0.90])
    pool_before = pool_probabilities.copy()
    holdout_before = holdout_probabilities.copy()
    report, sweep = evaluate_calibrated_operating_threshold(
        pool_labels=pool_labels,
        pool_probabilities=pool_probabilities,
        pool_caseids=np.array([f"case-{index}" for index in range(len(pool_labels))]),
        pool_quarters=np.full(len(pool_labels), "2025Q4"),
        holdout_labels=holdout_labels,
        holdout_probabilities=holdout_probabilities,
        legacy_threshold=0.35,
        seed=20260824,
        sensitivity_constraint=0.90,
    )
    assert report["selection"]["holdoutUsedForSelection"] is False
    assert report["lockedHoldout2026"]["usedForThresholdSelection"] is False
    assert report["selection"]["selectedOperatingPoint"]["recallSensitivity"] >= 0.90
    assert report["cohortAllocation"]["overlapRows"] == 0
    assert report["thresholdSweep"]["step"] == 0.001
    assert len(sweep) == 1001
    assert np.array_equal(pool_probabilities, pool_before)
    assert np.array_equal(holdout_probabilities, holdout_before)
