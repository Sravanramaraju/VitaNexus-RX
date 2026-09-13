from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
from joblib import Parallel, delayed
from scipy.optimize import minimize_scalar
from scipy.special import expit
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score

from vitanexus_ml.models.hgnn_evaluation import expected_calibration_error


CALIBRATION_METHODS = ("identity", "temperature", "platt", "isotonic")


@dataclass
class CalibrationBundle:
    method: str
    payload: object
    minimum_support: int
    fallback_labels: list[int]


def _binary_nll(labels: np.ndarray, probabilities: np.ndarray) -> float:
    values = np.clip(probabilities, 1e-7, 1.0 - 1e-7)
    return float(-np.mean(labels * np.log(values) + (1 - labels) * np.log(1 - values)))


def fit_temperature(targets, logits) -> CalibrationBundle:
    y = np.asarray(targets, dtype=np.float64)
    z = np.asarray(logits, dtype=np.float64)

    def objective(log_temperature: float) -> float:
        return _binary_nll(y, expit(z / np.exp(log_temperature)))

    result = minimize_scalar(objective, bounds=(-4.0, 4.0), method="bounded", options={"xatol": 1e-7})
    if not result.success:
        raise RuntimeError(f"HGNN temperature scaling failed: {result.message}")
    return CalibrationBundle("temperature", {"temperature": float(np.exp(result.x))}, 0, [])


def fit_per_label_calibrators(targets, probabilities, *, method: str, minimum_support: int) -> CalibrationBundle:
    if method not in {"platt", "isotonic"}:
        raise ValueError("Per-label HGNN calibration supports only platt or isotonic")
    y = np.asarray(targets, dtype=np.int8)
    p = np.asarray(probabilities, dtype=np.float64)
    def fit_one(index: int):
        labels = y[:, index]
        positives = int(labels.sum())
        negatives = len(labels) - positives
        if min(positives, negatives) < minimum_support:
            return index, None
        if method == "platt":
            model = LogisticRegression(solver="lbfgs", max_iter=200, random_state=20260824)
            model.fit(p[:, index].reshape(-1, 1), labels)
        else:
            model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            model.fit(p[:, index], labels)
        return index, model

    workers = min(4, max(1, os.cpu_count() or 1), y.shape[1])
    fitted = Parallel(n_jobs=workers, prefer="threads")(
        delayed(fit_one)(index) for index in range(y.shape[1])
    )
    models = [None] * y.shape[1]
    fallbacks = []
    for index, model in fitted:
        models[index] = model
        if model is None:
            fallbacks.append(index)
    return CalibrationBundle(method, models, minimum_support, fallbacks)


def fit_calibration_candidate(
    method: str,
    targets,
    logits,
    probabilities,
    *,
    minimum_support: int,
) -> CalibrationBundle:
    if method == "identity":
        return CalibrationBundle("identity", None, 0, [])
    if method == "temperature":
        return fit_temperature(targets, logits)
    if method in {"platt", "isotonic"}:
        return fit_per_label_calibrators(targets, probabilities, method=method, minimum_support=minimum_support)
    raise ValueError(f"Unknown HGNN calibration method: {method}")


def fit_calibration_candidates(targets, logits, probabilities, *, minimum_support: int) -> dict[str, CalibrationBundle]:
    return {
        method: fit_calibration_candidate(
            method, targets, logits, probabilities, minimum_support=minimum_support,
        )
        for method in CALIBRATION_METHODS
    }


def apply_calibration(bundle: CalibrationBundle, logits, probabilities) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64)
    p = np.asarray(probabilities, dtype=np.float64)
    if bundle.method == "identity":
        return p.copy()
    if bundle.method == "temperature":
        return expit(z / float(bundle.payload["temperature"]))
    result = p.copy()
    for index, model in enumerate(bundle.payload):
        if model is None:
            continue
        if bundle.method == "platt":
            result[:, index] = model.predict_proba(p[:, index].reshape(-1, 1))[:, 1]
        elif bundle.method == "isotonic":
            result[:, index] = model.predict(p[:, index])
        else:
            raise ValueError(f"Unknown HGNN calibration method: {bundle.method}")
    return result


def calibration_diagnostics(targets, probabilities) -> dict:
    y = np.asarray(targets, dtype=np.int8)
    p = np.asarray(probabilities, dtype=np.float64)
    positives = y.sum(axis=0)
    valid_ap = positives > 0
    per_label = []
    for index in range(y.shape[1]):
        labels = y[:, index]
        scores = p[:, index]
        per_label.append({
            "index": index,
            "support": int(labels.sum()),
            "brier": float(np.mean((scores - labels) ** 2)),
            "ece": expected_calibration_error(labels[:, None], scores[:, None]),
        })
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "ece": expected_calibration_error(y, p),
        "microAUPRC": float(average_precision_score(y, p, average="micro")),
        "macroAUPRC": float(average_precision_score(y[:, valid_ap], p[:, valid_ap], average="macro")),
        "negativeLogLikelihood": _binary_nll(y, p),
        "perLabel": per_label,
    }


def choose_calibration(diagnostics: dict[str, dict]) -> dict:
    raw = diagnostics["identity"]
    eligible = []
    for method, values in diagnostics.items():
        if method == "identity":
            continue
        brier_gain = (raw["brier"] - values["brier"]) / max(raw["brier"], 1e-12)
        ece_gain = (raw["ece"] - values["ece"]) / max(raw["ece"], 1e-12)
        if (
            brier_gain >= 0.005
            and ece_gain >= 0.10
            and values["microAUPRC"] >= raw["microAUPRC"] - 0.002
            and values["macroAUPRC"] >= raw["macroAUPRC"] - 0.002
        ):
            eligible.append((values["brier"], values["ece"], -values["microAUPRC"], method, brier_gain, ece_gain))
    if not eligible:
        return {
            "method": "identity",
            "adopted": False,
            "reason": "No calibrator materially improved both Brier score and ECE while preserving AUPRC.",
            "relativeBrierImprovement": 0.0,
            "relativeEceImprovement": 0.0,
        }
    _, _, _, method, brier_gain, ece_gain = min(eligible)
    return {
        "method": method,
        "adopted": True,
        "reason": "Selected pre-2026 calibrator materially improves Brier score and ECE while preserving AUPRC.",
        "relativeBrierImprovement": float(brier_gain),
        "relativeEceImprovement": float(ece_gain),
    }
