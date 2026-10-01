import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
import torch

import vitanexus_ml.models.hgnn_colab_pipeline as hgnn_pipeline
from vitanexus_ml.models.hgnn_colab_pipeline import (
    _selection_evaluation_report,
    _streaming_label_positive_counts,
    focal_loss_with_logits,
    focal_positive_alpha,
)


def test_focal_alpha_uses_only_training_prevalence_and_respects_bounds():
    alpha = focal_positive_alpha(
        np.asarray([50, 5, 1], dtype=np.int64),
        100,
        minimum=0.25,
        maximum=0.95,
    )
    assert alpha.tolist() == pytest.approx([0.5, 0.95, 0.95])


def test_focal_counts_exclude_validation_rows(tmp_path, monkeypatch):
    cohort = tmp_path / "cohort.parquet"
    pd.DataFrame([
        {"quarter": "2024Q4", "reactions": ["Nausea"]},
        {"quarter": "2025Q1", "reactions": ["Vomiting"]},
    ]).to_parquet(cohort, index=False)
    monkeypatch.setitem(hgnn_pipeline.EXPECTED_ROWS, "developmentTrain", 1)

    counts, rows = _streaming_label_positive_counts(
        pq.ParquetFile(cohort), [{"term": "NAUSEA", "index": 0}]
    )

    assert rows == 1
    assert counts.tolist() == [1]


def test_multilabel_focal_loss_is_finite_and_differentiable():
    logits = torch.tensor([[1.0, -1.0], [-0.5, 0.5]], requires_grad=True)
    targets = torch.tensor([[1.0, 0.0], [0.0, 1.0]])
    alpha = torch.tensor([0.8, 0.9])
    loss = focal_loss_with_logits(logits, targets, alpha, gamma=2.0)
    loss.backward()
    assert torch.isfinite(loss)
    assert logits.grad is not None
    assert torch.isfinite(logits.grad).all()


def test_selection_evaluation_includes_all_label_and_top_k_diagnostics():
    vocabulary = [{"term": f"ADR-{index:02d}", "index": index} for index in range(10)]
    targets = np.eye(10, dtype=np.int8)
    probabilities = np.full((10, 10), 0.01)
    np.fill_diagonal(probabilities, 0.99)

    report = _selection_evaluation_report(targets, probabilities, vocabulary, top_k=(5, 10))

    assert report["threshold"] == 0.5
    assert len(report["perLabel"]) == 10
    assert len(report["top10ByAUPRC"]) == 10
    assert len(report["bottom10ByAUPRC"]) == 10
    assert report["topK"]["precisionAt5"] == pytest.approx(0.2)
    assert report["topK"]["recallAt5"] == pytest.approx(1.0)
    assert report["topK"]["precisionAt10"] == pytest.approx(0.1)
    assert report["topK"]["recallAt10"] == pytest.approx(1.0)
