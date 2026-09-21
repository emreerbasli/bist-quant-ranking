# EXP-FREEZE-001 — RESEARCH CANDIDATE FREEZE & CLEAN FORWARD CONTRACT

## 1. Executive Summary

Two independent **FROZEN RESEARCH CANDIDATE / CLEAN FORWARD MONITORING** candidates were created. Neither is production-validated or forward-validated.

## 2. Historical Research Closure

Historical alpha research is closed for these candidate versions. Material model/data changes create a new version and terminate comparability of the existing clean-forward evidence.

## 3. Candidate Set

| candidate_id | model_type | target_procedure | horizon_procedure | training_cutoff | training_observations |
| --- | --- | --- | --- | --- | --- |
| RC-LGBMR-001 | LGBM_REGRESSION | RAW | 60 | 2025-05-30 | 1538 |
| RC-LAMBDAMART-001 | LAMBDAMART | BETA_RESIDUAL | 60 | 2025-05-30 | 1538 |

## 4. Regression Freeze

`RC-LGBMR-001`: RAW/H60 from EXP-MODEL-001 O4 locked inner selection.

## 5. LambdaMART Freeze

`RC-LAMBDAMART-001`: BETA_RESIDUAL/H60 from EXP-MODEL-001 O4 locked inner selection.

## 6. Code / Data Hashes

Combined manifest: `research/frozen_candidates/EXP-FREEZE-001_combined_manifest.json`.

## 7. Feature Schema

| name | formula | lookback | minimum_history | transform | dtype |
| --- | --- | --- | --- | --- | --- |
| mom_12_1 | last_valid_close[-22] / last_valid_close[-253] - 1 | 252 sessions with 1-month skip | 253 | raw price return | float64 |
| mom_63 | last_valid_close / last_valid_close[-64] - 1 | 63 returns | 64 | raw price return | float64 |
| vol_63 | std of last 63 valid close-to-close returns | 63 returns | 64 | raw volatility | float64 |

## 8. Target / Horizon Procedure

Global target/horizon remains NOT FIXED. Historical inner-only procedure is frozen; forward observations cannot reselect it.

## 9. Final Training

Training labels end on or before 2025-05-30; no post-cutoff data is used.

## 10. Seeds / Determinism

Seeds 11/29/47, median aggregation, deterministic/force-column-wise settings, n_jobs=1. Two same-input fits produced identical predictions and Top-10 selections within 1e-12.

## 11. Portfolio Contract

K=10 equal weight; 60-session holding/rebalance; existing cost/liquidity/unfilled/cash/mark/terminal contract.

## 12. Execution Contract

After-close signal; next applicable eligible open; no same-close execution.

## 13. Shadow Signal Logging

Append-only JSONL files are initialized separately per candidate. Retroactive signals are operational events, not clean-forward evidence.

## 14. Shadow Portfolio Logging

Separate append-only intended-order/portfolio JSONL files are initialized; production paper portfolios are untouched.

## 15. Clean Forward Definition

Only signals generated strictly after 2026-09-18T02:25:56.600962+03:00 are evidence. Completed configured-horizon cohorts only.

## 16. Completed Cohort Logic

Each signal records selected H and label-end completion. Pending cohorts are excluded from forward statistics.

## 17. Overlap / Dependence

20/40/60 cohorts can overlap; raw cohort counts are not independent market histories.

## 18. Change Control

{
  "NON_MATERIAL_OPERATIONAL_FIX": "append change ledger; candidate version retained only if alpha output unchanged",
  "MATERIAL_MODEL_DATA_CHANGE": "NEW CANDIDATE VERSION; no evidence pooling",
  "PRODUCTION_BUG_FIX": "production remains separate and cannot silently alter research candidate"
}

## 19. Caveat Register

{
  "RC-LGBMR-001": [
    "survivor universe",
    "provider-dependent price history",
    "only three price features",
    "mom_63 dependency",
    "macro excluded",
    "fundamental excluded",
    "historical evidence is not clean forward",
    "O1 sensitivity",
    "top-stock concentration",
    "bootstrap IC uncertainty"
  ],
  "RC-LAMBDAMART-001": [
    "survivor universe",
    "provider-dependent price history",
    "only three price features",
    "mom_63 dependency",
    "macro excluded",
    "fundamental excluded",
    "historical evidence is not clean forward",
    "sector concentration",
    "weaker stability classification",
    "lower bootstrap P(IC>0)",
    "ranking-objective complexity"
  ]
}

## 20. Reproduction Commands

`python research/run_frozen_shadow.py --candidate RC-LGBMR-001 --asof YYYY-MM-DD`  
`python research/run_frozen_shadow.py --candidate RC-LAMBDAMART-001 --asof YYYY-MM-DD`

## 21. Tests

| candidate_id | deterministic_predictions | training_cutoff_pass | top10_reproducible |
| --- | --- | --- | --- |
| RC-LGBMR-001 | True | True | True |
| RC-LAMBDAMART-001 | True | True | True |

## 22. Production Isolation

Production writes = 0; final protected hash check required.

## 23. Phase L Gate

PASS if both candidate manifests/artifacts and deterministic validation are present.

## 24. CLEAN FORWARD START

2026-09-18T02:25:56.600962+03:00

## 25. SINGLE NEXT BEST ACTION

Run only the research shadow runner prospectively when new eligible data arrives; do not treat any historical reconstruction as clean-forward evidence.
