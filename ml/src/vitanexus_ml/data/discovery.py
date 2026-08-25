from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import ZipFile


QUARTER_PATTERN = re.compile(r"(?P<year>20\d{2})[^0-9]*[Qq](?P<quarter>[1-4])")
TABLE_PATTERN = re.compile(r"^(DEMO|DRUG|REAC|INDI|OUTC|THER|RPSR).*\.TXT$", re.I)


@dataclass(frozen=True)
class QuarterSource:
    quarter: str
    source_path: Path
    is_zip: bool
    tables: dict[str, str]

    def serializable(self) -> dict:
        value = asdict(self)
        value["source_path"] = str(self.source_path)
        return value


def quarter_from_path(path: Path) -> str | None:
    match = QUARTER_PATTERN.search(path.name)
    if not match:
        match = QUARTER_PATTERN.search(str(path.parent))
    return f"{match.group('year')}Q{match.group('quarter')}" if match else None


def discover_quarters(root: Path) -> list[QuarterSource]:
    sources: list[QuarterSource] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file() or path.suffix.lower() == ".crdownload":
            continue
        quarter = quarter_from_path(path)
        if not quarter:
            continue
        if path.suffix.lower() == ".zip":
            with ZipFile(path) as archive:
                tables = _table_map(archive.namelist())
            if tables:
                sources.append(QuarterSource(quarter, path, True, tables))
        elif path.suffix.lower() == ".txt":
            table = _table_name(path.name)
            if table:
                existing = next((item for item in sources if item.quarter == quarter and not item.is_zip), None)
                if existing:
                    existing.tables[table] = str(path)
                else:
                    sources.append(QuarterSource(quarter, path.parent, False, {table: str(path)}))
    unique: dict[str, QuarterSource] = {}
    for source in sources:
        current = unique.get(source.quarter)
        if current is None or (source.is_zip and not current.is_zip):
            unique[source.quarter] = source
    return [unique[key] for key in sorted(unique)]


def _table_name(name: str) -> str | None:
    match = TABLE_PATTERN.match(Path(name).name)
    return match.group(1).upper() if match else None


def _table_map(names: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        table = _table_name(name)
        if table and table not in result:
            result[table] = name
    return result


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
