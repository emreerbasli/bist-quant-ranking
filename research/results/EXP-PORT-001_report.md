# EXP-PORT-001 — PORTFOLIO, COST & CAPACITY CONTROL

## 1. Executive Summary

Phase H gate: **PASS**.

## 2. MASTER_PLAN Phase Mapping

Phase G is substantively satisfied by EXP-MODEL-001 locked outer evidence; no duplicate outer evaluation was created.

## 3. Locked Portfolio Contract

`exp_port_001.json` frozen before results.

## 4. Frozen Alpha Finalists

LGBM Regression and LambdaMART only; same EXP-MODEL-001 features, target/horizon selections, seeds and fixed hyperparameters.

## 5. Execution Contract

next applicable eligible research_open after signal plus delay. no fill.

## 6. Turnover Accounting

two_sided_notional=sum(abs(target_value-pretrade_value))/pretrade_equity; includes retained-name reweights, entries, exits and cash

## 7. Transaction Costs

One-way cost on every traded nominal including terminal liquidation: 0/30/50/100 bps.

## 8. K Sensitivity

| architecture | k | mean_net_return | mean_cagr | mean_sharpe | worst_daily_maxdd | worst_day | mean_turnover | mean_fill_rate | mean_cash | mean_holdings |
|---|---|---|---|---|---|---|---|---|---|---|
| LAMBDAMART | 5 | 0.4971 | 1.2066 | 2.3793 | -0.3369 | -0.0946 | 1.3210 | 1.0000 | 0.0027 | 5.0000 |
| LAMBDAMART | 10 | 0.6864 | 1.2983 | 2.6292 | -0.3037 | -0.0914 | 1.2117 | 1.0000 | 0.0033 | 10.0000 |
| LAMBDAMART | 15 | 0.6250 | 1.0885 | 2.2502 | -0.2668 | -0.0918 | 1.1131 | 1.0000 | 0.0040 | 15.0000 |
| LAMBDAMART | 20 | 0.6789 | 1.2170 | 2.4061 | -0.2462 | -0.0900 | 1.0776 | 1.0000 | 0.0041 | 20.0000 |
| LGBM_REGRESSION | 5 | 0.7270 | 1.3901 | 2.1192 | -0.3406 | -0.0968 | 1.3188 | 1.0000 | 0.0026 | 5.0000 |
| LGBM_REGRESSION | 10 | 0.7267 | 1.2579 | 2.1407 | -0.2718 | -0.0894 | 1.2374 | 1.0000 | 0.0032 | 10.0000 |
| LGBM_REGRESSION | 15 | 0.6235 | 1.0474 | 1.8948 | -0.2734 | -0.0891 | 1.1900 | 1.0000 | 0.0035 | 15.0000 |
| LGBM_REGRESSION | 20 | 0.6773 | 1.2077 | 2.3649 | -0.2667 | -0.0887 | 1.1237 | 1.0000 | 0.0038 | 20.0000 |

## 9. LGBM Regression Results

| architecture | k | mean_net_return | mean_cagr | mean_sharpe | worst_daily_maxdd | worst_day | mean_turnover | mean_fill_rate | mean_cash | mean_holdings |
|---|---|---|---|---|---|---|---|---|---|---|
| LGBM_REGRESSION | 5 | 0.7270 | 1.3901 | 2.1192 | -0.3406 | -0.0968 | 1.3188 | 1.0000 | 0.0026 | 5.0000 |
| LGBM_REGRESSION | 10 | 0.7267 | 1.2579 | 2.1407 | -0.2718 | -0.0894 | 1.2374 | 1.0000 | 0.0032 | 10.0000 |
| LGBM_REGRESSION | 15 | 0.6235 | 1.0474 | 1.8948 | -0.2734 | -0.0891 | 1.1900 | 1.0000 | 0.0035 | 15.0000 |
| LGBM_REGRESSION | 20 | 0.6773 | 1.2077 | 2.3649 | -0.2667 | -0.0887 | 1.1237 | 1.0000 | 0.0038 | 20.0000 |

## 10. LambdaMART Results

| architecture | k | mean_net_return | mean_cagr | mean_sharpe | worst_daily_maxdd | worst_day | mean_turnover | mean_fill_rate | mean_cash | mean_holdings |
|---|---|---|---|---|---|---|---|---|---|---|
| LAMBDAMART | 5 | 0.4971 | 1.2066 | 2.3793 | -0.3369 | -0.0946 | 1.3210 | 1.0000 | 0.0027 | 5.0000 |
| LAMBDAMART | 10 | 0.6864 | 1.2983 | 2.6292 | -0.3037 | -0.0914 | 1.2117 | 1.0000 | 0.0033 | 10.0000 |
| LAMBDAMART | 15 | 0.6250 | 1.0885 | 2.2502 | -0.2668 | -0.0918 | 1.1131 | 1.0000 | 0.0040 | 15.0000 |
| LAMBDAMART | 20 | 0.6789 | 1.2170 | 2.4061 | -0.2462 | -0.0900 | 1.0776 | 1.0000 | 0.0041 | 20.0000 |

## 11. Daily Risk

| architecture | k | worst_daily_maxdd | worst_day |
|---|---|---|---|
| LAMBDAMART | 5 | -0.3369 | -0.0946 |
| LAMBDAMART | 10 | -0.3037 | -0.0914 |
| LAMBDAMART | 15 | -0.2668 | -0.0918 |
| LAMBDAMART | 20 | -0.2462 | -0.0900 |
| LGBM_REGRESSION | 5 | -0.3406 | -0.0968 |
| LGBM_REGRESSION | 10 | -0.2718 | -0.0894 |
| LGBM_REGRESSION | 15 | -0.2734 | -0.0891 |
| LGBM_REGRESSION | 20 | -0.2667 | -0.0887 |

## 12. Liquidity

ADV20 uses only resolved positive-volume history. | architecture | capital_try | adv_limit_pct | mean_net_return | mean_fill_rate | unfilled | mean_cash | median_order_adv | p95_order_adv | max_order_adv | pct_orders_gt_10pct_adv |
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

## 13. Capacity Scenarios

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

## 14. Fill / Delay Stress

| architecture | delay_sessions | mean_net_return | mean_sharpe | worst_daily_maxdd | mean_fill_rate |
|---|---|---|---|---|---|
| LAMBDAMART | 1 | 0.7077 | 2.7537 | -0.2983 | 1.0000 |
| LAMBDAMART | 2 | 0.7452 | 2.8930 | -0.2982 | 1.0000 |
| LGBM_REGRESSION | 1 | 0.7298 | 2.2461 | -0.2708 | 1.0000 |
| LGBM_REGRESSION | 2 | 0.7684 | 2.4303 | -0.2698 | 1.0000 |

## 15. Concentration

Equal-weight target maximum single-name weight is 1/K; holdings and cash exposure are reported in K sensitivity. Sector/stock PnL concentration is descriptive-only under the current survivor universe caveat.

## 16. Cost Survival

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

## 17. Architecture Comparison

| architecture | classification | cost_monotonic | k | mean_net_return | mean_cagr | mean_sharpe | worst_daily_maxdd | worst_day | mean_turnover | mean_fill_rate | mean_cash | mean_holdings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LGBM_REGRESSION | VIABLE | True | 10 | 0.7267 | 1.2579 | 2.1407 | -0.2718 | -0.0894 | 1.2374 | 1.0000 | 0.0032 | 10.0000 |
| LAMBDAMART | VIABLE | True | 10 | 0.6864 | 1.2983 | 2.6292 | -0.3037 | -0.0914 | 1.2117 | 1.0000 | 0.0033 | 10.0000 |

## 18. Limitations

Current universe is survivorship-limited; price/volume and corporate-action evidence remains provider-dependent. Fundamental, macro and USDTRY are excluded.

## 19. Tests

13/13 dedicated portfolio tests and 114/114 full research regression tests PASS. Coverage includes frozen-model scope, no alpha redesign, K isolation, two-sided turnover, cost monotonicity, terminal liquidation, no-borrowing cash, ADV eligibility, capacity metrics, delay and daily NAV.

## 20. Production Integrity

Final protected-production hash verification: PASS, 0 changed. Research-only outputs.

## 21. Phase H Gate

**PASS**

| architecture | classification | cost_monotonic | k | mean_net_return | mean_cagr | mean_sharpe | worst_daily_maxdd | worst_day | mean_turnover | mean_fill_rate | mean_cash | mean_holdings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LGBM_REGRESSION | VIABLE | True | 10 | 0.7267 | 1.2579 | 2.1407 | -0.2718 | -0.0894 | 1.2374 | 1.0000 | 0.0032 | 10.0000 |
| LAMBDAMART | VIABLE | True | 10 | 0.6864 | 1.2983 | 2.6292 | -0.3037 | -0.0914 | 1.2117 | 1.0000 | 0.0033 | 10.0000 |

## 22. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Stop after this package. Review the Phase H gate before any Phase I stress/ablation work; do not initiate it automatically.
