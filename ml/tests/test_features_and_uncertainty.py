import numpy as np
import pandas as pd

from vitanexus_ml.config import NO_SERIOUS, SERIOUS, TrainConfig
from vitanexus_ml.conformal.split import conformal_quantile, prediction_set
from vitanexus_ml.features.builder import FeatureBuilder
from vitanexus_ml.models.metrics import bootstrap_interval


def test_feature_builder_train_serving_parity_and_unknowns():
    rows = pd.DataFrame([{"age_years": 58.0, "sex": "M", "candidate_drug": "WARFARIN", "indication": "THROMBOSIS", "current_medications": ["ASPIRIN"]}])
    builder = FeatureBuilder(TrainConfig()).fit(rows)
    batch = builder.transform(rows)
    one, coverage = builder.transform_one({"age": 58, "sex": "M", "candidateDrug": "WARFARIN", "indication": "THROMBOSIS", "currentMedications": ["ASPIRIN"]})
    assert (batch != one).nnz == 0
    assert coverage.candidateKnown and coverage.indicationKnown
    _, unknown = builder.transform_one({"age": None, "sex": "X", "candidateDrug": "NEW DRUG", "indication": "NEW USE", "currentMedications": ["UNKNOWN MED"]})
    assert not unknown.candidateKnown and not unknown.indicationKnown
    assert unknown.unknownCurrentMedications == ["UNKNOWN MED"]


def test_bootstrap_and_conformal_calculations():
    lower, upper = bootstrap_interval(np.array([0.1, 0.2, 0.3, 0.4]))
    assert lower < upper
    probabilities = np.array([0.1, 0.9, 0.2, 0.8])
    labels = np.array([0, 1, 0, 1])
    q_hat = conformal_quantile(probabilities, labels, alpha=0.1)
    assert 0 <= q_hat <= 1
    assert prediction_set(0.5, 0.6) == [NO_SERIOUS, SERIOUS]
