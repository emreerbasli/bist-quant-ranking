# EXP-FREEZE-001R — FORWARD INFRASTRUCTURE REMEDIATION

## 1. Executive Summary

Remediation gate: **PARTIAL**. Frozen candidates are unchanged and protected. Clean-forward remains **NOT STARTED / PENDING INDEPENDENT AUDIT**.

## 2. Audit Defects Addressed

The runner is activation-gated, validates actual signal date rather than only requested `asof`, classifies backfill outside official evidence, records data snapshots, supports run/event IDs, idempotency, append locks and correction events.

## 3. Frozen Candidate Preservation

`RC-LGBMR-001` remains RAW/H60 and `RC-LAMBDAMART-001` remains BETA_RESIDUAL/H60. Model files and original manifests were not modified.

## 4. Signal-Date Protection

`classify_signal` fails closed when actual signal date is on/before model freeze, before clean-forward start, differs from requested session, precedes market close, or exceeds the 18-hour operational window.

## 5. Backfill / Missed Signal Policy

Rejected historical/date-mismatched runs are `NON_CLEAN_BACKFILL` in the separate debug namespace. Late runs are `MISSED_FORWARD_SIGNAL`; neither may create clean evidence.

## 6. Data-As-Of Evidence

Run snapshots contain every selected input price file SHA-256, provider snapshot identifier, source maximum timestamp, generated time and deterministic input snapshot hash.

## 7. Idempotency

The unique clean-signal key is candidate ID, candidate version and actual signal date. A duplicate is an append-only `ALREADY_EXISTS_NO_OP` operational event.

## 8. Append-Only / Corrections

All JSONL append operations require run/event IDs, use non-blocking Windows file locks and fsync, and fail closed on contention. Corrections append a row referencing the original event.

## 9. Forward Portfolio State Machine

Research helpers implement cost-reserved sells-first rebalance, fill/unfilled decisions, cash retention, ADV checks and retained last-valid marks. The runner currently writes only intended orders; durable daily execution-state persistence is not yet connected.

## 10. Execution Parity

The helper follows the frozen K=10 equal-weight, 50 bps, 10% ADV, no-borrowing policy. It is not yet invoked as a daily forward execution/NAV lifecycle.

## 11. Cost / Liquidity / Cash

Helpers record gross traded nominal, ADV, order/ADV, fill status and cost; negative cash fails closed. Daily operational wiring remains outstanding.

## 12. Daily NAV

`mark_to_market` supports last-valid marks and cash/positions/NAV output. Append-only daily NAV persistence is not yet wired into the runner.

## 13. H60 Cohort Lifecycle

H60 label-end calculation uses eligible-session calendar semantics; PENDING/COMPLETED eligibility and overlap metadata are implemented as helpers. Durable cohort update/evaluation records and predictive-statistic output remain outstanding.

## 14. Overlap Handling

New cohort records include `overlapping_active_cohorts`; overlapping cohorts are not asserted independent.

## 15. Write-Once Freeze Protection

`exp_freeze_001.py` now verifies existing model hashes and returns `FROZEN_ARTIFACTS_READ_ONLY_REUSE`; partial/mismatched frozen sets fail closed.

## 16. Forward Infrastructure Manifest

Original v1 manifest remains immutable as a pre-regression-test record. Final v2 forward manifest is immutable, `PENDING_INDEPENDENT_AUDIT`, and binds candidate/model hashes plus runner, logging, state-machine, contract and test hashes: `087d2d346699a3756c039a60dc52925e2f3c5472fd91544d4135a4ee840fb465`.

## 17. Tests

31/31 dedicated remediation tests PASS. 192/192 full research tests PASS.

## 18. Production Integrity

Independent read-only protected-hash comparison: PASS, 0 changed of 13 protected files.

## 19. Remaining Issues

The runner must still durably process pending orders on the next eligible session, append executions and daily NAV, and append completed H60 cohort evaluations before clean-forward activation can be audited as PASS.

## 20. Remediation Gate

**PARTIAL.** Candidates are **UNCHANGED**. No official clean-forward start timestamp exists.

## 21. SINGLE NEXT BEST ACTION

Complete the durable daily portfolio/execution/NAV and H60 cohort-evaluator wiring, then run a new independent read-only audit before any activation or official signal.
