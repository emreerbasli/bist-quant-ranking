# EXP-DATA-007 — KAP DISCLOSURE & VINTAGE RECOVERY PILOT

## 1. Executive Summary

**KAP VINTAGE RECOVERY = GO** under the thresholds locked before retrieval. The
unchanged 30-observation pilot recovered 30 exact mappings, 30 exact announcement
timestamps, 30 first publications, 30 consolidation bases and 30 accounting-period
classifications. False matches and completely unrecoverable observations were both
zero. This is a gate for a separate, controlled reconstruction experiment; it is not
permission to start the 2,646-row bulk job or model/feature research.

The result is not globally clean accounting data. TFRS29 status is resolved for only
20/30 observations (66.67%), separately proven restated-comparative columns are
0/30, and several local-versus-official CFO/FCF/operating-profit differences are
material. These remain semantic/vintage risks rather than being hidden as unit errors.

## 2. Locked Pilot Design

The pre-result contract remained unchanged: 30 observations, ten tickers, three
periods per ticker, with non-financial, bank and insurance cases; large/medium/smaller
names; pre/post-TFRS29 periods; and Q1/Q2/Q3/Q4 statement types. No observation was
added, removed or replaced. The mapping and gate thresholds in
`research/contracts/exp_data_007_pilot.json` were not relaxed.

The official KAP POST endpoint was queried in annual windows. The original broad
2022–2026 window returned HTTP 500; the execution-only annual split did not change
the sample, candidate key, preferred accounting basis or first-publication rule.

## 3. Official KAP Mapping

The exact key was ticker + report year + KAP period + exact `Finansal Rapor` subject,
followed by detail-page proof of the locked consolidation basis. The pilot produced
43 exact-key notification candidates. Thirty-one matched the locked basis and twelve
opposite-basis bank/insurance candidates were retained as diagnostics but rejected.

Mapping was exact for 30/30 observations (100%). Mapping confidence is recorded
separately and is `HIGH` only for proven exact mappings. No first-search-result or
best-value matching was used. The ISCTR 2024Q3 regression recovered notification
1353364, timestamp `04.11.2024 18:22:35`, non-consolidated basis and official YTD net
income of TRY 34,684,797,000.

## 4. Disclosure Timing Recovery

Exact timestamp was recovered for 30/30 (100%). The mutually exclusive
`EXACT_DATE`-only bucket is 0/30 because all recovered records contain seconds-level
timestamps; every timestamp also supplies the calendar date. Availability is marked
for next-session handling, but no trading or label experiment was started.

## 5. First Publication / Corrected / Restatement

First publication was recovered for 30/30. Lineage was resolved for 30/30: 29 have a
proven first report with no observed correction in the bounded listing history; one
has a corrected chain. AEFES 2022Q3 is the regression case:

- notification 1076388, `DUZELTILEN` (original being corrected);
- notification 1076969, `DUZENLENEN` (correcting report);
- ordered by official publication timestamp and kept on the same preferred basis.

The local snapshot classification is field-specific. Where first and latest official
values are equal, a local mismatch cannot be called a later-vintage match; it remains
`DIFFERS_FROM_FIRST_AND_LATEST_EQUAL`. No observation was forced into `LATEST_ONLY`.

## 6. Consolidated vs Solo

The locked basis was consolidated for non-financial firms and non-consolidated for
banks and insurers. Basis was resolved for 30/30. Bank and insurer searches produced
12 opposite-basis candidates in addition to 12 selected solo candidates. Those
alternatives were rejected without looking at which values resembled the local data,
preventing value-based cherry-picking.

## 7. Presentation Unit Normalization

The parser now reads every statement-level `Sunum Para Birimi` row and normalizes
recognized `TL`, `1.000 TL` and `1.000.000 TL` display units to base TRY. Candidate
pages contained 13 TL, 27 thousand-TL and three million-TL presentations. All 43
candidate pages had internally consistent recognized units; selected-observation unit
coverage is 30/30.

Unknown, unrecognized or mixed units fail closed: normalized values remain missing
and the page is marked `UNKNOWN` or `INVALID_MIXED_OR_UNKNOWN`. There is no
ticker-specific THYAO exception. Regression tests cover million-TL, thousand-TL,
plain-TL, mixed-unit rejection and equivalent economic values across scales. The
pre-fix materiality calculation was discarded; no fake `%99,999,900` result remains.

## 8. Accounting Period Semantics

Balance-sheet values are classified as point-in-time. Flow semantics are Q1 single
quarter, Q2 YTD 6M, Q3 YTD 9M and Q4 annual. Classification is resolved for 30/30.
Q2/Q3/Q4 single-quarter values were not derived because same-basis, comparable,
first-vintage predecessor availability was not jointly proven. Missing remains null,
never economic zero.

## 9. TFRS29 Findings

Status is resolved for 20/30: ten `PRE_TFRS29`, four bank observations under the
local BDDK-not-applied contract, and six post-TFRS29 pages with an explicit TFRS/TMS29
mention. Ten post-period observations remain `UNKNOWN`.

For the six confirmed post-TFRS29 observations, applying V4's additional manual CPI
division is classified **DOUBLE-ADJUSTMENT RISK**. Pre-TFRS29 and the four locked bank
cases are `SAFE` for this specific double-adjustment question; the remaining ten are
`UNKNOWN`. Published comparative columns are retained, but none is relabelled as a
separately proven restated comparative. `restated_comparative_net_income_try` therefore
remains null for all 30, with the limitation recorded explicitly.

## 10. Local vs Official Vintage Differences

All figures below use base TRY after the unit fix. They describe the local current
snapshot versus first official publication; they are not performance thresholds.

| Field | Comparable n | Median absolute difference (TRY) | Median absolute relative difference | Maximum absolute relative difference |
|---|---:|---:|---:|---:|
| Revenue | 18 | 632,462,000 | 3.899% | 44.379% |
| Net income | 30 | 525 | 0.000060% | 44.379% |
| Equity | 30 | 0 | 0.000% | 44.379% |
| CFO | 18 | 570,869,500 | 33.294% | 1,689.066% |
| FCF | 18 | 303,248,500 | 33.294% | 2,010.621% |
| Operating profit | 24 | 3,075,063,000 | 38.328% | 43,030.327% |

The recurring 44.379% group is consistent with a later inflation-restated local
snapshot versus the first publication and is not a display-unit artefact. The extreme
CFO/FCF and operating-profit cases show that local field definitions and/or cumulative
accounting presentation are not automatically interchangeable with the selected KAP
taxonomy rows. EBITDA has 0/30 official matches under the conservative taxonomy map;
it was not substituted with an approximate line. Investing cash flow has 30/30
official values but no direct local comparison field.

## 11. Recovery Coverage

| Metric | Count | Percent |
|---|---:|---:|
| Total pilot observations | 30 | 100.00% |
| Exact mapped | 30 | 100.00% |
| Exact timestamp | 30 | 100.00% |
| Exact-date only | 0 | 0.00% |
| First publication | 30 | 100.00% |
| Restatement lineage resolved | 30 | 100.00% |
| Consolidation basis resolved | 30 | 100.00% |
| Accounting semantics resolved | 30 | 100.00% |
| TFRS29 status resolved | 20 | 66.67% |
| Presentation unit resolved | 30 | 100.00% |
| Completely unresolved | 0 | 0.00% |
| False match | 0 | 0.00% |

Official field coverage is revenue 18/30, operating profit 24/30, EBITDA 0/30, net
income 30/30, equity 30/30, CFO 24/30, investing cash flow 30/30 and derived FCF
24/30. Structural sector differences remain missing.

## 12. Failure Modes

Three material incidents are retained even though the final cached run succeeded:

1. broad multi-year list query returned HTTP 500; resolved by bounded annual windows;
2. presentation-unit mis-scaling invalidated preliminary materiality; resolved by the
   general statement-level parser and regression tests;
3. repeated uncached runs encountered HTTP 429; mitigated by deterministic list/detail
   caches and bounded 0/5/15/30-second backoff, with no source substitution.

Remaining failure modes are ambiguous/mixed future unit metadata, KAP schema change,
rate limiting, large-page parse cost, incomplete TFRS29 comparative lineage, and
field-definition incompatibility. These fail closed or remain explicitly unknown.

## 13. Automation Feasibility

| Component | Assessment |
|---|---|
| A. Search/list query | YES — annual official queries and deterministic cache |
| B. Correct notification mapping | YES in pilot — exact key plus locked basis; opposite basis rejected |
| C. Detail-page parsing | YES WITH CONTROLS — large HTML/XBRL pages and schema risk |
| D. Original/corrected lineage | YES in pilot — duplicate chain retained; only one positive correction case |
| E. Unit normalization | YES WITH FAIL-CLOSED RULE — three observed scales normalized |
| F. Accounting semantics | PARTIAL — period class resolved; field comparability/TFRS29 not fully resolved |
| G. Request/runtime complexity | PARTIAL — technically feasible, operationally rate-sensitive |

A full 88-ticker, nine-year run is estimated at about 792 annual list requests plus
2,646–5,292 candidate detail requests: approximately 3,438–6,084 logical requests
before retries. Expected mapping coverage from this pilot is high, but 100% must not be
extrapolated as a guarantee. False-match risk is controlled by rejection, at the cost
of possible unresolved rows. Staged batches, persistent content-addressed hashes,
resume-safe cache reuse, request de-duplication and bounded backoff are required.

The final reproducibility run made 83 logical reads with 83 cache hits and zero network
attempts. No new provider, paid source or package is required for a controlled next
experiment. Bulk reconstruction was not started.

## 14. Feature-Family Research Value

| Family | Potential | Reason |
|---|---|---|
| Quality | MEDIUM | Equity/net-income timing recoverable; ratios and sector definitions still need safe construction |
| Cash flow | MEDIUM | Industrial coverage exists, but large semantic/local differences and structural financial-sector gaps remain |
| Balance sheet | HIGH | Point-in-time equity recovered 30/30 with exact disclosure timing and basis |
| Earnings | MEDIUM | Net income is strong; revenue/operating coverage and TFRS29 comparability are incomplete |
| Value | LOW | Disclosure recovery alone does not solve signal-date market cap, capital history or corporate-action alignment |

## 15. GO / PARTIAL / NO-GO

Every locked bulk gate passed: mapping 100% ≥95%, first publication 100% ≥70%, exact
date/timestamp 100% ≥80%, accounting semantics 100% ≥80%, false matches 0% ≤2%,
unrecoverable 0% ≤10%, and the existing implementation completed a cache-only
reproducibility run. Therefore **KAP VINTAGE RECOVERY = GO**.

`GO` means only that a separately approved, staged KAP reconstruction experiment is
methodologically justified. Accounting-field usability remains PARTIAL, TFRS29 is
PARTIAL, and production/model use is not authorized.

## 16. External Data Needs

No external paid provider, new package or alternate API is required to attempt the
official KAP bulk reconstruction. Separate evidence is still needed for explicit
restated-comparative lineage when the page does not prove it, historical signal-date
capital/market value, complete corporate-action alignment, and broader TFRS29 basis
validation. Those gaps must not be filled by silent inference.

## 17. Tests

**11/11 PASS.** Covered: ISCTR 2024Q3 official regression, AEFES original→corrected
chain, THYAO million-TL scaling, thousand-TL and plain-TL normalization, mixed-unit
rejection, same economic field across units, consolidated/solo discrimination,
duplicate handling, timestamp/date classification, YTD semantics, TFRS29 risk,
missing ≠ zero, pilot scope and production hashes. Standalone production integrity
verification also returned `PASS 0`.

## 18. Production Integrity

All code, cache and outputs are under `research/`. The experiment did not overwrite
production fundamentals, models, portfolios, signals or schedulers. The production
hash verifier found zero protected-file changes attributable to this research package.
The reproducibility manifest contains code/contract hashes plus hashes for all 40 list
and 43 detail cache files.

## 19. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

The single next action is a new, separately gated **staged bulk KAP disclosure and
first-vintage reconstruction experiment for the 2,646 legacy observations**, using the
now-tested exact mapping, preferred-basis, lineage, fail-closed unit, cache and retry
contracts. It must first lock batching/runtime limits and preserve unresolved rows; it
must not start target, feature, model, K, portfolio or macro research. EXP-DATA-007
stops here.
