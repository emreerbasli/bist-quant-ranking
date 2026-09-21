# EXP-DEPLOY-001 — Phase C append-only canonical prospective extension

## Result

Phase C acceptance is **PASS** for the research-only append-only extension.
The source partition `acq_20260919T102219Z` (89 tickers, 180 prospective rows)
was transformed into `data/prospective_canonical/pc_20260919T105500Z` without
publishing or modifying the frozen historical views.

The transformation reuses the EXP-DATA-004 OHLC/status and chain helpers. Each
symbol record contains raw and research OHLC, raw close, volume, price quality,
trading eligibility, corporate-action flag, chain state, source hash, file size,
source-max, and frozen-parent path/hash. The partition manifest records the
activation baseline hash, source/action acquisitions, append-only policy, and
`historical_backfill=false`, `canonical_publish=false`.

## Corporate actions and PIT behavior

The BIMAS.IS 2026-09-16 cash dividend is retained as
`RETROSPECTIVE_ACTION_EXCLUDED` / `RETROSPECTIVE_OR_UNKNOWN_ACTION`; it is not
used to create clean-forward evidence and does not mutate the frozen chain.
The other 88 symbols continue from their frozen parent chain state. Provider
actions without a PIT-safe authoritative event remain fail-closed.

## Evidence

- Focused Phase C suite: 4/4 PASS.
- Partition records: 89/89; file hash/size provenance: 89/89; all extension
  dates are strictly after the frozen parent session.
- Deterministic canonical content hash: PASS.
- V12 exact validation for both candidates: PASS.
- Candidate artifact hashes: PASS.
- Protected production hash verification: PASS (0 changed).
- Official signal/portfolio/operational JSONL logs: unchanged and empty.
- Fresh discovered research suite: 284/285 PASS. The single failure is the
  pre-existing `test_exp_freeze_001r2.LifecycleE2ETests.test_09_activation_absent_runner_contract`,
  whose historical assertion requires activation to be absent and conflicts
  with the already approved active activation artifact; no Phase C code caused
  or changed that activation state.

No V12-bound file, candidate artifact, activation artifact, production file, or
frozen historical parquet was changed. Phase D/E was not started.
