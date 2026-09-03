from __future__ import annotations

import json
import shutil
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import joblib
import numpy as np

from vitanexus_ml.config import PORTABLE_STATE_VERSION, TRAINING_PIPELINE_VERSION, TrainConfig
from vitanexus_ml.models.feature_cache import (
    _cache_identity,
    normalize_processed_input_identity,
    processed_input_identity,
)
from vitanexus_ml.training_runtime import atomic_json, file_sha256, stable_hash, utc_now


CACHE_FILES = (
    "data.npy",
    "indices.npy",
    "indptr.npy",
    "labels.npy",
    "quarter_codes.npy",
    "caseids.npy",
    "feature_builder.joblib",
    "metadata.json",
)


def portable_run_identity(identity: dict) -> dict:
    result = deepcopy(identity)
    result["input"] = normalize_processed_input_identity(result.get("input", {}))
    return result


def portable_run_key(identity: dict) -> str:
    return stable_hash(portable_run_identity(identity))[:20]


def portable_cache_identity(input_identity: dict, config: dict) -> dict:
    return _cache_identity(normalize_processed_input_identity(input_identity), TrainConfig(**config))


def portable_cache_key(input_identity: dict, config: dict) -> str:
    return stable_hash(portable_cache_identity(input_identity, config))[:20]


def _latest_run(source_root: Path) -> Path:
    states = sorted((source_root / "training_runs").glob("*/state.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not states:
        raise FileNotFoundError(f"No training run state found below {source_root / 'training_runs'}")
    return states[0].parent


def _required_checkpoint_for_stage(stage: str) -> str | None:
    if stage.startswith("tuning_") and stage != "tuning_samples":
        return f"checkpoints/{stage}.joblib"
    if stage.startswith("baseline_"):
        return f"checkpoints/{stage}.joblib"
    return {"final_model": "checkpoints/final_model.joblib", "calibration": "checkpoints/calibration.joblib"}.get(stage)


def inspect_training_state(source_root: Path, cohort_path: Path, run_key: str | None = None) -> dict:
    source_root = source_root.resolve()
    run_root = source_root / "training_runs" / run_key if run_key else _latest_run(source_root)
    state_path = run_root / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Training state does not exist: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    expected_input = processed_input_identity(cohort_path)
    if normalize_processed_input_identity(state["identity"]["input"]) != expected_input:
        raise RuntimeError("Existing training state does not match the immutable cohort hashes and sizes.")
    if state["identity"].get("pipelineVersion") != TRAINING_PIPELINE_VERSION:
        raise RuntimeError("Existing training state uses a different LightGBM pipeline version.")

    config = state["identity"]["config"]
    expected_replicas = int(config["bootstrap_replicas"])
    stages = state.get("stages", {})
    completed = sorted(name for name, value in stages.items() if value.get("status") == "complete")
    interrupted = sorted(name for name, value in stages.items() if value.get("status") != "complete")
    completed_replicas = sorted(
        int(name.split("_")[1]) for name in completed
        if name.startswith("bootstrap_") and name.split("_")[1].isdigit()
    )
    cache_key = stages.get("feature_cache", {}).get("cacheKey")
    if not cache_key:
        raise RuntimeError("The source state has no completed feature-cache key.")
    cache_root = source_root / "feature_cache" / cache_key
    missing_cache = [name for name in CACHE_FILES if not (cache_root / name).exists()]
    if missing_cache:
        raise FileNotFoundError(f"Finalized feature cache is incomplete: {', '.join(missing_cache)}")

    required_run_files = ["state.json"]
    if "tuning_samples" in completed:
        required_run_files.extend(["checkpoints/tuning_train_indices.npy", "checkpoints/tuning_validation_indices.npy"])
    for stage in completed:
        checkpoint = _required_checkpoint_for_stage(stage)
        if checkpoint:
            required_run_files.append(checkpoint)
    for replica in completed_replicas:
        required_run_files.append(f"bootstrap/replica_{replica:02d}.joblib")
    missing_run = [name for name in required_run_files if not (run_root / name).exists()]
    if missing_run:
        raise FileNotFoundError(f"Completed state references missing checkpoint files: {', '.join(missing_run)}")

    input_files = [cohort_path.parent / "dataset_manifest.json", cohort_path.parent / "data_quality.json"]
    items = [(cache_root / name, f"feature_cache/{name}") for name in CACHE_FILES]
    items += [(run_root / name, f"training_run/{name}") for name in sorted(set(required_run_files))]
    items += [(path, f"input_metadata/{path.name}") for path in input_files]
    included_bytes = sum(path.stat().st_size for path, _ in items)
    bootstrap_bytes = sum((run_root / f"bootstrap/replica_{index:02d}.joblib").stat().st_size for index in completed_replicas)
    return {
        "sourceRoot": str(source_root),
        "sourceRunRoot": str(run_root),
        "sourceCacheRoot": str(cache_root),
        "state": state,
        "datasetIdentity": expected_input,
        "sourceRunKey": run_root.name,
        "portableRunIdentity": portable_run_identity(state["identity"]),
        "portableRunKey": portable_run_key(state["identity"]),
        "sourceCacheKey": cache_key,
        "portableCacheIdentity": portable_cache_identity(expected_input, config),
        "portableCacheKey": portable_cache_key(expected_input, config),
        "completedStages": completed,
        "interruptedStages": interrupted,
        "completedBootstrapReplicas": completed_replicas,
        "expectedBootstrapReplicas": expected_replicas,
        "items": items,
        "includedBytes": included_bytes,
        "bootstrapBytes": bootstrap_bytes,
        "cohortBytes": cohort_path.stat().st_size,
    }


def export_training_state(source_root: Path, cohort_path: Path, output: Path, run_key: str | None = None) -> dict:
    audit = inspect_training_state(source_root, cohort_path, run_key)
    output = output.resolve()
    manifest_path = output / "portable_state_manifest.json"
    if manifest_path.exists():
        existing = verify_training_state_bundle(output, cohort_path)
        if existing["portableRunKey"] == audit["portableRunKey"]:
            return existing
        raise RuntimeError(f"Output already contains a different portable state: {output}")
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"Refusing to mix a portable state with non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)

    for source, relative in audit["items"]:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative == "training_run/state.json":
            state = deepcopy(audit["state"])
            state["identity"] = audit["portableRunIdentity"]
            for value in state.get("stages", {}).values():
                if value.get("status") == "running":
                    value["status"] = "interrupted"
                    value["interruptedAt"] = utc_now()
            state["migration"] = {
                "sourceRunKey": audit["sourceRunKey"],
                "portableRunKey": audit["portableRunKey"],
                "exportedAt": utc_now(),
            }
            atomic_json(target, state)
        elif relative == "feature_cache/metadata.json":
            shutil.copy2(source, target)
        else:
            shutil.copy2(source, target)
    atomic_json(output / "feature_cache" / "identity.json", audit["portableCacheIdentity"])

    file_rows = []
    for path in sorted(item for item in output.rglob("*") if item.is_file() and item.name != manifest_path.name):
        file_rows.append({
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        })
    manifest = {
        "formatVersion": PORTABLE_STATE_VERSION,
        "createdAt": utc_now(),
        "pipelineVersion": TRAINING_PIPELINE_VERSION,
        "datasetIdentity": audit["datasetIdentity"],
        "sourceRunKey": audit["sourceRunKey"],
        "portableRunKey": audit["portableRunKey"],
        "sourceCacheKey": audit["sourceCacheKey"],
        "portableCacheKey": audit["portableCacheKey"],
        "completedStages": audit["completedStages"],
        "interruptedStages": audit["interruptedStages"],
        "expectedBootstrapReplicas": audit["expectedBootstrapReplicas"],
        "completedBootstrapReplicas": audit["completedBootstrapReplicas"],
        "cohortIncluded": False,
        "cohortBytes": audit["cohortBytes"],
        "bundleBytes": sum(item["bytes"] for item in file_rows),
        "files": file_rows,
    }
    atomic_json(manifest_path, manifest)
    return manifest


def verify_training_state_bundle(bundle: Path, cohort_path: Path | None = None) -> dict:
    bundle = bundle.resolve()
    manifest_path = bundle / "portable_state_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Portable state manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("formatVersion") != PORTABLE_STATE_VERSION:
        raise RuntimeError("Unsupported portable training-state format.")
    for item in manifest.get("files", []):
        path = bundle / item["path"]
        if not path.exists() or path.stat().st_size != int(item["bytes"]) or file_sha256(path) != item["sha256"]:
            raise RuntimeError(f"Portable training-state checksum mismatch: {item['path']}")
    if cohort_path is not None and processed_input_identity(cohort_path) != normalize_processed_input_identity(manifest["datasetIdentity"]):
        raise RuntimeError("Portable training state does not match the supplied immutable cohort.")
    state = json.loads((bundle / "training_run" / "state.json").read_text(encoding="utf-8"))
    if portable_run_key(state["identity"]) != manifest["portableRunKey"]:
        raise RuntimeError("Portable run identity does not match its manifest.")
    builder = joblib.load(bundle / "feature_cache" / "feature_builder.joblib")
    if builder.metadata()["config"] != state["identity"]["config"]:
        raise RuntimeError("Feature-builder configuration does not match training state.")
    cache_metadata = json.loads((bundle / "feature_cache" / "metadata.json").read_text(encoding="utf-8"))
    arrays = {
        name: np.load(bundle / "feature_cache" / f"{name}.npy", mmap_mode="r")
        for name in ("data", "indices", "indptr", "labels", "quarter_codes", "caseids")
    }
    rows, columns, nnz = (int(cache_metadata[name]) for name in ("rows", "columns", "nnz"))
    if len(builder.feature_names) != columns:
        raise RuntimeError("Feature-builder column count does not match portable CSR metadata.")
    if not (
        arrays["data"].shape == arrays["indices"].shape == (nnz,)
        and arrays["indptr"].shape == (rows + 1,)
        and arrays["labels"].shape == arrays["quarter_codes"].shape == arrays["caseids"].shape == (rows,)
        and int(arrays["indptr"][0]) == 0
        and int(arrays["indptr"][-1]) == nnz
    ):
        raise RuntimeError("Portable CSR arrays do not match metadata dimensions.")
    del arrays

    completed_replicas = sorted(
        int(name.removeprefix("bootstrap_"))
        for name, value in state.get("stages", {}).items()
        if name.removeprefix("bootstrap_").isdigit() and value.get("status") == "complete"
    )
    if completed_replicas != manifest["completedBootstrapReplicas"]:
        raise RuntimeError("Portable state and manifest disagree about completed bootstrap replicas.")
    for path in sorted((bundle / "training_run" / "checkpoints").glob("*.joblib")) + sorted((bundle / "training_run" / "bootstrap").glob("*.joblib")):
        payload = joblib.load(path)
        model = payload.get("model") if isinstance(payload, dict) else None
        if model is not None and model.__class__.__name__ == "LGBMClassifier":
            device_type = str(getattr(model, "booster_", None).params.get("device_type", "cpu")).lower()
            if device_type not in {"cpu", ""}:
                raise RuntimeError(f"Transferred LightGBM checkpoint unexpectedly uses {device_type}: {path.name}")
    return manifest


def _copy_without_overwrite(source: Path, target: Path) -> None:
    if target.exists():
        if target.stat().st_size != source.stat().st_size or file_sha256(target) != file_sha256(source):
            raise RuntimeError(f"Existing imported artifact differs; refusing overwrite: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def import_training_state(
    bundle: Path,
    cohort_path: Path,
    cache_parent: Path,
    run_parent: Path,
) -> dict:
    manifest = verify_training_state_bundle(bundle, cohort_path)
    cache_target = cache_parent.resolve() / manifest["portableCacheKey"]
    run_target = run_parent.resolve() / manifest["portableRunKey"]
    cache_target.mkdir(parents=True, exist_ok=True)
    run_target.mkdir(parents=True, exist_ok=True)
    for source in sorted((bundle / "feature_cache").rglob("*")):
        if source.is_file():
            _copy_without_overwrite(source, cache_target / source.relative_to(bundle / "feature_cache"))

    incoming_state = json.loads((bundle / "training_run" / "state.json").read_text(encoding="utf-8"))
    target_state_path = run_target / "state.json"
    if target_state_path.exists():
        current = json.loads(target_state_path.read_text(encoding="utf-8"))
        if current.get("identity") != incoming_state.get("identity"):
            raise RuntimeError("Existing destination run has a different scientific identity.")
    else:
        atomic_json(target_state_path, incoming_state)
    for source in sorted((bundle / "training_run").rglob("*")):
        if source.is_file() and source.name != "state.json":
            _copy_without_overwrite(source, run_target / source.relative_to(bundle / "training_run"))
    return {
        "status": "IMPORTED",
        "runKey": manifest["portableRunKey"],
        "cacheKey": manifest["portableCacheKey"],
        "runRoot": str(run_target),
        "cacheRoot": str(cache_target),
        "completedBootstrapReplicas": manifest["completedBootstrapReplicas"],
        "expectedBootstrapReplicas": manifest["expectedBootstrapReplicas"],
    }
