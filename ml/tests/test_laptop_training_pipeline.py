from types import SimpleNamespace
from pathlib import Path
import os
import shutil
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from vitanexus_ml.config import TrainConfig
from vitanexus_ml.models.feature_cache import QUARTER_TO_CODE, build_or_load_feature_cache
from vitanexus_ml.models.laptop_lightgbm_pipeline import (
    PARTITIONS,
    _balanced_weights,
    _bootstrap_multiplicities,
    _pending_bootstrap_indices,
    _temporal_stratified_sample,
)
from vitanexus_ml.training_runtime import StageStore


def test_bootstrap_multiplicities_are_deterministic_and_do_not_materialize_rows():
    first = _bootstrap_multiplicities(10_000, 42)
    second = _bootstrap_multiplicities(10_000, 42)
    assert np.array_equal(first, second)
    assert first.dtype == np.float32
    assert first.shape == (10_000,)
    assert first.sum() == 10_000
    assert np.count_nonzero(first == 0) > 0


def test_balanced_bootstrap_weights_equalize_weighted_classes():
    labels = np.array([0, 0, 0, 1, 1], dtype=np.int8)
    multiplicities = np.array([2, 0, 1, 3, 1], dtype=np.float32)
    weights = _balanced_weights(labels, multiplicities)
    assert weights[labels == 0].sum() == pytest.approx(weights[labels == 1].sum())
    assert weights.sum() == pytest.approx(multiplicities.sum())


def test_temporal_stratified_tuning_sample_is_deterministic_and_preserves_strata():
    quarter_values = []
    label_values = []
    for quarter in ("2022Q1", "2022Q2", "2023Q1", "2024Q4"):
        for label in (0, 1):
            quarter_values.extend([QUARTER_TO_CODE[quarter]] * 50)
            label_values.extend([label] * 50)
    cache = SimpleNamespace(
        labels=np.asarray(label_values, dtype=np.int8),
        quarter_codes=np.asarray(quarter_values, dtype=np.int8),
    )
    indices = np.arange(len(label_values), dtype=np.int64)
    first = _temporal_stratified_sample(indices, cache, 80, 123)
    second = _temporal_stratified_sample(indices, cache, 80, 123)
    assert np.array_equal(first, second)
    assert len(first) == 80
    observed = set(zip(cache.quarter_codes[first], cache.labels[first]))
    assert len(observed) == 8


def test_temporal_windows_keep_2026_out_of_all_training_and_calibration_stages():
    for name in ("developmentTrain", "tuningValidation", "finalFit", "calibration", "conformal"):
        assert PARTITIONS[name][1] <= "2025Q4"
    assert PARTITIONS["holdout"] == ("2026Q1", "2026Q2")


def test_stage_store_resumes_same_identity_and_rejects_mismatch():
    path = Path(os.environ.get("LOCALAPPDATA", "ml/artifacts")) / "VitaNexus-RX" / "tests" / f"state-{uuid4().hex}.json"
    try:
        identity = {"pipeline": "test", "config": {"bootstrap_replicas": TrainConfig().bootstrap_replicas}}
        store = StageStore(path, identity)
        store.start("model", rows=100)
        assert not store.is_complete("model")
        store.complete("model", rows=100)
        assert StageStore(path, identity).is_complete("model")
        with pytest.raises(RuntimeError, match="identity mismatch"):
            StageStore(path, {"pipeline": "different"})
    finally:
        path.unlink(missing_ok=True)


def test_bootstrap_resume_skips_only_completed_replicas_with_artifacts(tmp_path):
    state = StageStore(tmp_path / "state.json", {"pipeline": "test"})
    replica_root = tmp_path / "bootstrap"
    replica_root.mkdir()
    state.complete("bootstrap_00")
    (replica_root / "replica_00.joblib").write_bytes(b"checkpoint")
    state.complete("bootstrap_01")  # Missing artifact must be retrained.
    state.start("bootstrap_02")
    assert _pending_bootstrap_indices(state, replica_root, 4) == [1, 2, 3]


def test_sparse_feature_cache_is_single_resumable_representation():
    root = Path(os.environ.get("LOCALAPPDATA", "ml/artifacts")) / "VitaNexus-RX" / "tests" / f"feature-cache-{uuid4().hex}"
    processed = root / "processed"
    cache_parent = root / "cache"
    processed.mkdir(parents=True)
    quarters = list(QUARTER_TO_CODE)
    rows = []
    for index, quarter in enumerate(quarters):
        for label in (0, 1):
            rows.append({
                "caseid": str(10_000 + index * 2 + label),
                "quarter": quarter,
                "has_serious_outcome": label,
                "age_years": 30.0 + index,
                "sex": "M" if label else "F",
                "candidate_drug": f"DRUG {index % 3}",
                "indication": f"INDICATION {index % 2}",
                "current_medications": ["ASPIRIN"] if label else [],
            })
    cohort = processed / "cohort.parquet"
    pd.DataFrame(rows).to_parquet(cohort, index=False)
    (processed / "dataset_manifest.json").write_text("{}", encoding="utf-8")
    (processed / "data_quality.json").write_text("{}", encoding="utf-8")
    config = TrainConfig(cache_batch_rows=7)
    try:
        first = build_or_load_feature_cache(cohort, config, cache_parent)
        second = build_or_load_feature_cache(cohort, config, cache_parent)
        assert first.features.shape == second.features.shape == (len(rows), len(first.builder.feature_names))
        assert first.features.nnz == second.features.nnz
        assert first.metadata["cacheKey"] == second.metadata["cacheKey"]
        assert (first.root / "data.npy").exists()
        assert (first.root / "metadata.json").exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)
