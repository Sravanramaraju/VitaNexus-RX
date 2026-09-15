from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.neural_network import MLPClassifier
from sklearn.multiclass import OneVsRestClassifier
from torch import nn
from torch_geometric.data import HeteroData
from torch_geometric.nn import HeteroConv, SAGEConv

from vitanexus_ml.config import ARTIFACT_ROOT, HGNN_VERSION, REPORT_ROOT, TrainConfig, ensure_output_directories
from vitanexus_ml.normalization import normalize_drug, normalize_indication, normalize_reaction, normalize_sex


RELATIONS = (
    ("report", "primary_suspect", "drug"), ("drug", "rev_primary_suspect", "report"),
    ("report", "concomitant", "drug"), ("drug", "rev_concomitant", "report"),
    ("report", "indication", "indication"), ("indication", "rev_indication", "report"),
    ("drug", "historically_associated", "adr"), ("adr", "rev_historically_associated", "drug"),
    ("indication", "historically_associated", "adr"), ("adr", "rev_indication_associated", "indication"),
)


def _items(value) -> list:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    return list(value) if not isinstance(value, str) else [value]


def build_adr_vocabulary(rows: pd.DataFrame, min_frequency: int = 500, max_labels: int = 100) -> list[dict]:
    counts = Counter(normalize_reaction(term) for values in rows["reactions"] for term in _items(values))
    ordered = sorted(((term, count) for term, count in counts.items() if term and count >= min_frequency), key=lambda item: (-item[1], item[0]))[:max_labels]
    return [{"term": term, "trainingFrequency": count, "index": index, "version": HGNN_VERSION} for index, (term, count) in enumerate(ordered)]


def _hash_features(value: str, dimensions: int = 64) -> list[float]:
    vector = np.zeros(dimensions, dtype=np.float32)
    for token in value.split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "big") % dimensions] += 1.0 if digest[4] % 2 else -1.0
    norm = np.linalg.norm(vector)
    return (vector / norm if norm else vector).tolist()


def historical_associations(rows: pd.DataFrame, labels: dict[str, int], minimum: int = 2) -> dict[str, dict[str, list[int]]]:
    drug_counts: dict[str, Counter] = defaultdict(Counter)
    indication_counts: dict[str, Counter] = defaultdict(Counter)
    for _, row in rows.iterrows():
        present = {labels[normalize_reaction(term)] for term in _items(row["reactions"]) if normalize_reaction(term) in labels}
        candidate = normalize_drug(row["candidate_drug"])
        indication = normalize_indication(row["indication"])
        for index in present:
            drug_counts[candidate][index] += 1
            indication_counts[indication][index] += 1
    return {
        "drug": {key: sorted(index for index, count in values.items() if count >= minimum) for key, values in drug_counts.items()},
        "indication": {key: sorted(index for index, count in values.items() if count >= minimum) for key, values in indication_counts.items()},
    }


def _edge(pairs: list[tuple[int, int]]) -> torch.Tensor:
    return torch.tensor(pairs, dtype=torch.long).t().contiguous() if pairs else torch.empty((2, 0), dtype=torch.long)


def build_heterodata(rows: pd.DataFrame, vocabulary: list[dict], associations: dict, *, include_targets: bool) -> HeteroData:
    label_index = {item["term"]: item["index"] for item in vocabulary}
    drugs = sorted({normalize_drug(row["candidate_drug"]) for _, row in rows.iterrows()} | {normalize_drug(value) for values in rows["current_medications"] for value in _items(values)})
    indications = sorted({normalize_indication(value) for value in rows["indication"]})
    drug_index = {value: index for index, value in enumerate(drugs)}
    indication_index = {value: index for index, value in enumerate(indications)}
    data = HeteroData()
    report_features = []
    primary, concomitant, report_indication = [], [], []
    targets = np.zeros((len(rows), len(vocabulary)), dtype=np.float32)
    for report_index, (_, row) in enumerate(rows.iterrows()):
        age = row.get("age_years")
        age_missing = age is None or pd.isna(age)
        sex = normalize_sex(row.get("sex"))
        report_features.append([0.0 if age_missing else float(age) / 120.0, float(age_missing), float(sex == "M"), float(sex == "F"), float(len(_items(row.get("current_medications")))) / 20.0])
        candidate = normalize_drug(row["candidate_drug"])
        primary.append((report_index, drug_index[candidate]))
        for value in _items(row.get("current_medications")):
            concomitant.append((report_index, drug_index[normalize_drug(value)]))
        indication = normalize_indication(row["indication"])
        report_indication.append((report_index, indication_index[indication]))
        if include_targets:
            for term in _items(row.get("reactions")):
                index = label_index.get(normalize_reaction(term))
                if index is not None:
                    targets[report_index, index] = 1.0
    data["report"].x = torch.tensor(report_features, dtype=torch.float32)
    data["drug"].x = torch.tensor([_hash_features(value) for value in drugs], dtype=torch.float32)
    data["indication"].x = torch.tensor([_hash_features(value) for value in indications], dtype=torch.float32)
    data["adr"].x = torch.eye(len(vocabulary), dtype=torch.float32)
    for relation, pairs in (
        (("report", "primary_suspect", "drug"), primary), (("report", "concomitant", "drug"), concomitant), (("report", "indication", "indication"), report_indication),
    ):
        data[relation].edge_index = _edge(pairs)
        reverse = (relation[2], f"rev_{relation[1]}", relation[0])
        data[reverse].edge_index = _edge([(target, source) for source, target in pairs])
    drug_associations = [(drug_index[drug], adr) for drug in drugs for adr in associations["drug"].get(drug, [])]
    indication_associations = [(indication_index[value], adr) for value in indications for adr in associations["indication"].get(value, [])]
    data[("drug", "historically_associated", "adr")].edge_index = _edge(drug_associations)
    data[("adr", "rev_historically_associated", "drug")].edge_index = _edge([(target, source) for source, target in drug_associations])
    data[("indication", "historically_associated", "adr")].edge_index = _edge(indication_associations)
    data[("adr", "rev_indication_associated", "indication")].edge_index = _edge([(target, source) for source, target in indication_associations])
    if include_targets:
        data["report"].y = torch.tensor(targets, dtype=torch.float32)
    data.graph_metadata = {"targetRelationExcludedFromEncoder": True, "relations": [list(item) for item in RELATIONS]}
    return data


class HeterogeneousAdrNetwork(nn.Module):
    def __init__(self, hidden_channels: int, output_labels: int):
        super().__init__()
        self.projections = nn.ModuleDict({node_type: nn.LazyLinear(hidden_channels) for node_type in ("report", "drug", "indication", "adr")})
        self.convs = nn.ModuleList([
            HeteroConv({relation: SAGEConv((-1, -1), hidden_channels) for relation in RELATIONS}, aggr="sum") for _ in range(2)
        ])
        self.output = nn.Linear(hidden_channels, output_labels)

    def forward(self, data: HeteroData) -> torch.Tensor:
        x_dict = {node_type: torch.relu(self.projections[node_type](features)) for node_type, features in data.x_dict.items()}
        for conv in self.convs:
            updated = conv(x_dict, data.edge_index_dict)
            x_dict = {node_type: torch.relu(updated.get(node_type, values) + values) for node_type, values in x_dict.items()}
        return self.output(x_dict["report"])


def _multilabel_metrics(targets: np.ndarray, probabilities: np.ndarray, threshold: float = 0.5) -> dict:
    predictions = probabilities >= threshold
    valid = np.where(targets.sum(axis=0) > 0)[0]
    return {
        "microAUPRC": float(average_precision_score(targets, probabilities, average="micro")),
        "macroAUPRC": float(average_precision_score(targets[:, valid], probabilities[:, valid], average="macro")) if len(valid) else None,
        "microF1": float(f1_score(targets, predictions, average="micro", zero_division=0)),
        "microPrecision": float(precision_score(targets, predictions, average="micro", zero_division=0)),
        "microRecall": float(recall_score(targets, predictions, average="micro", zero_division=0)),
    }


def _targets(rows: pd.DataFrame, vocabulary: list[dict]) -> np.ndarray:
    index = {item["term"]: item["index"] for item in vocabulary}
    values = np.zeros((len(rows), len(vocabulary)), dtype=np.int8)
    for row_index, reactions in enumerate(rows["reactions"]):
        for reaction in _items(reactions):
            if normalize_reaction(reaction) in index:
                values[row_index, index[normalize_reaction(reaction)]] = 1
    return values


def train_hgnn(cohort_path: Path, *, fast: bool = False, config: TrainConfig | None = None) -> dict:
    config = config or TrainConfig()
    artifact_version = f"{HGNN_VERSION}-fast-smoke" if fast else HGNN_VERSION
    ensure_output_directories()
    torch.manual_seed(config.seed); np.random.seed(config.seed)
    frame = pd.read_parquet(cohort_path)
    development = frame[(frame.quarter >= "2022Q1") & (frame.quarter <= "2024Q4")].reset_index(drop=True)
    validation = frame[(frame.quarter >= "2025Q1") & (frame.quarter <= "2025Q2")].reset_index(drop=True)
    final_fit = frame[(frame.quarter >= "2022Q1") & (frame.quarter <= "2025Q2")].reset_index(drop=True)
    calibration = frame[frame.quarter == "2025Q3"].reset_index(drop=True)
    holdout = frame[(frame.quarter >= "2026Q1") & (frame.quarter <= "2026Q2")].reset_index(drop=True)
    minimum = 2 if fast else config.adr_min_frequency
    vocabulary = build_adr_vocabulary(development, minimum, min(15, config.adr_max_labels) if fast else config.adr_max_labels)
    vocabulary = [{**item, "version": artifact_version} for item in vocabulary]
    if not vocabulary:
        raise RuntimeError("No ADR labels meet the configured training-only vocabulary threshold")
    (ARTIFACT_ROOT / "adr_vocabulary.json").write_text(json.dumps(vocabulary, indent=2), encoding="utf-8")
    label_map = {item["term"]: item["index"] for item in vocabulary}
    associations = historical_associations(final_fit, label_map, minimum=1 if fast else 5)

    serious_artifact = joblib.load(ARTIFACT_ROOT / "serious_outcome.joblib")
    builder = serious_artifact["featureBuilder"]
    x_development = builder.transform(development)
    x_validation = builder.transform(validation)
    y_development, y_validation = _targets(development, vocabulary), _targets(validation, vocabulary)
    popularity = np.tile(y_development.mean(axis=0), (len(validation), 1))
    baseline_results = [{"model": "Training prevalence", "fastMode": fast, **_multilabel_metrics(y_validation, popularity)}]
    logistic = OneVsRestClassifier(LogisticRegression(max_iter=100 if fast else 300, solver="liblinear", class_weight="balanced", random_state=config.seed, n_jobs=-1)).fit(x_development, y_development)
    baseline_results.append({"model": "One-vs-Rest Logistic Regression", "fastMode": fast, **_multilabel_metrics(y_validation, logistic.predict_proba(x_validation))})
    mlp = MLPClassifier(hidden_layer_sizes=(64,), max_iter=20 if fast else 80, early_stopping=True, random_state=config.seed).fit(x_development, y_development)
    baseline_results.append({"model": "Multi-label MLP", "fastMode": fast, **_multilabel_metrics(y_validation, mlp.predict_proba(x_validation))})

    model = HeterogeneousAdrNetwork(hidden_channels=48 if fast else 96, output_labels=len(vocabulary))
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    batch_size, epochs = (256, 2) if fast else (2048, 20)
    model.train()
    for _ in range(epochs):
        order = np.random.default_rng(config.seed).permutation(len(final_fit))
        for start in range(0, len(order), batch_size):
            batch = final_fit.iloc[order[start:start + batch_size]].reset_index(drop=True)
            graph = build_heterodata(batch, vocabulary, associations, include_targets=True)
            optimizer.zero_grad()
            loss = nn.functional.binary_cross_entropy_with_logits(model(graph), graph["report"].y)
            loss.backward(); optimizer.step()
    validation_probabilities = _predict_in_batches(model, validation, vocabulary, associations, batch_size)
    hgnn_validation = _multilabel_metrics(y_validation, validation_probabilities)
    baseline_results.append({"model": "HGNN", "fastMode": fast, **hgnn_validation})
    pd.DataFrame(baseline_results).to_csv(REPORT_ROOT / "hgnn_baselines.csv", index=False)

    raw_calibration = _predict_in_batches(model, calibration, vocabulary, associations, batch_size)
    calibration_targets = _targets(calibration, vocabulary)
    calibrators = []
    for index in range(len(vocabulary)):
        labels = calibration_targets[:, index]
        calibrators.append(IsotonicRegression(out_of_bounds="clip").fit(raw_calibration[:, index], labels) if len(np.unique(labels)) > 1 else None)
    raw_holdout = _predict_in_batches(model, holdout, vocabulary, associations, batch_size)
    calibrated_holdout = np.column_stack([calibrator.predict(raw_holdout[:, index]) if calibrator else raw_holdout[:, index] for index, calibrator in enumerate(calibrators)])
    holdout_metrics = _multilabel_metrics(_targets(holdout, vocabulary), calibrated_holdout)
    report = {"version": artifact_version, "vocabularySize": len(vocabulary), "validation": hgnn_validation, "holdout2026": holdout_metrics, "targetLeakageSafeguard": "report-to-ADR target edges are never passed to the encoder", "fastMode": fast}
    (REPORT_ROOT / "hgnn_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    joblib.dump({"associations": associations, "calibrators": calibrators, "vocabulary": vocabulary, "hiddenChannels": 48 if fast else 96, "version": artifact_version, "fastMode": fast}, ARTIFACT_ROOT / "hgnn_metadata.joblib")
    torch.save(model.state_dict(), ARTIFACT_ROOT / "hgnn_state.pt")
    return {"baselines": baseline_results, **report}


def _predict_in_batches(model, rows, vocabulary, associations, batch_size: int) -> np.ndarray:
    model.eval(); results = []
    with torch.no_grad():
        for start in range(0, len(rows), batch_size):
            graph = build_heterodata(rows.iloc[start:start + batch_size].reset_index(drop=True), vocabulary, associations, include_targets=False)
            results.append(torch.sigmoid(model(graph)).cpu().numpy())
    return np.vstack(results) if results else np.empty((0, len(vocabulary)))
