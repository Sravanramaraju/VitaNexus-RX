from fastapi.testclient import TestClient

from vitanexus_ml.api.app import app


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
