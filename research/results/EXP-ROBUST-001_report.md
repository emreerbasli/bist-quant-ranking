# EXP-ROBUST-001 — FINALIST STRESS, ABLATION & CONCENTRATION

## 1. Executive Summary

Phase I gate: **PASS**.

## 2. Locked Stress Contract

`exp_robust_001.json` locked before results.

## 3. Frozen Finalists

LGBM Regression and LambdaMART; exact Phase F/H contracts and portfolio rules.

## 4. Feature Ablation

| architecture | family | case | mean_rank_ic | median_rank_ic | mean_net_return | mean_sharpe | worst_maxdd |
|---|---|---|---|---|---|---|---|
| LAMBDAMART | ABLATION | WITHOUT_mom_12_1 | 0.0987 | 0.0995 | 0.7334 | 2.2977 | -0.2756 |
| LAMBDAMART | ABLATION | WITHOUT_mom_63 | -0.0195 | -0.0212 | 0.8382 | 2.5323 | -0.2008 |
| LAMBDAMART | ABLATION | WITHOUT_vol_63 | 0.0284 | 0.0492 | 0.6070 | 2.4684 | -0.2475 |
| LGBM_REGRESSION | ABLATION | WITHOUT_mom_12_1 | 0.0280 | -0.0109 | 0.6410 | 2.0157 | -0.2505 |
| LGBM_REGRESSION | ABLATION | WITHOUT_mom_63 | -0.0176 | -0.0268 | 0.7271 | 2.0562 | -0.2648 |
| LGBM_REGRESSION | ABLATION | WITHOUT_vol_63 | 0.0524 | 0.0572 | 0.6921 | 2.3654 | -0.2442 |

## 5. Feature Noise

| architecture | family | case | mean_rank_ic | median_rank_ic | mean_net_return | mean_sharpe | worst_maxdd |
|---|---|---|---|---|---|---|---|
| LAMBDAMART | FEATURE_NOISE | MILD | 0.0474 | 0.0437 | 0.6859 | 2.5962 | -0.3217 |
| LAMBDAMART | FEATURE_NOISE | MODERATE | 0.0513 | 0.0313 | 0.6814 | 2.6015 | -0.3156 |
| LGBM_REGRESSION | FEATURE_NOISE | MILD | 0.0244 | 0.0070 | 0.7690 | 2.3661 | -0.2986 |
| LGBM_REGRESSION | FEATURE_NOISE | MODERATE | 0.0505 | 0.0488 | 0.7902 | 2.8026 | -0.3220 |

## 6. Rank Perturbation

| architecture | family | case | mean_rank_ic | median_rank_ic | mean_net_return | mean_sharpe | worst_maxdd |
|---|---|---|---|---|---|---|---|
| LAMBDAMART | RANK_NOISE | MILD | 0.0352 | 0.0292 | 0.6671 | 2.5411 | -0.3037 |
| LAMBDAMART | RANK_NOISE | MODERATE | 0.0367 | 0.0285 | 0.6430 | 2.4601 | -0.3037 |
| LGBM_REGRESSION | RANK_NOISE | MILD | 0.0254 | 0.0166 | 0.6816 | 2.0389 | -0.2718 |
| LGBM_REGRESSION | RANK_NOISE | MODERATE | 0.0247 | 0.0147 | 0.6674 | 2.0055 | -0.2941 |

## 7. Delay Stress

| architecture | delay_sessions | mean_net_return | mean_sharpe | worst_daily_maxdd | mean_fill_rate |
|---|---|---|---|---|---|
| LAMBDAMART | 1 | 0.7077 | 2.7537 | -0.2983 | 1.0000 |
| LAMBDAMART | 2 | 0.7452 | 2.8930 | -0.2982 | 1.0000 |
| LGBM_REGRESSION | 1 | 0.7298 | 2.2461 | -0.2708 | 1.0000 |
| LGBM_REGRESSION | 2 | 0.7684 | 2.4303 | -0.2698 | 1.0000 |

## 8. Cost Stress

| architecture | cost_bps | mean_net_return | mean_turnover |
|---|---|---|---|
| LAMBDAMART | 0 | 0.7281 | 1.2081 |
| LAMBDAMART | 30 | 0.7028 | 1.2148 |
| LAMBDAMART | 50 | 0.6864 | 1.2117 |
| LAMBDAMART | 100 | 0.6463 | 1.2039 |
| LGBM_REGRESSION | 0 | 0.7701 | 1.2344 |
| LGBM_REGRESSION | 30 | 0.7443 | 1.2405 |
| LGBM_REGRESSION | 50 | 0.7267 | 1.2374 |
| LGBM_REGRESSION | 100 | 0.6834 | 1.2295 |

## 9. Liquidity / Capacity Stress

| architecture | capital_try | adv_limit_pct | mean_net_return | mean_fill_rate | unfilled | mean_cash | median_order_adv | p95_order_adv | max_order_adv | pct_orders_gt_10pct_adv |
|---|---|---|---|---|---|---|---|---|---|---|
| LAMBDAMART | 1000000 | 0.0500 | 0.6864 | 1.0000 | 0 | 0.0033 | 0.0003 | 0.0144 | 0.0198 | 0.0000 |
| LAMBDAMART | 1000000 | 0.2000 | 0.6864 | 1.0000 | 0 | 0.0033 | 0.0003 | 0.0144 | 0.0198 | 0.0000 |
| LAMBDAMART | 10000000 | 0.0500 | 0.7042 | 0.9082 | 13 | 0.0611 | 0.0028 | 0.0666 | 0.1975 | 0.0173 |
| LAMBDAMART | 10000000 | 0.1000 | 0.7031 | 0.9725 | 5 | 0.0226 | 0.0024 | 0.0677 | 0.1975 | 0.0173 |
| LAMBDAMART | 10000000 | 0.2000 | 0.6864 | 1.0000 | 0 | 0.0033 | 0.0028 | 0.1438 | 0.1975 | 0.0229 |
| LAMBDAMART | 50000000 | 0.0500 | 0.5459 | 0.7749 | 28 | 0.1851 | 0.0119 | 0.2977 | 0.7521 | 0.1269 |
| LAMBDAMART | 50000000 | 0.1000 | 0.7142 | 0.8625 | 20 | 0.1157 | 0.0123 | 0.2977 | 0.7521 | 0.1253 |
| LAMBDAMART | 50000000 | 0.2000 | 0.7042 | 0.9082 | 13 | 0.0611 | 0.0142 | 0.3332 | 0.9877 | 0.1424 |
| LGBM_REGRESSION | 1000000 | 0.0500 | 0.7267 | 1.0000 | 0 | 0.0032 | 0.0002 | 0.0082 | 0.0198 | 0.0000 |
| LGBM_REGRESSION | 1000000 | 0.2000 | 0.7267 | 1.0000 | 0 | 0.0032 | 0.0002 | 0.0082 | 0.0198 | 0.0000 |
| LGBM_REGRESSION | 10000000 | 0.0500 | 0.7468 | 0.9334 | 12 | 0.0379 | 0.0020 | 0.0800 | 0.1975 | 0.0110 |
| LGBM_REGRESSION | 10000000 | 0.1000 | 0.7226 | 0.9833 | 3 | 0.0086 | 0.0022 | 0.0828 | 0.1975 | 0.0056 |
| LGBM_REGRESSION | 10000000 | 0.2000 | 0.7267 | 1.0000 | 0 | 0.0032 | 0.0020 | 0.0825 | 0.1975 | 0.0054 |
| LGBM_REGRESSION | 50000000 | 0.0500 | 0.5566 | 0.8222 | 28 | 0.1358 | 0.0099 | 0.2824 | 0.7459 | 0.1079 |
| LGBM_REGRESSION | 50000000 | 0.1000 | 0.5791 | 0.8967 | 18 | 0.0970 | 0.0099 | 0.2824 | 0.7127 | 0.0977 |
| LGBM_REGRESSION | 50000000 | 0.2000 | 0.7499 | 0.9275 | 13 | 0.0448 | 0.0099 | 0.3998 | 0.9877 | 0.0999 |

## 10. Leave-One-Year-Out

| architecture | omitted_outer_period | mean_rank_ic | mean_net_return | mean_sharpe | worst_maxdd |
|---|---|---|---|---|---|
| LAMBDAMART | O1 | 0.0298 | 0.3214 | 1.7544 | -0.3037 |
| LAMBDAMART | O2 | 0.0650 | 0.7534 | 3.0627 | -0.1497 |
| LAMBDAMART | O3 | 0.0409 | 0.8042 | 2.9360 | -0.3037 |
| LAMBDAMART | O4 | 0.0025 | 0.8667 | 2.7635 | -0.3037 |
| LGBM_REGRESSION | O1 | -0.0087 | 0.3778 | 1.2228 | -0.2718 |
| LGBM_REGRESSION | O2 | 0.0467 | 0.6555 | 2.1429 | -0.1747 |
| LGBM_REGRESSION | O3 | 0.0439 | 0.9105 | 2.5364 | -0.2718 |
| LGBM_REGRESSION | O4 | 0.0117 | 0.9628 | 2.6605 | -0.2718 |

## 11. Sector Concentration

| architecture | largest_sector | largest_sector_abs_pnl_share |
|---|---|---|
| LAMBDAMART | XUSIN.IS | 0.6974 |
| LGBM_REGRESSION | XU100.IS | 0.4359 |

Leave-one-sector-out worst mean Rank IC: LGBM Regression excluding XUSIN.IS = -0.0411; LambdaMART excluding XUSIN.IS = -0.0127. Sector taxonomy is proxy-only.

## 12. Stock / PnL Concentration

| architecture | top1_abs_pnl_share | top3_abs_pnl_share | top5_abs_pnl_share | top10_abs_pnl_share | stock_pnl_hhi | largest_sector_abs_pnl_share | largest_sector |
|---|---|---|---|---|---|---|---|
| LAMBDAMART | 0.0822 | 0.1859 | 0.2750 | 0.4730 | 0.0339 | 0.6974 | XUSIN.IS |
| LGBM_REGRESSION | 0.1543 | 0.2967 | 0.3963 | 0.5749 | 0.0520 | 0.4359 | XU100.IS |

## 13. Jackpot Dependence

Top contribution shares are absolute mark-to-market PnL shares; main results remain uncensored. | architecture | top1_abs_pnl_share | top3_abs_pnl_share | top5_abs_pnl_share | top10_abs_pnl_share | stock_pnl_hhi | largest_sector_abs_pnl_share | largest_sector |
|---|---|---|---|---|---|---|---|
| LAMBDAMART | 0.0822 | 0.1859 | 0.2750 | 0.4730 | 0.0339 | 0.6974 | XUSIN.IS |
| LGBM_REGRESSION | 0.1543 | 0.2967 | 0.3963 | 0.5749 | 0.0520 | 0.4359 | XU100.IS |

## 14. Block Bootstrap

| architecture | replications | block_length | ic_p05 | ic_median | ic_p95 | prob_ic_positive | net_p05 | net_median | net_p95 | prob_net_positive | sharpe_p05 | sharpe_median | sharpe_p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LAMBDAMART | 2000 | 2 | -0.0414 | 0.0167 | 0.0661 | 0.6875 | 0.1169 | 0.2059 | 0.2955 | 1.0000 | 0.9864 | 1.7974 | 3.4186 |
| LGBM_REGRESSION | 2000 | 2 | -0.0259 | 0.0413 | 0.1089 | 0.8370 | 0.1036 | 0.2267 | 0.3463 | 0.9995 | 0.9027 | 1.7681 | 3.6906 |

## 15. Parameter Perturbation

| architecture | family | case | mean_rank_ic | median_rank_ic | mean_net_return | mean_sharpe | worst_maxdd |
|---|---|---|---|---|---|---|---|
| LAMBDAMART | PARAMETER | HIGH_COMPLEXITY | 0.0321 | 0.0335 | 0.6508 | 2.5135 | -0.2964 |
| LAMBDAMART | PARAMETER | LOW_COMPLEXITY | 0.0484 | 0.0376 | 0.7217 | 2.6700 | -0.3263 |
| LGBM_REGRESSION | PARAMETER | HIGH_COMPLEXITY | 0.0249 | 0.0086 | 0.6835 | 2.0004 | -0.2909 |
| LGBM_REGRESSION | PARAMETER | LOW_COMPLEXITY | 0.0225 | 0.0083 | 0.7186 | 2.2578 | -0.2741 |

## 16. Seed Stability

Fixed three-seed evidence reused; no best seed selection. Mean within-fold seed IC dispersion from EXP-MODEL-001: LGBM Regression 0.0087; LambdaMART 0.0159.

## 17. Price-Derived Regimes

Only pre-locked BIST price trend/volatility regimes are used; macro/FX labels excluded. Regime sample remains small and descriptive.

| architecture | regime | mean_rank_ic | observations |
|---|---|---|---|
| LAMBDAMART | TREND_DOWN | 0.0064 | 3 |
| LAMBDAMART | TREND_UP | 0.0103 | 9 |
| LGBM_REGRESSION | TREND_DOWN | 0.0552 | 3 |
| LGBM_REGRESSION | TREND_UP | -0.0096 | 9 |
| LAMBDAMART | VOL_HIGH | -0.0079 | 6 |
| LAMBDAMART | VOL_LOW | 0.0266 | 6 |
| LGBM_REGRESSION | VOL_HIGH | 0.0024 | 6 |
| LGBM_REGRESSION | VOL_LOW | 0.0109 | 6 |

## 18. Model Similarity / Ranking Overlap

| rank_correlation | top10_overlap |
|---|---|
| 0.5575 | 0.3786 |

## 19. Robustness Classification

| architecture | classification | dimensions_passed | bootstrap_prob_ic_positive | bootstrap_prob_net_positive | alpha_pass | feature_pass | time_pass | sector_pass | stock_pass | cost_pass | delay_pass | liquidity_pass | seed_parameter_pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LGBM_REGRESSION | ROBUST WITH CAVEATS | 8 | 0.8370 | 0.9995 | False | True | True | True | True | True | True | True | True |
| LAMBDAMART | ROBUST WITH CAVEATS | 7 | 0.6875 | 1.0000 | False | True | True | False | True | True | True | True | True |

## 20. Limitations

Signals/folds are dependent; bootstrap is uncertainty analysis, not independent market histories. Survivor universe, provider data and proxy sector taxonomy remain.

## 21. Tests

14/14 dedicated robustness tests and 128/128 full research regression tests PASS.

## 22. Production Integrity

Final protected-production hash verification: PASS, 0 changed.

## 23. Phase I Gate

**PASS**

| architecture | classification | dimensions_passed | bootstrap_prob_ic_positive | bootstrap_prob_net_positive | alpha_pass | feature_pass | time_pass | sector_pass | stock_pass | cost_pass | delay_pass | liquidity_pass | seed_parameter_pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LGBM_REGRESSION | ROBUST WITH CAVEATS | 8 | 0.8370 | 0.9995 | False | True | True | True | True | True | True | True | True |
| LAMBDAMART | ROBUST WITH CAVEATS | 7 | 0.6875 | 1.0000 | False | True | True | False | True | True | True | True | True |

## 24. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Stop and review Phase I evidence before Phase J Pareto finalist decision; do not start it automatically.
