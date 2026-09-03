from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd
import torch

from vitanexus_ml.config import ARTIFACT_ROOT, HGNN_VERSION, NO_SERIOUS, SERIOUS
from vitanexus_ml.conformal.split import prediction_set
from vitanexus_ml.models.hgnn import HeterogeneousAdrNetwork, _predict_in_batches
from vitanexus_ml.models.metrics import bootstrap_interval
from vitanexus_ml.normalization import normalize_drug, normalize_indication


class ArtifactsUnavailable(RuntimeError):
    pass


def _lightgbm_probability(model, matrix) -> float:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="X does not have valid feature names, but LGBMClassifier was fitted with feature names")
        return float(model.predict_proba(matrix)[0, 1])


class Predictor:
    def __init__(self, artifact_root: Path = ARTIFACT_ROOT):
        serious_path = artifact_root / "serious_outcome.joblib"
        metadata_path = artifact_root / "hgnn_metadata.joblib"
        state_path = artifact_root / "hgnn_state.pt"
        missing = [str(path) for path in (serious_path, metadata_path, state_path) if not path.exists()]
        if missing:
            raise ArtifactsUnavailable(f"Required trained artifacts are missing: {', '.join(missing)}")
        self.serious = joblib.load(serious_path)
        self.bootstrap = [joblib.load(path) for path in sorted((artifact_root / "bootstrap").glob("replica_*.joblib"))]
        if not self.bootstrap:
            raise ArtifactsUnavailable("No bootstrap replica artifacts were found")
        self.hgnn_metadata = joblib.load(metadata_path)
        self.hgnn = HeterogeneousAdrNetwork(self.hgnn_metadata["hiddenChannels"], len(self.hgnn_metadata["vocabulary"]))
        example = self._hgnn_frame({"patient": {"age": None, "sex": "UNKNOWN", "currentMedications": []}, "candidateDrug": {"canonicalName": "UNKNOWN"}, "indication": {"name": "UNKNOWN"}})
        graph_probabilities = _predict_in_batches(self.hgnn, example, self.hgnn_metadata["vocabulary"], self.hgnn_metadata["associations"], 1)
        del graph_probabilities
        self.hgnn.load_state_dict(torch.load(state_path, map_location="cpu", weights_only=True))
        self.hgnn.eval()

    def predict(self, request: dict) -> dict:
        candidate = normalize_drug(request["candidateDrug"]["canonicalName"])
        indication = normalize_indication(request["indication"]["name"])
        current = [normalize_drug(value) for value in request["patient"].get("currentMedications", [])]
        matrix, coverage = self.serious["featureBuilder"].transform_one({
            "age": request["patient"].get("age"), "sex": request["patient"].get("sex"),
            "candidateDrug": candidate, "indication": indication, "currentMedications": current,
        })
        raw = _lightgbm_probability(self.serious["model"], matrix)
        point = float(self.serious["calibrator"].predict([raw])[0])
        replica_probabilities = [float(item["calibrator"].predict([_lightgbm_probability(item["model"], matrix)])[0]) for item in self.bootstrap]
        lower, upper = bootstrap_interval(np.asarray(replica_probabilities))
        conformal_set = prediction_set(point, float(self.serious["qHat"]))
        hgnn_raw = _predict_in_batches(self.hgnn, self._hgnn_frame(request), self.hgnn_metadata["vocabulary"], self.hgnn_metadata["associations"], 1)[0]
        hgnn_scores = np.asarray([
            calibrator.predict([hgnn_raw[index]])[0] if calibrator else hgnn_raw[index]
            for index, calibrator in enumerate(self.hgnn_metadata["calibrators"])
        ])
        top_indices = np.argsort(-hgnn_scores)[:10]
        specific = [{"term": self.hgnn_metadata["vocabulary"][index]["term"].title(), "score": float(hgnn_scores[index])} for index in top_indices]
        smoke_artifact = bool(self.serious.get("fastMode") or self.hgnn_metadata.get("fastMode"))
        status = "ok" if coverage.candidateKnown and coverage.indicationKnown and not coverage.unknownCurrentMedications and not smoke_artifact else "DEGRADED_COVERAGE"
        return {
            "status": status,
            "artifactMode": "FAST_SMOKE" if smoke_artifact else "FULL",
            "versions": {**self.serious["versions"], "hgnn": self.hgnn_metadata.get("version", HGNN_VERSION)},
            "overall": {
                "task": "serious-outcome classification among FAERS adverse-event reports",
                "calibratedProbability": point,
                "uncertainty": {"method": "bootstrap", "level": 0.90, "lower": lower, "upper": upper, "replicas": len(self.bootstrap)},
                "conservativeUpperBound": upper,
                "conformal": {"method": "split_conformal", "targetCoverage": 0.90, "qHat": float(self.serious["qHat"]), "predictionSet": conformal_set, "setSize": len(conformal_set), "calibrationVersion": self.serious["versions"]["conformal"]},
            },
            "specificAdrs": specific,
            "inputCoverage": coverage.__dict__,
            "dataWindow": self.serious["dataWindow"],
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "clinicalInterpretation": {
                "population": "FAERS adverse-event reporting context",
                "limitations": ["FAERS is a spontaneous-reporting system and has reporting bias.", "The probability is not exposed-population incidence.", "Specific ADR scores are model scores, not population incidence."],
            },
        }

    @staticmethod
    def _hgnn_frame(request: dict) -> pd.DataFrame:
        patient = request["patient"]
        return pd.DataFrame([{
            "age_years": patient.get("age"), "sex": patient.get("sex"),
            "candidate_drug": request["candidateDrug"]["canonicalName"],
            "indication": request["indication"]["name"],
            "current_medications": patient.get("currentMedications", []), "reactions": [],
        }])
