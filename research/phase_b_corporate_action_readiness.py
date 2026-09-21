"""Read-only Phase B reconciliation for prospective provider-action evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(provider: list[dict], official_payload: dict) -> dict:
    schema = official_payload.get("schema", {})
    events = official_payload.get("events", [])
    index = {(event.get("ticker"), event.get("ex_date"), event.get("event_type")): event for event in events}
    rows = []
    for observation in provider:
        if float(observation.get("dividends") or 0) == 0:
            continue
        event = index.get((observation.get("ticker"), observation.get("date"), "CASH_DIVIDEND"))
        if not event:
            rows.append({"ticker": observation.get("ticker"), "date": observation.get("date"), "status": "MISSING_OFFICIAL_EVENT"})
            continue
        required = set(schema.get("common_required", [])) | set(schema.get("cash_dividend_required", []))
        complete = required.issubset(event) and all(event.get(key) not in {None, ""} for key in required)
        reconciled = float(event["gross_amount"]) == float(observation["dividends"])
        rows.append({"ticker": observation["ticker"], "date": observation["date"],
                     "status": "RECONCILED" if complete and reconciled else "MISMATCH",
                     "official_gross_amount": event.get("gross_amount"),
                     "provider_dividend": observation.get("dividends"),
                     "pit_status": event.get("pit_status")})
    result = {"schema_supported": set(["CASH_DIVIDEND", "STOCK_SPLIT", "BONUS_ISSUE", "RIGHTS_ISSUE"]).issubset(schema.get("event_types", [])),
              "missing_event_fail_closed": schema.get("missing_or_ambiguous") == "FAIL_CLOSED",
              "rows": rows,
              "authoritative_reconciliation": all(row["status"] == "RECONCILED" for row in rows) and bool(rows),
              "pit_enforced": all(row.get("pit_status") in {"PROSPECTIVE_CAPTURED", "RETROSPECTIVE_ONLY"} for row in rows)}
    result["phase_b_source_readiness"] = all([result["schema_supported"], result["missing_event_fail_closed"], result["authoritative_reconciliation"], result["pit_enforced"]])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-observations", required=True, type=Path)
    parser.add_argument("--official-events", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    provider = json.loads(args.provider_observations.read_text(encoding="utf-8"))
    official_payload = json.loads(args.official_events.read_text(encoding="utf-8"))
    result = evaluate(provider, official_payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
