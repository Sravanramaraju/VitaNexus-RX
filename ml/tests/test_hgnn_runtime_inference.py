from pathlib import Path

import pytest
import torch

from vitanexus_ml.inference.hgnn_predictor import HgnnArtifactsUnavailable, HgnnPredictor
from vitanexus_ml.models.hgnn import RELATIONS


@pytest.fixture(scope="module")
def predictor():
    return HgnnPredictor(device_name="cpu")


@pytest.fixture(scope="module")
def known_request():
    return {
        "requestId": "runtime-test",
        "patient": {"age": 38, "sex": "F", "currentMedications": ["Paracetamol"]},
        "candidateDrug": {"canonicalName": "Deferasirox"},
        "indication": {"name": "Iron overload"},
    }


def test_protected_selection_checkpoint_identity_and_architecture(predictor):
    status = predictor.get_status()
    assert status["status"] == "READY"
    assert status["modelVersion"] == "faers-specific-adr-hgnn-1.0.0"
    assert status["checkpointVersion"] == "7ca91da8449c87e65c08550083eab12cf3e267faa9e44284c496853de7fa5420"
    assert status["trainingEpoch"] == 20
    assert status["eventVocabularySize"] == 100
    assert status["nodeTypes"] == ["report", "drug", "indication", "adr"]
    assert status["edgeTypes"] == [list(relation) for relation in RELATIONS]
    assert status["modelStage"] == "BASELINE"
    assert status["validationStatus"] == "AUDIT_PENDING"
    assert status["rankingInfluence"] == "none"


def test_runtime_is_cpu_eval_and_grad_free(predictor):
    assert predictor.device.type == "cpu"
    assert predictor.model.training is False
    assert all(parameter.device.type == "cpu" for parameter in predictor.model.parameters())


def test_event_scores_are_real_finite_sorted_and_deterministic(predictor, known_request):
    first = predictor.predict(known_request)
    second = predictor.predict(known_request)
    assert first["status"] in {"SUCCESS", "DEGRADED_COVERAGE"}
    assert first["events"] == second["events"]
    assert first["inputHash"] == second["inputHash"]
    assert len(first["events"]) == predictor.top_k
    scores = [event["eventScore"] for event in first["events"]]
    assert all(torch.isfinite(torch.tensor(score)) and 0 <= score <= 1 for score in scores)
    assert scores == sorted(scores, reverse=True)
    assert [event["rank"] for event in first["events"]] == list(range(1, predictor.top_k + 1))
    assert first["eventScoreType"] == "BASELINE_MODEL_SCORE"
    assert "patient-incidence probabilities" in first["interpretation"]


def test_unknown_entities_are_typed_and_never_silently_reported_as_full(predictor):
    result = predictor.predict({
        "requestId": "unknown-test",
        "patient": {"age": None, "sex": "UNKNOWN", "currentMedications": ["never-seen-concomitant-zz"]},
        "candidateDrug": {"canonicalName": "never-seen-drug-zz"},
        "indication": {"name": "never-seen-indication-zz"},
    })
    assert result["status"] == "DEGRADED_COVERAGE"
    assert result["coverage"]["status"] == "DEGRADED"
    assert {item["entityType"] for item in result["coverage"]["unknownEntities"]} == {
        "candidateDrug", "indication", "currentMedication",
    }
    assert result["events"]


def test_missing_integrity_manifest_fails_closed():
    with pytest.raises(HgnnArtifactsUnavailable):
        HgnnPredictor(integrity_manifest_path=Path(__file__).with_name("definitely-missing-hgnn-manifest.json"), device_name="cpu")
