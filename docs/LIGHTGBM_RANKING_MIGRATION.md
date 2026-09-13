# LightGBM Safety-Aware Ranking Migration

## Baseline and scope

This migration makes the full LightGBM serious-outcome model the only runtime
ML dependency for overall adverse-risk assessment and alternative-drug ranking.
It deliberately does not load, invoke, or rank with HGNN artifacts while the
event-level model remains under validation.

## Runtime evidence requirements

Production inference accepts only an artifact whose `training_manifest.json`
declares `fastMode: false`, `fullFinalData: true`, and exactly twenty contiguous
bootstrap replicas.  Development smoke artifacts must fail safely rather than
being represented as clinically evaluable results.

## Target decision path

```text
Patient context + same-indication candidate
  -> safety gates (severe DDI / serious drug-disease restriction)
  -> LightGBM overall adverse-risk probability for eligible candidates
  -> LightGBM split-conformal reliability information
  -> uncertainty-adjusted adverse risk
  -> 50% adjusted adverse risk + 30% DDI + 20% drug-disease risk
```

Conformal uncertainty is an interpretation of the LightGBM estimate, not an
independent clinical hazard. Allergy information remains visible to clinicians
but does not enter automated ranking. HGNN is reserved for a future,
event-level, supplementary interface and has no ranking or conformal role.
