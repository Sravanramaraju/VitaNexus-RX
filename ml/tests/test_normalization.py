from vitanexus_ml.normalization import age_in_years, normalize_drug, normalize_sex


def test_age_conversion_and_bounds():
    assert age_in_years("18", "MON") == 1.5
    assert age_in_years("7", "DY") == 0.0192
    assert age_in_years("121", "YR") is None
    assert age_in_years("unknown", "YR") is None


def test_sex_and_drug_normalization():
    assert normalize_sex("m") == "M"
    assert normalize_sex("") == "UNKNOWN"
    assert normalize_drug(" acetaminophen ") == "PARACETAMOL"
