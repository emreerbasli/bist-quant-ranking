# EXP-DATA-006 — FUNDAMENTAL PIT, VINTAGE & ACCOUNTING INTEGRITY

## 1. Executive Summary

**FUNDAMENTAL DATA = PARTIAL.** The legacy dataset is retained unchanged and production
was not touched. All 2,646 observations across 88 tickers have real period labels and
locally retained İş Yatırım statement values, but all use a fixed 45/75-day availability
schedule. Exact KAP timestamp/date coverage inside the dataset is zero, first-versus-
restated vintage is unknown for every row, and consolidation basis is not stored.

The audit did not reduce all fundamental families to one global failure. Raw balance-
sheet points and explicitly identified YTD flow values support bounded **proxy**
research. Legacy derived ROE/ROA/EV-EBITDA/FCF-yield are not comparable across
quarters as named, and stored valuation ratios are not recomputed at each signal date.
No current fundamental cell reaches `VERIFIED`; positive proxy results cannot be
reported as verified alpha evidence.

## 2. Fundamental Data Provenance

| Item | Result |
|---|---:|
| Fundamental parquet files | 88 |
| Observations | 2,646 |
| Tickers | 88 |
| Period-end years | 2018–2026 |
| `isyatirim_pit` rows | 2,307 |
| `isyatirim_bank_pit` rows | 339 |
| Raw annual İş Yatırım JSON snapshots | 753 |
| Dated HisseTekil capital/market-value files | 88 |

Each row retains ticker, period, period end, inferred `XI_29`/`UFRS` group, source,
the annual raw-cache file and a filesystem modification timestamp. It does **not**
retain a KAP notification ID, source URL, actual download timestamp, disclosure date
or time, first/restated status, or consolidation basis. The raw JSON contains item
code/description and four period values; it is a current annual snapshot rather than
a filing-version archive.

Field provenance is mixed: statement items are raw API values, while total/net debt,
EBITDA, export ratio, market value and all stored ratios are builder-derived. The
row-level inventory is in `EXP-DATA-006_provenance.csv`.

## 3. PIT Coverage

| Period-end year | Total | Exact timestamp | Exact date | Approximate fixed lag | Unknown |
|---:|---:|---:|---:|---:|---:|
| 2018 | 246 | 0 | 0 | 246 | 0 |
| 2019 | 256 | 0 | 0 | 256 | 0 |
| 2020 | 282 | 0 | 0 | 282 | 0 |
| 2021 | 298 | 0 | 0 | 298 | 0 |
| 2022 | 342 | 0 | 0 | 342 | 0 |
| 2023 | 352 | 0 | 0 | 352 | 0 |
| 2024 | 351 | 0 | 0 | 351 | 0 |
| 2025 | 350 | 0 | 0 | 350 | 0 |
| 2026 | 169 | 0 | 0 | 169 | 0 |
| **Total** | **2,646** | **0 (0%)** | **0 (0%)** | **2,646 (100%)** | **0 (0%)** |

`gecerlilik_tarihi` is therefore classified as `APPROXIMATE_FIXED_LAG`, never as a
real disclosure date. Unknown is zero only because the proxy method itself is known;
the actual disclosure date remains absent.

Local recovery feasibility is limited. The 753 İş Yatırım JSON files have period
values but no notification metadata; 88 HisseTekil files have dated PD/capital but no
filing link; yfinance PIT cache is another 45-day proxy; `data/events.csv` is a
synthetic calendar. The existing KAP API script timed out during the controlled test.
Targeted official HTTP lookup can recover exact per-filing metadata, but there is no
local normalized index linking 2,646 rows to those filings.

## 4. Vintage / Restatement Findings

There are zero duplicate ticker-period rows locally, but this does not prove that only
one filing version existed. Each annual API cache is a single current snapshot; all
2,646 rows are `UNKNOWN_CURRENT_SNAPSHOT`, have no first-publication or correction
flag, and carry latest-overwrite risk.

The bounded KAP proof-of-concept found one exact financial report: ISCTR 2024Q3,
notification 1353364, published 2024-11-04 18:22:35, versus the local proxy date
2024-11-15. KAP reports YTD net profit of TRY 34,684,797,000; the local snapshot holds
TRY 34,684,755,378, a TRY -41,622 difference. The difference is small economically
but proves that the current snapshot is not guaranteed to reproduce the first filing.

SASA 2023Q3 and TUPRS 2026Q2 official pages demonstrated ticker/period support, but
were activity/general disclosures rather than the exact financial-report filings and
were correctly rejected as exact vintage evidence. Sources:
<https://www.kap.org.tr/tr/Bildirim/1353364>,
<https://www.kap.org.tr/tr/Bildirim/1208792>, and
<https://www.kap.org.tr/tr/Bildirim/1643171>.

## 5. Period Semantics — Single Quarter / YTD / TTM

The İş Yatırım request asks for periods 3, 6, 9 and 12 months. `value1…value4` flow
items are therefore cumulative YTD values, not four independent quarters:

- Q1: 685 rows, three-month YTD (also the first single quarter);
- Q2: 685 rows, six-month YTD;
- Q3: 612 rows, nine-month YTD;
- Q4: 664 rows, twelve-month/YTD annual.

Sales, EBITDA, operating profit, net income, CFO and FCF are stored without an
explicit YTD marker. No Q2/Q3/Q4 single-quarter decomposition and no true TTM series
exists. Missing preceding periods are not checked because decomposition is never
attempted. Same-period YoY on explicit YTD values can be meaningful; QoQ or cross-
quarter level comparisons cannot use the legacy columns directly.

Balance-sheet fields are period-end point-in-time values. However their disclosure
timing and vintage remain proxy/unknown. Legacy `roe`, `roa`, `ev_ebitda` and
`fcf_verim` mix YTD flows with point-in-time or signal-date denominators and are
classified `INVALID` as general cross-quarter features.

## 6. TFRS29 / Inflation Accounting Risks

The dataset has 848 mechanically flagged TFRS29 rows: 78 in 2023Q4, 311 in 2024,
310 in 2025 and 149 in 2026. The flag is assigned solely from year/quarter; no filing-
level nominal/restated basis, comparative-column vintage or restatement metadata is
retained.

Consequently revenue, operating profit, net income, margins, ROE/ROA and growth can
mix original and inflation-restated comparative bases. The V4 `reel_eps` path divides
current net income by CPI before comparison even when the statement may already be
TFRS29-adjusted. This is a concrete double-inflation-adjustment risk. No new real
feature was produced in this experiment.

## 7. Historical Capital / Market Value

The builder contains a risky fallback: historical price × the final available capital
row. The earlier static audit identified 190 potentially exposed records. Re-running
the exact data path changes the interpretation:

- 190 records have no historical HisseTekil PD;
- all 190 also lack a historical price on the proxy date, mostly because the periods
  precede listing;
- their later capital rows exist, but the multiplication branch cannot execute;
- stored market value and related valuation fields remain missing;
- **confirmed future/latest-capital usage: 0 rows**.

Thus the current dataset has 190 missing/pre-listing valuation observations, not 190
proven future-capital-contaminated observations. The dangerous fallback code remains
and must not be reused in research, but the measured stored-data contamination is zero.
Affected fields if the branch ever executes are market cap, P/B, EV, EV/EBITDA and
FCF yield.

## 8. Signal-Date Valuation

For all 2,646 records, market value is calculated once at the fixed proxy date. The
loader then carries P/B, EV/EBITDA and FCF yield forward until the next statement; it
does not recompute them from the price and capital known on each signal date.

Therefore dynamic signal-date valuation coverage is **0/2,646**. Even the 2,456 rows
with market value are only proxy-date snapshots. Existing stored value ratios are not
admissible for general signal-date value research. A later research-only builder must
join the latest-known financial statement, capital known on the signal date and the
DATA-005-safe signal-date price; this experiment does not build it.

## 9. Sector / Accounting Applicability

The data contains 78 industrial/holding-style and 10 UFRS financial tickers. The UFRS
group includes banks and insurers; common item codes have sector-specific meanings
(for example `3AA` is loan interest for banks but earned premium for insurers).

| Metric | Industrial | Bank/insurance |
|---|---|---|
| ROIC | Potential after semantic repair | Not applicable under current schema |
| Net debt/EBITDA | Potential after semantic repair | Not applicable |
| FCF | Potential with explicit YTD semantics | Not applicable |
| EBITDA margin | Potential after decomposition | Not applicable |
| ROE | Potential after period repair | Sector-specific definition required |
| P/B | Potential with signal-date rebuild | Sector-specific definition required |

Missing financial-sector EBITDA, debt or FCF is structural and must not be zero-
imputed. Insurance must not inherit bank loan/NPL interpretations merely because both
use the UFRS group.

## 10. Missingness Semantics

The static code audit found 34 locations that convert missing values to zero, a neutral
z-score or a hard-coded fallback: 3 in `fundamental_pit.py`, 13 in
`temel_analiz.py`, 7 in the V3 ranking path and 11 in the V4 path. Examples include
missing factor z-scores becoming zero, missing net debt becoming zero, and missing net
income/assets becoming zero in reel-EPS calculation.

These are model/pipeline semantics, not evidence of an economic zero. DATA-006 does
not optimize imputation. Its safe contract is: preserve missing raw data; record
applicability; fit any later imputation inside training folds only; never reinterpret
structurally unavailable bank/insurance fields as zero.

## 11. VERIFIED / PROXY / INVALID / MISSING Coverage

The field × ticker × period audit covers 52,920 cells across 20 audited fields:

| Status | Cells | Share |
|---|---:|---:|
| VERIFIED | 0 | 0.00% |
| PROXY / UNVERIFIED | 36,056 | 68.13% |
| INVALID | 11,541 | 21.81% |
| MISSING | 5,323 | 10.06% |

`PROXY` primarily covers raw YTD flows, balance-sheet points and non-fallback market
values whose PIT/vintage is unverified. `INVALID` covers mixed-semantics derived
profitability/yield ratios and the mechanical TFRS29 flag. `MISSING` preserves true or
structural absence, including the 190 pre-listing valuation rows.

## 12. Feature-Family Readiness

| Family | Row coverage | Tickers | Years | Decision |
|---|---:|---:|---:|---|
| Quality | 2,646 (100%) | 88 | 9 | PARTIAL |
| Profitability | 2,646 (100%) | 88 | 9 | PARTIAL |
| Cash flow | 2,306 (87.15%) | 78 | 9 | PARTIAL |
| Balance sheet | 2,646 (100%) | 88 | 9 | PARTIAL |
| Earnings | 2,646 (100%) | 88 | 9 | PARTIAL |
| Value | 2,456 (92.82%) | 88 | 9 | FAIL for current stored ratios |

Required readiness decisions:

- **QUALITY FEATURES: PARTIAL** — raw inputs exist; legacy ROE/ROA not accepted.
- **CASH-FLOW FEATURES: PARTIAL** — industrial YTD fields only, explicit semantics.
- **BALANCE-SHEET FEATURES: PARTIAL** — period-end raw points, proxy PIT/vintage.
- **EARNINGS FEATURES: PARTIAL** — explicit same-period YTD comparisons only.
- **VALUE FEATURES: NO** — current carried ratios are not signal-date values.
- **FULL FUNDAMENTAL ML: NO** — zero exact PIT coverage and unknown vintages.

`PARTIAL` authorizes bounded proxy/sensitivity research only; it does not authorize a
verified alpha claim or production use.

## 13. Safe Research Subsets

The mechanically safer subsets are:

1. Raw point-in-time balance values: equity for 2,646 rows; assets/debt/cash for 2,307
   non-financial-style rows. Use only with the fixed-lag/vintage caveat.
2. Explicit YTD earnings: sales, operating profit and net income for 2,646 rows. Only
   same-period YoY or other like-for-like YTD comparisons are semantically admissible.
3. Explicit YTD cash flow: CFO and FCF for 2,306 rows/78 industrial-style tickers;
   financial-sector absence stays missing.
4. Non-TFRS29 industrial rows: 1,459 observations avoid the mechanical TFRS29 flag,
   but still do not solve PIT/vintage provenance.

There is no multi-period `VERIFIED` subset yet. The single exact ISCTR recovery proves
feasibility, not sample adequacy. Restricting to older, long-listed industrial firms
would introduce selection/survivorship bias and cannot be generalized to all BIST or
all years.

## 14. External Data Needs

To move from proxy to verified research, the missing source is a filing-level KAP
index containing notification ID, exact publication timestamp, ticker, period,
consolidation basis, original/correction relationship and first-published values. The
current local caches cannot reconstruct these fields.

Targeted KAP HTTP lookup is accurate per filing, but scaling it across 2,646 rows plus
corrections/restatements is a medium/high-complexity data-engineering project. It
would materially improve PIT and vintage safety, especially for earnings and TFRS29
comparisons. No paid provider, package, new API integration or bulk scrape was started.
Historical capital is not the immediate external-data blocker for the 190 observations:
they are pre-listing/no-price rows and should remain unavailable.

## 15. Tests

DATA-006 tests: **6/6 PASS**.

1. PIT classification consistency.
2. Future/restated vintage leakage sanity and official/local value mismatch.
3. YTD/single-quarter/point-in-time semantics sanity.
4. Historical-capital fallback detection, including the 190-vs-0 distinction.
5. Signal-date valuation consistency.
6. Missing is not silently classified as verified/economic zero.

Python syntax compilation passed. Production hash integrity is reported separately.

## 16. Production Integrity

`research/verify_production_hashes.py` reports **PASS, 0 changed protected files**.
Production fundamental parquet files, caches, loaders, feature code, models and
portfolios were not overwritten. All audit code, contracts and outputs are isolated
under `research/`.

## 17. FUNDAMENTAL DATA GATE

**FUNDAMENTAL DATA = PARTIAL**

This is not a global permission for fundamental ML. Semantically explicit raw balance,
earnings and cash-flow subsets may proceed only as `PROXY / UNVERIFIED` exploration
with subset-bias disclosure. Current value ratios, legacy mixed-period derived ratios,
TFRS29-sensitive growth and full fundamental ML remain closed. No fundamental result
may be treated as verified until real disclosure/vintage coverage exists.

Family status is preserved as stated in Section 12 rather than collapsed into one
global failure.

## 18. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Remain in Phase A and run a bounded KAP disclosure/vintage recovery pilot on a
predeclared representative sample of industrial, bank and insurance filings across
pre/post-TFRS29 years. Measure exact match rate, first-versus-restated recovery and
consolidation mapping before authorizing any 2,646-row reconstruction. Do not start a
bulk scrape, macro audit, target research, feature discovery or model training
automatically.
