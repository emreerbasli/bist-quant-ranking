# EXP-FEAT-001 — PRICE-ONLY ECONOMIC FEATURE DISCOVERY

## 1. Executive Summary

Execution PASS. **PRICE FEATURE DISCOVERY = FAIL**. Candidate classifications: {'REJECTED': 25}.

## 2. Locked Contract

25 candidates, fixed ridge alpha=1, baseline mom_12_1/mom_63/vol_63, inner-only feature/target/horizon selection, K=10 and fixed 60-session holding/rebalance.

## 3. Candidate Feature Definitions

Seven momentum, two consistency, three reversal, six risk and seven liquidity representations were hashed before results.

## 4. Data Quality & Coverage

| candidate | family | coverage | missingness | outlier_ratio_3iqr | max_ticker_share |
|---|---|---|---|---|---|
| downside_vol_126 | RISK | 1.0000 | 0.0000 | 0.0011 | 0.0153 |
| downside_vol_63 | RISK | 1.0000 | 0.0000 | 0.0011 | 0.0153 |
| log_adv20 | LIQUIDITY | 1.0000 | 0.0000 | 0.0000 | 0.0153 |
| log_adv63 | LIQUIDITY | 1.0000 | 0.0000 | 0.0000 | 0.0153 |
| log_amihud20 | LIQUIDITY | 1.0000 | 0.0000 | 0.0737 | 0.0153 |
| log_amihud63 | LIQUIDITY | 1.0000 | 0.0000 | 0.0788 | 0.0153 |
| max_drawdown_63 | RISK | 1.0000 | 0.0000 | 0.0045 | 0.0153 |
| mom_126 | MOMENTUM | 1.0000 | 0.0000 | 0.0136 | 0.0153 |
| mom_126_skip20 | MOMENTUM | 1.0000 | 0.0000 | 0.0147 | 0.0153 |
| mom_20 | MOMENTUM | 1.0000 | 0.0000 | 0.0051 | 0.0153 |
| mom_252 | MOMENTUM | 1.0000 | 0.0000 | 0.0221 | 0.0153 |
| mom_252_skip20 | MOMENTUM | 0.9609 | 0.0391 | 0.0207 | 0.0153 |
| mom_40 | MOMENTUM | 1.0000 | 0.0000 | 0.0062 | 0.0153 |
| mom_63_rank | MOMENTUM | 1.0000 | 0.0000 | 0.0091 | 0.0153 |
| positive_return_ratio_63 | MOMENTUM_CONSISTENCY | 1.0000 | 0.0000 | 0.0000 | 0.0153 |
| ret_10 | REVERSAL | 1.0000 | 0.0000 | 0.0085 | 0.0153 |
| ret_20 | REVERSAL | 1.0000 | 0.0000 | 0.0051 | 0.0153 |
| ret_5 | REVERSAL | 1.0000 | 0.0000 | 0.0147 | 0.0153 |
| sign_consistency_4x20 | MOMENTUM_CONSISTENCY | 1.0000 | 0.0000 | 0.0000 | 0.0153 |
| vol_126 | RISK | 1.0000 | 0.0000 | 0.0006 | 0.0153 |
| vol_20 | RISK | 1.0000 | 0.0000 | 0.0017 | 0.0153 |
| vol_63_rank | RISK | 1.0000 | 0.0000 | 0.0011 | 0.0153 |
| volume_cv63 | LIQUIDITY | 1.0000 | 0.0000 | 0.0091 | 0.0153 |
| zero_return_ratio20 | LIQUIDITY | 1.0000 | 0.0000 | 0.0176 | 0.0153 |
| zero_return_ratio63 | LIQUIDITY | 1.0000 | 0.0000 | 0.0465 | 0.0153 |

## 5. Correlation / Redundancy

Full pairwise rank correlations and baseline correlations are separate artifacts. Correlation is diagnostic, not an automatic drop rule.

| family | candidate_count | viable_count | weak_count | rejected_count | strongest_representations | best_median_inner_delta_rank_ic | high_correlation_cluster_ids |
|---|---|---|---|---|---|---|---|
| LIQUIDITY | 7 | 0 | 0 | 7 | log_adv63|log_adv20|log_amihud20 | 0.0218 | 6 |
| MOMENTUM | 7 | 0 | 0 | 7 | mom_252|mom_20|mom_126 | 0.0027 | 1|2|3|4 |
| MOMENTUM_CONSISTENCY | 2 | 0 | 0 | 2 | sign_consistency_4x20|positive_return_ratio_63 | 0.0131 |  |
| REVERSAL | 3 | 0 | 0 | 3 | ret_20|ret_10|ret_5 | -0.0002 | 1 |
| RISK | 6 | 0 | 0 | 6 | vol_126|vol_63_rank|downside_vol_63 | 0.0341 | 5 |

## 6. Momentum Features

20/40/63/126/252 and 126/252 skip-20 representations were evaluated against the baseline, not presumed independent.

## 7. Momentum Consistency

Positive-return ratio and four-block sign consistency used only historical returns.

## 8. Reversal Features

ret_5/10/20 were evaluated as predictors; ret_20 did not alter the fixed 60-session portfolio rotation rule.

## 9. Risk Features

20/63/126 volatility, downside volatility and 63-session historical drawdown were evaluated.

## 10. Liquidity Features

ADV uses raw close × positive observed volume. Amihud, zero-return and volume stability exclude unresolved/missing-volume rows; missing is never zero.

## 11. Univariate IC

IC frequency is one cross-sectional Spearman observation per scheduled 60-session signal date. Full inner-fold mean/median/std/positive ratio/ICIR is in the univariate artifact.

## 12. Incremental Baseline Tests

| candidate | family | inner_selection_frequency | median_inner_delta_rank_ic | outer_mean_delta_rank_ic | outer_mean_delta_ndcg | classification |
|---|---|---|---|---|---|---|
| mom_20 | MOMENTUM | 1 | -0.0002 | 0.0460 | -0.0087 | REJECTED |
| mom_40 | MOMENTUM | 0 | -0.0178 | N/A | N/A | REJECTED |
| mom_63_rank | MOMENTUM | 0 | -0.0300 | N/A | N/A | REJECTED |
| mom_126 | MOMENTUM | 0 | -0.0086 | N/A | N/A | REJECTED |
| mom_252 | MOMENTUM | 1 | 0.0027 | -0.0081 | -0.0164 | REJECTED |
| mom_126_skip20 | MOMENTUM | 0 | -0.0139 | N/A | N/A | REJECTED |
| mom_252_skip20 | MOMENTUM | 0 | -0.0098 | N/A | N/A | REJECTED |
| positive_return_ratio_63 | MOMENTUM_CONSISTENCY | 1 | 0.0087 | -0.0161 | -0.0405 | REJECTED |
| sign_consistency_4x20 | MOMENTUM_CONSISTENCY | 0 | 0.0131 | N/A | N/A | REJECTED |
| ret_5 | REVERSAL | 0 | -0.0134 | N/A | N/A | REJECTED |
| ret_10 | REVERSAL | 0 | -0.0115 | N/A | N/A | REJECTED |
| ret_20 | REVERSAL | 1 | -0.0002 | 0.0460 | -0.0087 | REJECTED |
| vol_20 | RISK | 1 | -0.0307 | 0.0820 | 0.0493 | REJECTED |
| vol_63_rank | RISK | 1 | 0.0056 | 0.0906 | -0.0382 | REJECTED |
| vol_126 | RISK | 0 | 0.0341 | N/A | N/A | REJECTED |
| downside_vol_63 | RISK | 0 | -0.0068 | N/A | N/A | REJECTED |
| downside_vol_126 | RISK | 0 | -0.0150 | N/A | N/A | REJECTED |
| max_drawdown_63 | RISK | 0 | -0.0325 | N/A | N/A | REJECTED |
| log_adv20 | LIQUIDITY | 1 | 0.0147 | 0.1112 | -0.1280 | REJECTED |
| log_adv63 | LIQUIDITY | 1 | 0.0218 | 0.1062 | -0.1296 | REJECTED |
| log_amihud20 | LIQUIDITY | 1 | 0.0105 | 0.0752 | -0.1547 | REJECTED |
| log_amihud63 | LIQUIDITY | 1 | -0.0038 | 0.0726 | -0.0998 | REJECTED |
| zero_return_ratio20 | LIQUIDITY | 0 | -0.0365 | N/A | N/A | REJECTED |
| zero_return_ratio63 | LIQUIDITY | 0 | -0.0593 | N/A | N/A | REJECTED |
| volume_cv63 | LIQUIDITY | 0 | -0.0009 | N/A | N/A | REJECTED |

## 13. Inner Feature Selection

Each outer fold selected candidates from its two inner years only. No outer result added a feature.

## 14. Target/Horizon Selection Interaction

Baseline target/horizon was inner-selected and frozen for candidate incremental tests. The per-outer combined inner-selected feature set was allowed one inner-only target/horizon reselection.

## 15. Outer Generalization

Combined selected-set mean outer delta Rank IC versus the same target/horizon baseline: 0.0374. Outer results only veto classifications.

## 16. Turnover / Cost / Daily Risk

Combined procedures were simulated at 0/30/50/100 bps with actual turnover and daily NAV/MaxDD. Prediction metrics, not Sharpe/CAGR, govern selection.

## 17. Family Ablation

N/A: no feature reached final VIABLE status, so the locked rule did not open family ablation.

## 18. Final Viable Feature Set

VIABLE: none. WEAK / RESEARCH ONLY: none. All others are REJECTED under this wave's locked criteria.

## 19. Limitations

Current-survivor universe, provider-dependent price history, sparse scheduled signal dates, simple ridge control, multiple testing across 25 candidates and unresolved official volume/status provenance limit inference.

## 20. Tests

No-future formulas, window/minimum history, volume/SASA handling, cross-sectional transform, train-only preprocessing, nested selection/isolation, forbidden inputs and reproducibility are tested separately.

## 21. Production Integrity

Research-only outputs; protected hashes are verified separately.

## 22. Phase D Gate

**PRICE FEATURE DISCOVERY = FAIL**.

## 23. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Carry only VIABLE features (and separately labeled WEAK research controls if justified) to the next MASTER_PLAN phase. Do not expand this first price-feature wave or start model-family comparison automatically.
