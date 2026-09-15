from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


EXPECTED_HASHES = {
    "cohort.parquet": "6a0fd3166a6ca8d6b315b009d996c145e7484a7c850dceaaa6ec135e264205a3",
    "dataset_manifest.json": "42d4decd9f3dab04b64bc00e6fbba255f4f5a47487109702e475e1f6d93459eb",
    "data_quality.json": "e50fba1f86f64023b0b988a9014fd55f8e77f008892c0501a8858b88dc4fcc2f",
}
EXPECTED_ROWS = 6_309_764
EXPECTED_PACKAGES = {
    "numpy": "2.3.2",
    "pandas": "2.3.2",
    "pyarrow": "21.0.0",
    "scipy": "1.16.1",
    "scikit-learn": "1.7.1",
    "lightgbm": "4.6.0",
    "torch-geometric": "2.6.1",
    "joblib": "1.5.1",
    "psutil": "7.2.2",
}


@dataclass(frozen=True)
class ColabPaths:
    drive_root: Path
    repository: Path
    local_root: Path = Path("/content/vitanexus-ml-work")

    @property
    def drive_data(self) -> Path:
        return self.drive_root / "data" / "processed" / "faers"

    @property
    def state_bundle(self) -> Path:
        return self.drive_root / "training_state" / "imports" / "lightgbm_state"

    @property
    def persistent_runs(self) -> Path:
        return self.drive_root / "training_state" / "training_runs"

    @property
    def drive_models(self) -> Path:
        return self.drive_root / "models" / "runtime"

    @property
    def drive_reports(self) -> Path:
        return self.drive_root / "reports"

    @property
    def drive_exports(self) -> Path:
        return self.drive_root / "exports"

    @property
    def local_data(self) -> Path:
        return self.local_root / "data" / "processed" / "faers"

    @property
    def local_cache(self) -> Path:
        return self.local_root / "feature_cache"


def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def print_runtime() -> dict:
    import psutil
    import torch

    disk = shutil.disk_usage("/content" if Path("/content").exists() else Path.cwd())
    info = {
        "python": sys.version,
        "platform": platform.platform(),
        "cpuCount": os.cpu_count(),
        "hostRamGB": round(psutil.virtual_memory().total / 1024**3, 2),
        "hostRamAvailableGB": round(psutil.virtual_memory().available / 1024**3, 2),
        "localDiskFreeGB": round(disk.free / 1024**3, 2),
        "torch": torch.__version__,
        "cudaAvailable": torch.cuda.is_available(),
        "cudaVersion": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "gpuMemoryGB": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2) if torch.cuda.is_available() else None,
    }
    print(json.dumps(info, indent=2))
    return info


def verify_dependencies() -> dict:
    from importlib.metadata import version

    if not ((3, 10) <= sys.version_info[:2] < (3, 14)):
        raise RuntimeError(f"Unsupported Python {sys.version_info.major}.{sys.version_info.minor}; expected 3.10-3.13")
    installed = {name: version(name) for name in EXPECTED_PACKAGES}
    mismatches = {
        name: {"expected": expected, "installed": installed[name]}
        for name, expected in EXPECTED_PACKAGES.items() if installed[name] != expected
    }
    if mismatches:
        raise RuntimeError(f"Colab dependency versions differ from the constrained environment: {mismatches}")
    import torch

    torch_major_minor = tuple(int(value) for value in torch.__version__.split("+")[0].split(".")[:2])
    if not ((2, 5) <= torch_major_minor < (3, 0)):
        raise RuntimeError(f"Colab CUDA PyTorch must be >=2.5,<3.0; found {torch.__version__}")
    installed["torch"] = torch.__version__
    print(json.dumps({"dependencies": installed}, indent=2))
    return installed


def configure(paths: ColabPaths) -> None:
    repository = paths.repository.resolve()
    sys.path.insert(0, str(repository / "ml" / "src"))
    os.environ["PYTHONPATH"] = str(repository / "ml" / "src")
    os.environ["VITANEXUS_PROCESSED_FAERS_ROOT"] = str(paths.local_data)
    os.environ["VITANEXUS_ML_CACHE_ROOT"] = str(paths.local_cache)
    os.environ["VITANEXUS_ML_RUN_ROOT"] = str(paths.persistent_runs)
    os.environ["VITANEXUS_ML_ARTIFACT_ROOT"] = str(paths.drive_models)
    os.environ["VITANEXUS_ML_REPORT_ROOT"] = str(paths.drive_reports)
    if str(paths.drive_root).startswith("/content/drive/") and not Path("/content/drive/MyDrive").exists():
        raise RuntimeError("Google Drive is not mounted. Run the Drive authorization cell first.")
    for path in (
        paths.drive_data,
        paths.state_bundle,
        paths.persistent_runs,
        paths.drive_models,
        paths.drive_reports,
        paths.drive_exports,
        paths.local_data,
        paths.local_cache,
    ):
        path.mkdir(parents=True, exist_ok=True)
    print(json.dumps({
        "repository": str(repository),
        "driveRoot": str(paths.drive_root),
        "driveData": str(paths.drive_data),
        "stateBundle": str(paths.state_bundle),
        "persistentRuns": str(paths.persistent_runs),
        "localData": str(paths.local_data),
        "localCache": str(paths.local_cache),
        "models": str(paths.drive_models),
        "reports": str(paths.drive_reports),
        "exports": str(paths.drive_exports),
    }, indent=2))


def verify_repository(paths: ColabPaths, branch: str, require_clean: bool = False) -> dict:
    package = paths.repository / "package.json"
    pipeline = paths.repository / "ml" / "src" / "vitanexus_ml" / "models" / "laptop_lightgbm_pipeline.py"
    if not package.exists() or not pipeline.exists():
        raise RuntimeError(f"VitaNexus-RX repository is incomplete at {paths.repository}")
    current_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=paths.repository, text=True).strip()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=paths.repository, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=paths.repository, text=True).strip()
    if current_branch != branch:
        raise RuntimeError(f"Expected branch {branch}, found {current_branch}")
    if require_clean and dirty:
        raise RuntimeError("Colab repository has uncommitted changes; reproducible training requires a committed checkout.")
    result = {"branch": current_branch, "commit": commit, "clean": not bool(dirty)}
    print(json.dumps(result, indent=2))
    return result


def verify_dataset(directory: Path) -> dict:
    results = {}
    for name, expected in EXPECTED_HASHES.items():
        path = directory / name
        if not path.exists():
            raise FileNotFoundError(f"Immutable FAERS input is missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"Immutable FAERS checksum mismatch for {name}: expected {expected}, found {actual}")
        results[name] = {"bytes": path.stat().st_size, "sha256": actual}
    import pyarrow.parquet as pq

    rows = pq.ParquetFile(directory / "cohort.parquet").metadata.num_rows
    if rows != EXPECTED_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_ROWS:,} cohort rows, found {rows:,}")
    results["rows"] = rows
    print(json.dumps(results, indent=2))
    return results


def _copy_verified(source: Path, target: Path, expected_hash: str) -> None:
    if target.exists() and sha256(target) == expected_hash:
        print(f"[stage] reused {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.copying")
    shutil.copy2(source, temporary)
    if sha256(temporary) != expected_hash:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Copy verification failed for {source}")
    temporary.replace(target)
    print(f"[stage] copied and verified {source} -> {target}")


def stage_dataset(paths: ColabPaths) -> None:
    verify_dataset(paths.drive_data)
    required = sum((paths.drive_data / name).stat().st_size for name in EXPECTED_HASHES)
    free = shutil.disk_usage(paths.local_root.parent).free
    if free < required + 2 * 1024**3:
        raise RuntimeError(f"Insufficient /content disk: need at least {(required + 2 * 1024**3) / 1024**3:.2f} GB free")
    for name, expected in EXPECTED_HASHES.items():
        _copy_verified(paths.drive_data / name, paths.local_data / name, expected)
    verify_dataset(paths.local_data)


def import_lightgbm_state(paths: ColabPaths) -> dict:
    from vitanexus_ml.portable_state import import_training_state, verify_training_state_bundle

    manifest = verify_training_state_bundle(paths.state_bundle, paths.local_data / "cohort.parquet")
    cache_bytes = sum(
        int(item["bytes"]) for item in manifest["files"] if item["path"].startswith("feature_cache/")
    )
    free = shutil.disk_usage(paths.local_root.parent).free
    if free < cache_bytes + 2 * 1024**3:
        raise RuntimeError(f"Insufficient /content disk for sparse cache plus safety margin: need {(cache_bytes + 2 * 1024**3) / 1024**3:.2f} GB")
    result = import_training_state(
        paths.state_bundle,
        paths.local_data / "cohort.parquet",
        paths.local_cache,
        paths.persistent_runs,
    )
    print(json.dumps(result, indent=2))
    if result["completedBootstrapReplicas"] != list(range(8)):
        raise RuntimeError("Expected imported LightGBM state to contain exactly bootstrap replicas 0-7.")
    return result


def lightgbm_preflight(paths: ColabPaths, branch: str) -> dict:
    runtime = print_runtime()
    dependencies = verify_dependencies()
    if runtime["hostRamAvailableGB"] < 4:
        raise RuntimeError("At least 4 GB free host RAM is required for the remaining LightGBM stages.")
    repository = verify_repository(paths, branch, require_clean=True)
    dataset = verify_dataset(paths.local_data)
    imported = import_lightgbm_state(paths)
    benchmark_source = paths.repository / "ml" / "reports" / "lightgbm_benchmark.json"
    benchmark_target = paths.drive_reports / "lightgbm_benchmark.json"
    if not benchmark_source.exists():
        raise FileNotFoundError("Committed LightGBM benchmark report is missing from the repository.")
    if not benchmark_target.exists():
        shutil.copy2(benchmark_source, benchmark_target)
    elif sha256(benchmark_target) != sha256(benchmark_source):
        raise RuntimeError("Drive contains a different LightGBM benchmark report; refusing silent replacement.")
    from vitanexus_ml.cli import training_status
    from vitanexus_ml.models.laptop_lightgbm_pipeline import PARTITIONS

    if any(value[1].startswith("2026") for name, value in PARTITIONS.items() if name != "holdout"):
        raise RuntimeError("2026 leakage detected in LightGBM partition configuration.")
    status = training_status()
    completed = int(status["bootstrap"]["completed"])
    total = int(status["bootstrap"]["total"])
    if total != 20 or not 8 <= completed <= total:
        raise RuntimeError(
            "Expected the recovered LightGBM run to retain at least the original "
            f"8/20 replicas and no more than 20/20; found {status['bootstrap']}"
        )
    state = status.get("stages", {})
    completed_indices = sorted(
        int(name.removeprefix("bootstrap_"))
        for name, value in state.items()
        if name.removeprefix("bootstrap_").isdigit() and value.get("status") == "complete"
    )
    if completed_indices != list(range(completed)):
        raise RuntimeError(
            "Bootstrap completion is not a contiguous zero-based prefix; refusing an ambiguous resume: "
            f"{completed_indices}"
        )
    result = {"runtime": runtime, "dependencies": dependencies, "repository": repository, "datasetRows": dataset["rows"], "import": imported, "status": status}
    if completed == 8:
        print("LIGHTGBM PREFLIGHT PASSED: original Windows run recognized with 8/20 bootstrap replicas complete")
    else:
        print(f"LIGHTGBM PREFLIGHT PASSED: persistent Drive run recognized with {completed}/20 bootstrap replicas complete")
    return result


def hgnn_preflight(paths: ColabPaths, branch: str) -> dict:
    runtime = print_runtime()
    dependencies = verify_dependencies()
    if runtime["hostRamAvailableGB"] < 6:
        raise RuntimeError("At least 6 GB free host RAM is required for full HGNN streaming/evaluation.")
    repository = verify_repository(paths, branch, require_clean=True)
    dataset = verify_dataset(paths.local_data)
    manifest_path = paths.drive_models / "training_manifest.json"
    serious_path = paths.drive_models / "serious_outcome.joblib"
    if not manifest_path.exists() or not serious_path.exists():
        raise RuntimeError("Full LightGBM artifacts have not been promoted to Drive; HGNN cannot start.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("fastMode") is not False or manifest.get("fullFinalData") is not True:
        raise RuntimeError("HGNN preflight refuses smoke or partial serious-outcome artifacts.")
    from vitanexus_ml.models.hgnn_colab_pipeline import assert_hgnn_target_edge_integrity, assert_hgnn_temporal_integrity

    assert_hgnn_temporal_integrity()
    assert_hgnn_target_edge_integrity()
    print("HGNN PREFLIGHT PASSED: full LightGBM dependency, corrected temporal split and target-edge safeguards active")
    return {"runtime": runtime, "dependencies": dependencies, "repository": repository, "datasetRows": dataset["rows"], "lightgbmManifest": manifest}
