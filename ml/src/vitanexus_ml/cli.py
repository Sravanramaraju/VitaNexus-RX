from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn

from vitanexus_ml.config import PROCESSED_FAERS_ROOT, RAW_FAERS_ROOT, REPORT_ROOT, TrainConfig, ensure_output_directories
from vitanexus_ml.data.faers import FaersPreprocessor
from vitanexus_ml.models.hgnn import train_hgnn
from vitanexus_ml.models.lightgbm_pipeline import train_lightgbm_pipeline


def cohort_path(fast: bool) -> Path:
    return PROCESSED_FAERS_ROOT / ("cohort_fast.parquet" if fast else "cohort.parquet")


def preprocess(fast: bool) -> dict:
    return FaersPreprocessor(RAW_FAERS_ROOT, PROCESSED_FAERS_ROOT, fast=fast).run()


def train_lightgbm(fast: bool) -> dict:
    return train_lightgbm_pipeline(cohort_path(fast), fast=fast, config=TrainConfig())


def hgnn(fast: bool) -> dict:
    return train_hgnn(cohort_path(fast), fast=fast, config=TrainConfig())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VitaNexus-RX reproducible FAERS ML pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("preprocess", "train-lightgbm", "train-hgnn", "evaluate", "all"):
        command = subparsers.add_parser(name)
        command.add_argument("--fast", action="store_true", help="Explicit development smoke mode; outputs are labelled non-final")
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    ensure_output_directories()
    if args.command == "serve":
        uvicorn.run("vitanexus_ml.api.app:app", host=args.host, port=args.port)
        return 0
    if args.command == "preprocess":
        result = preprocess(args.fast)
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
