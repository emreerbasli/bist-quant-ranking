"""Fetch a research-only Yahoo raw/adjusted snapshot using the installed provider."""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path(__file__).resolve().parent
OUT = RESEARCH / "data" / "provider_snapshot"
sys.path.insert(0, str(ROOT))
import config as cfg

START = "2018-01-01"
END_EXCLUSIVE = "2026-09-16"


def fetch(symbol: str) -> dict:
    try:
        df = yf.Ticker(symbol).history(
            start=START, end=END_EXCLUSIVE, auto_adjust=False, actions=True,
            repair=False,
        )
        if df.empty:
            return {"symbol": symbol, "status": "EMPTY"}
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index = pd.DatetimeIndex(df.index).normalize()
        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
        wanted = ["open", "high", "low", "close", "adj_close", "volume", "dividends", "stock_splits"]
        df = df.reindex(columns=wanted)
        path = OUT / f"{symbol.replace('.', '_').replace('^', 'IDX_')}.parquet"
        df.to_parquet(path)
        return {
            "symbol": symbol, "status": "OK", "rows": len(df),
            "first_date": str(df.index.min().date()), "last_date": str(df.index.max().date()),
            "path": path.relative_to(RESEARCH).as_posix(),
        }
    except Exception as exc:
        return {"symbol": symbol, "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    symbols = list(dict.fromkeys([*cfg.HISSELER, "XU100.IS"]))
    records = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            print(record["symbol"], record["status"])
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Yahoo Finance via installed yfinance",
        "request": {"start": START, "end_exclusive": END_EXCLUSIVE, "auto_adjust": False, "actions": True, "repair": False},
        "records": sorted(records, key=lambda x: x["symbol"]),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(r["status"] == "OK" for r in records)
    print(f"OK={ok}/{len(records)}")


if __name__ == "__main__":
    main()
