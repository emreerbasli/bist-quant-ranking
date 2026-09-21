# EXP-DEPLOY-001 — Phase F prospective dry-run

## Result

Phase F PASS. The real immutable acquisition → KAP action partition →
canonical extension → frozen feature → frozen candidate inference chain ran as
a research-only dry-run for session `2026-09-16`.

- Acquisition source-max: `2026-09-18`.
- Eligible universe: 86 equities.
- Fail-closed exclusions: BIMAS.IS (`RETROSPECTIVE_ACTION_EXCLUDED`) and
  SASA.IS (`UNRESOLVED_MISSING_VOLUME`).
- RC-LGBMR-001 role: PRIMARY_SHADOW_MODEL; ordered Top-10 generated.
- RC-LAMBDAMART-001 role: SECONDARY_SHADOW_MODEL; ordered Top-10 generated.
- No official signal/order/fill/NAV/cohort record was written.

Artifact: `data/prospective_dry_runs/dry_20260919T130000Z.json`.
It is marked `DRY_RUN_ONLY=true`, binds source/canonical/activation/candidate
hashes, and has substantive digest
`fa9122e1f87ef3899b39797ad623e7c946a30d47f10fb19e8d59ac57cbd3aa6b`.
The same input reran with the same substantive digest and write-once reuse.

Focused tests: 5/5 PASS. V12 and candidate integrity PASS, protected
production diff 0, activation unchanged, and all official candidate logs
remained empty. No successor manifest was created.
