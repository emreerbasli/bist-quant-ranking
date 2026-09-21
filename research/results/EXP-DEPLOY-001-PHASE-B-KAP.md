# EXP-DEPLOY-001 — Phase B KAP corporate-action readiness

## Official source and reconciliation

The repository's existing KAP member endpoint (`/tr/api/disclosure/members/byCriteria`) returned Borsa İstanbul disclosure `1663015` for BIMAS.IS. The official detail states:

- announcement timestamp: `2026-09-15T17:12:47+03:00`
- event type: `CASH_DIVIDEND`
- ex-date: `2026-09-16`
- gross dividend: `2.5 TRY`
- net dividend: `2.125 TRY`
- source: `https://www.kap.org.tr/tr/Bildirim/1663015`

The Yahoo prospective action field (`2.5`) reconciles exactly to the official gross amount. This is reconciliation evidence only; the Yahoo value was not used as authority.

## Prospective/PIT handling

The official record was acquired at `2026-09-19T10:40:03.715115+00:00`, after its ex-date. It is therefore persisted as `RETROSPECTIVE_ONLY` and cannot create or amend clean-forward evidence for 2026-09-16. The normalized schema records source timestamp, acquisition time, source hashes, source reference, gross/net/currency, and a fail-closed PIT status.

## Gate

The Phase B source-readiness reconciliation is PASS: official source available, BIMAS event confirmed, cash-dividend schema present, provenance complete, and missing events fail closed. Focused tests: 4/4 PASS. No canonical data was published and no runner, activation, candidate, frozen history, V12-bound source, or production file changed.
