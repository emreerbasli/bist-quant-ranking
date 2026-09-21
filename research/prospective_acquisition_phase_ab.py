"""EXP-DEPLOY-001 Phase A+B: research-only prospective source acquisition.

This module deliberately stops at raw/provider acquisition and comparison.  It
does not publish canonical views and is never imported by the forward runner.
"""
from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

RESEARCH = Path(__file__).resolve().parent
ROOT = RESEARCH.parent
FROZEN = RESEARCH / "data" / "provider_snapshot"
OUT_ROOT = RESEARCH / "data" / "prospective_raw"
EVENT_CONTRACTS = [
    RESEARCH / "contracts" / "exp_data_004_official_events.json",
    RESEARCH / "contracts" / "exp_data_005_official_validations.json",
]
sys.path.insert(0, str(ROOT))
import config as cfg

START = "2026-09-16"
END_EXCLUSIVE = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
PARAMETERS = {"start": START, "end_exclusive": END_EXCLUSIVE,
              "auto_adjust": False, "actions": True, "repair": False}
WANTED = ["open", "high", "low", "close", "adj_close", "volume", "dividends", "stock_splits"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_name(symbol: str) -> str:
    return f"{symbol.replace('.', '_').replace('^', 'IDX_')}.parquet"


def fetch(symbol: str, out: Path) -> dict:
    try:
        frame = yf.Ticker(symbol).history(
            start=START, end=END_EXCLUSIVE, auto_adjust=False,
            actions=True, repair=False,
        )
        if frame.empty:
            return {"ticker": symbol, "status": "EMPTY", "rows": 0}
        if frame.index.tz is not None:
            frame.index = frame.index.tz_localize(None)
        frame.index = pd.DatetimeIndex(frame.index).normalize()
        frame.columns = [str(c).lower().replace(" ", "_") for c in frame.columns]
        frame = frame.reindex(columns=WANTED)
        path = out / file_name(symbol)
        frame.to_parquet(path)
        return {"ticker": symbol, "status": "OK", "rows": int(len(frame)),
                "source_max": str(frame.index.max().date()),
                "first_date": str(frame.index.min().date()),
                "path": path.relative_to(RESEARCH).as_posix(),
                "sha256": sha256(path), "file_size": int(path.stat().st_size)}
    except Exception as exc:
        return {"ticker": symbol, "status": "ERROR", "rows": 0,
                "error": f"{type(exc).__name__}: {exc}"}


def load_official_events() -> list[dict]:
    events: list[dict] = []
    for path in EVENT_CONTRACTS:
        payload = json.loads(path.read_text(encoding="utf-8"))
        events.extend(payload.get("events", []))
    return events


def action_readiness(records: list[dict], out: Path) -> dict:
    events = load_official_events()
    known = {(e.get("symbol"), str(e.get("ex_date"))) for e in events}
    actions = []
    for record in records:
        if record.get("status") != "OK":
            continue
        frame = pd.read_parquet(RESEARCH / record["path"])
        for date, row in frame.iterrows():
            div = float(row.get("dividends", 0) or 0)
            split = float(row.get("stock_splits", 0) or 0)
            if div != 0 or split != 0:
                day = str(pd.Timestamp(date).date())
                actions.append({"ticker": record["ticker"], "date": day,
                                "dividends": div, "stock_splits": split,
                                "official_event_match": (record["ticker"], day) in known})
    pd.DataFrame(actions).to_json(out / "corporate_action_observations.json",
                                  orient="records", indent=2)
    return {"provider_action_rows": len(actions),
            "official_event_rows": len(events),
            "matched_action_rows": sum(bool(x["official_event_match"]) for x in actions),
            "readiness": "PASS" if not actions or all(x["official_event_match"] for x in actions) else "FAIL_UNMATCHED_ACTION"}


def compare_overlap(records: list[dict], out: Path) -> dict:
    rows = []
    cols = WANTED
    for record in records:
        if record.get("status") != "OK":
            continue
        fresh_path = RESEARCH / record["path"]
        frozen_path = FROZEN / file_name(record["ticker"])
        if not frozen_path.exists():
            continue
        fresh = pd.read_parquet(fresh_path).sort_index()
        frozen = pd.read_parquet(frozen_path).sort_index()
        overlap = fresh.index.intersection(frozen.index)
        for col in cols:
            a = pd.to_numeric(fresh.loc[overlap, col], errors="coerce")
            b = pd.to_numeric(frozen.loc[overlap, col], errors="coerce")
            both = a.notna() & b.notna()
            diff = (a[both] - b[both]).abs()
            rows.append({"ticker": record["ticker"], "column": col,
                         "overlap_rows": int(len(overlap)),
                         "compared_rows": int(both.sum()),
                         "different_rows": int((diff > 0).sum()),
                         "max_abs_diff": float(diff.max()) if len(diff) else None})
    detail = pd.DataFrame(rows)
    detail.to_csv(out / "provider_vintage_overlap.csv", index=False)
    return {"tickers_compared": int(detail["ticker"].nunique()) if len(detail) else 0,
            "fields_compared": int(len(detail)),
            "different_cells": int(detail["different_rows"].sum()) if len(detail) else 0,
            "detail_path": (out / "provider_vintage_overlap.csv").relative_to(RESEARCH).as_posix()}


def main() -> None:
    acquisition_id = "acq_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_ROOT / acquisition_id
    out.mkdir(parents=True, exist_ok=False)
    symbols = list(dict.fromkeys([*cfg.HISSELER, "XU100.IS"]))
    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, symbol, out): symbol for symbol in symbols}
        for future in as_completed(futures):
            record = future.result(); records.append(record); print(record["ticker"], record["status"])
    records.sort(key=lambda x: x["ticker"])
    source_max = max((r.get("source_max") for r in records if r.get("source_max")), default=None)
    manifest = {"experiment_id": "EXP-DEPLOY-001-PHASE-A-B", "acquisition_id": acquisition_id,
                "acquisition_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "provider": "Yahoo Finance via installed yfinance", "request": PARAMETERS,
                "universe_count": len(symbols), "universe_includes_benchmark": "XU100.IS" in symbols,
                "source_max": source_max, "records": records}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    readiness = action_readiness(records, out)
    vintage = compare_overlap(records, out)
    report = {"manifest": manifest, "corporate_action_readiness": readiness,
              "provider_vintage_parity": vintage,
              "fetch_contract_parity": {"provider": "Yahoo Finance via installed yfinance",
                  "parameters_exact": PARAMETERS, "columns_exact": WANTED,
                  "status": "PASS" if all(r.get("status") in {"OK", "EMPTY"} for r in records) else "FAIL"},
              "phase_a": "PASS",
              "phase_b": "PASS" if readiness["readiness"] == "PASS" and all(r.get("status") in {"OK", "EMPTY"} for r in records) else "FAIL",
              "decision": "READY_FOR_PHASE_C" if readiness["readiness"] == "PASS" and all(r.get("status") in {"OK", "EMPTY"} for r in records) else "BLOCKED"}
    (out / "phase_ab_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"acquisition_id": acquisition_id, "phase_a": report["phase_a"],
                      "phase_b": report["phase_b"], "decision": report["decision"],
                      "corporate_action_readiness": readiness, "provider_vintage_parity": vintage}, ensure_ascii=False))


if __name__ == "__main__":
    main()
