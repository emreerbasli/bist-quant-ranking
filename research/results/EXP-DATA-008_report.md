# EXP-DATA-008 — STAGED KAP PIT/VINTAGE BULK RECONSTRUCTION

## 1. Executive Summary

**KAP BULK PIT/VINTAGE = PARTIAL.** The locked 2,646-observation universe and
methodology were preserved. The three-ticker canary completed successfully: 80/87
observations were recovered with exact timestamps, first-publication values, preferred
consolidation basis, resolved units and period semantics; seven pre-listing/early AGROT
records were unrecoverable. The canary had zero ambiguous mappings, zero unit failures,
zero basis mismatches, zero parse errors and zero HTTP 429 responses.

The ten-ticker medium batch then crossed the locked stop condition on the eleventh HTTP
429 response. Execution stopped immediately. No threshold, batch boundary, mapping
rule or parser rule was relaxed, and no full progression was attempted. The remaining
2,559 records are `SOURCE_ERROR / NOT_PROCESSED_RATE_LIMIT_STOP`; they are not 2,559
failed KAP mappings.

## 2. Locked Bulk Contract

`research/contracts/exp_data_008_bulk.json` was written before the first bulk request.
It fixes the official source, exact universe hash, mapping key, consolidation policy,
first-publication rule, unit handling, accounting semantics, TFRS29 policy, comparison
thresholds, batch boundaries, retry schedule, cache/checkpoint rules and stop criteria.

The input hash is `8b78533e3ee6f25f22686da9d77549fa2ddefdfd5168a77c2601c07bb9732a66`.
The contract was not changed after seeing recovery or HTTP results.

## 3. Input Universe

The canonical universe contains exactly 2,646 unique legacy IDs from 88 production
fundamental parquet files. No row was removed, substituted or added. Verbatim legacy
ticker text—including existing leading whitespace in several files—is retained in the
legacy ID. Whitespace is stripped only for the official KAP query key.

The final research table still contains all 2,646 IDs: 87 processed canary records and
2,559 explicitly unprocessed records after the rate-limit stop.

## 4. Batch Execution

The locked plan was 3-ticker canary, 10-ticker medium batch, then deterministic
15-ticker chunks.

| Batch | Tickers | Observations completed | Outcome |
|---|---|---:|---|
| 1 — canary | AEFES, AGHOL, AGROT | 87 | CONTINUE |
| 2 — medium | Next ten alphabetic tickers | 0 ticker checkpoints | STOP — HTTP 429 limit |
| Remaining | Not started | 0 | Prohibited after stop |

Canary metrics were 109 logical requests, 101 network attempts, eight pilot-cache seed
hits, zero 429s and zero retries. Batch 2 successfully persisted additional responses
before stopping, but the original exception occurred before its metrics were serialized.
The exact aborted-batch request/retry total is therefore unavailable; the observed 429
count is at least eleven. The logging order has been fixed for any future run.

## 5. Cache / Rate Limit

At stop, the EXP-DATA-008 cache contained 34 annual list responses and 104 detail
responses, approximately 449.53 MB. Every cached official response has a SHA-256
sidecar; final manifest hashes are also recorded. Completed ticker checkpoints are
resume-safe, and an incomplete ticker can reuse its validated response cache.

The canary cache-only rerun was byte-equivalent for every EXP-DATA-008 result artefact.
No request parallelism was used. Uncached requests used a 0.35-second minimum interval
and bounded 0/5/15/30-second retries. The medium batch nevertheless exceeded the
locked maximum of ten 429s, so continued access was not considered safe.

## 6. Mapping Quality

The unchanged key was normalized ticker + statement year + KAP period + exact
`Finansal Rapor` subject + predefined consolidation basis. No first-result or
local-value-similarity selection was used.

Among the 87 completed canary observations, 80 were exact, zero ambiguous, and seven
had no exact financial report. Official-key/basis QC mismatch was 0%. The seven misses
are AGROT periods before or around its public-reporting history, not discarded failures.

## 7. Disclosure Timing

Exact seconds-level timestamps were recovered for all 80 mapped observations. The
research-facing `available_from` is the first observed XU100 trading-session close
strictly after publication; the legacy fixed-lag date remains in a separate column.
No date-only record occurred in the completed subset.

## 8. First Publication / Vintage

First publication and high-confidence lineage were recovered for all 80 mapped rows.
Seventy-six are `FIRST_ONLY`; four are `FIRST_PLUS_CORRECTION`. Notification chains
remain timestamp ordered, and latest values never replace first-publication values.
The AEFES 2022Q3 regression continues to select notification 1076388 as first and
1076969 as the correcting version.

## 9. Consolidation

All 80 completed mappings are industrial/holding cases with the locked consolidated
basis. Selected-basis mismatches were zero. Batch 2 stopped before any additional
accounting-type checkpoint completed, so this experiment does not claim bulk bank or
insurance coverage. Their non-consolidated rule remains locked and regression-tested
through EXP-DATA-007.

## 10. Presentation Unit

Presentation unit was resolved for 80/80 mapped canary observations: 68 used `1.000 TL`
and twelve used plain `TL`. Unknown/mixed units remained fail-closed. No silent scaling
or ticker-specific exception was introduced.

## 11. Period Semantics

All 80 completed observations have resolved balance/flow period classes. Balance-sheet
equity is point-in-time; Q1–Q3 flows are YTD and Q4 flows annual. The locked safe
derivation rules produced 34 revenue and 34 net-income single-quarter values. No CFO,
FCF or operating-profit single-quarter value was derived because their comparability
remains conditional.

## 12. TFRS29

Within the 80 exact rows, 47 are `PRE_TFRS29`, five are
`POST_TFRS29_CONFIRMED`, and 28 are `POST_TFRS29_UNKNOWN_COMPARATIVE`. Published
comparatives were not relabelled as explicitly restated. No V4-style second manual CPI
adjustment was applied.

## 13. Raw vs Normalized Values

The long-form research table retains raw KAP label, taxonomy code, raw displayed
value, raw unit, normalized TRY value, semantic class, confidence and first
notification ID. Revenue, net income, equity, CFO, investing cash flow and operating
profit were present for 80/80 exact rows. Derived FCF was present for 80/80. EBITDA
remained missing for 80/80 because no pilot-approved exact taxonomy row was found.

## 14. Local vs Official Differences

The 560 canary field comparisons were classified using thresholds locked before the
run:

| Audit class | Count |
|---|---:|
| Exact match | 109 |
| Small difference | 21 |
| Material difference | 110 |
| Semantic mismatch | 240 |
| Missing official | 80 |

The 240 semantic mismatches are CFO, FCF and operating-profit comparisons whose
numeric difference is retained but whose definition is not treated as proven
equivalent. The 80 missing-official results are EBITDA. These classifications measure
data compatibility, not model performance.

## 15. Failure Modes

- Seven canary records: no exact KAP financial report, retained as `UNRECOVERABLE`.
- Batch 2: at least eleven HTTP 429 responses, triggering the locked source-stability
  stop.
- Initial stopped-run logging serialized after the exception rather than before it, so
  exact batch-2 attempt totals were lost. Code now records `BatchStop` before re-raise;
  the known incident is preserved in `stop_event_batch_2.json`.
- Remaining known risks: KAP schema changes, large detail pages, unproven restated
  comparatives, conditional cash-flow/operating-profit semantics, and absent safe
  EBITDA taxonomy.

## 16. Coverage

| Metric | Count | Percent of 2,646 |
|---|---:|---:|
| Fully recovered / exact | 80 | 3.0234% |
| Exact timestamp | 80 | 3.0234% |
| Exact first publication | 80 | 3.0234% |
| Vintage lineage recovered | 80 | 3.0234% |
| Accounting semantics resolved | 80 | 3.0234% |
| TFRS29 confirmed/pre | 52 | 1.9652% |
| Partial metadata | 0 | 0% |
| Ambiguous | 0 | 0% |
| Unrecoverable after processing | 7 | 0.2646% |
| Source error / not processed after stop | 2,559 | 96.7120% |

Coverage must not be interpreted as a 96.7% mapping failure. Only 87 observations
reached mapping evaluation.

## 17. Year / Sector Breakdown

Processed canary recovery by period-end year was: 2018 8/8, 2019 8/8, 2020 8/9,
2021 8/9, 2022 8/11, 2023 10/12, 2024 12/12, 2025 12/12 and 2026 6/6. All seven
unrecoverable rows belong to AGROT.

All completed records are `INDUSTRIAL_OR_HOLDING`: 80 exact and seven unrecoverable.
The 272 bank and 67 insurance legacy records were not processed before the stop and
must not be reported as failed mappings.

## 18. Safe Research Subsets

A narrowly defined data-engineering-safe subset exists: exact recovery, resolved unit,
preferred basis and high-confidence field semantics; for inflation-sensitive use it
must additionally be PRE_TFRS29 or explicitly confirmed/bank-safe. This yields at most
80 observations before field filtering.

It is an alphabetically selected canary, not a representative investment sample. It is
not authorized for IC, backtest, feature selection or model training.

## 19. Feature-Family Data Readiness

| Family | Readiness | Reason |
|---|---|---|
| Quality | PARTIAL | Exact net-income/equity data exist only in the canary; full universe incomplete |
| Balance sheet | PARTIAL | Exact point-in-time equity works in canary; bulk coverage absent |
| Cash flow | NO | Bulk incomplete and CFO/FCF semantics remain conditional |
| Earnings | PARTIAL | Exact canary earnings exist; TFRS29 unknown comparative and bulk gap remain |
| Value | NO | Signal-date capital/shares/market cap remain a separate unresolved gate |

These are data-readiness decisions, not model-success claims.

## 20. Tests

EXP-DATA-008 preflight: **10/10 PASS**, including locked universe hash, member parser,
timestamp availability, cache corruption detection, deterministic batching, missing ≠
zero, safe YTD derivation, no latest→first substitution, nested EXP-DATA-007 suite and
production hashes. EXP-DATA-007 remained **11/11 PASS**. Canary cache-only output
equivalence also passed.

## 21. Production Integrity

Production changes attributable to EXP-DATA-008 are zero. Source fundamental files,
models, portfolios, schedulers and production caches were not overwritten. All new
contracts, code, response caches, checkpoints and outputs are under `research/`.

## 22. KAP BULK PIT/VINTAGE GATE

**PARTIAL.** Mapping/parser feasibility was confirmed on the completed canary, but the
2,646-row reconstruction did not finish. PASS is prohibited because only 87 records
were evaluated and the locked rate-limit stop fired. FAIL is also too strong because
80 exact reconstructions and deterministic cache reproduction succeeded without a
methodological or parser failure.

## 23. Remaining Data Blockers

The immediate blocker is official-source HTTP 429 stability under the locked medium
batch. Additional blockers remain: 2,559 unprocessed observations, bulk bank/insurance
coverage, TFRS29 unknown comparatives, CFO/FCF/operating-profit semantic equivalence,
safe EBITDA taxonomy, and signal-date capital/market-cap history.

## 24. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Do not proceed to macro, target, feature or model research. The single next action is
to resume **the same EXP-DATA-008 medium batch** only after a documented KAP cooldown
and source-stability check, using the unchanged contract and existing hashed caches.
If the same locked 429 stop recurs, retain PARTIAL and treat the public endpoint as a
bulk-source blocker rather than weakening the contract.
