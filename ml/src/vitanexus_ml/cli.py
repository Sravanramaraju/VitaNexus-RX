from __future__ import annotations

import argparse
import json
from pathlib import Path

from vitanexus_ml.config import (
    ARTIFACT_ROOT,
    FEATURE_CACHE_ROOT,
    PROCESSED_FAERS_ROOT,
    RAW_FAERS_ROOT,
    REPORT_ROOT,
    TRAINING_RUN_ROOT,
    TrainConfig,
    ensure_output_directories,
)


def cohort_path(fast: bool) -> Path:
    return PROCESSED_FAERS_ROOT / ("cohort_fast.parquet" if fast else "cohort.parquet")


def preprocess(fast: bool) -> dict:
    from vitanexus_ml.data.faers import FaersPreprocessor

    return FaersPreprocessor(RAW_FAERS_ROOT, PROCESSED_FAERS_ROOT, fast=fast).run()


def train_lightgbm(fast: bool) -> dict:
    from vitanexus_ml.models.lightgbm_pipeline import train_lightgbm_pipeline

    return train_lightgbm_pipeline(cohort_path(fast), fast=fast, config=TrainConfig())


def training_status() -> dict:
    states = sorted(TRAINING_RUN_ROOT.glob("*/state.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not states:
        return {"status": "NOT_STARTED", "message": "No resumable full-training run exists."}
    state_path = states[0]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    stages = state.get("stages", {})
    def is_replica(name: str) -> bool:
        return name.startswith("bootstrap_") and name.removeprefix("bootstrap_").isdigit()

    completed_replicas = sum(1 for name, value in stages.items() if is_replica(name) and value.get("status") == "complete")
    replica_seconds = [value.get("elapsedSeconds") for name, value in stages.items() if is_replica(name) and value.get("status") == "complete" and value.get("elapsedSeconds")]
    remaining_seconds = None
    if replica_seconds:
        remaining_seconds = sum(replica_seconds) / len(replica_seconds) * (state["identity"]["config"]["bootstrap_replicas"] - completed_replicas)
    return {
        "status": "COMPLETE" if stages.get("promoted", {}).get("status") == "complete" else "IN_PROGRESS_OR_INTERRUPTED",
        "run": state_path.parent.name,
        "statePath": str(state_path),
        "updatedAt": state.get("updatedAt"),
        "currentOrLastStage": next(reversed(stages), None),
        "stages": stages,
        "bootstrap": {
            "completed": completed_replicas,
            "total": state["identity"]["config"]["bootstrap_replicas"],
            "estimatedRemainingSeconds": remaining_seconds,
        },
    }


def hgnn_training_status() -> dict:
    states = sorted(
        (TRAINING_RUN_ROOT / "hgnn").glob("*/state.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not states:
        return {"status": "NOT_STARTED", "message": "No resumable full HGNN training run exists."}
    state_path = states[0]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    stages = state.get("stages", {})
    selection = stages.get("hgnn_selection", {})
    completed_epochs = int(selection.get("completedEpoch", selection.get("epochs", 0)) or 0)
    total_epochs = int(selection.get("totalEpochs", state.get("identity", {}).get("hgnnConfig", {}).get("epochs", 20)) or 20)
    promoted = stages.get("promoted", {}).get("status") == "complete"
    return {
        "status": "COMPLETE" if promoted else "IN_PROGRESS_OR_INTERRUPTED",
        "run": state_path.parent.name,
        "statePath": str(state_path),
        "updatedAt": state.get("updatedAt"),
        "currentOrLastStage": next(reversed(stages), None),
        "selection": {
            "completedEpochs": completed_epochs,
            "totalEpochs": total_epochs,
            "resumeAtEpoch": min(completed_epochs + 1, total_epochs) if not promoted else None,
            "bestEpoch": selection.get("bestEpoch"),
            "bestValidationMicroAUPRC": selection.get("bestValidationMicroAUPRC"),
        },
        "stages": stages,
    }


def hgnn(fast: bool) -> dict:
    if fast:
        from vitanexus_ml.models.hgnn import train_hgnn

        return train_hgnn(cohort_path(True), fast=True, config=TrainConfig())
    from vitanexus_ml.models.hgnn_colab_pipeline import train_hgnn_colab

    return train_hgnn_colab(cohort_path(False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VitaNexus-RX reproducible FAERS ML pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("preprocess", "train-lightgbm", "train-hgnn", "evaluate", "all"):
        command = subparsers.add_parser(name)
        command.add_argument("--fast", action="store_true", help="Explicit development smoke mode; outputs are labelled non-final")
    benchmark_parser = subparsers.add_parser("benchmark-lightgbm")
    benchmark_parser.add_argument("--sample-rows", type=int, default=None, help="Deterministic temporal benchmark size; never used as final training data")
    threshold_parser = subparsers.add_parser("optimize-lightgbm-threshold")
    threshold_parser.add_argument("--cohort", type=Path, default=PROCESSED_FAERS_ROOT / "cohort.parquet")
    threshold_parser.add_argument("--artifact", type=Path, default=ARTIFACT_ROOT / "serious_outcome.joblib")
    threshold_parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    threshold_parser.add_argument("--sensitivity", type=float, default=0.90)
    threshold_parser.add_argument("--step", type=float, default=0.001)
    subparsers.add_parser("training-status")
    subparsers.add_parser("hgnn-training-status")
    plan_parser = subparsers.add_parser("training-export-plan")
    plan_parser.add_argument("--source-root", type=Path, required=True)
    plan_parser.add_argument("--run-key", default=None)
    plan_parser.add_argument("--cohort", type=Path, default=PROCESSED_FAERS_ROOT / "cohort.parquet")
    export_state_parser = subparsers.add_parser("export-training-state")
    export_state_parser.add_argument("--source-root", type=Path, required=True)
    export_state_parser.add_argument("--run-key", default=None)
    export_state_parser.add_argument("--cohort", type=Path, default=PROCESSED_FAERS_ROOT / "cohort.parquet")
    export_state_parser.add_argument("--output", type=Path, required=True)
    verify_state_parser = subparsers.add_parser("verify-training-state")
    verify_state_parser.add_argument("--bundle", type=Path, required=True)
    verify_state_parser.add_argument("--cohort", type=Path, default=None)
    import_state_parser = subparsers.add_parser("import-training-state")
    import_state_parser.add_argument("--bundle", type=Path, required=True)
    import_state_parser.add_argument("--cohort", type=Path, default=PROCESSED_FAERS_ROOT / "cohort.parquet")
    import_state_parser.add_argument("--cache-root", type=Path, default=FEATURE_CACHE_ROOT)
    import_state_parser.add_argument("--run-root", type=Path, default=TRAINING_RUN_ROOT)
    export_inference_parser = subparsers.add_parser("export-inference-bundle")
    export_inference_parser.add_argument("--output", type=Path, required=True)
    export_inference_parser.add_argument("--component", choices=("lightgbm", "all"), default="all")
    verify_inference_parser = subparsers.add_parser("verify-inference-bundle")
    verify_inference_parser.add_argument("--bundle", type=Path, required=True)
    verify_inference_parser.add_argument("--require-hgnn", action="store_true", help="Require a legacy combined LightGBM+HGNN bundle.")
    import_inference_parser = subparsers.add_parser("import-inference-bundle")
    import_inference_parser.add_argument("--bundle", type=Path, required=True)
    import_inference_parser.add_argument("--require-hgnn", action="store_true", help="Reject a LightGBM-only bundle for a legacy combined import.")
    hgnn_cache_parser = subparsers.add_parser("cache-hgnn-post-training")
    hgnn_cache_parser.add_argument("--snapshot-root", type=Path, required=True)
    hgnn_cache_parser.add_argument("--work-root", type=Path, required=True)
    hgnn_cache_parser.add_argument("--cache-root", type=Path, required=True)
    hgnn_cache_parser.add_argument("--device", choices=("cpu", "cuda"), default=None)
    hgnn_audit_parser = subparsers.add_parser("optimize-hgnn-post-training")
    hgnn_audit_parser.add_argument("--work-root", type=Path, required=True)
    hgnn_audit_parser.add_argument("--cache-root", type=Path, required=True)
    hgnn_audit_parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    hgnn_holdout_parser = subparsers.add_parser("evaluate-frozen-hgnn-holdout")
    hgnn_holdout_parser.add_argument("--work-root", type=Path, required=True)
    hgnn_holdout_parser.add_argument("--cache-root", type=Path, required=True)
    hgnn_holdout_parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    hgnn_holdout_parser.add_argument("--device", choices=("cpu", "cuda"), default=None)
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    ensure_output_directories()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("vitanexus_ml.api.app:app", host=args.host, port=args.port)
        return 0
    if args.command == "preprocess":
        result = preprocess(args.fast)
    elif args.command == "benchmark-lightgbm":
        from vitanexus_ml.models.lightgbm_pipeline import benchmark_lightgbm_pipeline

        result = benchmark_lightgbm_pipeline(cohort_path(False), config=TrainConfig(), sample_rows=args.sample_rows)
    elif args.command == "optimize-lightgbm-threshold":
        from vitanexus_ml.models.operating_threshold import optimize_existing_lightgbm_threshold

        result = optimize_existing_lightgbm_threshold(
            cohort_path=args.cohort,
            serious_artifact_path=args.artifact,
            report_root=args.report_root,
            seed=TrainConfig().seed,
            sensitivity_constraint=args.sensitivity,
            threshold_step=args.step,
        )
    elif args.command == "training-status":
        result = training_status()
    elif args.command == "hgnn-training-status":
        result = hgnn_training_status()
    elif args.command == "training-export-plan":
        from vitanexus_ml.portable_state import inspect_training_state

        audit = inspect_training_state(args.source_root, args.cohort, args.run_key)
        result = {
            key: value for key, value in audit.items()
            if key not in {"state", "items", "portableRunIdentity", "portableCacheIdentity"}
        }
        result["filesToExport"] = [relative for _, relative in audit["items"]]
    elif args.command == "export-training-state":
        from vitanexus_ml.portable_state import export_training_state

        result = export_training_state(args.source_root, args.cohort, args.output, args.run_key)
    elif args.command == "verify-training-state":
        from vitanexus_ml.portable_state import verify_training_state_bundle

        result = verify_training_state_bundle(args.bundle, args.cohort)
    elif args.command == "import-training-state":
        from vitanexus_ml.portable_state import import_training_state

        result = import_training_state(args.bundle, args.cohort, args.cache_root, args.run_root)
    elif args.command == "export-inference-bundle":
        from vitanexus_ml.artifact_bundle import export_inference_bundle

        result = export_inference_bundle(ARTIFACT_ROOT, REPORT_ROOT, args.output, args.component)
    elif args.command == "verify-inference-bundle":
        from vitanexus_ml.artifact_bundle import verify_inference_bundle

        result = verify_inference_bundle(args.bundle, require_all=args.require_hgnn)
    elif args.command == "import-inference-bundle":
        from vitanexus_ml.artifact_bundle import import_inference_bundle

        result = import_inference_bundle(
            args.bundle,
            ARTIFACT_ROOT,
            REPORT_ROOT,
            allow_lightgbm_only=not args.require_hgnn,
        )
    elif args.command == "cache-hgnn-post-training":
        from vitanexus_ml.models.hgnn_post_training import (
            cache_frozen_predictions,
            create_checkpoint_integrity_manifest,
        )

        integrity_path = args.work_root / "checkpoint_integrity.json"
        create_checkpoint_integrity_manifest(args.snapshot_root, integrity_path)
        caches = {}
        for cohort in ("validation", "calibration", "operating"):
            caches[f"selection_{cohort}"] = cache_frozen_predictions(
                integrity_path, args.cache_root, cohort=cohort, device_name=args.device,
            )
        caches["partialRefit_operating"] = cache_frozen_predictions(
            integrity_path, args.cache_root, cohort="operating", model_kind="partialRefit", device_name=args.device,
        )
        result = {"integrityManifest": str(integrity_path), "caches": caches}
    elif args.command == "optimize-hgnn-post-training":
        from vitanexus_ml.models.hgnn_post_training_audit import run_preholdout_audit

        result = run_preholdout_audit(
            args.work_root / "checkpoint_integrity.json", args.cache_root, args.work_root, args.report_root,
        )
    elif args.command == "evaluate-frozen-hgnn-holdout":
        from vitanexus_ml.models.hgnn_post_training_audit import run_frozen_holdout_evaluation

        result = run_frozen_holdout_evaluation(
            args.work_root / "checkpoint_integrity.json",
            args.report_root / "hgnn_post_training_frozen_manifest.json",
            args.cache_root,
            args.work_root,
            args.report_root,
            device_name=args.device,
        )
    elif args.command == "train-lightgbm":
        result = train_lightgbm(args.fast)
    elif args.command == "train-hgnn":
        result = hgnn(args.fast)
    elif args.command == "evaluate":
        reports = sorted(str(path) for path in REPORT_ROOT.glob("*.json"))
        if not reports:
            raise RuntimeError("No trained evaluation reports exist. Run training first.")
        result = {"reports": reports}
    else:
        result = {"preprocessing": preprocess(args.fast), "lightgbm": train_lightgbm(args.fast), "hgnn": hgnn(args.fast)}
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
