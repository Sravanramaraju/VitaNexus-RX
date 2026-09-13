import hashlib
import json

import numpy as np
import pytest

from vitanexus_ml.models.hgnn_post_training import (
    EXPECTED_RUN_KEY,
    HGNN_POST_TRAINING_VERSION,
    _label_hash,
    cache_frozen_predictions,
    load_prediction_cache,
    verify_checkpoint_integrity,
)


def test_checkpoint_guard_rejects_mutated_source(tmp_path):
    snapshot = tmp_path / "snapshot"
    run = snapshot / "training_state" / "training_runs" / "hgnn" / EXPECTED_RUN_KEY
    run.mkdir(parents=True)
    protected = run / "checkpoint.pt"
    protected.write_bytes(b"frozen")
    manifest = {
        "version": HGNN_POST_TRAINING_VERSION,
        "snapshotRoot": str(snapshot),
        "runKey": EXPECTED_RUN_KEY,
        "files": {"checkpoint.pt": {"bytes": 6, "sha256": hashlib.sha256(b"frozen").hexdigest()}},
    }
    path = tmp_path / "integrity.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    verify_checkpoint_integrity(path)
    protected.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="changed or is missing"):
        verify_checkpoint_integrity(path)


def test_prediction_cache_preserves_label_order_and_reloads_without_pickle(tmp_path):
    labels = [{"index": 0, "term": "alpha"}, {"index": 1, "term": "beta"}]
    root = tmp_path / "cache" / "selection_operating"
    root.mkdir(parents=True)
    arrays = {
        "caseids": np.array([b"1", b"2"], dtype="S24"),
        "targets": np.array([[1, 0], [0, 1]], dtype=np.uint8),
        "logits": np.array([[1.0, -1.0], [-1.0, 1.0]], dtype=np.float32),
        "probabilities": np.array([[0.7, 0.3], [0.3, 0.7]], dtype=np.float32),
    }
    for name, values in arrays.items():
        np.save(root / f"{name}.npy", values, allow_pickle=False)
    metadata = {
        "labels": labels,
        "shapes": {name: list(values.shape) for name, values in arrays.items()},
    }
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    loaded = load_prediction_cache(tmp_path / "cache", "selection_operating", expected_label_hash=_label_hash(labels))
    assert loaded["metadata"]["labels"] == labels
    assert loaded["probabilities"][0, 0] == pytest.approx(0.7)
    with pytest.raises(RuntimeError, match="label order"):
        load_prediction_cache(tmp_path / "cache", "selection_operating", expected_label_hash="wrong")


def test_pre_freeze_cache_api_cannot_read_holdout(tmp_path):
    with pytest.raises(RuntimeError, match="holdout is inaccessible"):
        cache_frozen_predictions(tmp_path / "missing.json", tmp_path, cohort="holdout")
