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
    assert response.json()["eventRiskModelStatus"] == "model_not_available"


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
