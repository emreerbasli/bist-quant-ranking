# Validation and execution contract v1.0.0

This contract was written before baseline results were opened.

## Information timing

- Signal: after the close of `signal_date`.
- Entry: next available market session open, subject to valid open data.
- Labels: `signal_date`, `entry_date`, `label_start`, `label_end`, and `horizon_sessions` are stored for every observation.
- Horizons: 20, 40, and 60 trading sessions. Horizon is selected only in inner temporal validation.
- `LEGACY_V3_TARGET` remains the legacy approximately three-calendar-month label and is never treated as the 60-session label.
- Prediction horizon, rebalance frequency, and holding period are independent configuration fields.

## Initial portfolio control

- Equal weighting; Top-10 for ranked strategies.
- Research-control rebalance frequency: 60 benchmark sessions.
- Minimum holding: 60 sessions. This is a separate portfolio constraint and does not make 60 the preferred prediction horizon.
- The rejected 20-day forced rotation remains closed. A 20-session prediction label is allowed.
- One-way transaction costs: 0, 30, 50, and 100 bps on traded stock notional.
- Daily NAV uses close marks. The control simulator trades at the next open and accounts for both sales and purchases in turnover.
- Terminal positions are liquidated at the configured one-way cost for comparison.

## Temporal validation

- Expanding outer walk-forward with temporal inner validation; no random split.
- All selection is inside inner folds. Outer results cannot select horizon, target, feature, model, hyperparameters, K, or thresholds.
- Purge is observation-specific: a training row is retained only when its actual `label_end_date` is strictly before validation/test start.
- Learned imputation, scaling, winsorization, residualization, and feature selection are fitted only on training data.
- The period starting 2025-06-01 is descriptive only.

## Missing and execution events

- Eligibility is determined from information available at signal time; future return availability cannot define the universe.
- Missing entry prices cause an explicit unfilled selection record rather than a synthetic return.
- Missing marks, halts, delistings, and corporate actions must be counted and reported. No observation is silently dropped or assigned a zero return without a declared policy.

## First package evidence status

Price-only baseline results are diagnostic and `PROXY_UNVERIFIED` because the current ticker list, official listing/delist history, and corporate-action provenance are incomplete. Fundamental/macro-dependent baselines are `N/A` until their inputs pass Phase A gates.
