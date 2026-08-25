import json
from pathlib import Path
from zipfile import ZipFile

import pyarrow.parquet as pq

from vitanexus_ml.data.discovery import discover_quarters
from vitanexus_ml.data.faers import FaersPreprocessor


def _archive(path: Path, quarter: str, version: int, primaryid: str, caseid: str = "10", drug_rows: str | None = None):
    suffix = quarter[2:]
    tables = {
        f"ASCII/DEMO{suffix}.txt": f"primaryid$caseid$caseversion$fda_dt$age$age_cod$sex\n{primaryid}${caseid}${version}$20260101$60$YR$F\n",
        f"ASCII/DRUG{suffix}.txt": drug_rows or f"primaryid$caseid$drug_seq$role_cod$drugname$prod_ai\n{primaryid}${caseid}$1$PS$TYLENOL$ACETAMINOPHEN\n{primaryid}${caseid}$2$C$WARFARIN$WARFARIN\n",
        f"ASCII/REAC{suffix}.txt": f"primaryid$caseid$pt\n{primaryid}${caseid}$Nausea\n{primaryid}${caseid}$Nausea\n",
        f"ASCII/INDI{suffix}.txt": f"primaryid$caseid$indi_drug_seq$indi_pt\n{primaryid}${caseid}$1$Pain\n",
        f"ASCII/OUTC{suffix}.txt": f"primaryid$caseid$outc_cod\n{primaryid}${caseid}$HO\n",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as archive:
        for name, content in tables.items():
            archive.writestr(name, content)


def test_zip_discovery_deduplication_and_cohort(tmp_path):
    raw = tmp_path / "raw"
    _archive(raw / "2022" / "faers_ascii_2022q1.zip", "22Q1", 1, "100")
    _archive(raw / "2026" / "faers_ascii_2026q1.zip", "26Q1", 2, "200")
    (raw / "2026" / "Unconfirmed.crdownload").write_bytes(b"partial")
    discovered = discover_quarters(raw)
    assert [item.quarter for item in discovered] == ["2022Q1", "2026Q1"]
    output = tmp_path / "processed"
    report = FaersPreprocessor(raw, output).run()
    assert report["deduplication"]["versionsRemoved"] == 1
    frame = pq.read_table(output / "cohort.parquet").to_pandas()
    assert frame["quarter"].tolist() == ["2026Q1"]
    assert frame.iloc[0].candidate_drug == "PARACETAMOL"
    assert frame.iloc[0].reactions == ["NAUSEA"]
    assert frame.iloc[0].has_serious_outcome == 1
    manifest = json.loads((output / "dataset_manifest.json").read_text())
    assert len(manifest["quarters"][0]["sha256"]) == 64


def test_single_primary_suspect_filter(tmp_path):
    raw = tmp_path / "raw"
    path = raw / "2022" / "faers_ascii_2022q1.zip"
    _archive(path, "22Q1", 1, "100", drug_rows="primaryid$caseid$drug_seq$role_cod$drugname$prod_ai\n100$10$1$PS$A$A\n100$10$2$PS$B$B\n")
    report = FaersPreprocessor(raw, tmp_path / "out").run()
    assert report["finalCohortSize"] == 0
