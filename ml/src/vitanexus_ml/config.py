from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_FAERS_ROOT = PROJECT_ROOT / "data" / "raw" / "faers"
PROCESSED_FAERS_ROOT = PROJECT_ROOT / "data" / "processed" / "faers"
ML_ROOT = PROJECT_ROOT / "ml"
ARTIFACT_ROOT = ML_ROOT / "artifacts"
REPORT_ROOT = ML_ROOT / "reports"

PREPROCESSING_VERSION = "faers-case-cohort-1.0.0"
FEATURE_SCHEMA_VERSION = "faers-runtime-features-1.0.0"
LIGHTGBM_VERSION = "faers-serious-lightgbm-1.0.0"
BOOTSTRAP_VERSION = "faers-serious-bootstrap-1.0.0"
CONFORMAL_VERSION = "faers-split-conformal-1.0.0"
HGNN_VERSION = "faers-specific-adr-hgnn-1.0.0"

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


def ensure_output_directories() -> None:
    for path in (PROCESSED_FAERS_ROOT, ARTIFACT_ROOT, REPORT_ROOT):
        path.mkdir(parents=True, exist_ok=True)
