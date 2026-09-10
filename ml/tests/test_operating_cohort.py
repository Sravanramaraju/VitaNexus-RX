import numpy as np
import pytest

from vitanexus_ml.models.operating_threshold import (
    assert_operating_cohort_is_pre_holdout,
    deterministic_group_stratified_split,
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
