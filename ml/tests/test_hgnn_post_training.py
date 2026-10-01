import hashlib
import json

import numpy as np
import pytest
import torch

from vitanexus_ml.models.hgnn_post_training import (
    EXPECTED_RUN_KEY,
    HGNN_POST_TRAINING_VERSION,
    _label_hash,
    cache_frozen_holdout_predictions,
    cache_frozen_predictions,
    create_checkpoint_integrity_manifest,
    load_prediction_cache,
    verify_checkpoint_integrity,
)
from vitanexus_ml.config import HGNN_TRAINING_PIPELINE_VERSION, HGNN_VERSION
from vitanexus_ml.models.hgnn_colab_pipeline import HgnnTrainConfig


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


def test_selection_only_manifest_records_focal_checkpoint_without_final_refit(tmp_path):
    snapshot = tmp_path / "snapshot"
    run = snapshot / "training_state" / "training_runs" / "hgnn" / "fresh-objective"
    run.mkdir(parents=True)
    labels = [{"index": 0, "term": "alpha"}]
    (run / "adr_vocabulary.json").write_text(json.dumps({"items": labels}), encoding="utf-8")
    (run / "development_associations.joblib").write_bytes(b"associations")
    (run / "hgnn_focal_objective.json").write_text(json.dumps({"identity": "focal-objective"}), encoding="utf-8")
    checkpoint = {
        "epoch": 19,
        "checkpointMetadata": {"trainingObjective": "focal-objective"},
    }
    torch.save(checkpoint, run / "hgnn_selection_best.pt")
    torch.save(checkpoint, run / "hgnn_selection_latest.pt")
    state = {
        "identity": {
            "pipelineVersion": HGNN_TRAINING_PIPELINE_VERSION,
            "modelVersion": HGNN_VERSION,
            "hgnnConfig": HgnnTrainConfig().__dict__,
            "input": {"cohort": "fixture"},
        },
    }
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")

    manifest_path = tmp_path / "integrity.json"
    manifest = create_checkpoint_integrity_manifest(snapshot, manifest_path, run_key="fresh-objective")

    assert manifest["model"]["selection"]["epoch"] == 20
    assert manifest["model"]["finalRefit"]["status"].startswith("not-run")
    assert manifest["model"]["trainingObjective"] == "focal-objective"
    assert "hgnn_focal_objective.json" in manifest["files"]
    assert "hgnn_final_refit_latest.pt" not in manifest["files"]
    assert verify_checkpoint_integrity(manifest_path)["runKey"] == "fresh-objective"


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


def test_holdout_cache_requires_integrity_and_completed_freeze(tmp_path):
    frozen = tmp_path / "frozen.json"
    frozen.write_text('{"status":"DRAFT"}', encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        cache_frozen_holdout_predictions(tmp_path / "missing.json", frozen, tmp_path)
