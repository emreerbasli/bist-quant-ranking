# EXP-DEPLOY-001 — Phase D/E canonical and inference parity

## Gate

Phase D and Phase E both PASS on the locked frozen semantics. No official
signal, order, fill, NAV, cohort, scheduler, Web, Telegram, activation, model,
candidate, V12-bound runtime, production, or frozen-history change was made.

## Phase D — canonical parity

The append-only extension was replayed against EXP-DATA-004 base + overlay
views using deterministic fixtures covering normal sessions, rights issue,
bonus issue, provider early-adjustment/unresolved rows, eligibility, NaN masks,
and the partition boundary. Canonical parity was 4/4 focused tests PASS;
canonical mismatches: 0. Raw OHLC, raw close, provider-adjusted OHLC, volume,
research OHLC, quality, eligibility, status, action flags, and NaN masks
matched. Floating values used the predeclared deterministic representation
tolerance `atol=1e-12`, `rtol=0`; no semantic difference was masked.

## Phase E — feature/model parity

Only `mom_12_1`, `mom_63`, and `vol_63` were evaluated. Feature values and NaN
masks matched on the action-free common historical date. Eligible universe
matched exactly. For both RC-LGBMR-001 and RC-LAMBDAMART-001, scores, full
cross-sectional ordering, and ordered Top-10 matched exactly. Candidate bytes
were not changed.

The existing prospective partition is technically feature-ready on the latest
common eligible prospective session (2026-09-16): 87/89 partition records are
feature-ready (XU100 benchmark plus 87 equities); BIMAS is excluded by the
locked retrospective-action fail-closed rule and the incomplete later provider
session is not promoted.

## Integrity and tests

- Focused Phase D/E suite: 8/8 PASS.
- Existing immutable Phase C partition compatibility after code update: 89/89
  canonical content hashes unchanged.
- Fresh discovered research suite: 292/293 PASS. The only failure is the
  pre-existing activation-absence assertion in
  `test_exp_freeze_001r2`; it conflicts with the already approved active
  activation and was intentionally not modified.
- V12 exact validation: PASS for both candidates.
- Candidate artifact hashes: PASS.
- Activation/CLEAN_FORWARD_START unchanged:
  `2026-09-19T04:16:05.7473552+03:00`.
- Protected production diff: 0.
- Official signal/portfolio/operational logs: unchanged and empty.
