from __future__ import annotations

import json

import pandas as pd

from vitanexus_ml.config import PROCESSED_FAERS_ROOT
from vitanexus_ml.inference.predictor import Predictor


def main() -> None:
    row = pd.read_parquet(PROCESSED_FAERS_ROOT / "cohort_fast.parquet").iloc[0]
    result = Predictor().predict({
        "requestId": "smoke-inference",
        "patient": {"age": None if pd.isna(row.age_years) else float(row.age_years), "sex": row.sex, "currentMedications": list(row.current_medications)},
        "candidateDrug": {"canonicalName": row.candidate_drug, "ingredients": [row.candidate_drug]},
        "indication": {"id": "smoke-drugcentral-indication", "name": row.indication, "source": "DrugCentral"},
    })
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
