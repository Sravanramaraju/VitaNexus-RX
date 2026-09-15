from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import joblib
import pandas as pd
import torch

from vitanexus_ml.config import PROJECT_ROOT
from vitanexus_ml.models.hgnn import HeterogeneousAdrNetwork, RELATIONS, build_heterodata
from vitanexus_ml.models.hgnn_post_training import verify_checkpoint_integrity
from vitanexus_ml.normalization import normalize_drug, normalize_indication, normalize_sex


class HgnnArtifactsUnavailable(RuntimeError):
    """Raised when the protected baseline HGNN bundle cannot be served safely."""


def _stable_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _ordered_vocabulary(path: Path) -> tuple[list[dict], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        raise HgnnArtifactsUnavailable("The protected HGNN event vocabulary is missing or empty.")
    indexes = [int(item.get("index", -1)) for item in items]
    if indexes != list(range(len(items))) or any(not str(item.get("term", "")).strip() for item in items):
        raise HgnnArtifactsUnavailable("The protected HGNN event vocabulary is not ordered and contiguous.")
    return items, payload if isinstance(payload, dict) else {}


class HgnnPredictor:
    """Cached inference for the protected epoch-20 baseline HGNN.

    The predictor deliberately exposes uncalibrated sigmoid event scores only.
    It has no dependency on LightGBM, its bootstrap replicas, conformal metadata,
    or the recommendation-ranking service.
    """

    def __init__(self, integrity_manifest_path: Path | None = None, device_name: str | None = None):
        configured_manifest = os.environ.get("VITANEXUS_HGNN_INTEGRITY_MANIFEST")
        self.integrity_manifest_path = Path(
            integrity_manifest_path
            or configured_manifest
            or PROJECT_ROOT / "ml" / "training_state" / "hgnn_post_training" / "checkpoint_integrity.json"
        )
        try:
            manifest = verify_checkpoint_integrity(self.integrity_manifest_path)
            snapshot_root = Path(manifest["snapshotRoot"])
            run_root = snapshot_root / "training_state" / "training_runs" / "hgnn" / manifest["runKey"]
            checkpoint_name = manifest["model"]["selection"]["checkpoint"]
            checkpoint = torch.load(run_root / checkpoint_name, map_location="cpu", weights_only=False)
            vocabulary, vocabulary_payload = _ordered_vocabulary(run_root / "adr_vocabulary.json")
            associations = joblib.load(run_root / "development_associations.joblib")
        except HgnnArtifactsUnavailable:
            raise
        except Exception as error:
            raise HgnnArtifactsUnavailable("The protected baseline HGNN artifacts could not be validated.") from error

        self.device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.manifest = manifest
        self.vocabulary = vocabulary
        self.associations = associations
        self.top_k = max(1, min(int(os.environ.get("HGNN_TOP_K_EVENTS", "10")), len(vocabulary)))

        model_metadata = manifest.get("model", {})
        configuration = model_metadata.get("configuration", {})
        hidden_channels = int(configuration.get("hidden_channels", 0))
        training_epoch = int(model_metadata.get("selection", {}).get("epoch", 0))
        checkpoint_epoch = int(checkpoint.get("epoch", -1)) + 1
        model_state = checkpoint.get("modelState")
        if hidden_channels <= 0 or not isinstance(model_state, dict):
            raise HgnnArtifactsUnavailable("The protected HGNN architecture metadata is incomplete.")
        if training_epoch != checkpoint_epoch:
            raise HgnnArtifactsUnavailable("The protected HGNN checkpoint epoch does not match its manifest.")
        output_weight = model_state.get("output.weight")
        if output_weight is None or tuple(output_weight.shape) != (len(vocabulary), hidden_channels):
            raise HgnnArtifactsUnavailable("The HGNN output dimension does not match the event vocabulary.")

        checkpoint_identity = checkpoint.get("checkpointMetadata", {})
        if checkpoint_identity.get("vocabularyIdentity") != vocabulary_payload.get("identity"):
            raise HgnnArtifactsUnavailable("The HGNN checkpoint and event vocabulary identities differ.")
        if checkpoint_identity.get("targetEdgesExcluded") is not True:
            raise HgnnArtifactsUnavailable("The HGNN target-edge leakage safeguard is not recorded.")

        self.model = HeterogeneousAdrNetwork(hidden_channels, len(vocabulary)).to(self.device)
        initialization_frame = pd.DataFrame([{
            "age_years": None,
            "sex": "UNKNOWN",
            "candidate_drug": "__HGNN_RUNTIME_INITIALIZATION__",
            "indication": "__HGNN_RUNTIME_INITIALIZATION__",
            "current_medications": [],
        }])
        with torch.inference_mode():
            self.model(build_heterodata(
                initialization_frame, vocabulary, associations, include_targets=False
            ).to(self.device))
        try:
            self.model.load_state_dict(model_state, strict=True)
        except Exception as error:
            raise HgnnArtifactsUnavailable("The HGNN architecture is incompatible with the protected checkpoint.") from error
        self.model.eval()

        run_identity = checkpoint_identity.get("runIdentity", {})
        self.model_version = str(model_metadata.get("version") or run_identity.get("modelVersion"))
        self.checkpoint_version = manifest["files"][checkpoint_name]["sha256"]
        self.training_epoch = training_epoch
        self.event_vocabulary_version = str(vocabulary_payload.get("identity"))
        self.graph_schema_version = str(run_identity.get("pipelineVersion"))
        self.feature_schema_version = self.graph_schema_version

    def get_status(self) -> dict:
        return {
            "status": "READY",
            "modelType": "HGNN",
            "modelFamily": "HGNN",
            "modelStage": "BASELINE",
            "validationStatus": "AUDIT_PENDING",
            "modelVersion": self.model_version,
            "checkpointVersion": self.checkpoint_version,
            "trainingEpoch": self.training_epoch,
            "eventVocabularyVersion": self.event_vocabulary_version,
            "eventVocabularySize": len(self.vocabulary),
            "graphSchemaVersion": self.graph_schema_version,
            "featureSchemaVersion": self.feature_schema_version,
            "device": self.device.type,
            "topK": self.top_k,
            "nodeTypes": ["report", "drug", "indication", "adr"],
            "edgeTypes": [list(relation) for relation in RELATIONS],
            "supportedInputs": ["age", "sex", "candidateDrug", "indication", "currentMedications"],
            "eventScoreType": "BASELINE_MODEL_SCORE",
            "rankingInfluence": "none",
        }

    def _prepare_input(self, request: dict) -> tuple[pd.DataFrame, dict, dict]:
        candidate = normalize_drug(request["candidateDrug"]["canonicalName"])
        indication = normalize_indication(request["indication"]["name"])
        medications = sorted(normalize_drug(value) for value in request["patient"].get("currentMedications", []))
        age = request["patient"].get("age")
        sex = normalize_sex(request["patient"].get("sex"))
        unknown = []
        if candidate not in self.associations.get("drug", {}):
            unknown.append({"entityType": "candidateDrug", "value": candidate})
        if indication not in self.associations.get("indication", {}):
            unknown.append({"entityType": "indication", "value": indication})
        for medication in medications:
            if medication not in self.associations.get("drug", {}):
                unknown.append({"entityType": "currentMedication", "value": medication})
        coverage_status = "FULL" if not unknown else "DEGRADED"
        consumed = {
            "patient": {"age": age, "sex": sex, "currentMedications": medications},
            "candidateDrug": candidate,
            "indication": indication,
            "modelVersion": self.model_version,
            "checkpointVersion": self.checkpoint_version,
            "graphSchemaVersion": self.graph_schema_version,
            "featureSchemaVersion": self.feature_schema_version,
            "eventVocabularyVersion": self.event_vocabulary_version,
        }
        frame = pd.DataFrame([{
            "age_years": age,
            "sex": sex,
            "candidate_drug": candidate,
            "indication": indication,
            "current_medications": medications,
        }])
        return frame, {"status": coverage_status, "unknownEntities": unknown}, consumed

    def predict(self, request: dict) -> dict:
        frame, coverage, consumed = self._prepare_input(request)
        graph = build_heterodata(frame, self.vocabulary, self.associations, include_targets=False).to(self.device)
        self.model.eval()
        with torch.inference_mode():
            logits = self.model(graph)
            scores = torch.sigmoid(logits)[0].detach().cpu().numpy()
        if scores.shape != (len(self.vocabulary),) or not torch.isfinite(torch.as_tensor(scores)).all():
            raise RuntimeError("HGNN inference produced an invalid event-score vector.")
        ordered = sorted(
            ((float(scores[item["index"]]), str(item["term"]), item) for item in self.vocabulary),
            key=lambda value: (-value[0], value[1]),
        )[: self.top_k]
        events = [{
            "eventCode": item.get("code"),
            "eventName": name,
            "eventScore": score,
            "displayPercent": round(score * 100, 2),
            "rank": rank,
        } for rank, (score, name, item) in enumerate(ordered, start=1)]
        return {
            **self.get_status(),
            "status": "SUCCESS" if coverage["status"] == "FULL" else "DEGRADED_COVERAGE",
            "coverage": coverage,
            "inputHash": _stable_hash(consumed),
            "events": events,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "interpretation": (
                "Baseline HGNN model scores represent learned event-label associations for the current encoded "
                "medicine and context. They are not validated patient-incidence probabilities."
            ),
            "rankingInfluence": "none",
        }
