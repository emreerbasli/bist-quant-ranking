"""EXP-DEPLOY-001 Phase C: append-only canonical prospective extension."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from exp_data_004 import OHLC, _status, share_factor, theoretical_ex_price

RESEARCH = Path(__file__).resolve().parent
BASE_VIEW = RESEARCH / "data" / "price_view_data004"
OVERLAY_VIEW = RESEARCH / "data" / "price_view_data005_overlay"
FROZEN_MANIFEST = RESEARCH / "data" / "provider_snapshot" / "manifest.json"
ACTIVATION = RESEARCH / "forward_infrastructure" / "forward_activation.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_name(symbol: str) -> str:
    return f"{symbol.replace('.', '_').replace('^', 'IDX_')}.parquet"


def canonical_hash(frame: pd.DataFrame) -> str:
    payload = frame.sort_index().to_json(orient="split", date_format="iso", double_precision=15)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_view(symbol: str) -> tuple[pd.DataFrame, Path]:
    path = OVERLAY_VIEW / file_name(symbol)
    if not path.exists():
        path = BASE_VIEW / file_name(symbol)
    return pd.read_parquet(path).sort_index(), path


def load_records(price_acquisition: Path) -> dict[str, dict]:
    manifest = json.loads((price_acquisition / "manifest.json").read_text(encoding="utf-8"))
    return {row["ticker"]: row for row in manifest["records"] if row.get("status") == "OK"}


def build_symbol(symbol: str, raw_path: Path, parent: pd.DataFrame, events: dict[tuple[str, str], dict]) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_parquet(raw_path).sort_index()
    parent_max = pd.Timestamp(parent.index.max()).normalize()
    if not raw.index.is_monotonic_increasing:
        raw = raw.sort_index()
    if len(raw) and pd.Timestamp(raw.index.min()).normalize() <= parent_max:
        raise ValueError(f"HISTORICAL_BACKFILL_FORBIDDEN:{symbol}")
    previous_close = float(parent.iloc[-1]["raw_close"])
    previous_research_close = float(parent.iloc[-1]["research_close"])
    if not np.isfinite(previous_close) or not np.isfinite(previous_research_close) or previous_research_close <= 0:
        raise ValueError(f"FROZEN_CHAIN_STATE_INVALID:{symbol}")
    rows = []
    blocked_reason: str | None = None
    for date, source_row in raw.iterrows():
        date = pd.Timestamp(date).normalize()
        raw_values = {column: pd.to_numeric(source_row.get(column), errors="coerce") for column in OHLC}
        volume = pd.to_numeric(source_row.get("volume"), errors="coerce")
        dividend_value = pd.to_numeric(source_row.get("dividends"), errors="coerce")
        split_value = pd.to_numeric(source_row.get("stock_splits"), errors="coerce")
        dividend = float(dividend_value) if pd.notna(dividend_value) else 0.0
        split = float(split_value) if pd.notna(split_value) else 0.0
        action = events.get((symbol, str(date.date())))
        action_type = action.get("action_type", action.get("event_type")) if action else None
        early_action = next((event for event in events.values() if event.get("ticker", event.get("symbol")) == symbol and event.get("provider_adjusted_date") and pd.Timestamp(event["provider_adjusted_date"]) <= date < pd.Timestamp(event["ex_date"])), None)
        calculation_values = raw_values.copy()
        if early_action:
            factor = share_factor(early_action)
            calculation_values = {column: float(raw_values[column]) * factor if pd.notna(raw_values[column]) else raw_values[column] for column in OHLC}
        row_blocked_reason = blocked_reason
        provider_action = dividend != 0.0 or split != 0.0
        if provider_action and (action is None or action.get("pit_status") != "PROSPECTIVE_CAPTURED"):
            blocked_reason = "RETROSPECTIVE_OR_UNKNOWN_ACTION"
            row_blocked_reason = blocked_reason
        elif early_action:
            row_blocked_reason = "PROVIDER_EARLY_ADJUSTMENT"
        status = _status(pd.Series({f"raw_{k}": v for k, v in raw_values.items()} | {"volume": volume}), previous_close)
        quality = "PROVIDER_ONLY"
        source = "YAHOO_PROSPECTIVE_RAW"
        if row_blocked_reason == "PROVIDER_EARLY_ADJUSTMENT":
            quality = "UNRESOLVED"
            source = "YAHOO_PROSPECTIVE_RAW+PROVIDER_EARLY_ADJUSTMENT"
            if status == "TRADED_PROVIDER" and all(pd.notna(calculation_values[k]) and calculation_values[k] > 0 for k in OHLC):
                growth = float(calculation_values["close"] / previous_close)
                current_research_close = previous_research_close * growth
                economic_return = float(growth - 1.0)
                previous_close = float(calculation_values["close"])
                previous_research_close = current_research_close
            else:
                economic_return = np.nan
            research_values = {column: np.nan for column in OHLC}
        elif row_blocked_reason:
            quality = "UNRESOLVED"
            source = f"YAHOO_PROSPECTIVE_RAW+{row_blocked_reason}"
            research_values = {column: np.nan for column in OHLC}
            economic_return = np.nan
        elif status != "TRADED_PROVIDER" or any(pd.isna(raw_values[column]) or raw_values[column] <= 0 for column in OHLC):
            quality = "UNRESOLVED" if status.startswith("UNRESOLVED") else quality
            research_values = {column: np.nan for column in OHLC}
            economic_return = np.nan
        else:
            event_type = action_type
            denominator = previous_close
            numerator = float(raw_values["close"]) + dividend
            if event_type in {"BONUS_ISSUE", "RIGHTS_ISSUE"}:
                denominator = theoretical_ex_price(previous_close, action)
                numerator = float(raw_values["close"])
                quality = "RECONSTRUCTED"
                source = "YAHOO_PROSPECTIVE_RAW+OFFICIAL_KAP_EVENT"
            elif event_type == "CASH_DIVIDEND":
                source = "YAHOO_PROSPECTIVE_RAW+OFFICIAL_KAP_CASH_DIVIDEND"
            growth = numerator / denominator
            current_research_close = previous_research_close * growth
            scale = current_research_close / float(raw_values["close"])
            research_values = {column: float(raw_values[column]) * scale for column in OHLC}
            economic_return = float(growth - 1.0)
            previous_close = float(raw_values["close"])
            previous_research_close = current_research_close
        row = {"ticker": symbol, "date": date, **{f"raw_{k}": raw_values[k] for k in OHLC},
               **{f"provider_adjusted_{k}": float(raw_values[k]) * (float(source_row.get("adj_close")) / float(source_row.get("close"))) if pd.notna(source_row.get("adj_close")) and pd.notna(source_row.get("close")) and float(source_row.get("close")) != 0 else np.nan for k in OHLC},
               **{f"research_{k}": research_values[k] for k in OHLC}, "volume": volume,
               "dividends": dividend, "provider_stock_splits": split,
               "economic_return": economic_return, "price_quality": quality,
               "corporate_action_flag": action_type if action and quality != "UNRESOLVED" else ("RETROSPECTIVE_ACTION_EXCLUDED" if row_blocked_reason == "RETROSPECTIVE_OR_UNKNOWN_ACTION" else ("PROVIDER_EARLY_ADJUSTMENT" if row_blocked_reason == "PROVIDER_EARLY_ADJUSTMENT" else "NONE")),
               "trading_status": status, "trading_eligible": bool(quality in {"VERIFIED", "RECONSTRUCTED", "PROVIDER_ONLY"} and status == "TRADED_PROVIDER" and all(pd.notna(research_values[k]) and research_values[k] > 0 for k in OHLC)),
               "source": source, "chain_state_status": row_blocked_reason or "CONTINUED"}
        rows.append(row)
    return pd.DataFrame(rows).set_index("date"), {"parent_last_session": str(parent_max.date()), "extension_last_session": str(raw.index.max().date()) if len(raw) else None, "chain_state_status": blocked_reason or "CONTINUED"}


def build_extension(price_acquisition: Path, action_acquisition: Path, output: Path) -> dict:
    price_acquisition = price_acquisition.resolve()
    action_acquisition = action_acquisition.resolve()
    output = output.resolve()
    records = load_records(price_acquisition)
    action_payload = json.loads((action_acquisition / "normalized_events.json").read_text(encoding="utf-8"))
    events = {(event["ticker"], event["ex_date"]): event for event in action_payload.get("events", [])}
    activation = json.loads(ACTIVATION.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    output_records, states = [], []
    for symbol in sorted(records):
        parent, parent_path = load_view(symbol)
        raw_path = RESEARCH / records[symbol]["path"]
        frame, state = build_symbol(symbol, raw_path, parent, events)
        target = output / file_name(symbol)
        frame.to_parquet(target)
        output_records.append({"ticker": symbol, "path": target.relative_to(RESEARCH).as_posix(), "rows": len(frame), "source_max": state["extension_last_session"], "sha256": sha256(target), "file_size": target.stat().st_size, "canonical_content_sha256": canonical_hash(frame), "parent_frozen_path": parent_path.relative_to(RESEARCH).as_posix(), "parent_frozen_sha256": sha256(parent_path), "source_raw_sha256": records[symbol]["sha256"]})
        states.append({"ticker": symbol, **state})
    manifest = {"experiment_id": "EXP-DEPLOY-001-PHASE-C", "status": "RESEARCH_ONLY_PENDING_PHASE_D", "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_acquisition": str(price_acquisition.relative_to(RESEARCH)), "action_acquisition": str(action_acquisition.relative_to(RESEARCH)), "parent_activation_baseline_snapshot_hash": activation["activation_baseline_snapshot_hash"], "parent_frozen_snapshot_manifest": str(FROZEN_MANIFEST.relative_to(RESEARCH)), "records": output_records, "chain_states": states, "append_only": True, "historical_backfill": False, "canonical_publish": False}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-acquisition", required=True, type=Path)
    parser.add_argument("--action-acquisition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_extension(args.price_acquisition, args.action_acquisition, args.output)
    print(json.dumps({"records": len(manifest["records"]), "append_only": manifest["append_only"], "historical_backfill": manifest["historical_backfill"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
