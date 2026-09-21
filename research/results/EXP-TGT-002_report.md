# EXP-TGT-002 — TARGET FAMILY COMPARISON

## 1. Executive Summary

Execution **PASS**. Target decision: **NO CLEAR TARGET WINNER**. These target families did not separate under the current simple price-only predictor control; this is not evidence that all targets or price-only alpha fail.

## 2. Locked Contract

Four target families, target-specific inner H=20/40/60 selection, fixed EXP-TGT-001 features/ridge, K=10, 60-session holding/rebalance, 50 bps primary cost. Macro and fundamentals excluded.

## 3. Target Definitions

RAW: raw close-to-close forward return. SECTOR_RELATIVE: raw minus sector median, with universe-median fallback below five names (actual fallback ratio 6.21%). BETA_RESIDUAL: raw minus signal-date ex-ante beta times BIST return. VOL_SCALED: raw divided by signal-date 63-return daily volatility clipped to [0.005, 0.10].

## 4. Fold Design

Same four outer and two-inner-year expanding folds as EXP-TGT-001. Each family selects its own horizon in inner data. Outer evaluates only that selected family procedure.

## 5. Sample Coverage

| target_family | horizon_sessions | candidate_observations | usable_observations | coverage_pct |
|---|---|---|---|---|
| BETA_RESIDUAL | 20 | 1763 | 1756 | 0.9960 |
| BETA_RESIDUAL | 40 | 1677 | 1666 | 0.9934 |
| BETA_RESIDUAL | 60 | 1677 | 1538 | 0.9171 |
| RAW | 20 | 1763 | 1756 | 0.9960 |
| RAW | 40 | 1677 | 1666 | 0.9934 |
| RAW | 60 | 1677 | 1538 | 0.9171 |
| SECTOR_RELATIVE | 20 | 1763 | 1756 | 0.9960 |
| SECTOR_RELATIVE | 40 | 1677 | 1666 | 0.9934 |
| SECTOR_RELATIVE | 60 | 1677 | 1538 | 0.9171 |
| VOL_SCALED | 20 | 1763 | 1756 | 0.9960 |
| VOL_SCALED | 40 | 1677 | 1666 | 0.9934 |
| VOL_SCALED | 60 | 1677 | 1538 | 0.9171 |

## 6. RAW Results

See outer robustness table; horizon remained inner-selected.

## 7. Sector-Relative Results

Uses the locked time-invariant `PROXY_TAXONOMY`; no future reassignment occurs, but historical sector-vintage verification is unavailable.

## 8. Beta-Residual Results

Beta uses only up-to-signal returns with 252-session window, minimum 126 aligned observations and [-3,3] cap.

## 9. Volatility-Scaled Results

Scale uses only the 63 pre-signal returns and the locked daily floor/cap; forward volatility is never used.

## 10. Horizon Selection by Target

| target_family | horizon_sessions | selection_count |
|---|---|---|
| RAW | 20 | 1 |
| RAW | 40 | 2 |
| RAW | 60 | 1 |
| SECTOR_RELATIVE | 20 | 1 |
| SECTOR_RELATIVE | 40 | 2 |
| SECTOR_RELATIVE | 60 | 1 |
| BETA_RESIDUAL | 20 | 1 |
| BETA_RESIDUAL | 40 | 2 |
| BETA_RESIDUAL | 60 | 1 |
| VOL_SCALED | 20 | 1 |
| VOL_SCALED | 40 | 2 |
| VOL_SCALED | 60 | 1 |

## 11. Outer Robustness

| target_family | mean_rank_ic | median_fold_rank_ic | positive_fold_ratio | mean_ndcg_at_10 | mean_top_k_spread_raw | viable |
|---|---|---|---|---|---|---|
| RAW | -0.0613 | -0.0795 | 0.5000 | 0.5582 | 0.0326 | False |
| SECTOR_RELATIVE | -0.0666 | -0.0639 | 0.5000 | 0.5453 | 0.0295 | False |
| BETA_RESIDUAL | -0.0691 | -0.0685 | 0.5000 | 0.5415 | 0.0266 | False |
| VOL_SCALED | -0.1105 | -0.0743 | 0.5000 | 0.4800 | -0.0096 | False |

## 12. Cost / Turnover

0/30/50/100 bps and actual two-sided turnover are recorded per family/outer fold; no K or rebalance optimization was performed. Inner-selected family procedures produced mean net return 1.1286/1.1154/1.1066/1.0847 and mean turnover 1.0177/1.0187/1.0193/1.0208 at 0/30/50/100 bps respectively. These portfolio diagnostics did not select the target.

## 13. Daily Risk

Daily NAV and daily MaxDD were generated for every family-selected horizon and cost scenario. At the primary 50 bps cost, worst fold daily MaxDD by family was RAW -25.59%, SECTOR_RELATIVE -24.85%, BETA_RESIDUAL -29.02%, VOL_SCALED -27.96%.

## 14. Target Decision

**NO CLEAR TARGET WINNER** under the locked inner-frequency plus multi-metric outer-veto rule.

## 15. Limitations

Current-survivor universe, provider-dependent research prices, sparse 60-session signal schedule, simple ridge/three-feature control and proxy sector taxonomy limit generalization. A negative result does not establish that all target definitions fail.

## 16. Tests

Formula, no-future sector/beta/volatility, dynamic labels, inner-only horizon selection, outer isolation, fixed model/features, forbidden inputs, reproducibility and production hash controls are tested separately.

## 17. Production Integrity

Research-only outputs. Final protected production hashes are verified separately.

## 18. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

If no clear target winner emerges, close Phase C without forcing a target and move to Phase D economic feature discovery while retaining target family and horizon as inner-selected procedure parameters. Otherwise carry only the viable target procedure(s) into Phase D. Do not start automatically.
