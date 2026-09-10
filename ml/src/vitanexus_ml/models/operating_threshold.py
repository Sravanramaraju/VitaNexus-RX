from __future__ import annotations

import hashlib

import numpy as np


OPERATING_THRESHOLD_VERSION = "faers-calibrated-operating-threshold-1.0.0"


def assert_operating_cohort_is_pre_holdout(quarters, *, required_quarter: str = "2025Q4") -> None:
    values = {str(value) for value in np.asarray(quarters).tolist()}
    if not values:
        raise ValueError("Operating-threshold cohort is empty")
    if any(value >= "2026Q1" for value in values):
        raise ValueError("The locked 2026 holdout cannot participate in threshold selection")
    if values != {required_quarter}:
        raise ValueError(
            f"Operating-threshold selection requires only {required_quarter}; observed {sorted(values)}"
        )


def deterministic_group_stratified_split(
    labels,
    group_ids,
    *,
    selection_fraction: float = 0.5,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Split groups into disjoint conformal and threshold-selection positions."""
    labels = np.asarray(labels, dtype=np.int8)
    group_ids = np.asarray(group_ids).astype(str)
    if labels.ndim != 1 or group_ids.ndim != 1 or len(labels) != len(group_ids):
        raise ValueError("Labels and group IDs must be equally sized one-dimensional arrays")
    if not 0.0 < selection_fraction < 1.0:
        raise ValueError("Selection fraction must be in (0, 1)")
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError("Both classes are required before cohort partitioning")

    group_labels: dict[str, int] = {}
    for group_id, label in zip(group_ids, labels):
        previous = group_labels.setdefault(group_id, int(label))
        if previous != int(label):
            raise ValueError(f"Group {group_id} spans multiple target classes")

    selection_groups: set[str] = set()
    for label in (0, 1):
        members = [group_id for group_id, group_label in group_labels.items() if group_label == label]
        if len(members) < 2:
            raise ValueError("Each class requires at least two groups for a disjoint split")
        ordered = sorted(
            members,
            key=lambda value: hashlib.sha256(f"{seed}:{value}".encode("utf-8")).digest(),
        )
        count = min(len(ordered) - 1, max(1, int(round(len(ordered) * selection_fraction))))
        selection_groups.update(ordered[:count])

    selection_mask = np.fromiter((value in selection_groups for value in group_ids), dtype=bool)
    selection_positions = np.flatnonzero(selection_mask)
    conformal_positions = np.flatnonzero(~selection_mask)
    if np.intersect1d(selection_positions, conformal_positions).size:
        raise RuntimeError("Conformal and threshold-selection cohorts overlap")
    if set(np.unique(labels[selection_positions])) != {0, 1} or set(np.unique(labels[conformal_positions])) != {0, 1}:
        raise RuntimeError("Disjoint cohorts did not retain both target classes")
    return conformal_positions.astype(np.int64), selection_positions.astype(np.int64)
