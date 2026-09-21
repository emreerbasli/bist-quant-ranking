# EXP-ENS-001 — SIMPLE RANK-AVERAGE ENSEMBLE

## 1. Executive Summary

Phase K gate **FAIL**; **ENSEMBLE DOES NOT ADD RELIABLE VALUE**.

## 2. Locked Ensemble Contract

`exp_ens_001.json`; one 50/50 formula, no alternate weights.

## 3. Frozen Parents

EXP-MODEL-001 LGBM Regression and LambdaMART procedures; hashes verified.

## 4. Alignment / Coverage

| outer_fold | signal_dates | parent_candidate_observations | common_observations | observations_lost | common_securities |
|---|---|---|---|---|---|
| O1 | 4 | 254 | 254 | 0 | 65 |
| O2 | 4 | 266 | 266 | 0 | 67 |
| O3 | 4 | 301 | 301 | 0 | 77 |
| O4 | 2 | 165 | 165 | 0 | 86 |

## 5. Ensemble Construction

for each signal_date: ensemble_score = 0.5 * percentile_rank(LGBM_REGRESSION_score) + 0.5 * percentile_rank(LAMBDAMART_score); deterministic average ties; no missing imputation

## 6. Predictive Comparison

| architecture | mean_rank_ic | median_rank_ic | rank_ic_std | positive_fold_ratio | mean_ndcg | mean_topk_spread |
|---|---|---|---|---|---|---|
| ENSEMBLE_50_50 | 0.0400 | 0.1111 | 0.1621 | 0.7500 | 0.5526 | 0.0463 |
| LAMBDAMART | 0.0311 | 0.1091 | 0.1733 | 0.7500 | 0.5891 | 0.0369 |
| LGBM_REGRESSION | 0.0357 | 0.0689 | 0.1048 | 0.7500 | 0.5549 | 0.0092 |

## 7. Ranking Diversity

Existing parent correlation 0.5575 and Top-10 overlap 37.9%; ensemble-parent overlap is reflected in common aligned K=10 holdings. No missing score imputation.

## 8. Portfolio Results

| architecture | mean_net_return | mean_sharpe | worst_daily_maxdd | worst_day | mean_turnover | mean_fill_rate | mean_cash |
|---|---|---|---|---|---|---|---|
| ENSEMBLE_50_50 | 0.6624 | 2.2508 | -0.2832 | -0.0907 | 1.2275 | 1.0000 | 0.0032 |
| LAMBDAMART | 0.6864 | 2.6292 | -0.3037 | -0.0914 | 1.2117 | 1.0000 | 0.0033 |
| LGBM_REGRESSION | 0.7267 | 2.1407 | -0.2718 | -0.0894 | 1.2374 | 1.0000 | 0.0032 |

## 9. Cost / Turnover

| architecture | cost_bps | mean_net_return |
|---|---|---|
| ENSEMBLE_50_50 | 0 | 0.6628 |
| ENSEMBLE_50_50 | 30 | 0.6790 |
| ENSEMBLE_50_50 | 50 | 0.6624 |
| ENSEMBLE_50_50 | 100 | 0.6218 |
| LAMBDAMART | 0 | 0.7281 |
| LAMBDAMART | 30 | 0.7028 |
| LAMBDAMART | 50 | 0.6864 |
| LAMBDAMART | 100 | 0.6463 |
| LGBM_REGRESSION | 0 | 0.7701 |
| LGBM_REGRESSION | 30 | 0.7443 |
| LGBM_REGRESSION | 50 | 0.7267 |
| LGBM_REGRESSION | 100 | 0.6834 |

## 10. Daily Risk

| architecture | worst_daily_maxdd | worst_day |
|---|---|---|
| ENSEMBLE_50_50 | -0.2832 | -0.0907 |
| LAMBDAMART | -0.3037 | -0.0914 |
| LGBM_REGRESSION | -0.2718 | -0.0894 |

## 11. Concentration

| architecture | top1_abs_pnl_share | top3_abs_pnl_share | stock_pnl_hhi | largest_sector_abs_pnl_share | largest_sector |
|---|---|---|---|---|---|
| ENSEMBLE_50_50 | 0.1190 | 0.2591 | 0.0419 | 0.5169 | XUSIN.IS |
| LAMBDAMART | 0.0822 | 0.1859 | 0.0339 | 0.6974 | XUSIN.IS |
| LGBM_REGRESSION | 0.1543 | 0.2967 | 0.0520 | 0.4359 | XU100.IS |

## 12. Minimal Robustness

| architecture | omitted_outer_period | mean_net_return | mean_sharpe | worst_maxdd |
|---|---|---|---|---|
| ENSEMBLE_50_50 | O1 | 0.3575 | 1.4556 | -0.2832 |
| ENSEMBLE_50_50 | O2 | 0.5910 | 2.3388 | -0.1768 |
| ENSEMBLE_50_50 | O3 | 0.8586 | 2.8378 | -0.2832 |
| ENSEMBLE_50_50 | O4 | 0.8426 | 2.3709 | -0.2832 |
| LAMBDAMART | O1 | 0.3214 | 1.7544 | -0.3037 |
| LAMBDAMART | O2 | 0.7534 | 3.0627 | -0.1497 |
| LAMBDAMART | O3 | 0.8042 | 2.9360 | -0.3037 |
| LAMBDAMART | O4 | 0.8667 | 2.7635 | -0.3037 |
| LGBM_REGRESSION | O1 | 0.3778 | 1.2228 | -0.2718 |
| LGBM_REGRESSION | O2 | 0.6555 | 2.1429 | -0.1747 |
| LGBM_REGRESSION | O3 | 0.9105 | 2.5364 | -0.2718 |
| LGBM_REGRESSION | O4 | 0.9628 | 2.6605 | -0.2718 |

| architecture | delay_sessions | mean_net_return | mean_sharpe |
|---|---|---|---|
| ENSEMBLE_50_50 | 1 | 0.6730 | 2.3991 |
| ENSEMBLE_50_50 | 2 | 0.6869 | 2.5105 |
| LAMBDAMART | 1 | 0.7077 | 2.7537 |
| LAMBDAMART | 2 | 0.7452 | 2.8930 |
| LGBM_REGRESSION | 1 | 0.7298 | 2.2461 |
| LGBM_REGRESSION | 2 | 0.7684 | 2.4303 |

## 13. Parent vs Ensemble Trade-offs

Predictive comparable=True; economic usable=False; adds value=False; adds robustness only=False.

## 14. Ensemble Decision

**ENSEMBLE DOES NOT ADD RELIABLE VALUE**; ensemble **REJECT**. Both parents remain CARRY.

## 15. Phase L Readiness

| candidate | classification |
|---|---|
| LGBM_REGRESSION | READY WITH CAVEATS |
| LAMBDAMART | READY WITH CAVEATS |
| ENSEMBLE_50_50 | NOT READY |

## 16. Limitations

Common RAW-60 label is evaluation-only; parent training procedures remain distinct. Survivor/provider and shared feature caveats remain.

## 17. Tests

10/10 dedicated Phase K tests and 146/146 full research regression tests PASS. Parent hashes, exact 50/50 formula, deterministic ranks, same-date alignment, no imputation/tuning, unchanged portfolio contract, cost behavior and production scope were verified.

## 18. Production Integrity

Final protected-production hash verification: PASS, 0 changed.

## 19. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Stop and review Phase K. Then prepare Phase L freeze only for the surviving carry-forward set; do not freeze or deploy automatically.
