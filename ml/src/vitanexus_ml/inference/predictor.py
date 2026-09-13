from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import warnings

import joblib
import numpy as np

from vitanexus_ml.config import ARTIFACT_ROOT, REPORT_ROOT
from vitanexus_ml.conformal.split import prediction_set
from vitanexus_ml.models.metrics import bootstrap_interval
from vitanexus_ml.normalization import normalize_drug, normalize_indication


class ArtifactsUnavailable(RuntimeError):
    """Raised when the full LightGBM runtime bundle cannot be used safely."""


def _lightgbm_probability(model, matrix) -> float:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="X does not have valid feature names, but LGBMClassifier was fitted with feature names",
        )
        return float(model.predict_proba(matrix)[0, 1])


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactsUnavailable(f"Could not read required runtime metadata: {path.name}") from error


def _full_manifest(path: Path) -> dict:
    manifest = _read_json(path)
    if not manifest:
        raise ArtifactsUnavailable("Full LightGBM training manifest is missing.")
    if manifest.get("fastMode") is not False or manifest.get("fullFinalData") is not True:
        raise ArtifactsUnavailable("Runtime rejects smoke or partial LightGBM artifacts.")
    if int(manifest.get("config", {}).get("bootstrap_replicas", 0)) != 20:
        raise ArtifactsUnavailable("Runtime requires exactly 20 configured LightGBM bootstrap replicas.")
    return manifest


def _operating_threshold(report_root: Path, fallback: float) -> tuple[float, str]:
    """Load the frozen 2025Q4-selected threshold when the audited report exists."""
    report = _read_json(report_root / "lightgbm_operating_threshold.json")
    selected = report and report.get("lockedHoldout2026", {}).get("frozenSelectedThreshold", {})
    threshold = selected.get("threshold") if isinstance(selected, dict) else None
    if isinstance(threshold, (float, int)) and 0.0 <= float(threshold) <= 1.0:
        return float(threshold), "frozen_2025Q4_operating_threshold"
    return float(fallback), "training_artifact_threshold"


def _conformal_interpretation(labels: list[str]) -> tuple[str, str]:
    if not labels:
        return "UNAVAILABLE", "The conformal prediction set was empty; clinician review is required."
    if len(labels) == 2:
        return "AMBIGUOUS", "Both outcome classes remain plausible at the configured conformal coverage."
    if labels[0] == "SERIOUS_OUTCOME":
        return "FOCUSED_SERIOUS_OUTCOME", "The prediction set is focused on the serious-outcome class."
    return "FOCUSED_NO_DOCUMENTED_SERIOUS_OUTCOME", "The prediction set is focused on the no-documented-serious-outcome class."


class LightGBMPredictor:
    """Cached, full-artifact-only inference for overall FAERS adverse risk.

    HGNN is intentionally absent: it remains a future, supplementary,
    event-level model and must not gate or alter overall-risk inference.
    """

    def __init__(self, artifact_root: Path = ARTIFACT_ROOT, report_root: Path = REPORT_ROOT):
        self.artifact_root = Path(artifact_root)
        self.manifest = _full_manifest(self.artifact_root / "training_manifest.json")
        serious_path = self.artifact_root / "serious_outcome.joblib"
        if not serious_path.exists():
            raise ArtifactsUnavailable("Full LightGBM model artifact is missing.")
        self.serious = joblib.load(serious_path)
        if self.serious.get("fastMode") is not False:
            raise ArtifactsUnavailable("Runtime rejects a smoke-mode LightGBM model artifact.")
        replica_paths = sorted((self.artifact_root / "bootstrap").glob("replica_*.joblib"))
        expected_names = [f"replica_{index:02d}.joblib" for index in range(20)]
        if len(replica_paths) != 20 or [path.name for path in replica_paths] != expected_names:
            raise ArtifactsUnavailable("Runtime requires 20 contiguous LightGBM bootstrap replicas.")
        self.bootstrap = [joblib.load(path) for path in replica_paths]
        self._validate_feature_schema()
        self.threshold, self.threshold_source = _operating_threshold(report_root, self.serious["threshold"])

    def _validate_feature_schema(self) -> None:
        builder = self.serious.get("featureBuilder")
        model = self.serious.get("model")
        if builder is None or model is None or not hasattr(builder, "feature_names"):
            raise ArtifactsUnavailable("LightGBM feature-builder artifact is incomplete.")
        expected = len(builder.feature_names)
        model_features = int(getattr(model, "n_features_in_", 0))
        if not expected or expected != model_features:
            raise ArtifactsUnavailable("LightGBM artifact feature schema does not match model feature ordering.")

    def predict(self, request: dict) -> dict:
        candidate = normalize_drug(request["candidateDrug"]["canonicalName"])
        indication = normalize_indication(request["indication"]["name"])
        current = [normalize_drug(value) for value in request["patient"].get("currentMedications", [])]
        matrix, coverage = self.serious["featureBuilder"].transform_one({
            "age": request["patient"].get("age"),
            "sex": request["patient"].get("sex"),
            "candidateDrug": candidate,
            "indication": indication,
            "currentMedications": current,
        })
        if int(matrix.shape[1]) != len(self.serious["featureBuilder"].feature_names):
            raise ArtifactsUnavailable("Generated LightGBM feature schema does not match the persisted schema.")
        raw_probability = _lightgbm_probability(self.serious["model"], matrix)
        probability = float(self.serious["calibrator"].predict([raw_probability])[0])
        replica_probabilities = [
            float(replica["calibrator"].predict([_lightgbm_probability(replica["model"], matrix)])[0])
            for replica in self.bootstrap
        ]
        lower, upper = bootstrap_interval(np.asarray(replica_probabilities))
        labels = prediction_set(probability, float(self.serious["qHat"]))
        reliability, interpretation = _conformal_interpretation(labels)
        versions = self.serious["versions"]
        overall = {
            "task": "serious-outcome classification among FAERS adverse-event reports",
            "riskProbability": probability,
            "riskPercent": round(probability * 100, 2),
            "classification": "ELEVATED" if probability >= self.threshold else "LOWER",
            "threshold": self.threshold,
            "thresholdSource": self.threshold_source,
            "uncertainty": {
                "method": "bootstrap_model_variability",
                "level": 0.90,
                "lower": lower,
                "upper": upper,
                "replicas": len(self.bootstrap),
            },
            "adjustedRisk": upper,
            "conformal": {
                "method": "split_conformal_classification",
                "targetCoverage": 0.90,
                "qHat": float(self.serious["qHat"]),
                "predictionSet": labels,
                "setSize": len(labels),
                "reliability": reliability,
                "interpretation": interpretation,
                "calibrationVersion": versions["conformal"],
                "interval": None,
                "intervalNote": "Split-conformal classification produces a prediction set, not a probability confidence interval.",
            },
        }
        return {
            "status": "ok" if coverage.candidateKnown and coverage.indicationKnown and not coverage.unknownCurrentMedications else "DEGRADED_COVERAGE",
            "artifactMode": "FULL",
            "model": "LightGBM",
            "modelVersion": versions["lightgbm"],
            "versions": {
                "preprocessing": versions["preprocessing"],
                "features": versions["features"],
                "lightgbm": versions["lightgbm"],
                "bootstrap": versions["bootstrap"],
                "conformal": versions["conformal"],
            },
            "overall": overall,
            "inputCoverage": coverage.__dict__,
            "dataWindow": self.serious["dataWindow"],
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "clinicalInterpretation": {
                "population": "FAERS adverse-event reporting context",
                "limitations": [
                    "FAERS is a spontaneous-reporting system and has reporting bias.",
                    "The risk probability is not exposed-population incidence.",
                    "Conformal output expresses classification-set reliability, not a conventional probability confidence interval.",
                ],
            },
        }


# Retained as a stable import for the FastAPI app and downstream consumers.
Predictor = LightGBMPredictor
