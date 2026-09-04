from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
import torch

from vitanexus_ml.artifact_bundle import export_inference_bundle, import_inference_bundle, verify_inference_bundle
from vitanexus_ml.cli import training_status
from vitanexus_ml.config import TRAINING_PIPELINE_VERSION, TrainConfig
from vitanexus_ml.features.builder import FeatureBuilder
from vitanexus_ml.models.feature_cache import processed_input_identity
from vitanexus_ml.models.hgnn_colab_pipeline import (
    PARTITIONS,
    _restore_cuda_rng_state_all,
    _resume_model,
    _streaming_associations,
    assert_hgnn_target_edge_integrity,
    assert_hgnn_temporal_integrity,
)
from vitanexus_ml.portable_state import (
    CACHE_FILES,
    export_training_state,
    import_training_state,
    portable_run_key,
    verify_training_state_bundle,
)
from vitanexus_ml.training_runtime import atomic_torch


def _immutable_fixture(root: Path) -> Path:
    processed = root / "data" / "processed" / "faers"
    processed.mkdir(parents=True)
    (processed / "cohort.parquet").write_bytes(b"identical-scientific-cohort")
    (processed / "dataset_manifest.json").write_text('{"manifest": true}', encoding="utf-8")
    (processed / "data_quality.json").write_text('{"quality": true}', encoding="utf-8")
    return processed / "cohort.parquet"


def test_processed_dataset_identity_is_location_independent(tmp_path):
    first = _immutable_fixture(tmp_path / "first-location")
    second = _immutable_fixture(tmp_path / "second-location")
    assert processed_input_identity(first) == processed_input_identity(second)
    assert "cohortPath" not in processed_input_identity(first)


def test_run_identity_is_location_independent_for_legacy_state():
    files = {"cohort.parquet": {"sha256": "a" * 64, "bytes": 10}}
    first = {"pipelineVersion": TRAINING_PIPELINE_VERSION, "input": {"files": files, "cohortPath": "C:/old/cohort.parquet"}}
    second = {"pipelineVersion": TRAINING_PIPELINE_VERSION, "input": {"files": files, "cohortPath": "/content/new/cohort.parquet"}}
    assert portable_run_key(first) == portable_run_key(second)


def test_old_checkpoint_export_import_preserves_completed_and_marks_interrupted(tmp_path):
    cohort = _immutable_fixture(tmp_path / "project")
    input_identity = processed_input_identity(cohort)
    legacy_input = {"files": input_identity["files"], "cohortPath": "C:/old/project/cohort.parquet"}
    config = TrainConfig()
    source = tmp_path / "old-work-root"
    cache_key = "legacy-cache"
    cache = source / "feature_cache" / cache_key
    run = source / "training_runs" / "legacy-run"
    cache.mkdir(parents=True)
    (run / "bootstrap").mkdir(parents=True)

    arrays = {
        "data": np.array([1.0], dtype=np.float32),
        "indices": np.array([0], dtype=np.int32),
        "indptr": np.array([0, 1], dtype=np.int64),
        "labels": np.array([1], dtype=np.int8),
        "quarter_codes": np.array([0], dtype=np.int8),
        "caseids": np.array([1], dtype=np.int64),
    }
    for name, values in arrays.items():
        np.save(cache / f"{name}.npy", values)
    builder = FeatureBuilder(config).fit_from_counts(Counter({"A": 1}), Counter({"I": 1}), Counter(), Counter({"A::I": 1}))
    joblib.dump(builder, cache / "feature_builder.joblib")
    (cache / "metadata.json").write_text(
        json.dumps({"rows": 1, "columns": len(builder.feature_names), "nnz": 1}),
        encoding="utf-8",
    )
    assert set(CACHE_FILES).issubset(path.name for path in cache.iterdir())
    joblib.dump({"model": "complete"}, run / "bootstrap" / "replica_00.joblib")
    state = {
        "identity": {
            "pipelineVersion": TRAINING_PIPELINE_VERSION,
            "input": legacy_input,
            "config": asdict(config),
            "mode": "FULL",
            "temporalPartitions": {name: list(window) for name, window in PARTITIONS.items()},
        },
        "createdAt": "test",
        "stages": {
            "feature_cache": {"status": "complete", "cacheKey": cache_key},
            "bootstrap_00": {"status": "complete"},
            "bootstrap_01": {"status": "running"},
        },
    }
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")

    bundle = tmp_path / "bundle"
    manifest = export_training_state(source, cohort, bundle, "legacy-run")
    assert manifest["completedBootstrapReplicas"] == [0]
    assert manifest["interruptedStages"] == ["bootstrap_01"]
    verify_training_state_bundle(bundle, cohort)

    imported = import_training_state(bundle, cohort, tmp_path / "cache", tmp_path / "runs")
    imported_state = json.loads(Path(imported["runRoot"]).joinpath("state.json").read_text(encoding="utf-8"))
    assert imported_state["stages"]["bootstrap_00"]["status"] == "complete"
    assert imported_state["stages"]["bootstrap_01"]["status"] == "interrupted"
    assert Path(imported["cacheRoot"]).joinpath("feature_builder.joblib").exists()
    (bundle / "feature_cache" / "metadata.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        verify_training_state_bundle(bundle, cohort)


def test_training_bundle_detects_tampering(tmp_path):
    cohort = _immutable_fixture(tmp_path / "project")
    with pytest.raises(FileNotFoundError):
        verify_training_state_bundle(tmp_path / "missing", cohort)


def test_hgnn_temporal_guards_reject_validation_leakage():
    assert_hgnn_temporal_integrity()
    assert_hgnn_target_edge_integrity()
    leaking = dict(PARTITIONS)
    leaking["developmentTrain"] = ("2022Q1", "2025Q1")
    with pytest.raises(RuntimeError, match="overlap"):
        assert_hgnn_temporal_integrity(leaking)


def test_hgnn_selection_associations_exclude_validation_rows(tmp_path):
    cohort = tmp_path / "cohort.parquet"
    pd.DataFrame([
        {"quarter": "2024Q4", "candidate_drug": "Development Drug", "indication": "Development Indication", "reactions": ["Development ADR"]},
        {"quarter": "2025Q1", "candidate_drug": "Validation Drug", "indication": "Validation Indication", "reactions": ["Validation ADR"]},
    ]).to_parquet(cohort, index=False)
    vocabulary = [
        {"term": "DEVELOPMENT ADR", "index": 0},
        {"term": "VALIDATION ADR", "index": 1},
    ]
    associations = _streaming_associations(
        pq.ParquetFile(cohort), vocabulary, ("2022Q1", "2024Q4"), minimum=1
    )
    assert associations["drug"] == {"DEVELOPMENT DRUG": [0]}
    assert "VALIDATION DRUG" not in associations["drug"]


def test_smoke_artifacts_cannot_be_exported_as_full(tmp_path):
    artifacts = tmp_path / "artifacts"
    reports = tmp_path / "reports"
    artifacts.mkdir()
    reports.mkdir()
    (artifacts / "training_manifest.json").write_text(
        json.dumps({"fastMode": True, "fullFinalData": False, "config": {"bootstrap_replicas": 2}}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Smoke or partial"):
        export_inference_bundle(artifacts, reports, tmp_path / "output", component="lightgbm")


def test_training_status_does_not_count_bootstrap_unit_audit(tmp_path, monkeypatch):
    run = tmp_path / "runs" / "portable-run"
    run.mkdir(parents=True)
    state = {
        "identity": {"config": {"bootstrap_replicas": 20}},
        "stages": {
            "bootstrap_unit_audit": {"status": "complete"},
            "bootstrap_00": {"status": "complete", "elapsedSeconds": 10},
            "bootstrap_01": {"status": "interrupted"},
        },
    }
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr("vitanexus_ml.cli.TRAINING_RUN_ROOT", tmp_path / "runs")
    status = training_status()
    assert status["bootstrap"]["completed"] == 1
    assert status["bootstrap"]["estimatedRemainingSeconds"] == 190


def test_hgnn_epoch_checkpoint_resume_validates_identity(tmp_path):
    metadata = {"dataset": "abc", "vocabulary": "def", "split": "development"}
    model = torch.nn.Linear(2, 1)
    atomic_torch(tmp_path / "selection_latest.pt", {
        "modelState": model.state_dict(),
        "nextEpoch": 3,
        "history": [{"epoch": 1}, {"epoch": 2}, {"epoch": 3}],
        "bestValidationMicroAUPRC": 0.4,
        "bestEpoch": 2,
        "checkpointMetadata": metadata,
    })
    restored = torch.nn.Linear(2, 1)
    next_epoch, history, best_score, best_epoch = _resume_model("selection", restored, tmp_path, torch.device("cpu"), metadata)
    assert next_epoch == 3
    assert len(history) == 3
    assert best_score == pytest.approx(0.4)
    assert best_epoch == 2
    with pytest.raises(RuntimeError, match="identity differs"):
        _resume_model("selection", restored, tmp_path, torch.device("cpu"), {"dataset": "different"})


def test_hgnn_cuda_rng_resume_normalizes_states_to_cpu_byte_tensors(monkeypatch):
    restored = {}
    monkeypatch.setattr(torch.cuda, "set_rng_state_all", lambda states: restored.setdefault("states", states))

    _restore_cuda_rng_state_all([torch.tensor([1, 2, 3], dtype=torch.uint8)])

    assert len(restored["states"]) == 1
    assert restored["states"][0].device.type == "cpu"
    assert restored["states"][0].dtype == torch.uint8
    assert restored["states"][0].is_contiguous()


def test_full_inference_bundle_is_validated_before_local_import(tmp_path):
    artifacts = tmp_path / "source-artifacts"
    reports = tmp_path / "source-reports"
    (artifacts / "bootstrap").mkdir(parents=True)
    reports.mkdir()
    (artifacts / "training_manifest.json").write_text(json.dumps({
        "fastMode": False, "fullFinalData": True, "config": {"bootstrap_replicas": 20}
    }), encoding="utf-8")
    joblib.dump({"fastMode": False}, artifacts / "serious_outcome.joblib")
    for index in range(20):
        joblib.dump({"replica": index}, artifacts / "bootstrap" / f"replica_{index:02d}.joblib")
    (artifacts / "hgnn_training_manifest.json").write_text(json.dumps({
        "fastMode": False, "fullFinalData": True
    }), encoding="utf-8")
    joblib.dump({"fastMode": False}, artifacts / "hgnn_metadata.joblib")
    (artifacts / "hgnn_state.pt").write_bytes(b"weights")
    (artifacts / "adr_vocabulary.json").write_text("[]", encoding="utf-8")
    for name in (
        "lightgbm_baselines.csv", "calibration_metrics.json", "bootstrap_summary.json",
        "conformal_metrics.json", "final_temporal_evaluation.json", "lightgbm_metrics.json",
        "hgnn_baselines.csv", "hgnn_metrics.json",
    ):
        (reports / name).write_text("{}", encoding="utf-8")
    bundle = tmp_path / "inference-bundle"
    export_inference_bundle(artifacts, reports, bundle, component="all")
    verify_inference_bundle(bundle, require_all=True)
    result = import_inference_bundle(bundle, tmp_path / "local-artifacts", tmp_path / "local-reports")
    assert result["component"] == "all"
    assert (tmp_path / "local-artifacts" / "training_manifest.json").exists()
    assert (tmp_path / "local-artifacts" / "bootstrap" / "replica_19.joblib").exists()
