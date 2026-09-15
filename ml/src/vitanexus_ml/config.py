from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_FAERS_ROOT = PROJECT_ROOT / "data" / "raw" / "faers"
PROCESSED_FAERS_ROOT = Path(
    os.environ.get("VITANEXUS_PROCESSED_FAERS_ROOT", str(PROJECT_ROOT / "data" / "processed" / "faers"))
)
ML_ROOT = PROJECT_ROOT / "ml"
ARTIFACT_ROOT = Path(os.environ.get("VITANEXUS_ML_ARTIFACT_ROOT", str(ML_ROOT / "artifacts")))
REPORT_ROOT = Path(os.environ.get("VITANEXUS_ML_REPORT_ROOT", str(ML_ROOT / "reports")))
TRAINING_WORK_ROOT = Path(
    os.environ.get(
        "VITANEXUS_ML_WORK_ROOT",
        str(Path(os.environ.get("LOCALAPPDATA", ML_ROOT)) / "VitaNexus-RX" / "ml-training"),
    )
)
FEATURE_CACHE_ROOT = Path(os.environ.get("VITANEXUS_ML_CACHE_ROOT", str(TRAINING_WORK_ROOT / "feature_cache")))
TRAINING_RUN_ROOT = Path(os.environ.get("VITANEXUS_ML_RUN_ROOT", str(TRAINING_WORK_ROOT / "training_runs")))

PREPROCESSING_VERSION = "faers-case-cohort-1.0.0"
FEATURE_SCHEMA_VERSION = "faers-runtime-features-1.0.0"
LIGHTGBM_VERSION = "faers-serious-lightgbm-1.0.0"
BOOTSTRAP_VERSION = "faers-serious-bootstrap-1.0.0"
CONFORMAL_VERSION = "faers-split-conformal-1.0.0"
HGNN_VERSION = "faers-specific-adr-hgnn-1.0.0"
TRAINING_PIPELINE_VERSION = "faers-laptop-training-2.0.2"
PORTABLE_STATE_VERSION = "vitanexus-portable-training-state-1.0.0"
INFERENCE_BUNDLE_VERSION = "vitanexus-inference-bundle-1.0.0"
HGNN_TRAINING_PIPELINE_VERSION = "faers-hgnn-colab-training-2.0.0"

SERIOUS_OUTCOME_CODES = frozenset({"DE", "LT", "HO", "DS", "CA", "RI", "OT"})
NO_SERIOUS = "NO_DOCUMENTED_SERIOUS_OUTCOME"
SERIOUS = "SERIOUS_OUTCOME"


@dataclass(frozen=True)
class TrainConfig:
    seed: int = 20260824
    medication_vocabulary_size: int = 1000
    candidate_vocabulary_size: int = 5000
    indication_vocabulary_size: int = 5000
    interaction_vocabulary_size: int = 5000
    adr_min_frequency: int = 500
    adr_max_labels: int = 100
    bootstrap_replicas: int = 20
    conformal_alpha: float = 0.10
    tuning_train_rows: int = 400_000
    tuning_validation_rows: int = 150_000
    benchmark_rows: int = 120_000
    cache_batch_rows: int = 100_000
    training_threads: int = 8
    lightgbm_estimators: int = 800
    tuning_early_stopping_rounds: int = 40


def ensure_output_directories() -> None:
    for path in (
        PROCESSED_FAERS_ROOT,
        ARTIFACT_ROOT,
        REPORT_ROOT,
        TRAINING_WORK_ROOT,
        FEATURE_CACHE_ROOT,
        TRAINING_RUN_ROOT,
    ):
        path.mkdir(parents=True, exist_ok=True)
