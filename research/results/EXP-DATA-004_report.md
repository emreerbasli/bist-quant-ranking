# EXP-DATA-004 — AUTHORITATIVE PRICE TIMELINE

## 1. Executive Summary

**PRICE DATA = PARTIAL.** A minimum viable, research-only price timeline was built
for 89/89 requested series without changing production. It separates provider-labelled
raw OHLC, provider-adjusted OHLC and a forward-chained research OHLC. The five known
early corporate-action adjustments are quarantined from their provider distortion date
through the session before the official ex-date, then reconnected only on the official
economic ex-date.

All five reference regressions pass. Across 159,229 rows, 157,305 are
`PROVIDER_ONLY`, 5 official-action sessions are `RECONSTRUCTED`, and 1,919 are
`UNRESOLVED`; zero rows qualify as `VERIFIED` because there is no provider-independent
raw quote archive. Known look-ahead is controlled, but target/model-selection evidence
is not accepted while the overwhelming majority remains provider-only and official
trading-status/action coverage is incomplete.

## 2. Source Inventory

| Source | Coverage | Event coverage | Authority | PIT suitability |
|---|---|---|---|---|
| `data/raw/*.parquet` | Mostly 2018-01-01–2026-09-15; 88 equities | Provider dividend/split fields | Provider, auto-adjusted | FAIL for action timing; five confirmed early adjustments |
| `research/data/provider_snapshot` | 2018-01-01–2026-09-15; 89/89 series | Provider-labelled raw/adjusted OHLCV, dividends, splits | Provider | PARTIAL; “raw” repeats all five early breaks |
| DATA-004 official event contract | Five tickers, 2024-08 to 2026-08 | Bonus and rights issues; announcement/effective/ex separated | Curated official KAP | PASS for five effective/ex dates; announcement captured for 3/5 |
| `data/events.csv` | 2018–2026 | Synthetic financial-report dates only | Derived | FAIL for corporate actions |
| `data/kap_vbts_arsiv.csv` | Header only | None | Intended official cache | FAIL; zero records |
| KAP HTML/API experiment scripts | Ad hoc | Page-fetch experiments | Official pages, unnormalized | FAIL as a retained master |
| Fundamental/KAP scraper caches | Quarterly fundamentals | No price actions/status | Provider/derived | Not applicable |
| Listing/delist/ticker/merger/status master | Missing | First trade, delist, rename, merger, demerger, suspension | Missing | FAIL |

The snapshot contains 443 provider dividend rows and 75 provider split rows. Raw and
adjusted close differ on 109,791 rows. These fields are retained as evidence, but the
provider is not treated as an authority for effective dates.

## 3. Corporate Action Date Semantics

- `announcement_date`: when terms became public. It determines information
  availability, not the price-adjustment date.
- `effective_date`: when the entitlement becomes economically/legal effective.
- `ex_date`: first trading session on the ex-action basis. This is the only date used
  to reconnect the research total-return chain.
- `provider_adjusted_date`: observed provider discontinuity. When earlier than the
  ex-date it starts an `UNRESOLVED` quarantine; it never starts an economic action.

The research chain is calculated forward. A future event never rescales already
published past research prices. When an early provider break is detected, the unsafe
window remains unavailable; after the official ex-date the cumulative chain resumes
using the verified bonus/rights terms.

## 4. Five Known Error Regression Tests

| Symbol | Provider date | Announcement | Official ex-date | Provider return | Quarantined sessions | Ex-date economic return | Result |
|---|---|---|---|---:|---:|---:|---|
| HEKTS | 2024-09-09 | 2024-09-16 | 2024-09-18 | -64.85% | 7 | -17.78% | PASS |
| BSOKE | 2024-12-02 | 2024-12-09 | 2024-12-10 | -74.22% | 6 | -10.01% | PASS |
| CCOLA | 2024-08-01 | Not captured | 2024-08-13 | -90.75% | 8 | +0.31% | PASS |
| KBORU | 2025-01-02 | Not captured | 2025-06-04 | -83.07% | 104 | +4.17% | PASS |
| CVKMD | 2026-08-03 | 2026-08-04 | 2026-08-05 | -61.88% | 2 | -1.99% | PASS |

For every event, the provider-date window is `UNRESOLVED`, the official ex-date is
`RECONSTRUCTED`, and the number of pre-provider rows rewritten by the future action is
zero. Full t-2/t-1/t/t+1/t+2 raw, adjusted and research values are in
`EXP-DATA-004_regression_windows.csv`.

The larger HEKTS/BSOKE ex-date returns are the cumulative observed economic movements
over their quarantined gaps, not a reclassification as provider crashes. No missing
daily path is invented.

## 5. SASA Investigation

Between 2025 and 2026, SASA has 140 zero-volume rows in the fresh provider snapshot:

- 134 have a nonzero raw close return;
- 137 have nonzero intraday high-low range;
- raw and adjusted close are identical on the affected rows; the adjustment ratio has
  one unique rounded value;
- no affected row reports a dividend or split.

This rules against a corporate-action adjustment artifact within the available
provider fields. It is most consistent with a provider volume-field defect, but no
official independent volume source is present. Classification:
`UNRESOLVED_PROVIDER_VOLUME_FIELD_DEFECT`. No SASA-specific repair is applied; the
generic eligibility rule excludes these rows from trading and signal formation.

## 6. Trading Status Coverage

| Trading status | Rows | Treatment |
|---|---:|---|
| TRADED_PROVIDER | 157,437 | Tradable only when price quality is also eligible |
| UNRESOLVED_MISSING_VOLUME | 144 | Not tradable; no volume fabrication |
| UNRESOLVED_NO_TRADE_OR_STALE | 1,646 | Not labelled suspension; last-valid mark policy |
| UNRESOLVED_BAD_OHLC | 2 | Excluded |

No official historical status feed exists locally. Therefore no row receives a fake
`SUSPENSION` label. Missing volume, no-trade/stale and bad OHLC remain explicit.

## 7. Canonical Research Price View

Full build result:

| Check | Result |
|---|---:|
| Requested series | 89 |
| Built series | 89 |
| Total rows | 159,229 |
| Global date range | 2018-01-01–2026-09-15 |
| Duplicate ticker-date rows | 0 |
| Monotonic date order | 89/89 PASS |

Each parquet contains provider-labelled raw OHLC, provider-adjusted OHLC,
forward-chained research OHLC, volume, provider actions, economic return, price
quality, corporate-action flag, trading status, explicit `trading_eligible`, and source.
The view lives only under `research/data/price_view_data004`.

`trading_eligible` is true only for positive finite research OHLC with eligible quality
and `TRADED_PROVIDER` status. Full signal-date eligibility still applies the fixed
252-history and 20-of-25 recent-valid requirements in `PRICE_DATA_POLICY.md`.

## 8. Quality Coverage

| Price quality | Rows | Share | Meaning |
|---|---:|---:|---|
| VERIFIED | 0 | 0.000% | No independent authoritative raw quote archive exists |
| RECONSTRUCTED | 5 | 0.003% | Official KAP action applied on official ex-date |
| PROVIDER_ONLY | 157,305 | 98.792% | Mechanically usable provider observation, not independently verified |
| UNRESOLVED | 1,919 | 1.205% | Quarantined or failed price/volume/status control |

Absence of independent provider verification is not the same as known systematic
corruption. `PROVIDER_ONLY` records are explicitly unverified; confirmed systematic
early-action corruption is separately quarantined as `UNRESOLVED`.

## 9. Remaining Unresolved Events

- 127 positive-volume sessions are quarantined because the provider adjusted five
  actions before the official ex-date.
- 144 rows have moving/ranged prices but missing volume.
- 1,646 rows are zero-volume no-trade/stale candidates with no official status label.
- 2 rows fail OHLC invariants.
- Announcement dates are not captured for CCOLA and KBORU, although official ex-dates
  and action terms are captured.
- Other provider-reported dividends/splits are not promoted to authoritative status
  without KAP/Borsa reconciliation.

No unresolved event is guessed or corrected. Ineligible observations are unavailable
to signal/execution and use last-valid-mark logic only when already held.

## 10. Baseline Sensitivity

All results use the unchanged 2019-01–2025-05 diagnostic contract and 50 bps cost.
Turnover is summed two-sided rebalance notional, excluding terminal liquidation.

| Strategy | View | Cumulative return | CAGR | Sharpe | Daily MaxDD | Worst day | Turnover | Unavailable | Unfilled |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BIST100 | AS-IS | 674.896% | 46.7605% | 1.483575 | -31.8154% | -9.7907% | 2.000 | 0 | 0 |
| BIST100 | DATA-003 | 674.896% | 46.7605% | 1.483575 | -31.8154% | -9.7907% | 2.000 | 0 | 0 |
| BIST100 | DATA-004 | 674.896% | 46.7605% | 1.483575 | -31.8154% | -9.7907% | 2.000 | 0 | 0 |
| Equal-weight | AS-IS | 1,657.544% | 71.0986% | 2.002466 | -34.1110% | -9.7010% | 4.937 | 105 | 0 |
| Equal-weight | DATA-003 | 1,705.307% | 71.9603% | 2.019636 | -34.1110% | -9.7010% | 4.913 | 142 | 0 |
| Equal-weight | DATA-004 | 1,704.388% | 71.9439% | 2.019808 | -34.1110% | -9.7010% | 4.898 | 163 | 0 |
| 12–1 momentum | AS-IS | 4,551.463% | 105.3244% | 2.199967 | -39.4251% | -9.7911% | 20.261 | 12 | 0 |
| 12–1 momentum | DATA-003 | 4,929.969% | 108.3561% | 2.251078 | -39.4251% | -9.7911% | 20.203 | 21 | 0 |
| 12–1 momentum | DATA-004 | 5,116.413% | 109.7818% | 2.270583 | -39.4251% | -9.7911% | 20.016 | 27 | 0 |

Relative to DATA-003, DATA-004 changes equal-weight CAGR by -0.016 percentage point
and momentum CAGR by +1.426 percentage points. Daily MaxDD and worst day remain
unchanged at shown precision. These are data diagnostics, not selection evidence.

## 11. Tests

- Controlled pre-full-build equivalence: five event windows, vectorized versus
  row-wise reference — **PASS**.
- Syntax/import compilation — **PASS**.
- Five corporate-action regressions — **5/5 PASS**.
- Official effective/ex-date alignment — **PASS**.
- Future action does not rewrite pre-anomaly prices — **PASS**.
- Duplicate/date ordering, quality-count consistency and eligibility — **PASS**.
- SASA generic exclusion and retained-mark behavior — **PASS**.
- Daily NAV compatibility — **PASS**.
- Full standard-library suite — **19/19 PASS**.

## 12. Production Integrity

Protected production hash comparison: **PASS, 0 changes**. All snapshots, views,
contracts, code, tests and reports remain under `research/`. No production price file,
model, portfolio or trading log was written.

## 13. External Data Needs

| Missing source | Coverage needed | Expected impact | Cost/complexity |
|---|---|---|---|
| Official KAP/Borsa action master | 2018 onward, full research universe | Detect remaining non-extreme date errors and promote action rows | Medium; bounded archive normalization may be possible |
| Official Borsa trading-status calendar | Closures, suspensions, resumptions | Resolve 1,646 no-trade/stale rows | Medium/high |
| Independent raw OHLCV archive | Full universe and study period | Verify provider raw labels and SASA volume | High or paid provider/API; not started |
| Listing/delist/ticker/merger history | Full historical universe | Identity- and survivorship-safe timeline | Medium/high |

Per the stop rule, no paid source, package, large API integration or separate long data
engineering project was started.

## 14. PRICE DATA Gate — PARTIAL

Known systematic corporate-action look-ahead is controlled, five of five regressions
pass, future actions do not rewrite earlier research prices, and unresolved coverage is
measured and excluded. The 98.792% `PROVIDER_ONLY` share is an independent-verification
limitation, not itself proof of systematic corruption.

The gate remains PARTIAL—not FAIL—because price-only exploration is mechanically safe
under quarantine/eligibility controls and baseline sensitivity is bounded. It is not
PASS because incomplete official action/status coverage means unresolved corruption
could still affect target or model ranking. Target generation and model selection remain
blocked.

## 15. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Perform a bounded official KAP/Borsa reconciliation of provider-reported actions and
all remaining discontinuous returns for the existing universe and study period, then
rerun the PRICE DATA gate. Do not start 20/40/60 targets or model research while the
gate remains PARTIAL.
