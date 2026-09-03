from __future__ import annotations

import json
import shutil
from pathlib import Path

import joblib

from vitanexus_ml.config import INFERENCE_BUNDLE_VERSION
from vitanexus_ml.training_runtime import atomic_json, atomic_replace, file_sha256, utc_now


LIGHTGBM_REPORTS = (
    "lightgbm_baselines.csv",
    "calibration_metrics.json",
    "bootstrap_summary.json",
    "conformal_metrics.json",
    "final_temporal_evaluation.json",
    "lightgbm_metrics.json",
)
HGNN_REPORTS = ("hgnn_baselines.csv", "hgnn_metrics.json")


def _validated_files(artifact_root: Path, report_root: Path, component: str) -> list[tuple[Path, str]]:
    training_manifest_path = artifact_root / "training_manifest.json"
    if not training_manifest_path.exists():
        raise FileNotFoundError("Full LightGBM training manifest is missing.")
    training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8"))
    if training_manifest.get("fastMode") is not False or training_manifest.get("fullFinalData") is not True:
        raise RuntimeError("Smoke or partial LightGBM artifacts cannot be exported as a full inference bundle.")
    files = [
        (artifact_root / "serious_outcome.joblib", "artifacts/serious_outcome.joblib"),
        (training_manifest_path, "artifacts/training_manifest.json"),
    ]
    replicas = sorted((artifact_root / "bootstrap").glob("replica_*.joblib"))
    expected = int(training_manifest["config"]["bootstrap_replicas"])
    if expected != 20:
        raise RuntimeError(f"Full VitaNexus-RX inference requires 20 bootstrap replicas, manifest requests {expected}.")
    if len(replicas) != expected or [path.name for path in replicas] != [f"replica_{index:02d}.joblib" for index in range(expected)]:
        raise RuntimeError(f"Expected {expected} contiguous bootstrap replicas, found {len(replicas)}.")
    files.extend((path, f"artifacts/bootstrap/{path.name}") for path in replicas)
    files.extend((report_root / name, f"reports/{name}") for name in LIGHTGBM_REPORTS)

    if component == "all":
        hgnn_manifest_path = artifact_root / "hgnn_training_manifest.json"
        if not hgnn_manifest_path.exists():
            raise FileNotFoundError("Full HGNN training manifest is missing.")
        hgnn_manifest = json.loads(hgnn_manifest_path.read_text(encoding="utf-8"))
        if hgnn_manifest.get("fastMode") is not False or hgnn_manifest.get("fullFinalData") is not True:
            raise RuntimeError("Smoke or partial HGNN artifacts cannot be exported as full artifacts.")
        for name in ("hgnn_metadata.joblib", "hgnn_state.pt", "adr_vocabulary.json", "hgnn_training_manifest.json"):
            files.append((artifact_root / name, f"artifacts/{name}"))
        files.extend((report_root / name, f"reports/{name}") for name in HGNN_REPORTS)
        metadata = joblib.load(artifact_root / "hgnn_metadata.joblib")
        if metadata.get("fastMode") is not False:
            raise RuntimeError("HGNN metadata is still smoke-mode.")
    missing = [str(source) for source, _ in files if not source.exists()]
    if missing:
        raise FileNotFoundError(f"Required inference artifacts are missing: {', '.join(missing)}")
    return files


def export_inference_bundle(artifact_root: Path, report_root: Path, output: Path, component: str = "all") -> dict:
    if component not in {"lightgbm", "all"}:
        raise ValueError("component must be 'lightgbm' or 'all'")
    files = _validated_files(artifact_root, report_root, component)
    output = output.resolve()
    manifest_path = output / "inference_bundle_manifest.json"
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"Inference bundle output must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for source, relative in files:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rows.append({"path": relative, "bytes": target.stat().st_size, "sha256": file_sha256(target)})
    manifest = {
        "formatVersion": INFERENCE_BUNDLE_VERSION,
        "component": component,
        "createdAt": utc_now(),
        "files": rows,
        "bundleBytes": sum(item["bytes"] for item in rows),
    }
    atomic_json(manifest_path, manifest)
    return manifest


def verify_inference_bundle(bundle: Path, require_all: bool = True) -> dict:
    manifest_path = bundle / "inference_bundle_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Inference bundle manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("formatVersion") != INFERENCE_BUNDLE_VERSION:
        raise RuntimeError("Unsupported inference-bundle format.")
    if require_all and manifest.get("component") != "all":
        raise RuntimeError("A combined full LightGBM+HGNN bundle is required for local application import.")
    for item in manifest.get("files", []):
        path = bundle / item["path"]
        if not path.exists() or path.stat().st_size != int(item["bytes"]) or file_sha256(path) != item["sha256"]:
            raise RuntimeError(f"Inference bundle checksum mismatch: {item['path']}")
    lightgbm = json.loads((bundle / "artifacts" / "training_manifest.json").read_text(encoding="utf-8"))
    if lightgbm.get("fastMode") is not False or lightgbm.get("fullFinalData") is not True:
        raise RuntimeError("Inference bundle LightGBM manifest is not full-mode.")
    if manifest.get("component") == "all":
        hgnn = json.loads((bundle / "artifacts" / "hgnn_training_manifest.json").read_text(encoding="utf-8"))
        if hgnn.get("fastMode") is not False or hgnn.get("fullFinalData") is not True:
            raise RuntimeError("Inference bundle HGNN manifest is not full-mode.")
        metadata = joblib.load(bundle / "artifacts" / "hgnn_metadata.joblib")
        if metadata.get("fastMode") is not False:
            raise RuntimeError("Inference bundle contains smoke HGNN metadata.")
    return manifest


def import_inference_bundle(bundle: Path, artifact_root: Path, report_root: Path) -> dict:
    manifest = verify_inference_bundle(bundle, require_all=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for item in manifest["files"]:
            source = bundle / item["path"]
            relative = Path(item["path"])
            target_root = artifact_root if relative.parts[0] == "artifacts" else report_root
            target = target_root.joinpath(*relative.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.validated-import.tmp")
            shutil.copy2(source, temporary)
            if file_sha256(temporary) != item["sha256"]:
                raise RuntimeError(f"Staged inference artifact checksum mismatch: {item['path']}")
            staged.append((temporary, target))
        for temporary, target in staged:
            atomic_replace(temporary, target)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    return {"status": "IMPORTED", "component": manifest["component"], "files": len(staged)}
