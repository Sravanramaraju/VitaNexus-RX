from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


FORMAT_VERSION = 1
DRIVE_DIRECTORY = "VitaNexus-RX-ML"
MANIFEST_NAME = "transfer_manifest.json"
INCLUDE_DIRECTORIES = (
    "training_state/training_runs/hgnn",
    "models/runtime",
    "reports",
    "exports/lightgbm_full_inference",
)
INCLUDE_FILES = (
    "data/processed/faers/cohort.parquet",
    "data/processed/faers/dataset_manifest.json",
    "data/processed/faers/data_quality.json",
)
REQUIRED_SUFFIXES = (
    "training_state/training_runs/hgnn",
    "models/runtime/training_manifest.json",
    "reports/lightgbm_metrics.json",
    "reports/conformal_metrics.json",
    "reports/final_temporal_evaluation.json",
    "exports/lightgbm_full_inference/inference_bundle_manifest.json",
    "data/processed/faers/cohort.parquet",
    "data/processed/faers/dataset_manifest.json",
    "data/processed/faers/data_quality.json",
)


def _sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _selected_files(source_root: Path, output: Path) -> list[Path]:
    selected: set[Path] = set()
    for relative in INCLUDE_FILES:
        path = source_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Required transfer file is missing: {path}")
        selected.add(path)
    for relative in INCLUDE_DIRECTORIES:
        directory = source_root / relative
        if not directory.is_dir():
            raise FileNotFoundError(f"Required transfer directory is missing: {directory}")
        selected.update(
            path for path in directory.rglob("*")
            if path.is_file()
            and path.resolve() != output.resolve()
            and not path.name.startswith(".")
            and not path.name.endswith((".tmp", ".copying"))
        )
    return sorted(selected, key=lambda path: path.relative_to(source_root).as_posix())


def export_snapshot(source_root: Path, output: Path) -> dict:
    source_root = source_root.resolve()
    output = output.resolve()
    files = _selected_files(source_root, output)
    hgnn_states = [path for path in files if path.name == "state.json" and "training_runs/hgnn" in path.as_posix()]
    latest_checkpoints = [path for path in files if path.name == "hgnn_selection_latest.pt"]
    if not hgnn_states or not latest_checkpoints:
        raise RuntimeError("No resumable HGNN state/checkpoint was found in Drive.")

    entries = []
    total_bytes = 0
    for index, path in enumerate(files, start=1):
        relative = path.relative_to(source_root).as_posix()
        size = path.stat().st_size
        entries.append({"path": f"{DRIVE_DIRECTORY}/{relative}", "bytes": size, "sha256": _sha256(path)})
        total_bytes += size
        print(f"[snapshot] hashed {index}/{len(files)}: {relative}", flush=True)

    manifest = {
        "formatVersion": FORMAT_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourceDriveRoot": str(source_root),
        "fileCount": len(entries),
        "totalBytes": total_bytes,
        "files": entries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
            for index, (path, entry) in enumerate(zip(files, entries), start=1):
                archive.write(path, entry["path"])
                print(f"[snapshot] archived {index}/{len(files)}: {entry['path']}", flush=True)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    result = {
        "status": "EXPORTED",
        "archive": str(output),
        "fileCount": len(entries),
        "totalBytes": total_bytes,
        "archiveBytes": output.stat().st_size,
        "archiveSha256": _sha256(output),
    }
    print(json.dumps(result, indent=2), flush=True)
    return result


def _safe_member(name: str) -> PurePosixPath:
    member = PurePosixPath(name)
    if member.is_absolute() or ".." in member.parts or "\\" in name:
        raise RuntimeError(f"Unsafe archive member: {name}")
    return member


def _crc32(path: Path, chunk_size: int = 8 * 1024 * 1024) -> int:
    checksum = 0
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            checksum = zlib.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF


def restore_drive_download(bundle: Path, my_drive: Path, expected_sha256: str | None = None) -> dict:
    """Restore a Google Drive folder-download ZIP safely and resumably."""
    bundle = bundle.resolve()
    my_drive = my_drive.resolve()
    if expected_sha256:
        actual_sha256 = _sha256(bundle)
        if actual_sha256.lower() != expected_sha256.lower():
            raise RuntimeError(
                f"Drive backup checksum mismatch: expected {expected_sha256}, found {actual_sha256}"
            )
    else:
        actual_sha256 = _sha256(bundle)

    restored = reused = 0
    with zipfile.ZipFile(bundle, "r") as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"Drive backup ZIP integrity failed at {bad}")
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        if not entries or any(_safe_member(entry.filename).parts[0] != DRIVE_DIRECTORY for entry in entries):
            raise RuntimeError(f"Drive backup must contain one top-level {DRIVE_DIRECTORY}/ directory.")
        for index, entry in enumerate(entries, start=1):
            member = _safe_member(entry.filename)
            target = my_drive.joinpath(*member.parts)
            resolved_target = target.resolve()
            try:
                resolved_target.relative_to(my_drive)
            except ValueError as error:
                raise RuntimeError(f"Archive member escapes the Drive root: {entry.filename}") from error
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_file() and target.stat().st_size == entry.file_size and _crc32(target) == entry.CRC:
                reused += 1
                print(f"[restore] reused {index}/{len(entries)}: {entry.filename}", flush=True)
                continue
            temporary = target.with_name(f".{target.name}.restoring")
            temporary.unlink(missing_ok=True)
            checksum = 0
            size = 0
            try:
                with archive.open(entry) as source, temporary.open("wb") as sink:
                    while chunk := source.read(8 * 1024 * 1024):
                        sink.write(chunk)
                        checksum = zlib.crc32(chunk, checksum)
                        size += len(chunk)
                if size != entry.file_size or (checksum & 0xFFFFFFFF) != entry.CRC:
                    raise RuntimeError(f"Restored file failed ZIP size/CRC verification: {entry.filename}")
                os.replace(temporary, target)
                restored += 1
                print(f"[restore] restored {index}/{len(entries)}: {entry.filename}", flush=True)
            finally:
                temporary.unlink(missing_ok=True)

    drive_root = my_drive / DRIVE_DIRECTORY
    required = [
        drive_root / "data/processed/faers/cohort.parquet",
        drive_root / "data/processed/faers/dataset_manifest.json",
        drive_root / "data/processed/faers/data_quality.json",
        drive_root / "models/runtime/training_manifest.json",
        drive_root / "models/runtime/serious_outcome.joblib",
        drive_root / "reports/lightgbm_metrics.json",
        drive_root / "exports/lightgbm_full_inference/inference_bundle_manifest.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    hgnn_runs = list((drive_root / "training_state/training_runs/hgnn").glob("*/state.json"))
    hgnn_latest = list((drive_root / "training_state/training_runs/hgnn").glob("*/hgnn_selection_latest.pt"))
    if missing or not hgnn_runs or not hgnn_latest:
        raise RuntimeError(
            f"Restored Drive state is incomplete; missing={missing}, hgnnState={len(hgnn_runs)}, "
            f"hgnnLatest={len(hgnn_latest)}"
        )
    result = {
        "status": "RESTORED_AND_VERIFIED",
        "archive": str(bundle),
        "archiveSha256": actual_sha256,
        "driveRoot": str(drive_root),
        "filesRestored": restored,
        "filesReused": reused,
        "fileCount": restored + reused,
    }
    print(json.dumps(result, indent=2), flush=True)
    return result


def verify_snapshot(bundle: Path) -> dict:
    bundle = bundle.resolve()
    with zipfile.ZipFile(bundle, "r") as archive:
        names = archive.namelist()
        if MANIFEST_NAME not in names:
            raise RuntimeError(f"Archive is missing {MANIFEST_NAME}")
        if len(names) != len(set(names)):
            raise RuntimeError("Archive contains duplicate member names.")
        manifest = json.loads(archive.read(MANIFEST_NAME))
        if manifest.get("formatVersion") != FORMAT_VERSION:
            raise RuntimeError(f"Unsupported snapshot format: {manifest.get('formatVersion')}")
        expected = {entry["path"]: entry for entry in manifest.get("files", [])}
        actual = set(names) - {MANIFEST_NAME}
        if actual != set(expected):
            raise RuntimeError("Archive file list differs from its transfer manifest.")
        for index, name in enumerate(sorted(actual), start=1):
            _safe_member(name)
            digest = hashlib.sha256()
            size = 0
            with archive.open(name) as source:
                while chunk := source.read(8 * 1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
            entry = expected[name]
            if size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
                raise RuntimeError(f"Snapshot checksum mismatch: {name}")
            print(f"[snapshot] verified {index}/{len(actual)}: {name}", flush=True)

    paths = set(expected)
    for suffix in REQUIRED_SUFFIXES[1:]:
        if f"{DRIVE_DIRECTORY}/{suffix}" not in paths:
            raise RuntimeError(f"Snapshot is missing required content: {suffix}")
    if not any(path.startswith(f"{DRIVE_DIRECTORY}/{REQUIRED_SUFFIXES[0]}/") for path in paths):
        raise RuntimeError("Snapshot is missing HGNN training state.")
    result = {
        "status": "VERIFIED",
        "archive": str(bundle),
        "archiveSha256": _sha256(bundle),
        "fileCount": len(expected),
        "totalBytes": sum(entry["bytes"] for entry in expected.values()),
    }
    print(json.dumps(result, indent=2), flush=True)
    return result


def import_snapshot(bundle: Path, destination: Path) -> dict:
    verification = verify_snapshot(bundle)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Import destination already exists: {destination}")
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        with zipfile.ZipFile(bundle.resolve(), "r") as archive:
            for name in archive.namelist():
                if name == MANIFEST_NAME:
                    continue
                member = _safe_member(name)
                relative_parts = member.parts[1:] if member.parts and member.parts[0] == DRIVE_DIRECTORY else member.parts
                target = staging.joinpath(*relative_parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink, length=8 * 1024 * 1024)
        (staging / MANIFEST_NAME).write_text(
            json.dumps({**verification, "importedAt": datetime.now(timezone.utc).isoformat()}, indent=2),
            encoding="utf-8",
        )
        os.replace(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    result = {**verification, "status": "IMPORTED", "destination": str(destination)}
    print(json.dumps(result, indent=2), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Export, verify, or safely import a VitaNexus Colab training snapshot.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--source-root", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--bundle", type=Path, required=True)
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--bundle", type=Path, required=True)
    import_parser.add_argument("--destination", type=Path, required=True)
    restore_parser = subparsers.add_parser("restore-drive-download")
    restore_parser.add_argument("--bundle", type=Path, required=True)
    restore_parser.add_argument("--my-drive", type=Path, required=True)
    restore_parser.add_argument("--expected-sha256", default=None)
    args = parser.parse_args()
    if args.command == "export":
        export_snapshot(args.source_root, args.output)
    elif args.command == "verify":
        verify_snapshot(args.bundle)
    elif args.command == "import":
        import_snapshot(args.bundle, args.destination)
    else:
        restore_drive_download(args.bundle, args.my_drive, args.expected_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
