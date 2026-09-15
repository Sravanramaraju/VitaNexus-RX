from __future__ import annotations

import json
import math
import os
import gc
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from numpy.lib.format import open_memmap
from scipy import sparse

from vitanexus_ml.config import PREPROCESSING_VERSION, TRAINING_PIPELINE_VERSION, TrainConfig
from vitanexus_ml.features.builder import FeatureBuilder, _items
from vitanexus_ml.normalization import normalize_drug, normalize_indication
from vitanexus_ml.training_runtime import ProgressReporter, atomic_joblib, atomic_json, atomic_replace, file_sha256, stable_hash


FEATURE_COLUMNS = ["age_years", "sex", "candidate_drug", "indication", "current_medications"]
CACHE_COLUMNS = ["caseid", "quarter", "has_serious_outcome", *FEATURE_COLUMNS]
DEVELOPMENT_START = "2022Q1"
DEVELOPMENT_END = "2024Q4"
QUARTERS = tuple(f"{year}Q{quarter}" for year in range(2022, 2027) for quarter in range(1, 5) if f"{year}Q{quarter}" <= "2026Q2")
QUARTER_TO_CODE = {quarter: index for index, quarter in enumerate(QUARTERS)}


def normalize_processed_input_identity(identity: dict) -> dict:
    """Return the location-independent scientific identity of processed input."""
    files = identity.get("files", {})
    return {
        "identitySchema": "faers-processed-input-1",
        "preprocessingVersion": identity.get("preprocessingVersion", PREPROCESSING_VERSION),
        "files": {
            name: {"sha256": str(value["sha256"]).lower(), "bytes": int(value["bytes"])}
            for name, value in sorted(files.items())
        },
    }


def processed_input_identity(cohort_path: Path) -> dict:
    cohort_path = cohort_path.resolve()
    related = [cohort_path, cohort_path.parent / "dataset_manifest.json", cohort_path.parent / "data_quality.json"]
    missing = [str(path) for path in related if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Required immutable processed inputs are missing: {', '.join(missing)}")
    return normalize_processed_input_identity({
        "preprocessingVersion": PREPROCESSING_VERSION,
        "files": {
            path.name: {"sha256": file_sha256(path), "bytes": path.stat().st_size}
            for path in related
        },
    })


def processed_input_location(cohort_path: Path) -> dict:
    """Informational provenance; never include this value in cache/run keys."""
    return {"cohortPath": str(cohort_path.resolve())}


def assert_input_identity(cohort_path: Path, expected: dict) -> None:
    current = processed_input_identity(cohort_path)
    if current != normalize_processed_input_identity(expected):
        raise RuntimeError("Immutable processed FAERS input changed during or between training stages; refusing to continue.")


@dataclass
class FeatureCache:
    root: Path
    builder: FeatureBuilder
    features: sparse.csr_matrix
    labels: np.ndarray
    quarter_codes: np.ndarray
    caseids: np.ndarray
    metadata: dict

    @property
    def rows(self) -> int:
        return int(self.features.shape[0])


def _cache_identity(input_identity: dict, config: TrainConfig) -> dict:
    return {
        "pipelineVersion": TRAINING_PIPELINE_VERSION,
        "input": input_identity,
        "featureConfig": {
            key: value for key, value in asdict(config).items()
            if key.endswith("vocabulary_size")
        },
        "vocabularyFitWindow": f"{DEVELOPMENT_START}-{DEVELOPMENT_END}",
    }


def _chunk_path(chunk_root: Path, index: int) -> Path:
    return chunk_root / f"chunk_{index:05d}.npz"


def _atomic_npz(path: Path, **arrays) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as target:
        np.savez(target, **arrays)
    atomic_replace(temporary, path)


def _fit_streaming_builder(parquet: pq.ParquetFile, config: TrainConfig, target: Path) -> FeatureBuilder:
    if target.exists():
        builder = joblib.load(target)
        if builder.metadata()["config"] != asdict(config):
            raise RuntimeError("Cached feature-builder configuration does not match the requested training configuration.")
        print("[feature-vocabulary] resumed from checkpoint", flush=True)
        return builder

    candidate_counts: Counter = Counter()
    indication_counts: Counter = Counter()
    medication_counts: Counter = Counter()
    interaction_counts: Counter = Counter()
    total_batches = math.ceil(parquet.metadata.num_rows / config.cache_batch_rows)
    progress = ProgressReporter("feature-vocabulary", total_batches)
    for batch_index, batch in enumerate(parquet.iter_batches(batch_size=config.cache_batch_rows, columns=["quarter", "candidate_drug", "indication", "current_medications"]), start=1):
        frame = batch.to_pandas()
        frame = frame[(frame["quarter"] >= DEVELOPMENT_START) & (frame["quarter"] <= DEVELOPMENT_END)]
        candidates = [normalize_drug(value) for value in frame["candidate_drug"]]
        indications = [normalize_indication(value) for value in frame["indication"]]
        candidate_counts.update(candidates)
        indication_counts.update(indications)
        interaction_counts.update(f"{candidate}::{indication}" for candidate, indication in zip(candidates, indications))
        medication_counts.update(
            normalize_drug(item)
            for values in frame["current_medications"]
            for item in _items(values)
        )
        progress.update(batch_index, f"development rows scanned={sum(candidate_counts.values()):,}")
    builder = FeatureBuilder(config).fit_from_counts(candidate_counts, indication_counts, medication_counts, interaction_counts)
    atomic_joblib(target, builder)
    progress.finish(f"features={len(builder.feature_names):,}")
    return builder


def _build_chunks(parquet: pq.ParquetFile, builder: FeatureBuilder, config: TrainConfig, chunk_root: Path) -> list[Path]:
    total_batches = math.ceil(parquet.metadata.num_rows / config.cache_batch_rows)
    progress = ProgressReporter("sparse-feature-cache", total_batches)
    paths: list[Path] = []
    rows_done = 0
    for chunk_index, batch in enumerate(parquet.iter_batches(batch_size=config.cache_batch_rows, columns=CACHE_COLUMNS)):
        path = _chunk_path(chunk_root, chunk_index)
        paths.append(path)
        if path.exists():
            with np.load(path, allow_pickle=False) as cached:
                rows_done += int(cached["shape"][0])
            progress.update(chunk_index + 1, f"resumed rows={rows_done:,}")
            continue
        frame = batch.to_pandas()
        unknown_quarters = sorted(set(frame["quarter"]) - set(QUARTER_TO_CODE))
        if unknown_quarters:
            raise RuntimeError(f"Unexpected quarters in immutable cohort: {unknown_quarters}")
        matrix = builder.transform(frame)
        labels = frame["has_serious_outcome"].to_numpy(dtype=np.int8, copy=True)
        quarters = frame["quarter"].map(QUARTER_TO_CODE).to_numpy(dtype=np.int8, copy=True)
        caseids = pd.to_numeric(frame["caseid"], errors="raise").to_numpy(dtype=np.int64, copy=True)
        _atomic_npz(
            path,
            data=matrix.data.astype(np.float32, copy=False),
            indices=matrix.indices.astype(np.int32, copy=False),
            indptr=matrix.indptr.astype(np.int64, copy=False),
            shape=np.asarray(matrix.shape, dtype=np.int64),
            labels=labels,
            quarters=quarters,
            caseids=caseids,
        )
        rows_done += len(frame)
        progress.update(chunk_index + 1, f"rows={rows_done:,}; nnz={matrix.nnz:,}")
    progress.finish(f"rows={rows_done:,}")
    return paths


def _finalize_chunks(root: Path, chunks: list[Path], feature_count: int, expected_rows: int) -> dict:
    metadata_path = root / "metadata.json"
    final_paths = {name: root / f"{name}.npy" for name in ("data", "indices", "indptr", "labels", "quarter_codes", "caseids")}
    if metadata_path.exists() and all(path.exists() for path in final_paths.values()):
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    chunk_metadata = []
    total_rows = 0
    total_nnz = 0
    for path in chunks:
        if not path.exists():
            raise RuntimeError(f"Sparse feature chunk is missing: {path}")
        with np.load(path, allow_pickle=False) as chunk:
            rows, columns = (int(value) for value in chunk["shape"])
            if columns != feature_count:
                raise RuntimeError(f"Feature-count mismatch in {path}")
            chunk_metadata.append((path, rows, len(chunk["data"])))
            total_rows += rows
            total_nnz += len(chunk["data"])
    if total_rows != expected_rows:
        raise RuntimeError(f"Sparse cache row count {total_rows:,} does not match immutable cohort {expected_rows:,}")

    temporary_paths = {name: path.with_name(f".{path.name}.{os.getpid()}.building") for name, path in final_paths.items()}
    arrays = {
        "data": open_memmap(temporary_paths["data"], mode="w+", dtype=np.float32, shape=(total_nnz,)),
        "indices": open_memmap(temporary_paths["indices"], mode="w+", dtype=np.int32, shape=(total_nnz,)),
        "indptr": open_memmap(temporary_paths["indptr"], mode="w+", dtype=np.int64, shape=(total_rows + 1,)),
        "labels": open_memmap(temporary_paths["labels"], mode="w+", dtype=np.int8, shape=(total_rows,)),
        "quarter_codes": open_memmap(temporary_paths["quarter_codes"], mode="w+", dtype=np.int8, shape=(total_rows,)),
        "caseids": open_memmap(temporary_paths["caseids"], mode="w+", dtype=np.int64, shape=(total_rows,)),
    }
    arrays["indptr"][0] = 0
    row_offset = 0
    nnz_offset = 0
    progress = ProgressReporter("finalize-feature-cache", len(chunk_metadata))
    for index, (path, rows, nnz) in enumerate(chunk_metadata, start=1):
        with np.load(path, allow_pickle=False) as chunk:
            arrays["data"][nnz_offset:nnz_offset + nnz] = chunk["data"]
            arrays["indices"][nnz_offset:nnz_offset + nnz] = chunk["indices"]
            arrays["indptr"][row_offset + 1:row_offset + rows + 1] = chunk["indptr"][1:] + nnz_offset
            arrays["labels"][row_offset:row_offset + rows] = chunk["labels"]
            arrays["quarter_codes"][row_offset:row_offset + rows] = chunk["quarters"]
            arrays["caseids"][row_offset:row_offset + rows] = chunk["caseids"]
        row_offset += rows
        nnz_offset += nnz
        progress.update(index, f"rows={row_offset:,}; nnz={nnz_offset:,}")
    for array in arrays.values():
        array.flush()
    for array in arrays.values():
        mmap = getattr(array, "_mmap", None)
        if mmap is not None:
            mmap.close()
    del array, mmap
    del arrays
    gc.collect()
    for name, final_path in final_paths.items():
        atomic_replace(temporary_paths[name], final_path)
    metadata = {
        "rows": total_rows,
        "columns": feature_count,
        "nnz": total_nnz,
        "quarterMapping": QUARTER_TO_CODE,
        "caseidUniqueExpected": True,
    }
    atomic_json(metadata_path, metadata)
    progress.finish()
    return metadata


def build_or_load_feature_cache(cohort_path: Path, config: TrainConfig, cache_parent: Path) -> FeatureCache:
    input_identity = processed_input_identity(cohort_path)
    identity = _cache_identity(input_identity, config)
    cache_key = stable_hash(identity)[:20]
    root = cache_parent / cache_key
    root.mkdir(parents=True, exist_ok=True)
    identity_path = root / "identity.json"
    if identity_path.exists():
        existing = json.loads(identity_path.read_text(encoding="utf-8"))
        if existing != identity:
            raise RuntimeError("Feature-cache identity mismatch; refusing silent reuse.")
    else:
        atomic_json(identity_path, identity)

    parquet = pq.ParquetFile(cohort_path)
    builder_path = root / "feature_builder.joblib"
    metadata_path = root / "metadata.json"
    final_names = ("data", "indices", "indptr", "labels", "quarter_codes", "caseids")
    cache_complete = builder_path.exists() and metadata_path.exists() and all((root / f"{name}.npy").exists() for name in final_names)
    if cache_complete:
        print(f"[sparse-feature-cache] resumed complete cache {cache_key}", flush=True)
        builder = joblib.load(builder_path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        builder = _fit_streaming_builder(parquet, config, builder_path)
        chunks = _build_chunks(parquet, builder, config, root / "chunks")
        metadata = _finalize_chunks(root, chunks, len(builder.feature_names), parquet.metadata.num_rows)
    assert_input_identity(cohort_path, input_identity)

    data = np.load(root / "data.npy", mmap_mode="r")
    indices = np.load(root / "indices.npy", mmap_mode="r")
    indptr = np.load(root / "indptr.npy", mmap_mode="r")
    features = sparse.csr_matrix((data, indices, indptr), shape=(metadata["rows"], metadata["columns"]), copy=False)
    return FeatureCache(
        root=root,
        builder=builder,
        features=features,
        labels=np.load(root / "labels.npy", mmap_mode="r"),
        quarter_codes=np.load(root / "quarter_codes.npy", mmap_mode="r"),
        caseids=np.load(root / "caseids.npy", mmap_mode="r"),
        metadata={**metadata, "identity": identity, "cacheKey": cache_key},
    )
