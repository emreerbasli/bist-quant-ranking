# EXP-MODEL-001 — CONTROLLED MODEL ARCHITECTURE COMPARISON

## 1. Executive Summary

Decision: **MULTIPLE VIABLE ARCHITECTURES**. Phase F gate: **PASS**.

## 2. Locked Contract

Contract: `exp_model_001.json`; fixed before full results.

## 3. Common Dataset

EXP-DATA-005 price research view; common dates and eligible universe.

## 4. Common Features

mom_12_1, mom_63, vol_63 only.

## 5. Models

FACTOR_COMPOSITE, RIDGE, LGBM_REGRESSION, LAMBDAMART; fixed configurations, no hyperparameter search.

## 6. Nested Validation

Target and horizon selected only in inner temporal validation; actual label_end purge.

## 7. Architecture-Controlled Comparison

| architecture | mean_outer_rank_ic | median_outer_rank_ic | outer_rank_ic_std | positive_fold_ratio | mean_ndcg_at_10 | mean_top_k_spread_raw | mean_prediction_dispersion |
|---|---|---|---|---|---|---|---|
| FACTOR_COMPOSITE | 0.0876 | 0.0974 | 0.1001 | 0.7500 | 0.4953 | 0.0324 | 0.1597 |
| RIDGE | -0.1054 | -0.0641 | 0.1694 | 0.5000 | 0.4836 | -0.0100 | 0.0256 |
| LGBM_REGRESSION | 0.1177 | 0.1369 | 0.0728 | 1.0000 | 0.5865 | 0.0826 | 1.3722 |
| LAMBDAMART | 0.0755 | 0.1014 | 0.0587 | 0.7500 | 0.5744 | 0.0055 | 0.4545 |

## 8. Ridge

| architecture | mean_outer_rank_ic | median_outer_rank_ic | outer_rank_ic_std | positive_fold_ratio | mean_ndcg_at_10 | mean_top_k_spread_raw | mean_prediction_dispersion |
|---|---|---|---|---|---|---|---|
| RIDGE | -0.1054 | -0.0641 | 0.1694 | 0.5000 | 0.4836 | -0.0100 | 0.0256 |

## 9. Factor Composite

| architecture | mean_outer_rank_ic | median_outer_rank_ic | outer_rank_ic_std | positive_fold_ratio | mean_ndcg_at_10 | mean_top_k_spread_raw | mean_prediction_dispersion |
|---|---|---|---|---|---|---|---|
| FACTOR_COMPOSITE | 0.0979 | 0.0836 | 0.0623 | 1.0000 | 0.5221 | 0.1066 | 0.1602 |

## 10. LightGBM Regression

| architecture | mean_outer_rank_ic | median_outer_rank_ic | outer_rank_ic_std | positive_fold_ratio | mean_ndcg_at_10 | mean_top_k_spread_raw | mean_prediction_dispersion |
|---|---|---|---|---|---|---|---|
| LGBM_REGRESSION | 0.0234 | 0.0101 | 0.0692 | 0.5000 | 0.5686 | 0.0189 | 0.4278 |

## 11. LambdaMART

| architecture | mean_outer_rank_ic | median_outer_rank_ic | outer_rank_ic_std | positive_fold_ratio | mean_ndcg_at_10 | mean_top_k_spread_raw | mean_prediction_dispersion |
|---|---|---|---|---|---|---|---|
| LAMBDAMART | 0.0346 | 0.0322 | 0.0674 | 0.7500 | 0.5667 | 0.0637 | 0.4480 |

## 12. Target/Horizon Selection

| outer_fold | architecture | selected_family | selected_horizon | selected_inner_score |
|---|---|---|---|---|
| O1 | FACTOR_COMPOSITE | BETA_RESIDUAL | 20 | 0.1386 |
| O1 | RIDGE | BETA_RESIDUAL | 40 | 0.1158 |
| O1 | LGBM_REGRESSION | VOL_SCALED | 40 | 0.1236 |
| O1 | LAMBDAMART | VOL_SCALED | 40 | 0.1051 |
| O2 | FACTOR_COMPOSITE | VOL_SCALED | 60 | 0.1776 |
| O2 | RIDGE | VOL_SCALED | 40 | 0.1228 |
| O2 | LGBM_REGRESSION | RAW | 40 | 0.1275 |
| O2 | LAMBDAMART | RAW | 20 | 0.0675 |
| O3 | FACTOR_COMPOSITE | SECTOR_RELATIVE | 60 | 0.1088 |
| O3 | RIDGE | VOL_SCALED | 60 | 0.0909 |
| O3 | LGBM_REGRESSION | BETA_RESIDUAL | 20 | 0.1177 |
| O3 | LAMBDAMART | VOL_SCALED | 20 | 0.1098 |
| O4 | FACTOR_COMPOSITE | RAW | 60 | 0.0805 |
| O4 | RIDGE | VOL_SCALED | 20 | 0.0744 |
| O4 | LGBM_REGRESSION | RAW | 60 | 0.0849 |
| O4 | LAMBDAMART | BETA_RESIDUAL | 60 | 0.0407 |

## 13. Predictive Metrics

| architecture | mean_outer_rank_ic | median_outer_rank_ic | outer_rank_ic_std | positive_fold_ratio | mean_ndcg_at_10 | mean_top_k_spread_raw | mean_prediction_dispersion |
|---|---|---|---|---|---|---|---|
| FACTOR_COMPOSITE | 0.0979 | 0.0836 | 0.0623 | 1.0000 | 0.5221 | 0.1066 | 0.1602 |
| RIDGE | -0.1054 | -0.0641 | 0.1694 | 0.5000 | 0.4836 | -0.0100 | 0.0256 |
| LGBM_REGRESSION | 0.0234 | 0.0101 | 0.0692 | 0.5000 | 0.5686 | 0.0189 | 0.4278 |
| LAMBDAMART | 0.0346 | 0.0322 | 0.0674 | 0.7500 | 0.5667 | 0.0637 | 0.4480 |

## 14. Seed Stability

| architecture | mean_seed_rank_ic_std |
|---|---|
| FACTOR_COMPOSITE | N/A |
| RIDGE | N/A |
| LGBM_REGRESSION | 0.0087 |
| LAMBDAMART | 0.0159 |

## 15. Portfolio Diagnostics

| architecture | mean_net_return_0bps | mean_net_return_30bps | mean_net_return_50bps | mean_net_return_100bps | mean_sharpe_50bps | worst_daily_maxdd_50bps | mean_turnover_50bps | worst_day_50bps |
|---|---|---|---|---|---|---|---|---|
| FACTOR_COMPOSITE | 0.9116 | 0.8986 | 0.8900 | 0.8686 | 2.8919 | -0.3051 | 1.0963 | -0.0882 |
| RIDGE | 1.1286 | 1.1154 | 1.1066 | 1.0847 | 2.3409 | -0.2796 | 1.0193 | -0.0958 |
| LGBM_REGRESSION | 0.7711 | 0.7551 | 0.7444 | 0.7179 | 2.1525 | -0.2742 | 1.3292 | -0.0903 |
| LAMBDAMART | 0.7277 | 0.7131 | 0.7033 | 0.6791 | 2.6412 | -0.3063 | 1.2948 | -0.0923 |

## 16. Cost / Turnover

Costs are debited at rebalance under the locked equal-weight K=10 execution contract. Return sensitivity and mean two-sided turnover are shown in the portfolio table.

## 17. Daily Risk

Daily MaxDD and worst-day evidence are computed from the daily NAV, not rebalance-only observations. See the portfolio table and `EXP-MODEL-001_daily_nav.csv`.

## 18. Complexity

| architecture | complexity_level | fixed_configuration |
|---|---|---|
| FACTOR_COMPOSITE | 1 | {"formula": "mean(rank(mom_12_1), rank(mom_63), 1-rank(vol_63)) within signal-date cross-section", "optimized": false, "weights": [1, 1, -1]} |
| RIDGE | 2 | {"alpha": 1.0, "preprocessing": "training-only median imputation and z-score scaling"} |
| LGBM_REGRESSION | 3 | {"colsample_bytree": 0.9, "deterministic": true, "force_col_wise": true, "learning_rate": 0.05, "max_depth": 4, "min_child_samples": 30, "n_estimators": 60, "n_jobs": 1, "num_leaves": 15, "objective": "regression", "reg_alpha": 0.1, "reg_lambda": 1.0, "subsample": 0.9, "subsample_freq": 1} |
| LAMBDAMART | 4 | {"colsample_bytree": 0.9, "deterministic": true, "eval_at": [10], "force_col_wise": true, "group": "signal_date cross-section", "learning_rate": 0.05, "max_depth": 4, "metric": "ndcg", "min_child_samples": 20, "n_estimators": 60, "n_jobs": 1, "num_leaves": 15, "objective": "lambdarank", "reg_alpha": 0.1, "reg_lambda": 1.0, "relevance_bins": 5, "relevance_mapping": "min(4,floor(target_percentile_rank*5))", "subsample": 0.9, "subsample_freq": 1} |

## 19. Model Decision

**MULTIPLE VIABLE ARCHITECTURES**

| architecture | absolute_viable | incremental_viable | classification | mean_controlled_delta_rank_ic | median_controlled_delta_rank_ic | positive_delta_fold_ratio | mean_controlled_delta_ndcg | mean_seed_rank_ic_std |
|---|---|---|---|---|---|---|---|---|
| FACTOR_COMPOSITE | True | N/A | CONTROL / BASELINE | N/A | N/A | N/A | N/A | N/A |
| RIDGE | False | N/A | CONTROL / BASELINE | N/A | N/A | N/A | N/A | N/A |
| LGBM_REGRESSION | True | True | VIABLE | 0.2232 | 0.1627 | 1.0000 | 0.1029 | 0.0087 |
| LAMBDAMART | True | True | VIABLE | 0.1809 | 0.1071 | 1.0000 | 0.0909 | 0.0159 |

## 20. Limitations

Inference is restricted to the three-feature price-only information set and four locked architectures; negative evidence is not a universal claim about ML or BIST.

## 21. Tests

Smoke PASS; 15/15 dedicated unittest checks and 101/101 full research regression checks PASS. Coverage includes contract, boundary, grouping, relevance mapping, determinism, seed completeness, daily NAV, cost monotonicity and production integrity.

## 22. Production Integrity

Final protected-production hash verification: PASS, 0 changed. Research outputs are isolated under `research/`.

## 23. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

After review, open only the pre-result contract for Phase H controlled portfolio/cost/capacity research, carrying the two viable tree architectures forward as frozen finalists; do not start it automatically and do not open another model zoo.
