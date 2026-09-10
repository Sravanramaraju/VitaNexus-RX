from pathlib import Path

from vitanexus_ml import cli
from vitanexus_ml.models import operating_threshold


def test_threshold_cli_passes_explicit_frozen_inputs(monkeypatch, tmp_path, capsys):
    cohort = tmp_path / "cohort.parquet"
    artifact = tmp_path / "serious_outcome.joblib"
    reports = tmp_path / "reports"
    captured = {}

    def fake_optimize(**kwargs):
        captured.update(kwargs)
        return {"selected": 0.4}

    monkeypatch.setattr(operating_threshold, "optimize_existing_lightgbm_threshold", fake_optimize)
    assert cli.main([
        "optimize-lightgbm-threshold",
        "--cohort", str(cohort),
        "--artifact", str(artifact),
        "--report-root", str(reports),
        "--sensitivity", "0.9",
        "--step", "0.001",
    ]) == 0
    assert captured["cohort_path"] == Path(cohort)
    assert captured["serious_artifact_path"] == Path(artifact)
    assert captured["report_root"] == Path(reports)
    assert captured["sensitivity_constraint"] == 0.9
    assert captured["threshold_step"] == 0.001
    assert '"selected": 0.4' in capsys.readouterr().out
