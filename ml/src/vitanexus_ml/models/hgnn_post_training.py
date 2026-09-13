from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

import joblib
import numpy as np
import pyarrow.parquet as pq
import torch

from vitanexus_ml.config import HGNN_TRAINING_PIPELINE_VERSION, HGNN_VERSION
from vitanexus_ml.models.hgnn import HeterogeneousAdrNetwork, build_heterodata
from vitanexus_ml.models.hgnn_colab_pipeline import HgnnTrainConfig, ROW_COLUMNS, _iter_frames
from vitanexus_ml.training_runtime import atomic_json, file_sha256, stable_hash, utc_now


HGNN_POST_TRAINING_VERSION = "faers-hgnn-post-training-1.0.0"
EXPECTED_RUN_KEY = "0c32c0c81bc415a1dbe2"
WINDOWS = {
    "validation": ("2025Q1", "2025Q2"),
    "calibration": ("2025Q3", "2025Q3"),
    "operating": ("2025Q4", "2025Q4"),
    "holdout": ("2026Q1", "2026Q2"),
}
MODEL_FILES = {
    "selection": ("hgnn_selection_best.pt", "development_associations.joblib"),
    "partialRefit": ("hgnn_final_refit_latest.pt", "final_associations.joblib"),
}


def _label_hash(vocabulary: list[dict]) -> str:
    return stable_hash({"labels": [{"index": item["index"], "term": item["term"]} for item in vocabulary]})


def _run_root(snapshot_root: Path, run_key: str = EXPECTED_RUN_KEY) -> Path:
    return Path(snapshot_root) / "training_state" / "training_runs" / "hgnn" / run_key


def _vocabulary(run_root: Path) -> list[dict]:
    payload = json.loads((run_root / "adr_vocabulary.json").read_text(encoding="utf-8"))
    vocabulary = payload["items"] if isinstance(payload, dict) else payload
    indexes = [int(item["index"]) for item in vocabulary]
    if indexes != list(range(len(vocabulary))):
        raise RuntimeError("HGNN vocabulary indexes are not contiguous and ordered")
    return vocabulary


def create_checkpoint_integrity_manifest(
    snapshot_root: Path,
    output_path: Path,
    *,
    run_key: str = EXPECTED_RUN_KEY,
) -> dict:
    snapshot_root = Path(snapshot_root).resolve()
    run_root = _run_root(snapshot_root, run_key)
    state_path = run_root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    identity = state["identity"]
    if identity["pipelineVersion"] != HGNN_TRAINING_PIPELINE_VERSION or identity["modelVersion"] != HGNN_VERSION:
        raise RuntimeError("HGNN checkpoint versions differ from the supported frozen evaluation contract")
    vocabulary = _vocabulary(run_root)
    files = {}
    for name in (
        "hgnn_selection_best.pt",
        "hgnn_selection_latest.pt",
        "hgnn_final_refit_latest.pt",
        "adr_vocabulary.json",
        "development_associations.joblib",
        "final_associations.joblib",
        "state.json",
    ):
        path = run_root / name
        if not path.exists():
            raise FileNotFoundError(path)
        files[name] = {"sha256": file_sha256(path), "bytes": path.stat().st_size}
    selection = torch.load(run_root / "hgnn_selection_best.pt", map_location="cpu", weights_only=False)
    partial = torch.load(run_root / "hgnn_final_refit_latest.pt", map_location="cpu", weights_only=False)
    if int(selection["epoch"]) + 1 != 20:
        raise RuntimeError("Protected selection checkpoint is not epoch 20")
    if int(partial["nextEpoch"]) != 5:
        raise RuntimeError("Protected partial-refit checkpoint is not the expected five-epoch experiment")
    manifest = {
        "version": HGNN_POST_TRAINING_VERSION,
        "createdAt": utc_now(),
        "snapshotRoot": str(snapshot_root),
        "runKey": run_key,
        "immutabilityPolicy": "verify every source hash before and after inference; never write beneath snapshotRoot",
        "model": {
            "version": identity["modelVersion"],
            "pipelineVersion": identity["pipelineVersion"],
            "configuration": identity["hgnnConfig"],
            "labelCount": len(vocabulary),
            "labelOrderSha256": _label_hash(vocabulary),
            "selection": {"epoch": 20, "checkpoint": "hgnn_selection_best.pt"},
            "partialRefit": {
                "completedEpochs": 5,
                "checkpoint": "hgnn_final_refit_latest.pt",
                "status": "experimental-not-promoted",
            },
        },
        "input": identity["input"],
        "files": files,
    }
    output_path = Path(output_path)
    atomic_json(output_path, manifest)
    return manifest


def verify_checkpoint_integrity(manifest_path: Path) -> dict:
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != HGNN_POST_TRAINING_VERSION:
        raise RuntimeError("Unsupported frozen HGNN integrity manifest")
    snapshot_root = Path(manifest["snapshotRoot"]).resolve()
    run_root = _run_root(snapshot_root, manifest["runKey"])
    for name, expected in manifest["files"].items():
        path = run_root / name
        if not path.exists() or path.stat().st_size != expected["bytes"] or file_sha256(path) != expected["sha256"]:
            raise RuntimeError(f"Frozen HGNN input changed or is missing: {name}")
    return manifest


def _count_window(parquet: pq.ParquetFile, window: tuple[str, str]) -> int:
    start, end = window
    total = 0
    for batch in parquet.iter_batches(batch_size=250_000, columns=["quarter"]):
        values = np.asarray(batch.column(0).to_pylist())
        total += int(np.logical_and(values >= start, values <= end).sum())
    return total


def _load_frozen_model(manifest: dict, model_kind: str, device: torch.device):
    if model_kind not in MODEL_FILES:
        raise ValueError(f"Unknown frozen HGNN model kind: {model_kind}")
    snapshot_root = Path(manifest["snapshotRoot"])
    run_root = _run_root(snapshot_root, manifest["runKey"])
    checkpoint_name, association_name = MODEL_FILES[model_kind]
    checkpoint = torch.load(run_root / checkpoint_name, map_location=device, weights_only=False)
    vocabulary = _vocabulary(run_root)
    associations = joblib.load(run_root / association_name)
    config = HgnnTrainConfig(**manifest["model"]["configuration"])
    model = HeterogeneousAdrNetwork(config.hidden_channels, len(vocabulary)).to(device)
    parquet = pq.ParquetFile(snapshot_root / "data" / "processed" / "faers" / "cohort.parquet")
    sample = next(_iter_frames(parquet, ("2022Q1", "2022Q1"), 2, ROW_COLUMNS))
    with torch.no_grad():
        model(build_heterodata(sample, vocabulary, associations, include_targets=False).to(device))
    model.load_state_dict(checkpoint["modelState"])
    model.eval()
    return model, vocabulary, associations, parquet, config


def _cache_paths(cache_root: Path, cache_name: str) -> dict[str, Path]:
    root = Path(cache_root) / cache_name
    return {
        "root": root,
        "metadata": root / "metadata.json",
        "caseids": root / "caseids.npy",
        "targets": root / "targets.npy",
        "logits": root / "logits.npy",
        "probabilities": root / "probabilities.npy",
    }


def cache_frozen_predictions(
    integrity_manifest_path: Path,
    cache_root: Path,
    *,
    cohort: str,
    model_kind: str = "selection",
    device_name: str | None = None,
) -> dict:
    if cohort not in WINDOWS:
        raise ValueError(f"Unknown HGNN evaluation cohort: {cohort}")
    if cohort == "holdout":
        raise RuntimeError("The 2026 holdout is inaccessible to pre-freeze prediction caching")
    manifest = verify_checkpoint_integrity(integrity_manifest_path)
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA prediction caching was requested but is unavailable")
    paths = _cache_paths(cache_root, f"{model_kind}_{cohort}")
    expected_identity = {
        "checkpointSha256": manifest["files"][MODEL_FILES[model_kind][0]]["sha256"],
        "cohort": cohort,
        "window": list(WINDOWS[cohort]),
        "labelOrderSha256": manifest["model"]["labelOrderSha256"],
    }
    if paths["metadata"].exists():
        existing = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        if existing.get("identity") != expected_identity:
            raise RuntimeError(f"Existing HGNN probability cache has a different identity: {paths['root']}")
        return existing
    if paths["root"].exists():
        raise RuntimeError(f"Incomplete cache directory exists and must be inspected manually: {paths['root']}")
    temporary = paths["root"].with_name(f".{paths['root'].name}.{os.getpid()}.tmp")
    temporary.mkdir(parents=True, exist_ok=False)
    model, vocabulary, associations, parquet, config = _load_frozen_model(manifest, model_kind, device)
    row_count = _count_window(parquet, WINDOWS[cohort])
    label_count = len(vocabulary)
    caseids = np.lib.format.open_memmap(temporary / "caseids.npy", mode="w+", dtype="S24", shape=(row_count,))
    targets = np.lib.format.open_memmap(temporary / "targets.npy", mode="w+", dtype=np.uint8, shape=(row_count, label_count))
    logits = np.lib.format.open_memmap(temporary / "logits.npy", mode="w+", dtype=np.float32, shape=(row_count, label_count))
    probabilities = np.lib.format.open_memmap(temporary / "probabilities.npy", mode="w+", dtype=np.float32, shape=(row_count, label_count))
    offset = 0
    with torch.no_grad():
        for frame in _iter_frames(parquet, WINDOWS[cohort], config.batch_size, ROW_COLUMNS):
            graph = build_heterodata(frame, vocabulary, associations, include_targets=True).to(device)
            batch_logits = model(graph)
            size = len(frame)
            caseids[offset : offset + size] = frame["caseid"].astype(str).str.encode("utf-8").to_numpy()
            targets[offset : offset + size] = graph["report"].y.detach().cpu().numpy().astype(np.uint8)
            logits[offset : offset + size] = batch_logits.detach().cpu().numpy().astype(np.float32)
            probabilities[offset : offset + size] = torch.sigmoid(batch_logits).detach().cpu().numpy().astype(np.float32)
            offset += size
            if offset == size or offset % (config.batch_size * 100) == 0:
                print(f"[hgnn-cache-{model_kind}-{cohort}] {offset:,}/{row_count:,}", flush=True)
            del graph, batch_logits
    if offset != row_count:
        raise RuntimeError(f"HGNN cache row count mismatch: wrote {offset:,}, expected {row_count:,}")
    for array in (caseids, targets, logits, probabilities):
        array.flush()
    metadata = {
        "version": HGNN_POST_TRAINING_VERSION,
        "createdAt": utc_now(),
        "identity": expected_identity,
        "rows": row_count,
        "labels": [{"index": item["index"], "term": item["term"]} for item in vocabulary],
        "shapes": {
            "caseids": [row_count],
            "targets": [row_count, label_count],
            "logits": [row_count, label_count],
            "probabilities": [row_count, label_count],
        },
        "dtypes": {"caseids": "S24", "targets": "uint8", "logits": "float32", "probabilities": "float32"},
        "device": str(device),
        "targetEdgesExcludedFromEncoder": True,
    }
    atomic_json(temporary / "metadata.json", metadata)
    paths["root"].parent.mkdir(parents=True, exist_ok=True)
    temporary.replace(paths["root"])
    verify_checkpoint_integrity(integrity_manifest_path)
    return metadata


def load_prediction_cache(cache_root: Path, cache_name: str, *, expected_label_hash: str | None = None) -> dict:
    paths = _cache_paths(cache_root, cache_name)
    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    labels = metadata["labels"]
    if expected_label_hash is not None and _label_hash(labels) != expected_label_hash:
        raise RuntimeError("HGNN probability cache label order differs from the frozen checkpoint")
    arrays = {
        name: np.load(paths[name], mmap_mode="r", allow_pickle=False)
        for name in ("caseids", "targets", "logits", "probabilities")
    }
    for name, array in arrays.items():
        if list(array.shape) != metadata["shapes"][name]:
            raise RuntimeError(f"HGNN probability cache shape mismatch for {name}")
    return {"metadata": metadata, **arrays}
