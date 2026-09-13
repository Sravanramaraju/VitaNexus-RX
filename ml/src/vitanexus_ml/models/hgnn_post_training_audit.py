from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import joblib
import numpy as np

from vitanexus_ml.models.hgnn_calibration import (
    apply_calibration,
    calibration_diagnostics,
    choose_calibration,
    fit_calibration_candidates,
)
from vitanexus_ml.models.hgnn_evaluation import (
    global_candidates,
    global_threshold_sweep,
    multilabel_metrics,
    per_label_metrics,
    precision_recall_frontier,
    score_distributions,
    top_k_metrics,
)
from vitanexus_ml.models.hgnn_post_training import (
    WINDOWS,
    cache_frozen_holdout_predictions,
    load_prediction_cache,
    verify_checkpoint_integrity,
)
from vitanexus_ml.models.hgnn_thresholds import (
    deterministic_group_folds,
    global_threshold_stability,
    local_threshold_sensitivity,
    stable_per_label_thresholds,
)
from vitanexus_ml.training_runtime import atomic_joblib, atomic_json, file_sha256, stable_hash, utc_now


AUDIT_VERSION = "faers-hgnn-post-training-audit-1.0.0"
REFERENCE_METRICS = {
    "microAUPRC": 0.15602346153610588,
    "macroAUPRC": 0.12954123154060937,
    "microF1": 0.06696248871612755,
    "microPrecision": 0.6218535722185358,
    "microRecall": 0.0353864898474985,
}
REFERENCE_REPRODUCTION_TOLERANCE = 5e-6


def _csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def _load(cache_root: Path, model: str, cohort: str, label_hash: str) -> dict:
    return load_prediction_cache(cache_root, f"{model}_{cohort}", expected_label_hash=label_hash)


def _configuration_candidates(
    y: np.ndarray,
    raw: np.ndarray,
    calibrated: np.ndarray,
    vocabulary: list[dict],
    folds: np.ndarray,
    minimum_support: int,
    calibration_choice: dict,
) -> tuple[list[dict], dict]:
    raw_sweep = global_threshold_sweep(y, raw, step=0.001)
    raw_globals = global_candidates(raw_sweep)
    raw_threshold = raw_globals["G1MaximumMicroF1"]["threshold"]
    raw_per_label, raw_threshold_rows, raw_per_label_stability = stable_per_label_thresholds(
        y, raw, vocabulary, folds,
        global_threshold=raw_threshold, minimum_support=minimum_support,
    )
    candidates = [
        {"name": "A-existing-global-0.5", "calibration": "identity", "thresholdType": "global", "thresholds": 0.5,
         "metrics": multilabel_metrics(y, raw, 0.5)},
        {"name": "B-optimized-global", "calibration": "identity", "thresholdType": "global", "thresholds": raw_threshold,
         "metrics": multilabel_metrics(y, raw, raw_threshold)},
        {"name": "C-stable-per-label", "calibration": "identity", "thresholdType": "per-label", "thresholds": raw_per_label.tolist(),
         "metrics": multilabel_metrics(y, raw, raw_per_label)},
    ]
    details = {
        "rawGlobalCandidates": raw_globals,
        "rawPrecisionRecallFrontier": precision_recall_frontier(raw_sweep),
        "rawGlobalSensitivity": local_threshold_sensitivity(y, raw, raw_threshold),
        "rawPerLabelThresholds": raw_threshold_rows,
        "rawPerLabelStability": raw_per_label_stability,
    }
    if calibration_choice["adopted"]:
        calibrated_sweep = global_threshold_sweep(y, calibrated, step=0.001)
        calibrated_globals = global_candidates(calibrated_sweep)
        calibrated_threshold = calibrated_globals["G1MaximumMicroF1"]["threshold"]
        calibrated_per_label, calibrated_rows, calibrated_stability = stable_per_label_thresholds(
            y, calibrated, vocabulary, folds,
            global_threshold=calibrated_threshold, minimum_support=minimum_support,
        )
        calibrated_options = [
            {"name": "D-calibrated-global", "calibration": calibration_choice["method"], "thresholdType": "global",
             "thresholds": calibrated_threshold, "metrics": multilabel_metrics(y, calibrated, calibrated_threshold)},
            {"name": "D-calibrated-stable-per-label", "calibration": calibration_choice["method"], "thresholdType": "per-label",
             "thresholds": calibrated_per_label.tolist(), "metrics": multilabel_metrics(y, calibrated, calibrated_per_label)},
        ]
        candidates.extend(calibrated_options)
        details.update({
            "calibratedGlobalCandidates": calibrated_globals,
            "calibratedPrecisionRecallFrontier": precision_recall_frontier(calibrated_sweep),
            "calibratedGlobalSensitivity": local_threshold_sensitivity(y, calibrated, calibrated_threshold),
            "calibratedPerLabelThresholds": calibrated_rows,
            "calibratedPerLabelStability": calibrated_stability,
        })
    return candidates, details


def select_configuration(candidates: list[dict]) -> tuple[dict, dict]:
    baseline = candidates[0]["metrics"]
    constraints = {
        "minimumMicroPrecision": 0.25,
        "minimumMacroF1RelativeToExisting": 0.80,
        "maximumAveragePredictedLabelsPerCase": max(1.0, 2.0 * baseline["averageActualLabelsPerCase"]),
    }
    eligible = []
    for candidate in candidates:
        metrics = candidate["metrics"]
        accepted = (
            metrics["microPrecision"] >= constraints["minimumMicroPrecision"]
            and metrics["macroF1"] >= constraints["minimumMacroF1RelativeToExisting"] * baseline["macroF1"]
            and metrics["averagePredictedLabelsPerCase"] <= constraints["maximumAveragePredictedLabelsPerCase"]
        )
        candidate["passesConstraints"] = bool(accepted)
        if accepted:
            eligible.append(candidate)
    selected = max(eligible or [candidates[0]], key=lambda row: (
        row["metrics"]["microF1"], row["metrics"]["macroF1"], row["metrics"]["microRecall"], row["metrics"]["microPrecision"]
    ))
    return selected, constraints


def run_preholdout_audit(
    integrity_manifest_path: Path,
    cache_root: Path,
    work_root: Path,
    report_root: Path,
) -> dict:
    """Optimize only on pre-2026 caches and irreversibly freeze the chosen configuration."""
    work_root, report_root = Path(work_root), Path(report_root)
    frozen_path = report_root / "hgnn_post_training_frozen_manifest.json"
    if frozen_path.exists():
        raise RuntimeError("HGNN post-training configuration is already frozen; optimization cannot be rerun")
    integrity = verify_checkpoint_integrity(integrity_manifest_path)
    label_hash = integrity["model"]["labelOrderSha256"]
    validation = _load(cache_root, "selection", "validation", label_hash)
    calibration = _load(cache_root, "selection", "calibration", label_hash)
    operating = _load(cache_root, "selection", "operating", label_hash)
    partial = _load(cache_root, "partialRefit", "operating", label_hash)
    vocabulary = validation["metadata"]["labels"]

    reproduced = multilabel_metrics(validation["targets"], validation["probabilities"], 0.5)
    deltas = {name: reproduced[name] - expected for name, expected in REFERENCE_METRICS.items()}
    if any(abs(value) > REFERENCE_REPRODUCTION_TOLERANCE for value in deltas.values()):
        raise RuntimeError(f"Epoch-20 reference metrics were not reproduced within tolerance: {deltas}")

    y = operating["targets"]
    raw = operating["probabilities"]
    logits = operating["logits"]
    minimum_support = max(200, int(math.ceil(math.sqrt(len(y)))))
    calibrators = fit_calibration_candidates(
        calibration["targets"], calibration["logits"], calibration["probabilities"],
        minimum_support=minimum_support,
    )
    calibration_results = {}
    calibrated_by_method = {}
    for method, bundle in calibrators.items():
        values = apply_calibration(bundle, logits, raw)
        calibrated_by_method[method] = values
        calibration_results[method] = calibration_diagnostics(y, values)
    calibration_choice = choose_calibration(calibration_results)
    chosen_probabilities = calibrated_by_method[calibration_choice["method"]]

    folds = deterministic_group_folds(operating["caseids"], folds=5)
    candidates, threshold_details = _configuration_candidates(
        y, raw, chosen_probabilities, vocabulary, folds, minimum_support, calibration_choice,
    )
    selected, constraints = select_configuration(candidates)
    selected_probabilities = calibrated_by_method[selected["calibration"]]
    selected_thresholds = selected["thresholds"]
    selected_bundle = calibrators[selected["calibration"]]

    calibrator_path = work_root / "frozen_calibrator.joblib"
    atomic_joblib(calibrator_path, selected_bundle)
    configuration = {
        "auditVersion": AUDIT_VERSION,
        "modelKind": "selection",
        "checkpointEpoch": 20,
        "checkpointSha256": integrity["files"]["hgnn_selection_best.pt"]["sha256"],
        "labelOrderSha256": label_hash,
        "labelCount": len(vocabulary),
        "calibrationMethod": selected["calibration"],
        "calibratorArtifact": calibrator_path.name,
        "calibratorSha256": file_sha256(calibrator_path),
        "thresholdType": selected["thresholdType"],
        "thresholds": selected_thresholds,
        "topK": [1, 3, 5],
        "minimumRareLabelSupport": minimum_support,
        "caseFoldSeed": 20260824,
    }
    frozen = {
        "status": "FROZEN_BEFORE_2026_HOLDOUT",
        "frozenAt": utc_now(),
        "configuration": configuration,
        "configurationSha256": stable_hash(configuration),
        "optimizationCohorts": {
            "calibration": list(WINDOWS["calibration"]),
            "operatingThresholdSelection": list(WINDOWS["operating"]),
            "referenceReproductionOnly": list(WINDOWS["validation"]),
        },
        "holdoutAccessed": False,
        "policy": "No model, calibrator, threshold, label, or top-k changes are permitted after this freeze.",
    }

    operating_baseline = multilabel_metrics(y, raw, 0.5)
    partial_baseline = multilabel_metrics(partial["targets"], partial["probabilities"], 0.5)
    partial_sweep = global_threshold_sweep(partial["targets"], partial["probabilities"], step=0.001)
    partial_global = global_candidates(partial_sweep)["G1MaximumMicroF1"]
    report = {
        "version": AUDIT_VERSION,
        "createdAt": utc_now(),
        "referenceReproduction": {
            "expected": REFERENCE_METRICS,
            "reproduced": reproduced,
            "deltas": deltas,
            "absoluteTolerance": REFERENCE_REPRODUCTION_TOLERANCE,
            "threshold": 0.5,
            "status": "reproduced",
        },
        "existingDecisionMethod": {
            "threshold": 0.5,
            "scope": "one global threshold for all ADR outputs",
            "scoreTransform": "sigmoid applied to raw logits before thresholding",
            "probabilityCalibration": "none on the protected selection checkpoint",
            "labelMasking": False,
            "adrOutputs": len(vocabulary),
            "zeroPositiveLabelPolicy": "excluded from macro AUPRC; retained with zero_division=0 for threshold metrics",
        },
        "cohorts": {
            "validation": {"window": list(WINDOWS["validation"]), "rows": len(validation["targets"]), "purpose": "reference reproduction only; previously used for epoch selection"},
            "calibration": {"window": list(WINDOWS["calibration"]), "rows": len(calibration["targets"]), "purpose": "calibrator fitting"},
            "operating": {"window": list(WINDOWS["operating"]), "rows": len(y), "purpose": "calibrator assessment and threshold selection"},
        },
        "minimumRareLabelSupport": minimum_support,
        "protectedArtifacts": integrity["model"],
        "baselineOperatingMetrics": operating_baseline,
        "baselineOperatingTopK": top_k_metrics(y, raw, values=(1, 3, 5)),
        "pooledPrevalenceBaseline": float(np.asarray(y).mean()),
        "calibration": {"diagnostics": calibration_results, "selection": calibration_choice},
        "globalStability": global_threshold_stability(y, selected_probabilities, folds, step=0.001),
        "thresholdAnalysis": threshold_details,
        "configurations": candidates,
        "selectionConstraints": constraints,
        "selectedConfiguration": selected,
        "selectedTopK": top_k_metrics(y, selected_probabilities, values=(1, 3, 5)),
        "partialFinalRefit": {
            "status": "exploratory-not-promoted",
            "trainedFromScratch": True,
            "completedEpochs": 5,
            "trainedThrough": "2025Q2",
            "comparisonCohort": list(WINDOWS["operating"]),
            "rawAtPointFive": partial_baseline,
            "exploratoryBestGlobal": partial_global,
            "decision": "Not eligible for automatic promotion because the stopped refit did not complete its prespecified training protocol.",
        },
        "existingLightweightBaselines": {
            "trainingPrevalence": {"microAUPRC": 0.030500338368452413, "macroAUPRC": 0.012447186518853676},
            "linearSGD": {"microAUPRC": 0.027535225559315396, "macroAUPRC": 0.05174984329862469, "microF1": 0.056246298446153246},
            "multilabelMLP": {"microAUPRC": 0.1341754439202199, "macroAUPRC": 0.10948893998468391, "microF1": 0.08387416580225268},
            "comparisonCaveat": "Existing lightweight baselines were measured on the epoch-selection validation cohort, not the independent operating cohort.",
        },
        "frozenConfigurationSha256": frozen["configurationSha256"],
        "holdoutAccessed": False,
    }
    per_label = per_label_metrics(y, selected_probabilities, vocabulary, selected_thresholds)
    distributions = score_distributions(y, raw, vocabulary)
    _csv(report_root / "hgnn_post_training_per_label_preholdout.csv", per_label)
    _csv(report_root / "hgnn_post_training_score_distributions.csv", distributions)
    verify_checkpoint_integrity(integrity_manifest_path)
    atomic_json(report_root / "hgnn_post_training_preholdout.json", report)
    atomic_json(frozen_path, frozen)
    return {"selected": selected, "frozenManifest": str(frozen_path), "report": str(report_root / "hgnn_post_training_preholdout.json")}


def _wilson(successes: int, total: int) -> dict | None:
    if total <= 0:
        return None
    z = 1.959963984540054
    value = successes / total
    denominator = 1 + z * z / total
    center = (value + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(value * (1 - value) / total + z * z / (4 * total * total)) / denominator
    return {"estimate": value, "lower95": center - margin, "upper95": center + margin, "method": "Wilson score"}


def run_frozen_holdout_evaluation(
    integrity_manifest_path: Path,
    frozen_manifest_path: Path,
    cache_root: Path,
    work_root: Path,
    report_root: Path,
    *,
    device_name: str | None = None,
) -> dict:
    frozen = json.loads(Path(frozen_manifest_path).read_text(encoding="utf-8"))
    configuration = frozen["configuration"]
    cache_frozen_holdout_predictions(
        integrity_manifest_path, frozen_manifest_path, cache_root, device_name=device_name,
    )
    cache = _load(cache_root, "selection", "holdout", configuration["labelOrderSha256"])
    calibrator_path = Path(work_root) / configuration["calibratorArtifact"]
    if file_sha256(calibrator_path) != configuration["calibratorSha256"]:
        raise RuntimeError("Frozen HGNN calibrator changed before holdout evaluation")
    bundle = joblib.load(calibrator_path)
    probabilities = apply_calibration(bundle, cache["logits"], cache["probabilities"])
    metrics = multilabel_metrics(cache["targets"], probabilities, configuration["thresholds"])
    confusion = metrics["confusion"]
    intervals = {
        "microPrecision": _wilson(confusion["truePositive"], confusion["truePositive"] + confusion["falsePositive"]),
        "microRecall": _wilson(confusion["truePositive"], confusion["truePositive"] + confusion["falseNegative"]),
    }
    report = {
        "version": AUDIT_VERSION,
        "evaluatedAt": utc_now(),
        "configurationSha256": frozen["configurationSha256"],
        "configuration": configuration,
        "cohort": {"name": "untouched-2026-temporal-holdout", "window": list(WINDOWS["holdout"]), "rows": len(cache["targets"])},
        "metrics": metrics,
        "confidenceIntervals": intervals,
        "topK": top_k_metrics(cache["targets"], probabilities, values=tuple(configuration["topK"])),
        "optimizationPerformedOnHoldout": False,
    }
    per_label = per_label_metrics(cache["targets"], probabilities, cache["metadata"]["labels"], configuration["thresholds"])
    _csv(Path(report_root) / "hgnn_post_training_per_label_holdout.csv", per_label)
    atomic_json(Path(report_root) / "hgnn_post_training_holdout.json", report)
    frozen["holdoutAccessed"] = True
    frozen["holdoutEvaluation"] = {
        "evaluatedAt": report["evaluatedAt"],
        "report": "hgnn_post_training_holdout.json",
        "configurationSha256": frozen["configurationSha256"],
    }
    atomic_json(Path(frozen_manifest_path), frozen)
    return report
