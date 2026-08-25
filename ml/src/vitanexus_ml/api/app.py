from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vitanexus_ml.inference.predictor import ArtifactsUnavailable, Predictor


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.predictor = Predictor()
        app.state.load_error = None
    except Exception as error:  # Health exposes only the class/message, never paths supplied by callers.
        app.state.predictor = None
        app.state.load_error = str(error)
    yield


app = FastAPI(title="VitaNexus-RX internal FAERS inference", version="1.0.0", lifespan=lifespan)


def _predictor(request: Request) -> Predictor:
    if request.app.state.predictor is None:
        raise HTTPException(status_code=503, detail={"status": "ML_UNAVAILABLE", "message": request.app.state.load_error or "Model artifacts unavailable"})
    return request.app.state.predictor


@app.get("/health")
def health(request: Request):
    ready = request.app.state.predictor is not None
    return {"status": "ok" if ready else "ML_UNAVAILABLE", "service": "vitanexus-faers-ml", "artifactsLoaded": ready}


@app.post("/v1/predict")
def predict(payload: PredictionRequest, request: Request):
    try:
        return _predictor(request).predict(payload.model_dump())
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail={"status": "INFERENCE_FAILED", "message": str(error)}) from error


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
