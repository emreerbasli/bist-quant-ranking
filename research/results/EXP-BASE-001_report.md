# EXP-BASE-001 — Price-only diagnostic baselines

**Gate: PARTIAL.** Results are descriptive and `PROXY_UNVERIFIED`; they cannot select a model, feature, target, horizon, or production change. The universe is the currently configured survivor list and corporate-action provenance is incomplete.

| strategy | cost_bps | evidence | observations | cumulative_return | cagr | sharpe_rf0 | sortino_rf0 | daily_max_drawdown | worst_day | missing_mark_events | unfilled_selections |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BIST100 | 0 | PROXY_UNVERIFIED | 1345 | 6.82703 | 0.470364 | 1.49014 | 1.86485 | -0.318154 | -0.0979071 | N/A | N/A |
| UNIVERSE_EQUAL_WEIGHT | 0 | PROXY_UNVERIFIED | 1345 | 17.1056 | 0.72054 | 2.02179 | 2.43708 | -0.34111 | -0.0970096 | 105 | 0 |
| MOMENTUM_12_1_TOP10 | 0 | PROXY_UNVERIFIED | 1345 | 50.7446 | 1.09465 | 2.25782 | 3.04705 | -0.394251 | -0.097911 | 12 | 0 |
| BIST100 | 30 | PROXY_UNVERIFIED | 1345 | 6.78014 | 0.46871 | 1.48622 | 1.8597 | -0.318154 | -0.0979071 | N/A | N/A |
| UNIVERSE_EQUAL_WEIGHT | 30 | PROXY_UNVERIFIED | 1345 | 16.7858 | 0.714804 | 2.01023 | 2.42309 | -0.34111 | -0.0970096 | 105 | 0 |
| MOMENTUM_12_1_TOP10 | 30 | PROXY_UNVERIFIED | 1345 | 47.5429 | 1.06973 | 2.22329 | 3.00174 | -0.394251 | -0.097911 | 12 | 0 |
| BIST100 | 50 | PROXY_UNVERIFIED | 1345 | 6.74896 | 0.467605 | 1.48358 | 1.85619 | -0.318154 | -0.0979071 | N/A | N/A |
| UNIVERSE_EQUAL_WEIGHT | 50 | PROXY_UNVERIFIED | 1345 | 16.5754 | 0.710986 | 2.00247 | 2.41491 | -0.34111 | -0.0970096 | 105 | 0 |
| MOMENTUM_12_1_TOP10 | 50 | PROXY_UNVERIFIED | 1345 | 45.5146 | 1.05324 | 2.19997 | 2.97113 | -0.394251 | -0.097911 | 12 | 0 |
| BIST100 | 100 | PROXY_UNVERIFIED | 1345 | 6.67128 | 0.464837 | 1.47684 | 1.84716 | -0.318154 | -0.0979071 | N/A | N/A |
| UNIVERSE_EQUAL_WEIGHT | 100 | PROXY_UNVERIFIED | 1345 | 16.0596 | 0.701462 | 1.98284 | 2.39127 | -0.34111 | -0.0970096 | 105 | 0 |
| MOMENTUM_12_1_TOP10 | 100 | PROXY_UNVERIFIED | 1345 | 40.7923 | 1.01247 | 2.14068 | 2.89245 | -0.394251 | -0.097911 | 12 | 0 |

## Unavailable common baselines

| baseline | status | reason |
|---|---|---|
| VALUE_QUALITY | N/A | fundamental PIT/accounting gate not passed |
| V3 | N/A | common refit comparison requires unverified fundamental/macro inputs |
| V4_1 | N/A | common refit comparison requires unverified fundamental/macro inputs and old lockbox is contaminated |
