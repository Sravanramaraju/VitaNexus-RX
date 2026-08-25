import pandas as pd

from vitanexus_ml.models.hgnn import build_adr_vocabulary, build_heterodata, historical_associations


def test_hgnn_target_edges_never_enter_encoder():
    rows = pd.DataFrame([{"age_years": 40.0, "sex": "F", "candidate_drug": "A", "indication": "I", "current_medications": ["B"], "reactions": ["Nausea"]}])
    vocabulary = build_adr_vocabulary(rows, min_frequency=1, max_labels=10)
    associations = historical_associations(rows, {"NAUSEA": 0}, minimum=1)
    graph = build_heterodata(rows, vocabulary, associations, include_targets=True)
    assert graph.graph_metadata["targetRelationExcludedFromEncoder"] is True
    assert ("report", "target_adr", "adr") not in graph.edge_types
    assert graph["report"].y.shape == (1, 1)
