from fastapi.testclient import TestClient

from vitanexus_ml.api.app import app
from vitanexus_ml.inference.predictor import LightGBMPredictor


def test_api_validation_rejects_non_drugcentral_indication():
    with TestClient(app) as client:
        response = client.post("/v1/predict", json={
            "requestId": "test", "patient": {"age": 50, "sex": "F", "currentMedications": []},
            "candidateDrug": {"canonicalName": "PARACETAMOL", "ingredients": []},
            "indication": {"id": "pain", "name": "Pain", "source": "free-text"},
        })
    assert response.status_code == 422


def test_health_never_claims_ready_without_artifacts():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "ML_UNAVAILABLE"}
    assert response.json()["activeModel"] == "LightGBM"
    assert response.json()["eventRiskModelStatus"] in {"BASELINE_ACTIVE_AUDIT_PENDING", "HGNN_UNAVAILABLE"}


def test_hgnn_api_rejects_extra_or_unsupported_inputs():
    with TestClient(app) as client:
        response = client.post("/v1/hgnn/predict-events", json={
            "requestId": "test",
            "patient": {"age": 50, "sex": "F", "currentMedications": [], "laboratoryValues": []},
            "candidateDrug": {"canonicalName": "PARACETAMOL"},
            "indication": {"name": "Pain"},
        })
    assert response.status_code == 422


def test_hgnn_status_is_explicit_about_baseline_and_audit_state():
    with TestClient(app) as client:
        response = client.get("/v1/hgnn/status")
    if response.status_code == 200:
        payload = response.json()
        assert payload["status"] == "READY"
        assert payload["modelStage"] == "BASELINE"
        assert payload["validationStatus"] == "AUDIT_PENDING"
        assert payload["rankingInfluence"] == "none"
    else:
        assert response.status_code == 503
        assert response.json()["detail"]["status"] == "HGNN_UNAVAILABLE"


def test_full_lightgbm_predictor_has_no_hgnn_runtime_output():
    predictor = LightGBMPredictor()
    result = predictor.predict({
        "patient": {"age": 50, "sex": "F", "currentMedications": ["Warfarin"]},
        "candidateDrug": {"canonicalName": "Ibuprofen", "ingredients": []},
        "indication": {"id": "pain", "name": "Pain", "source": "DrugCentral"},
    })

    assert result["artifactMode"] == "FULL"
    assert result["model"] == "LightGBM"
    assert 0.0 <= result["overall"]["riskProbability"] <= 1.0
    assert result["overall"]["adjustedRisk"] == result["overall"]["uncertainty"]["upper"]
    assert result["overall"]["conformal"]["interval"] is None
    assert "hgnn" not in result["versions"]
    assert "specificAdrs" not in result


def test_unknown_indication_is_not_scored_as_an_ordinary_category():
    predictor = LightGBMPredictor()
    result = predictor.predict({
        "patient": {"age": 20, "sex": "Male", "currentMedications": ["Paracetamol"]},
        "candidateDrug": {"canonicalName": "Deferasirox", "ingredients": []},
        "indication": {"id": "diagnostic", "name": "Diagnostic aid", "source": "DrugCentral"},
    })

    assert result["status"] == "OUT_OF_VOCABULARY"
    assert result["inputCoverage"]["sexKnown"] is True
    assert result["inputCoverage"]["candidateKnown"] is True
    assert result["inputCoverage"]["indicationKnown"] is False
    assert "overall" not in result


def test_unknown_current_medicine_returns_an_explicit_degraded_estimate():
    predictor = LightGBMPredictor()
    result = predictor.predict({
        "patient": {"age": 50, "sex": "F", "currentMedications": ["Warfarin", "Unlisted medicine"]},
        "candidateDrug": {"canonicalName": "Ibuprofen", "ingredients": []},
        "indication": {"id": "pain", "name": "Pain", "source": "DrugCentral"},
    })

    assert result["status"] == "DEGRADED_COVERAGE"
    assert result["inputCoverage"]["unknownCurrentMedications"] == ["UNLISTED MEDICINE"]
    assert 0.0 <= result["overall"]["riskProbability"] <= 1.0
    assert "incomplete medication coverage" in result["message"]


def test_coverage_endpoints_identify_supported_correction():
    payload = {
        "requestId": "coverage-test",
        "patient": {"age": 20, "sex": "Male", "currentMedications": ["Paracetamol"]},
        "candidateDrug": {"canonicalName": "Deferasirox", "ingredients": []},
        "indication": {"id": "diagnostic", "name": "Diagnostic aid", "source": "DrugCentral"},
    }
    with TestClient(app) as client:
        request_coverage = client.post("/v1/lightgbm/input-coverage", json=payload)
        term_coverage = client.post("/v1/lightgbm/term-coverage", json={"indications": ["Diagnostic aid", "Iron overload"]})

    assert request_coverage.status_code == 200
    assert request_coverage.json()["status"] == "OUT_OF_VOCABULARY"
    assert request_coverage.json()["inputCoverage"]["sexKnown"] is True
    supported = {item["input"]: item["supported"] for item in term_coverage.json()["indications"]}
    assert supported == {"Diagnostic aid": False, "Iron overload": True}


def test_coverage_endpoint_marks_unknown_current_medicine_as_degraded():
    payload = {
        "requestId": "coverage-degraded-test",
        "patient": {"age": 50, "sex": "F", "currentMedications": ["Warfarin", "Unlisted medicine"]},
        "candidateDrug": {"canonicalName": "Ibuprofen", "ingredients": []},
        "indication": {"id": "pain", "name": "Pain", "source": "DrugCentral"},
    }
    with TestClient(app) as client:
        response = client.post("/v1/lightgbm/input-coverage", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "DEGRADED_COVERAGE"
    assert response.json()["inputCoverage"]["unknownCurrentMedications"] == ["UNLISTED MEDICINE"]
