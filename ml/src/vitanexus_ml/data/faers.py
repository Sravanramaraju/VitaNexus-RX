from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from zipfile import ZipFile

import pyarrow as pa
import pyarrow.parquet as pq

from vitanexus_ml.config import PREPROCESSING_VERSION, SERIOUS_OUTCOME_CODES
from vitanexus_ml.data.discovery import QuarterSource, discover_quarters, sha256_file
from vitanexus_ml.normalization import age_in_years, normalize_drug, normalize_indication, normalize_reaction, normalize_sex


REQUIRED_TABLES = frozenset({"DEMO", "DRUG", "REAC", "INDI", "OUTC"})
REQUIRED_COLUMNS = {
    "DEMO": {"primaryid", "caseid", "caseversion", "age", "age_cod", "sex"},
    "DRUG": {"primaryid", "caseid", "drug_seq", "role_cod", "drugname"},
    "REAC": {"primaryid", "caseid", "pt"},
    "INDI": {"primaryid", "caseid", "indi_drug_seq", "indi_pt"},
    "OUTC": {"primaryid", "caseid", "outc_cod"},
}


@dataclass
class ParseStats:
    rows: int = 0
    malformed: int = 0


@contextmanager
def open_table(source: QuarterSource, table: str):
    if source.is_zip:
        archive = ZipFile(source.source_path)
        raw = archive.open(source.tables[table])
        text = io.TextIOWrapper(raw, encoding="latin-1", errors="replace", newline="")
        try:
            yield text
        finally:
            text.close()
            archive.close()
    else:
        with Path(source.tables[table]).open("r", encoding="latin-1", errors="replace", newline="") as text:
            yield text


def iter_rows(source: QuarterSource, table: str, stats: ParseStats | None = None) -> Iterator[dict[str, str]]:
    stats = stats or ParseStats()
    with open_table(source, table) as stream:
        reader = csv.DictReader(stream, delimiter="$", restkey="__extra__", restval="")
        if not reader.fieldnames:
            return
        reader.fieldnames = [str(name).strip().lower() for name in reader.fieldnames]
        for row in reader:
            stats.rows += 1
            if row.get("__extra__"):
                stats.malformed += 1
            yield {str(key).strip().lower(): (value or "").strip() for key, value in row.items() if key != "__extra__"}


def table_columns(source: QuarterSource, table: str) -> list[str]:
    with open_table(source, table) as stream:
        return [value.strip().lower() for value in stream.readline().rstrip("\r\n").split("$")]


def _version_key(row: dict[str, str]) -> tuple[int, str, int]:
    try:
        version = int(row.get("caseversion") or 0)
    except ValueError:
        version = 0
    date = row.get("fda_dt") or row.get("rept_dt") or row.get("mfr_dt") or ""
    try:
        primary = int(row.get("primaryid") or 0)
    except ValueError:
        primary = 0
    return version, date, primary


class FaersPreprocessor:
    def __init__(self, raw_root: Path, output_root: Path, *, fast: bool = False, max_rows_per_table: int = 50_000):
        self.raw_root = raw_root
        self.output_root = output_root
        self.fast = fast
        self.max_rows_per_table = max_rows_per_table
        self.stats: dict = {"preprocessingVersion": PREPROCESSING_VERSION, "fastMode": fast, "quarters": {}, "deduplication": {}}

    def run(self) -> dict:
        self.output_root.mkdir(parents=True, exist_ok=True)
        sources = discover_quarters(self.raw_root)
        if not sources:
            raise RuntimeError(f"No FAERS quarters discovered under {self.raw_root}")
        missing = {source.quarter: sorted(REQUIRED_TABLES - source.tables.keys()) for source in sources if REQUIRED_TABLES - source.tables.keys()}
        if missing:
            raise RuntimeError(f"Required FAERS tables missing: {missing}")
        self._audit_schemas(sources)
        db_path = self.output_root / "case_history.sqlite3"
        connection = sqlite3.connect(db_path)
        try:
            self._create_history(connection)
            self._scan_history(connection, sources)
            retained = self._retained_by_quarter(connection)
            output_path = self.output_root / ("cohort_fast.parquet" if self.fast else "cohort.parquet")
            writer: pq.ParquetWriter | None = None
            try:
                for source in sources:
                    rows = self._build_quarter(source, retained.get(source.quarter, {}))
                    if rows:
                        table = pa.Table.from_pylist(rows)
                        writer = writer or pq.ParquetWriter(output_path, table.schema, compression="zstd")
                        writer.write_table(table)
            finally:
                if writer:
                    writer.close()
            self.stats["cohortPath"] = str(output_path)
            self.stats["finalCohortSize"] = sum(item.get("retainedCohortRows", 0) for item in self.stats["quarters"].values())
            self.stats["seriousOutcomeClassDistribution"] = dict(Counter(
                row["has_serious_outcome"] for row in pq.read_table(output_path, columns=["has_serious_outcome"]).to_pylist()
            )) if output_path.exists() else {}
            self._write_manifest(sources)
            (self.output_root / "data_quality.json").write_text(json.dumps(self.stats, indent=2), encoding="utf-8")
            return self.stats
        finally:
            connection.close()

    @staticmethod
    def _create_history(connection: sqlite3.Connection) -> None:
        connection.execute("DROP TABLE IF EXISTS case_history")
        connection.execute("CREATE TABLE case_history (caseid TEXT PRIMARY KEY, caseversion INTEGER, primaryid TEXT, quarter TEXT, date_key TEXT, age TEXT, age_cod TEXT, sex TEXT)")

    def _audit_schemas(self, sources: list[QuarterSource]) -> None:
        baseline: dict[str, set[str]] = {}
        differences = []
        for source in sources:
            quarter_stats = self.stats["quarters"].setdefault(source.quarter, {})
            quarter_stats["rawSource"] = str(source.source_path.relative_to(self.raw_root))
            quarter_stats["parsedTables"] = sorted(source.tables)
            quarter_stats["rawFiles"] = source.tables
            quarter_stats["schemas"] = {}
            for table in sorted(REQUIRED_TABLES):
                columns = table_columns(source, table)
                column_set = set(columns)
                missing_required = sorted(REQUIRED_COLUMNS[table] - column_set)
                quarter_stats["schemas"][table] = {"columns": columns, "missingRequiredColumns": missing_required}
                if missing_required:
                    raise RuntimeError(f"{source.quarter} {table} is missing required columns: {missing_required}")
                if table not in baseline:
                    baseline[table] = column_set
                elif column_set != baseline[table]:
                    differences.append({"quarter": source.quarter, "table": table, "added": sorted(column_set - baseline[table]), "removed": sorted(baseline[table] - column_set)})
        self.stats["schemaDifferences"] = differences

    def _scan_history(self, connection: sqlite3.Connection, sources: list[QuarterSource]) -> None:
        before = 0
        for source in sources:
            parse = ParseStats()
            batch = []
            for row in iter_rows(source, "DEMO", parse):
                if self.fast and parse.rows > self.max_rows_per_table:
                    break
                caseid, primaryid = row.get("caseid"), row.get("primaryid")
                if not caseid or not primaryid:
                    parse.malformed += 1
                    continue
                version, date_key, _ = _version_key(row)
                batch.append((caseid, version, primaryid, source.quarter, date_key, row.get("age"), row.get("age_cod"), row.get("sex")))
                if len(batch) >= 10_000:
                    self._upsert_history(connection, batch)
                    batch.clear()
            self._upsert_history(connection, batch)
            connection.commit()
            before += parse.rows
            self.stats["quarters"].setdefault(source.quarter, {})["DEMO"] = vars(parse)
        unique = connection.execute("SELECT COUNT(*) FROM case_history").fetchone()[0]
        self.stats["deduplication"] = {
            "demoRecordsBeforeDeduplication": before,
            "uniqueCaseIds": unique,
            "versionsRemoved": max(0, before - unique),
            "retainedCases": unique,
        }

    @staticmethod
    def _upsert_history(connection: sqlite3.Connection, batch: list[tuple]) -> None:
        if not batch:
            return
        connection.executemany(
            """INSERT INTO case_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(caseid) DO UPDATE SET
              caseversion=excluded.caseversion, primaryid=excluded.primaryid, quarter=excluded.quarter,
              date_key=excluded.date_key, age=excluded.age, age_cod=excluded.age_cod, sex=excluded.sex
            WHERE excluded.caseversion > case_history.caseversion
               OR (excluded.caseversion = case_history.caseversion AND excluded.date_key > case_history.date_key)
               OR (excluded.caseversion = case_history.caseversion AND excluded.date_key = case_history.date_key AND CAST(excluded.primaryid AS INTEGER) > CAST(case_history.primaryid AS INTEGER))""",
            batch,
        )

    @staticmethod
    def _retained_by_quarter(connection: sqlite3.Connection) -> dict[str, dict[str, dict]]:
        retained: dict[str, dict[str, dict]] = defaultdict(dict)
        for caseid, version, primaryid, quarter, _, age, age_cod, sex in connection.execute("SELECT * FROM case_history"):
            retained[quarter][primaryid] = {"caseid": caseid, "caseversion": version, "age": age, "age_cod": age_cod, "sex": sex}
        return retained

    def _build_quarter(self, source: QuarterSource, retained: dict[str, dict]) -> list[dict]:
        primary_ids = set(retained)
        drugs: dict[str, list[dict]] = defaultdict(list)
        reactions: dict[str, set[str]] = defaultdict(set)
        indications: dict[str, list[tuple[str, str]]] = defaultdict(list)
        outcomes: dict[str, set[str]] = defaultdict(set)
        quarter_stats = self.stats["quarters"].setdefault(source.quarter, {})
        targets = (("DRUG", drugs), ("REAC", reactions), ("INDI", indications), ("OUTC", outcomes))
        for table_name, _ in targets:
            parse = ParseStats()
            for row in iter_rows(source, table_name, parse):
                if self.fast and parse.rows > self.max_rows_per_table:
                    break
                primaryid = row.get("primaryid")
                if primaryid not in primary_ids:
                    continue
                if table_name == "DRUG":
                    drugs[primaryid].append(row)
                elif table_name == "REAC":
                    reaction = normalize_reaction(row.get("pt"))
                    if reaction:
                        reactions[primaryid].add(reaction)
                elif table_name == "INDI":
                    indication = normalize_indication(row.get("indi_pt"))
                    indications[primaryid].append((row.get("indi_drug_seq", ""), indication))
                else:
                    code = str(row.get("outc_cod") or "").upper()
                    if code:
                        outcomes[primaryid].add(code)
            quarter_stats[table_name] = vars(parse)
        rows: list[dict] = []
        exclusions = Counter()
        for primaryid, demo in retained.items():
            report_drugs = drugs.get(primaryid, [])
            primary_suspects = [row for row in report_drugs if str(row.get("role_cod")).upper() == "PS"]
            if len(primary_suspects) != 1:
                exclusions["multiOrMissingPrimarySuspect"] += 1
                continue
            if not reactions.get(primaryid):
                exclusions["missingReaction"] += 1
                continue
            suspect = primary_suspects[0]
            drug = normalize_drug(suspect.get("prod_ai") or suspect.get("drugname"))
            if drug == "UNKNOWN":
                exclusions["unidentifiableCandidate"] += 1
                continue
            linked = sorted({value for sequence, value in indications.get(primaryid, []) if sequence == suspect.get("drug_seq")})
            current = sorted({normalize_drug(item.get("prod_ai") or item.get("drugname")) for item in report_drugs if str(item.get("role_cod")).upper() == "C"})
            current = [item for item in current if item != "UNKNOWN"]
            age = age_in_years(demo.get("age"), demo.get("age_cod"))
            rows.append({
                "caseid": demo["caseid"], "primaryid": primaryid, "caseversion": demo["caseversion"], "quarter": source.quarter,
                "age_years": age, "age_missing": age is None, "sex": normalize_sex(demo.get("sex")),
                "candidate_drug": drug, "indication": " | ".join(linked) if linked else "UNKNOWN",
                "current_medications": current, "reactions": sorted(reactions[primaryid]),
                "outcome_codes": sorted(outcomes.get(primaryid, set())),
                "has_serious_outcome": int(bool(outcomes.get(primaryid, set()) & SERIOUS_OUTCOME_CODES)),
            })
        quarter_stats["retainedLatestCases"] = len(retained)
        quarter_stats["retainedCohortRows"] = len(rows)
        quarter_stats["exclusions"] = dict(exclusions)
        return rows

    def _write_manifest(self, sources: list[QuarterSource]) -> None:
        manifest = {
            "preprocessingVersion": PREPROCESSING_VERSION,
            "quarters": [
                {"quarter": source.quarter, "sourcePath": str(source.source_path.relative_to(self.raw_root)), "isZip": source.is_zip, "tables": source.tables, "sha256": sha256_file(source.source_path) if source.is_zip else None}
                for source in sources
            ],
        }
        (self.output_root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
