# EXP-DEPLOY-001 — BIMAS.IS 2026-09-16 action investigation

## Finding

The prospective Yahoo acquisition contains one provider dividend observation:

- ticker: `BIMAS.IS`
- date: `2026-09-16`
- provider `dividends`: `2.5`
- `stock_splits`: `0.0`
- acquisition timestamp: `2026-09-19T10:22:27.854959+00:00`
- source file: `data/prospective_raw/acq_20260919T102219Z/BIMAS_IS.parquet`

## Repository evidence

`research/contracts/exp_data_004_official_events.json` contains no `BIMAS.IS` event. The reconciliation contract and the DATA-005 validation contract also contain no BIMAS official event. Their BIMAS rows in provider-event reports are provider observations only and have no announcement date, official ex-date, dividend amount, gross/net basis, event type, or official source.

`data/events.csv` is a synthetic financial-report calendar and has no corporate-action semantics. `data/kap_vbts_arsiv.csv` is header-only. No repository KAP cache or official disclosure record for this event was found.

## Classification

- A — missing official prospective event evidence: **YES**
- B — date matching issue: **not established**; no official date exists to compare
- C — gross/net difference: **UNKNOWN**; no official amount or basis exists
- D — ticker normalization: **NO evidence**; `BIMAS.IS` is consistent
- E — event schema limitation: **YES**; current official contracts model bonus/rights events, not cash-dividend fields
- F — Yahoo/provider anomaly: **not established**

No value or date was inferred, promoted to official status, or hardcoded. Canonical publishing remains blocked.
