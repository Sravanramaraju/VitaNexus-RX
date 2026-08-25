from __future__ import annotations

import re
import unicodedata


_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^A-Z0-9+/. -]+")


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    text = _PUNCT.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


_DRUG_EQUIVALENTS = {
    "ACETAMINOPHEN": "PARACETAMOL",
    "PARACETAMOL ACETAMINOPHEN": "PARACETAMOL",
}


def normalize_drug(value: object) -> str:
    normalized = normalize_text(value)
    return _DRUG_EQUIVALENTS.get(normalized, normalized or "UNKNOWN")


def normalize_indication(value: object) -> str:
    return normalize_text(value) or "UNKNOWN"


def normalize_reaction(value: object) -> str:
    return normalize_text(value)


def normalize_sex(value: object) -> str:
    normalized = normalize_text(value)
    return normalized if normalized in {"M", "F"} else "UNKNOWN"


_AGE_TO_YEARS = {
    "YR": 1.0,
    "DEC": 10.0,
    "MON": 1.0 / 12.0,
    "WK": 1.0 / 52.1429,
    "DY": 1.0 / 365.2425,
    "HR": 1.0 / (365.2425 * 24.0),
}


def age_in_years(age: object, unit: object) -> float | None:
    try:
        number = float(str(age).strip())
    except (TypeError, ValueError):
        return None
    factor = _AGE_TO_YEARS.get(normalize_text(unit))
    if factor is None:
        return None
    years = number * factor
    return round(years, 4) if 0 <= years <= 120 else None
