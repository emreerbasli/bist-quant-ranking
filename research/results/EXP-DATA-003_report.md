# EXP-DATA-003 — PRICE EVENT RECONCILIATION

## 1. Executive Summary

**PRICE DATA = PARTIAL.** Five apparent daily losses above 50% are all
`CONFIRMED_DATA_ERROR`: the provider inserted a price-level adjustment before the
official KAP/Borsa ex-date and left the local `stock_splits` field at zero. A
research-only total-return view neutralizes those false losses; production data is
unchanged.

The two OHLC failures split into one material source error (MTRKS) and one
one-inferred-tick rounding defect (MIATK). All 1,728 non-positive-volume bars have
OHLC values and volume equals zero; none has negative volume. Pattern attribution is
855 multi-session no-trade/suspension-like bars, 190 missing-volume-only bars and 683
single-session unknown bars. No bar is classified as a full OHLC data gap.

At 50 bps, reconciliation changes equal-weight CAGR by +0.86 percentage point and
momentum CAGR by +3.03 percentage points; Sharpe changes are +0.017 and +0.051.
Daily MaxDD and worst day are unchanged at shown precision. This supports continued
price-only exploration with explicit caveats, not model/target/horizon/K selection.

## 2. Five Extreme Price Events

### HEKTS.IS — 2024-09-09

| Field | Value |
|---|---:|
| Previous trading date | 2024-09-06 |
| Previous / current raw close (external Yahoo) | 11.760000 / 4.134030 |
| Previous / current adjusted close (local) | 11.760000 / 4.134030 |
| Raw / adjusted return | -64.8467% / -64.8467% |
| Volume; zero/stale | 49,948,771; no / no |
| Official action | 233.20158% rights issue at TRY 1.00 |
| Provider date / official ex-date | 2024-09-09 / 2024-09-18 |
| Local event/cache | dividends=0; stock_splits=0; no ticker-specific local corporate-action record |
| Source consistency | Local adjusted values match current Yahoo; both conflict with official ex-date and omit the action field |
| Reconciled economic return at provider boundary | -2.2521% |
| Classification | **CONFIRMED_DATA_ERROR** |

Official record: https://www.kap.org.tr/tr/Bildirim/1334639

### BSOKE.IS — 2024-12-02

| Field | Value |
|---|---:|
| Previous trading date | 2024-11-29 |
| Previous / current raw close (external Yahoo) | 60.000000 / 15.467761 |
| Previous / current adjusted close (local) | 60.000000 / 15.467761 |
| Raw / adjusted return | -74.2204% / -74.2204% |
| Volume; zero/stale | 10,220,683; no / no |
| Official action | 300% rights issue at TRY 1.00 |
| Provider date / official ex-date | 2024-12-02 / 2024-12-10 |
| Local event/cache | dividends=0; stock_splits=0; no ticker-specific local corporate-action record |
| Source consistency | Local adjusted values match current Yahoo; official KAP terms/date disagree with the provider boundary |
| Reconciled economic return at provider boundary | -1.7920% |
| Classification | **CONFIRMED_DATA_ERROR** |

Official record: https://www.kap.org.tr/tr/Bildirim/1363968

### CCOLA.IS — 2024-08-01

| Field | Value |
|---|---:|
| Previous trading date | 2024-07-31 |
| Previous / current raw close (external Yahoo) | 846.000000 / 78.272728 |
| Previous / current adjusted close (local) | 814.937500 / 75.398796 |
| Raw / adjusted return | -90.7479% / -90.7479% |
| Volume; zero/stale | 3,966,028; no / no |
| Official action | 1,000% bonus issue (11-for-1 post-action share count) |
| Provider date / official ex-date | 2024-08-01 / 2024-08-13 |
| Local event/cache | dividends=0; stock_splits=0; no ticker-specific local corporate-action record |
| Source consistency | Raw and adjusted Yahoo transitions agree with each other but are 12 days early versus KAP |
| Reconciled economic return at provider boundary | +1.7731% |
| Classification | **CONFIRMED_DATA_ERROR** |

Official record: https://kap.org.tr/tr/api/BildirimPdf/1321329

### KBORU.IS — 2025-01-02

| Field | Value |
|---|---:|
| Previous trading date | 2024-12-31 |
| Previous / current raw close (external Yahoo) | 77.750000 / 13.166666 |
| Previous / current adjusted close (local) | 76.462234 / 12.948587 |
| Raw / adjusted return | -83.0654% / -83.0654% |
| Volume; zero/stale | 7,241,616; no / no |
| Official action | 500% bonus issue (6-for-1 post-action share count) |
| Provider date / official ex-date | 2025-01-02 / 2025-06-04 |
| Local event/cache | dividends=0; stock_splits=0; no ticker-specific local corporate-action record |
| Source consistency | Local/current Yahoo agree; the discontinuity precedes official KAP ex-date by five months |
| Reconciled economic return at provider boundary | +1.6077% |
| Classification | **CONFIRMED_DATA_ERROR** |

Official record: https://www.kap.org.tr/tr/Bildirim/1446216

### CVKMD.IS — 2026-08-03

| Field | Value |
|---|---:|
| Previous trading date | 2026-07-31 |
| Previous / current raw close (external Yahoo) | 37.820000 / 14.417085 |
| Previous / current adjusted close (local) | 37.820000 / 14.417085 |
| Raw / adjusted return | -61.8797% / -61.8797% |
| Volume; zero/stale | 17,609,960; no / no |
| Official action | 170% rights issue at TRY 1.00 |
| Provider date / official ex-date | 2026-08-03 / 2026-08-05 |
| Local event/cache | dividends=0; stock_splits=0; no ticker-specific local corporate-action record |
| Source consistency | Local/current Yahoo agree; KAP/Borsa places rights trading two sessions later |
| Reconciled economic return at provider boundary | -1.5027% |
| Classification | **CONFIRMED_DATA_ERROR** |

Official record: https://www.kap.org.tr/tr/Bildirim/1642697

The local `data/events.csv` contains generic scheduled balance dates, not security
actions; `data/kap_vbts_arsiv.csv` contains no event rows. The raw closes above were
fetched without overwriting any cache, using the repository's installed yfinance
dependency with `auto_adjust=False`.

## 3. OHLC Inconsistencies

| Symbol/date | Open | High | Low | Close | Failed invariant | Gap | Relative gap | Raw/adjusted and source finding | Classification |
|---|---:|---:|---:|---:|---|---:|---:|---|---|
| MTRKS.IS 2022-06-27 | 14.474677 | 14.474677 | 14.474677 | 14.565225 | high < max(open, close) | 0.090547 | 0.6217% | Current external raw also has high 14.92 < close 15.013333; not an adjustment mix or local-cache mismatch | **DATA_ERROR** |
| MIATK.IS 2022-06-27 | 2.506153 | 2.506153 | 2.506153 | 2.504615 | low > min(open, close) | 0.001538 | 0.0614% | Raw equals adjusted; gap equals one inferred pre-adjustment TRY 0.02 tick | **ROUNDING_ONLY** |

Both satisfy `low <= high`. Neither is an adjusted/unadjusted mixture, and the local
cache matches the provider response. Both observations are excluded by the current
research eligibility mask. MIATK may only be admitted later through an explicit,
invariant-safe rounding transform; raw data is never mutated.

## 4. Zero/Negative Volume Pattern Analysis

All 1,728 observations are after the symbol's first positive-volume bar, all have
OHLC, and none has negative volume.

| Approximate category | Bars | Symbols | Maximum run | Return=0 | Return nonzero | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| LEGITIMATE_NO_TRADE / SUSPENSION | 855 | 88 | 17 | 855 | 0 | Multi-session flat OHLC/zero-volume runs; exchange-status data is still needed to split closures from suspensions |
| STALE_PRICE | 0 | 0 | 0 | 0 | 0 | No separate attribution after the conservative combined no-trade/suspension rule |
| MISSING_VOLUME_ONLY | 190 | 24 | 29 | 52 | 138 | OHLC exists and is not a flat carried bar; especially concentrated in SASA in 2025–2026 |
| FULL_DATA_GAP | 0 | 0 | 0 | 0 | 0 | No zero-volume row lacks OHLC |
| UNKNOWN | 683 | 80 | 1 | 683 | 0 | Isolated flat zero-volume bars; cannot be called a holiday or suspension without exchange status |

Year counts are saved in the detailed/grouped CSVs. The largest special pattern is
SASA: 25 missing-volume-only bars in 2025 and 111 in 2026, with nonzero price changes
on most observations. The common flat clusters on 2018/2019 holiday-like dates and
2026-05-27 through 2026-05-29 are pattern evidence only, not official status proof.

## 5. Corporate Action Findings

The production downloader requests `auto_adjust=True, actions=True`, but the provider
did not populate `stock_splits` for any of the five verified BIST actions. Therefore,
the action columns cannot independently validate the adjusted OHLC.

Research policy:

- KAP/Borsa action terms and ex-dates are authoritative.
- A total-return adjusted series embeds split/bonus and dividend effects; no separate
  dividend cash is added to that same NAV.
- Rights issues use either a verified total-return adjustment or explicit raw-price,
  subscription-cash and rights-entitlement accounting—never both.
- Raw/adjusted prices and action records remain separate and auditable.
- EXP-DATA-003 rescales pre-boundary OHLC only in memory. It neutralizes the false
  economic loss but does not pretend to reconstruct official raw prices or relocate
  the observation to the official ex-date.

## 6. Missing/Stale Price Policy

A held position is marked at the last valid close until a new valid price exists;
the reopening gap is recognized on that later valid date. This is a named valuation
mark, not a zero-return imputation. No future price is used, no position is silently
dropped, and an untradeable exit remains held. Entry/exit without a contemporaneous
valid positive-volume price is recorded as `trade not filled`. Unfilled new capital
stays in cash rather than being redistributed.

## 7. Eligibility Policy

A signal-date constituent must have positive finite OHLC, pass OHLC invariants, have
at least 252 valid positive-volume observations, have at least 20 valid observations
in the last 25 benchmark sessions, and have a current non-carried, non-stale,
positive-volume mark. These are fixed data-integrity minima; no return outcome was
used to tune them. Full wording is in `research/PRICE_DATA_POLICY.md`.

## 8. Baseline Sensitivity — AS-IS vs RECONCILED

Period and strategy contract are unchanged from EXP-BASE-001: 2019-01 to 2025-05,
60-session diagnostic control rebalance, 12–1 momentum top-10, and 50 bps costs.

| Strategy | View | CAGR | Sharpe | Daily MaxDD | Worst day |
|---|---|---:|---:|---:|---:|
| BIST100 | AS-IS | 46.7605% | 1.483575 | -31.8154% | -9.7907% |
| BIST100 | RECONCILED | 46.7605% | 1.483575 | -31.8154% | -9.7907% |
| Equal-weight | AS-IS | 71.0986% | 2.002466 | -34.1110% | -9.7010% |
| Equal-weight | RECONCILED | 71.9603% | 2.019635 | -34.1110% | -9.7010% |
| 12–1 momentum | AS-IS | 105.3244% | 2.199967 | -39.4251% | -9.7911% |
| 12–1 momentum | RECONCILED | 108.3561% | 2.251078 | -39.4251% | -9.7911% |

| Strategy | Δ CAGR | Δ Sharpe | Δ Daily MaxDD | Δ Worst day |
|---|---:|---:|---:|---:|
| BIST100 | 0.0000 pp | 0.000000 | 0.0000 pp | 0.0000 pp |
| Equal-weight | +0.8617 pp | +0.017169 | 0.0000 pp | 0.0000 pp |
| 12–1 momentum | +3.0317 pp | +0.051112 | 0.0000 pp | 0.0000 pp |

The reconciled simulation recorded 142 last-valid-mark events for equal-weight and 21
for momentum, versus 105 and 12 AS-IS missing-mark events. No rebalance order was
unfilled in this period. The counts differ because the reconciled policy explicitly
recognizes positive-volume validity and logs every valuation mark. Results remain
diagnostic and cannot select any model, target, horizon or K.

## 9. Price Data Gate — PARTIAL

The extreme-return contamination is identified and safely neutralized inside
research; its measured baseline effect is bounded and does not alter drawdown/worst
day in these controls. However, the provider's raw history and action fields are not
authoritative, 683 volume bars remain unknown, exchange closure/suspension provenance
is absent, and MTRKS contains a material OHLC source error. Price-only exploratory
research may continue only with this policy and caveats. Model-ranking evidence is
not yet accepted as research-safe.

## 10. Remaining External Data Needs

1. Dated Borsa/KAP corporate-action master with split, bonus, dividend and rights
   terms plus official ex-dates.
2. Provider-independent raw OHLCV for the seven investigated securities and ideally
   the full research universe.
3. Official Borsa session, market-closure, suspension and reopening history.
4. Clarification or replacement for SASA's moving-price/zero-volume sequence and the
   MTRKS 2022-06-27 bad bar.

## 11. Files Changed/Created

- `research/contracts/exp_data_003_event_reconciliation.json`
- `research/exp_data_003.py`
- `research/PRICE_DATA_POLICY.md`
- `research/tests/test_exp_data_003.py`
- `research/results/EXP-DATA-003_extreme_events.csv`
- `research/results/EXP-DATA-003_ohlc_inconsistencies.csv`
- `research/results/EXP-DATA-003_zero_volume_detail.csv`
- `research/results/EXP-DATA-003_zero_volume_grouped.csv`
- `research/results/EXP-DATA-003_baseline_comparison.csv`
- `research/results/EXP-DATA-003_reconciled_trades.csv`
- `research/results/EXP-DATA-003_universe_equal_weight_reconciled_daily.csv`
- `research/results/EXP-DATA-003_momentum_12_1_top10_reconciled_daily.csv`
- `research/results/EXP-DATA-003_summary.json`
- `research/results/EXP-DATA-003_report.md`
- `research/EXPERIMENT_LEDGER.md`

No production price, model, portfolio or log file is changed.

## 12. Tests Run

- Standard-library unit discovery for all research tests.
- Reproducible full EXP-DATA-003 audit/baseline run.
- Production protected-file SHA-256 comparison.
- `git diff --check -- research`.

Verification result: **11/11 unit/integration tests PASS**, protected production hash comparison
**PASS (0 changed)**, and `git diff --check -- research` **PASS**.

## 13. Single Next Best Action

Obtain and freeze an official Borsa/KAP corporate-action plus trading-status calendar,
then rebuild the research-only price view against that authority and rerun the price
gate. Do not begin feature or model research before that reconciliation is complete.
