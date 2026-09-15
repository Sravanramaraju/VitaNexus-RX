from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vitanexus_ml.inference.predictor import ArtifactsUnavailable, Predictor
from vitanexus_ml.inference.hgnn_predictor import HgnnArtifactsUnavailable, HgnnPredictor


class PatientInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age: float | None = Field(default=None, ge=0, le=120)
    sex: str = Field(min_length=1, max_length=30)
    currentMedications: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("currentMedications")
    @classmethod
    def medication_names(cls, values):
        if any(not value.strip() or len(value) > 255 for value in values):
            raise ValueError("Current medication names must be non-empty and at most 255 characters")
        return values


class CandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonicalName: str = Field(min_length=1, max_length=255)
    ingredients: list[str] = Field(default_factory=list, max_length=20)


class IndicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    source: str = Field(pattern=r"^DrugCentral$")


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: str = Field(min_length=1, max_length=128)
    patient: PatientInput
    candidateDrug: CandidateInput
    indication: IndicationInput


class BatchPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests: list[PredictionRequest] = Field(min_length=1, max_length=30)


class TermCoverageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[str] = Field(default_factory=list, max_length=500)
    indications: list[str] = Field(default_factory=list, max_length=500)
    medications: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("candidates", "indications", "medications")
    @classmethod
    def term_names(cls, values):
        if any(not value.strip() or len(value) > 255 for value in values):
            raise ValueError("Coverage terms must be non-empty and at most 255 characters")
        return values


class HgnnPatientInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age: float | None = Field(default=None, ge=0, le=120)
    sex: str = Field(min_length=1, max_length=30)
    currentMedications: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("currentMedications")
    @classmethod
    def hgnn_medication_names(cls, values):
        if any(not value.strip() or len(value) > 255 for value in values):
            raise ValueError("Current medication names must be non-empty and at most 255 characters")
        return values


class HgnnCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonicalName: str = Field(min_length=1, max_length=255)


class HgnnIndicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)


class HgnnPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: str = Field(min_length=1, max_length=128)
    patient: HgnnPatientInput
    candidateDrug: HgnnCandidateInput
    indication: HgnnIndicationInput


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.predictor = Predictor()
        app.state.load_error = None
    except Exception as error:  # Health exposes only the class/message, never paths supplied by callers.
        app.state.predictor = None
        app.state.load_error = str(error)
    try:
        app.state.hgnn_predictor = HgnnPredictor()
        app.state.hgnn_load_error = None
    except Exception as error:
        app.state.hgnn_predictor = None
        app.state.hgnn_load_error = str(error)
    yield


app = FastAPI(title="VitaNexus-RX internal FAERS inference", version="1.0.0", lifespan=lifespan)


def _predictor(request: Request) -> Predictor:
    if request.app.state.predictor is None:
        raise HTTPException(status_code=503, detail={"status": "ML_UNAVAILABLE", "message": request.app.state.load_error or "Model artifacts unavailable"})
    return request.app.state.predictor


def _hgnn_predictor(request: Request) -> HgnnPredictor:
    if request.app.state.hgnn_predictor is None:
        raise HTTPException(status_code=503, detail={
            "status": "HGNN_UNAVAILABLE",
            "message": request.app.state.hgnn_load_error or "Baseline HGNN artifacts unavailable",
        })
    return request.app.state.hgnn_predictor


@app.get("/health")
def health(request: Request):
    lightgbm_ready = request.app.state.predictor is not None
    hgnn_ready = request.app.state.hgnn_predictor is not None
    return {
        "status": "ok" if lightgbm_ready else "ML_UNAVAILABLE",
        "service": "vitanexus-faers-ml",
        "artifactsLoaded": lightgbm_ready,
        "activeModel": "LightGBM",
        "models": {
            "lightgbm": "READY" if lightgbm_ready else "UNAVAILABLE",
            "hgnn": "READY" if hgnn_ready else "UNAVAILABLE",
        },
        "eventRiskModelStatus": "BASELINE_ACTIVE_AUDIT_PENDING" if hgnn_ready else "HGNN_UNAVAILABLE",
    }


@app.get("/v1/hgnn/status")
def hgnn_status(request: Request):
    return _hgnn_predictor(request).get_status()


@app.post("/v1/predict")
def predict(payload: PredictionRequest, request: Request):
    try:
        return _predictor(request).predict(payload.model_dump())
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail={"status": "INFERENCE_FAILED", "message": str(error)}) from error


@app.post("/v1/lightgbm/input-coverage")
def lightgbm_input_coverage(payload: PredictionRequest, request: Request):
    result = _predictor(request).inspect_coverage(payload.model_dump())
    result.pop("matrix", None)
    return result


@app.post("/v1/lightgbm/term-coverage")
def lightgbm_term_coverage(payload: TermCoverageRequest, request: Request):
    return _predictor(request).inspect_terms(payload.model_dump())


@app.post("/v1/predict-batch")
def predict_batch(payload: BatchPredictionRequest, request: Request):
    predictor = _predictor(request)
    items = []
    for item in payload.requests:
        try:
            items.append({"requestId": item.requestId, "result": predictor.predict(item.model_dump())})
        except Exception as error:
            items.append({"requestId": item.requestId, "error": {"status": "INFERENCE_FAILED", "message": str(error)}})
    return {"status": "ok" if all("result" in item for item in items) else "PARTIAL_FAILURE", "items": items}


@app.post("/v1/hgnn/predict-events")
def predict_hgnn_events(payload: HgnnPredictionRequest, request: Request):
    try:
        return _hgnn_predictor(request).predict(payload.model_dump())
    except HTTPException:
        raise
    except HgnnArtifactsUnavailable as error:
        raise HTTPException(status_code=503, detail={"status": "ARTIFACT_MISMATCH", "message": str(error)}) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={"status": "INFERENCE_FAILED", "message": "Baseline HGNN inference could not be completed."},
        ) from error
