# Full LightGBM Evaluation Summary

## Scope

These are the frozen results for the full (`fastMode: false`) LightGBM
serious-outcome model. They use the untouched 2026Q1--2026Q2 FAERS holdout
(`696,604` reports; `370,840` serious-outcome and `325,764` non-serious-outcome
labels). The holdout was not used to choose the operating threshold.

## Threshold-independent model quality

| Measure | 2026 holdout result |
| --- | ---: |
| AUROC | 0.8177 |
| AUPRC | 0.8212 |
| Brier score | 0.1743 |
| Expected calibration error | 0.0358 |

## Evaluated operating point

The offline evaluation selected `0.389` on the disjoint 2025Q4 operating
subset by maximizing specificity subject to a sensitivity floor of 0.90. On
the untouched 2026 holdout it achieved sensitivity `0.9018`, specificity
`0.5404`, precision `0.6907`, F1 `0.7823`, and balanced accuracy `0.7211`.
That is a 1.45 percentage-point specificity increase over the historical
`0.35` reporting point while retaining the chosen sensitivity constraint.

The operating point is preserved for offline evaluation and clinical review.
It is intentionally **not** consumed by the live ranking path: live ranking
uses the calibrated LightGBM probability and its conservative upper bootstrap
bound instead of converting a report-level estimate into a binary judgement.

## Conformal result

Split conformal classification used a disjoint deterministic half of 2025Q4
with nominal target coverage 0.90. On the 2026 holdout it had empirical
coverage `0.8739`, average prediction-set size `1.3183`, a singleton rate of
`0.6817`, and no empty sets. This is classification-set reliability metadata;
it is not a probability confidence interval or a separate ranking component.

## Provenance

The source artifacts are:

- `ml/reports/lightgbm_metrics.json`
- `ml/reports/lightgbm_operating_threshold.json`
- `ml/reports/final_temporal_evaluation.json`

All probability semantics remain conditional on the FAERS serious-outcome
reporting task and do not establish population incidence or causality.
