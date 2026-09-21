"""Phase A: read-only integrity audit for isolated research.

Writes only research/results. It deliberately does not certify data merely because
files exist: absent historical universe membership, corporate-action provenance,
or actual announcement/release timestamps remain explicit blockers.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config as cfg

OUT = Path(__file__).resolve().parent / "results"


def _raw_path(symbol: str) -> Path:
    return cfg.DATA_RAW / f"{symbol.replace('^', 'IDX_').replace('.', '_').replace('=', '_')}.parquet"


def _fund_path(symbol: str) -> Path:
    return ROOT / "data" / "fundamentals" / f"{symbol.replace('.', '_')}.parquet"


def audit_prices() -> dict[str, Any]:
    benchmark_path = _raw_path("XU100.IS")
    benchmark = pd.read_parquet(benchmark_path).sort_index() if benchmark_path.exists() else pd.DataFrame()
    benchmark_days = pd.DatetimeIndex(benchmark.index).normalize().unique()
    rows: list[dict[str, Any]] = []
    for symbol in cfg.HISSELER:
        path = _raw_path(symbol)
        row: dict[str, Any] = {"symbol": symbol, "file": path.name}
        if not path.exists():
            row.update(status="FAIL", reason="missing raw price file")
            rows.append(row)
            continue
        try:
            df = pd.read_parquet(path).sort_index()
            index = pd.DatetimeIndex(df.index).normalize()
            required = {"close", "volume"}
            missing = sorted(required - set(df.columns))
            close = pd.to_numeric(df.get("close"), errors="coerce")
            volume = pd.to_numeric(df.get("volume"), errors="coerce")
            returns = close.pct_change()
            common = index.intersection(benchmark_days)
            row.update(
                status="PASS" if not missing and not index.duplicated().any() else "FAIL",
                bars=int(len(df)), first_date=str(index.min().date()), last_date=str(index.max().date()),
                missing_columns=missing, duplicate_dates=int(index.duplicated().sum()),
                nonpositive_close=int((close <= 0).sum()), nonpositive_volume=int((volume <= 0).sum()),
                missing_vs_benchmark=int(len(benchmark_days.difference(index))),
                overlap_with_benchmark=int(len(common)),
                extreme_abs_return_gt_50pct=int((returns.abs() > 0.50).sum()),
            )
        except Exception as exc:
            row.update(status="FAIL", reason=f"read error: {type(exc).__name__}: {exc}")
        rows.append(row)
    status_counts = Counter(row["status"] for row in rows)
    return {"benchmark_file": benchmark_path.name, "benchmark_days": int(len(benchmark_days)),
            "summary": dict(status_counts),
            "aggregate": {
                "nonpositive_close": int(sum(row.get("nonpositive_close", 0) for row in rows)),
                "nonpositive_volume": int(sum(row.get("nonpositive_volume", 0) for row in rows)),
                "missing_vs_benchmark": int(sum(row.get("missing_vs_benchmark", 0) for row in rows)),
                "extreme_abs_return_gt_50pct": int(sum(row.get("extreme_abs_return_gt_50pct", 0) for row in rows)),
            },
            "symbols": rows}


def audit_fundamentals() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    fixed_schedule_count = 0
    for symbol in cfg.HISSELER:
        path = _fund_path(symbol)
        row: dict[str, Any] = {"symbol": symbol, "file": path.name}
        if not path.exists():
            row.update(status="FAIL", reason="missing fundamental file")
            rows.append(row)
            continue
        try:
            df = pd.read_parquet(path)
            required = {"gecerlilik_tarihi", "ceyrek"}
            missing = sorted(required - set(df.columns))
            dates = pd.to_datetime(df.get("gecerlilik_tarihi"), errors="coerce")
            q = df.get("ceyrek", pd.Series(dtype=str)).astype(str)
            # The present builder assigns all records to fixed 15 May/Aug/Nov/Mar dates,
            # which is a publication-lag proxy rather than evidence of a KAP timestamp.
            fixed = int(dates.dt.strftime("%m-%d").isin({"05-15", "08-15", "11-15", "03-15"}).sum())
            fixed_schedule_count += fixed
            row.update(
                status="FAIL" if missing or dates.isna().any() else "WARN",
                records=int(len(df)), missing_columns=missing, null_validity_dates=int(dates.isna().sum()),
                duplicate_quarters=int(q.duplicated().sum()), duplicate_validity_dates=int(dates.duplicated().sum()),
                first_validity=str(dates.min().date()) if dates.notna().any() else None,
                last_validity=str(dates.max().date()) if dates.notna().any() else None,
                fixed_schedule_dates=fixed,
                provenance=sorted(map(str, df.get("kaynak", pd.Series(dtype=str)).dropna().unique().tolist())),
            )
        except Exception as exc:
            row.update(status="FAIL", reason=f"read error: {type(exc).__name__}: {exc}")
        rows.append(row)
    return {"summary": dict(Counter(row["status"] for row in rows)), "fixed_schedule_dates": fixed_schedule_count,
            "symbols": rows,
            "verdict": "BLOCKER: validity dates are proxy schedule dates, not stored KAP announcement timestamps."}


def audit_repository_constraints() -> dict[str, Any]:
    loader = ROOT / "models" / "v3_ranking" / "data_loader.py"
    builder = ROOT / "features" / "kap_scraper" / "isyatirim_pit_builder.py"
    loader_text = loader.read_text(encoding="utf-8") if loader.exists() else ""
    builder_text = builder.read_text(encoding="utf-8") if builder.exists() else ""
    return {
        "historical_universe": {
            "status": "BLOCKER",
            "finding": "Only a current hard-coded universe is present; no dated membership, IPO eligibility, or delisting archive was found.",
        },
        "corporate_actions": {
            "status": "INVESTIGATE",
            "finding": "Adjusted-price provenance and split/dividend event records are not stored beside historical bars; extreme-return flags need reconciliation.",
        },
        "macro": {
            "status": "BLOCKER",
            "finding": "The loader contains a hard-coded CPI table and falls back to 2.0% for absent months; no release timestamp/source metadata is stored.",
            "fallback_present": "tufe_aylik.get(m, 2.0)" in loader_text,
        },
        "pit_builder": {
            "status": "BLOCKER",
            "finding": "Fundamental validity dates are fixed period-end-plus-lag proxies, not actual filings.",
            "fixed_schedule_present": all(x in builder_text for x in ("05-15", "08-15", "11-15", "03-15")),
        },
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"experiment_id": "EXP-A-001", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "read-only research audit", "prices": audit_prices(),
              "fundamentals": audit_fundamentals(), "constraints": audit_repository_constraints(),
              "overall_disposition": "BLOCKED_FOR_FUNDAMENTAL_OR_MACRO_MODEL_SELECTION"}
    json_path = OUT / "EXP-A-001_data_audit.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    price = result["prices"]["summary"]
    price_agg = result["prices"]["aggregate"]
    fund = result["fundamentals"]["summary"]
    report = f"""# EXP-A-001 — Data and leakage audit\n\n**Disposition:** {result['overall_disposition']}\n\n- Price files: {price}\n- Price flags: {price_agg['nonpositive_volume']} zero/non-positive-volume bars, {price_agg['missing_vs_benchmark']} constituent-date absences versus XU100, and {price_agg['extreme_abs_return_gt_50pct']} raw returns above 50% in absolute value.\n- Fundamental files: {fund}; fixed proxy validity dates: {result['fundamentals']['fixed_schedule_dates']}\n- Historical universe: BLOCKER (current-universe survivorship bias cannot be measured).\n- PIT fundamentals: BLOCKER (the builder uses fixed release-lag dates, not actual KAP filing timestamps).\n- Macro: BLOCKER (hard-coded CPI values plus a 2% fallback; no release calendar).\n- Corporate actions: INVESTIGATE (adjustment provenance and event reconciliation absent).\n\nPrice-only descriptive baselines may proceed only with an explicit current-universe caveat. Feature/target/model selection that uses fundamental or macro inputs must wait for actual filing/release timestamps. See `{json_path.name}` for symbol-level evidence.\n"""
    (OUT / "EXP-A-001_data_audit.md").write_text(report, encoding="utf-8")
    print(json_path)


if __name__ == "__main__":
    main()
