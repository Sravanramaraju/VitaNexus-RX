from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np
from scipy import sparse

from vitanexus_ml.config import FEATURE_SCHEMA_VERSION, TrainConfig
from vitanexus_ml.normalization import normalize_drug, normalize_indication, normalize_sex


UNKNOWN = "UNKNOWN"


def _items(value) -> list:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    return list(value) if not isinstance(value, str) else [value]


def _vocabulary(values, limit: int) -> dict[str, int]:
    counts = Counter(value for value in values if value and value != UNKNOWN)
    return _vocabulary_from_counts(counts, limit)


def _vocabulary_from_counts(counts: Counter, limit: int) -> dict[str, int]:
    ordered = sorted(counts, key=lambda value: (-counts[value], value))[:limit]
    return {UNKNOWN: 0, **{value: index + 1 for index, value in enumerate(ordered)}}


@dataclass
class InputCoverage:
    candidateKnown: bool
    indicationKnown: bool
    recognizedCurrentMedications: int
    unknownCurrentMedications: list[str]


class FeatureBuilder:
    """Deterministic sparse encoder fitted only on model-training rows."""

    def __init__(self, config: TrainConfig | None = None):
        self.config = config or TrainConfig()
        self.candidate_vocabulary: dict[str, int] = {}
        self.indication_vocabulary: dict[str, int] = {}
        self.medication_vocabulary: dict[str, int] = {}
        self.interaction_vocabulary: dict[str, int] = {}
        self.feature_names: list[str] = []
        self.fitted = False

    def fit(self, rows) -> "FeatureBuilder":
        candidates = [normalize_drug(value) for value in rows["candidate_drug"]]
        indications = [normalize_indication(value) for value in rows["indication"]]
        medications = [normalize_drug(item) for values in rows["current_medications"] for item in _items(values)]
        interactions = [f"{candidate}::{indication}" for candidate, indication in zip(candidates, indications)]
        return self.fit_from_counts(
            Counter(candidates), Counter(indications), Counter(medications), Counter(interactions),
        )

    def fit_from_counts(
        self,
        candidate_counts: Counter,
        indication_counts: Counter,
        medication_counts: Counter,
        interaction_counts: Counter,
    ) -> "FeatureBuilder":
        """Fit deterministic vocabularies from streaming training-only counts."""
        self.candidate_vocabulary = _vocabulary_from_counts(candidate_counts, self.config.candidate_vocabulary_size)
        self.indication_vocabulary = _vocabulary_from_counts(indication_counts, self.config.indication_vocabulary_size)
        self.medication_vocabulary = _vocabulary_from_counts(medication_counts, self.config.medication_vocabulary_size)
        self.interaction_vocabulary = _vocabulary_from_counts(interaction_counts, self.config.interaction_vocabulary_size)
        self.feature_names = self._make_feature_names()
        self.fitted = True
        return self

    def transform(self, rows, *, return_coverage: bool = False):
        if not self.fitted:
            raise RuntimeError("FeatureBuilder must be fitted before transform")
        indices: list[int] = []
        data: list[float] = []
        indptr = [0]
        coverage = []
        columns = ["age_years", "sex", "candidate_drug", "indication", "current_medications"]
        for age, sex, candidate, indication, medications in rows[columns].itertuples(index=False, name=None):
            values, item_coverage = self._encoded_values(age, sex, candidate, indication, _items(medications))
            indices.extend(values[0])
            data.extend(values[1])
            indptr.append(len(indices))
            if return_coverage:
                coverage.append(item_coverage)
        matrix = sparse.csr_matrix(
            (np.asarray(data, dtype=np.float32), np.asarray(indices, dtype=np.int32), np.asarray(indptr, dtype=np.int64)),
            shape=(len(rows), len(self.feature_names)),
        )
        return (matrix, coverage) if return_coverage else matrix

    def transform_one(self, payload: dict) -> tuple[sparse.csr_matrix, InputCoverage]:
        encoded, coverage = self._encoded_values(
            payload.get("age"), payload.get("sex"), payload.get("candidateDrug"),
            payload.get("indication"), payload.get("currentMedications", []),
        )
        indices, values = encoded
        matrix = sparse.csr_matrix((values, ([0] * len(indices), indices)), shape=(1, len(self.feature_names)), dtype=np.float32)
        return matrix, coverage

    def _encoded_values(self, age, sex_value, candidate_value, indication_value, medication_values):
        age_missing = age is None or (isinstance(age, float) and np.isnan(age))
        age_value = 0.0 if age_missing else min(120.0, max(0.0, float(age))) / 120.0
        sex = normalize_sex(sex_value)
        candidate = normalize_drug(candidate_value)
        indication = normalize_indication(indication_value)
        medications = sorted({normalize_drug(value) for value in medication_values if value})
        unknown_medications = [value for value in medications if value not in self.medication_vocabulary]
        known_medications = [value for value in medications if value in self.medication_vocabulary and value != UNKNOWN]
        interaction = f"{candidate}::{indication}"
        offsets = self._offsets()
        indices: list[int] = []
        values: list[float] = []
        numeric = [age_value, float(age_missing), float(len(medications)), float(len(medications) >= 5), float(len(unknown_medications))]
        for index, value in enumerate(numeric):
            if value:
                indices.append(index)
                values.append(value)
        sex_index = {"M": 0, "F": 1, UNKNOWN: 2}[sex]
        indices.append(offsets["sex"] + sex_index); values.append(1.0)
        indices.append(offsets["candidate"] + self.candidate_vocabulary.get(candidate, 0)); values.append(1.0)
        indices.append(offsets["indication"] + self.indication_vocabulary.get(indication, 0)); values.append(1.0)
        indices.append(offsets["interaction"] + self.interaction_vocabulary.get(interaction, 0)); values.append(1.0)
        for medication in known_medications:
            indices.append(offsets["medication"] + self.medication_vocabulary[medication]); values.append(1.0)
        return (indices, values), InputCoverage(
            candidateKnown=candidate in self.candidate_vocabulary and candidate != UNKNOWN,
            indicationKnown=indication in self.indication_vocabulary and indication != UNKNOWN,
            recognizedCurrentMedications=len(known_medications), unknownCurrentMedications=unknown_medications,
        )

    def metadata(self) -> dict:
        return {
            "schemaVersion": FEATURE_SCHEMA_VERSION,
            "config": asdict(self.config),
            "featureCount": len(self.feature_names),
            "candidateVocabularySize": len(self.candidate_vocabulary),
            "indicationVocabularySize": len(self.indication_vocabulary),
            "medicationVocabularySize": len(self.medication_vocabulary),
            "interactionVocabularySize": len(self.interaction_vocabulary),
        }

    def _offsets(self) -> dict[str, int]:
        sex = 5
        candidate = sex + 3
        indication = candidate + len(self.candidate_vocabulary)
        interaction = indication + len(self.indication_vocabulary)
        medication = interaction + len(self.interaction_vocabulary)
        return {"sex": sex, "candidate": candidate, "indication": indication, "interaction": interaction, "medication": medication}

    def _make_feature_names(self) -> list[str]:
        names = ["age_scaled", "age_missing", "medication_count", "polypharmacy", "unknown_medication_count", "sex_M", "sex_F", "sex_UNKNOWN"]
        for prefix, vocabulary in (("candidate", self.candidate_vocabulary), ("indication", self.indication_vocabulary), ("candidate_indication", self.interaction_vocabulary), ("medication", self.medication_vocabulary)):
            names.extend(f"{prefix}={value}" for value, _ in sorted(vocabulary.items(), key=lambda item: item[1]))
        return names
