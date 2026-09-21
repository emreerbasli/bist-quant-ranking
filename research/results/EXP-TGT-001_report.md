# EXP-TGT-001 — RAW RETURN HORIZON COMPARISON

## 1. Executive Summary

Execution gate: **PASS**. Horizon decision: **NO CLEAR WINNER**. Horizon selection used inner folds only; outer folds evaluated the selected procedure and could only veto, never replace, the inner choice.

## 2. Locked Research Contract

Contract was written before results: price-only DATA-005 view, raw return rank target, fixed ridge control, K=10, 60-session rebalance/holding, 50 bps primary cost.

## 3. Dataset Scope

88 current-universe symbols; macro, USDTRY, fundamentals, value and legacy approximate fundamentals excluded. V3/V4.1 are N/A under the common safe contract; frozen behavior is not clean OOS.

## 4. Fold Design

Four expanding outer folds (2022, 2023, 2024, 2025 through May); each has two prior-year inner validations. Every training set is purged using that horizon's actual `label_end`.

## 5. Eligible Sample Coverage

| horizon_sessions | candidate_observations | usable_observations | coverage_pct |
|---|---|---|---|
| 20 | 1763 | 1756 | 0.9960 |
| 40 | 1677 | 1666 | 0.9934 |
| 60 | 1677 | 1538 | 0.9171 |

## 6. H20 Results

See common 50 bps table below; full fold metrics are in `EXP-TGT-001_outer_metrics.csv`.

## 7. H40 Results

Same fixed features/model/config; only the raw-return label horizon changes.

## 8. H60 Results

Same fixed features/model/config; 60 is not presumed optimal.

| horizon_sessions | rank_ic_mean | rank_ic_median | positive_ic_ratio | ndcg_at_10 | net_return | sharpe | daily_maxdd | turnover |
|---|---|---|---|---|---|---|---|---|
| 20 | -0.0139 | 0.0075 | 0.4375 | 0.5605 | 1.1332 | 2.4003 | -0.2263 | 1.1495 |
| 40 | -0.1041 | -0.0400 | 0.5000 | 0.5211 | 1.1696 | 2.6301 | -0.2559 | 1.0231 |
| 60 | -0.0318 | 0.0024 | 0.4583 | 0.5728 | 1.1246 | 2.8047 | -0.2632 | 1.0313 |

## 9. Inner Selection Frequency

H20=1, H40=2, H60=1 across four outer procedures.

## 10. Outer Robustness

Selected-procedure mean Rank IC=-0.0613, median fold Rank IC=-0.0795, positive-fold ratio=50.00%. Outer results did not choose a horizon.

## 11. Cost / Turnover

0/30/50/100 bps results and two-sided turnover are recorded per outer fold/horizon. 50 bps is primary.

## 12. Daily Risk

Daily NAV and true daily MaxDD are recorded for the inner-selected outer procedure; no cohort-only drawdown substitute is used.

## 13. Coverage Sensitivity

Coverage differences are reported as data availability, not performance. Universe formation uses signal-date history only; future label availability is not an eligibility feature.

## 14. Horizon Decision

**NO CLEAR WINNER** under the precommitted frequency-plus-veto rule. A single Sharpe did not determine the result.

## 15. Tests

Dynamic labels, leakage/purge, nested separation, fixed model/features, forbidden fields, future eligibility, reproducibility and production integrity are covered by the EXP-TGT-001 suite.

## 16. Production Integrity

Research-only outputs; final protected-file hash verification is run separately.

## 17. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Stop at the Phase C horizon gate and accept `NO CLEAR WINNER` as the current result. Do not open sector-relative, beta-residual or volatility-scaled targets until the MASTER_PLAN owner explicitly resolves how an inconclusive horizon gate should proceed.
