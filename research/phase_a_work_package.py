"""Execute the first research work package without touching production state."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path(__file__).resolve().parent
RESULTS = RESEARCH / "results"
MANIFESTS = RESEARCH / "manifests"
sys.path.insert(0, str(ROOT))
import config as cfg


READING_FILES = [
    "PROJECT_MEMORY.md",
    "IMPLEMENTATION_LOG.md",
    "reports/v3_v4_kapsamli_karsilastirma.md",
    "models/v3_ranking/ranking_pipeline.py",
    "models/v4_ranking/ranking_pipeline_v4.py",
    "scratch/train_v4_1_model.py",
    "scratch/faz3_v4_walk_forward_egitimi.py",
    "scratch/run_faz_d_candidate_race.py",
    "backtest/backtest_runner.py",
    "backtest/trading_engine.py",
    "features/feature_engine.py",
    "features/fundamental_pit.py",
    "features/kap_scraper/isyatirim_pit_builder.py",
    "models/v3_ranking/data_loader.py",
    "models/v4_ranking/data_loader_v4.py",
    "models/v3_ranking/paper_trader.py",
    "models/v4_ranking/paper_trader_v4.py",
]

PROTECTED_FILES = [
    "models/v3_ranking/winning_lgbm_ranker.joblib",
    "models/v4_ranking/winning_lgbm_ranker_v4.joblib",
    "models/v3_ranking/paper_portfolio.json",
    "models/v4_ranking/paper_portfolio_v4.json",
    "models/v3_ranking/paper_trading_log.csv",
    "models/v4_ranking/paper_trading_log_v4.csv",
    "models/v3_ranking/ranking_pipeline.py",
    "models/v4_ranking/ranking_pipeline_v4.py",
    "models/v3_ranking/paper_trader.py",
    "models/v4_ranking/paper_trader_v4.py",
    "run_paper_trader.py",
    "run_paper_trader_v4.py",
    "bot/telegram_bot.py",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.exists():
        return {"path": relative, "exists": False}
    raw = path.read_bytes()
    return {
        "path": relative,
        "exists": True,
        "bytes": len(raw),
        "lines": raw.count(b"\n") + (1 if raw else 0),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def write_manifests() -> None:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()
    reading = {
        "generated_at_utc": generated,
        "files": [file_record(path) for path in READING_FILES],
        "independent_phase_1_audit": {
            "status": "NOT_FOUND_BY_EXACT_TITLE",
            "searched_terms": ["phase 1 independent audit", "faz 1 bağımsız audit", "bağımsız kantitatif audit"],
            "nearest_artifacts": [
                "scratch/qa_red_team_audit.py",
                "scratch/audit_v4_robustness.py",
                "reports/faz1_ic_tarama_raporu.md"
            ]
        }
    }
    production = {"generated_at_utc": generated, "files": [file_record(path) for path in PROTECTED_FILES]}
    (MANIFESTS / "required_reading_manifest.json").write_text(json.dumps(reading, ensure_ascii=False, indent=2), encoding="utf-8")
    (MANIFESTS / "production_hash_manifest_before.json").write_text(json.dumps(production, ensure_ascii=False, indent=2), encoding="utf-8")


def raw_path(symbol: str) -> Path:
    name = symbol.replace("^", "IDX_").replace(".", "_").replace("=", "_")
    return cfg.DATA_RAW / f"{name}.parquet"


def quarter_ordinal(value: str) -> int | None:
    match = re.fullmatch(r"(\d{4})Q([1-4])", str(value))
    return int(match.group(1)) * 4 + int(match.group(2)) if match else None


def audit_prices() -> tuple[pd.DataFrame, pd.DataFrame]:
    benchmark = pd.read_parquet(raw_path("XU100.IS")).sort_index()
    sessions = pd.DatetimeIndex(benchmark.index).normalize().unique().sort_values()
    rows, events = [], []
    for symbol in cfg.HISSELER:
        path = raw_path(symbol)
        if not path.exists():
            rows.append({"symbol": symbol, "status": "INVALID", "reason": "missing_file"})
            continue
        df = pd.read_parquet(path).sort_index()
        idx = pd.DatetimeIndex(df.index).normalize()
        required = {"open", "high", "low", "close", "volume"}
        missing_cols = sorted(required - set(df.columns))
        numeric = df.reindex(columns=sorted(required)).apply(pd.to_numeric, errors="coerce") if not missing_cols else pd.DataFrame(index=df.index)
        if missing_cols:
            rows.append({"symbol": symbol, "status": "INVALID", "reason": f"missing_columns:{missing_cols}"})
            continue
        first_bar, last_bar = idx.min(), idx.max()
        in_life = sessions[(sessions >= first_bar) & (sessions <= last_bar)]
        missing_in_life = in_life.difference(idx)
        first_positive_volume = idx[numeric["volume"].to_numpy() > 0].min() if (numeric["volume"] > 0).any() else pd.NaT
        active = (idx >= first_positive_volume) if pd.notna(first_positive_volume) else np.ones(len(idx), dtype=bool)
        ret = numeric["close"].pct_change(fill_method=None)
        split = pd.to_numeric(df.get("stock_splits", 0.0), errors="coerce").fillna(0.0)
        extreme_positions = np.flatnonzero((ret.abs() > 0.50).to_numpy())
        for pos in extreme_positions:
            events.append({
                "symbol": symbol,
                "date": str(idx[pos].date()),
                "return": float(ret.iloc[pos]),
                "split_field": float(split.iloc[pos]) if hasattr(split, "iloc") else 0.0,
                "status": "INVESTIGATE",
            })
        tolerance = numeric["close"].abs().clip(lower=1.0) * 1e-8
        high_gap = numeric[["open", "close", "low"]].max(axis=1) - numeric["high"]
        low_gap = numeric["low"] - numeric[["open", "close", "high"]].min(axis=1)
        ohlc_invalid = int(((high_gap > tolerance) | (low_gap > tolerance)).sum())
        critical = int(idx.duplicated().sum()) + int(numeric[["open", "high", "low", "close"]].isna().any(axis=1).sum()) + int((numeric[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
        status = "INVALID" if critical else "PROXY_UNVERIFIED"
        rows.append({
            "symbol": symbol,
            "status": status,
            "first_bar": str(first_bar.date()),
            "first_positive_volume": str(first_positive_volume.date()) if pd.notna(first_positive_volume) else None,
            "last_bar": str(last_bar.date()),
            "pre_first_bar_sessions": int((sessions < first_bar).sum()),
            "missing_sessions_during_observed_life": int(len(missing_in_life)),
            "duplicate_dates": int(idx.duplicated().sum()),
            "nan_ohlc": int(numeric[["open", "high", "low", "close"]].isna().any(axis=1).sum()),
            "nonpositive_ohlc": int((numeric[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()),
            "zero_volume_after_first_positive": int((numeric.loc[active, "volume"] <= 0).sum()),
            "ohlc_inconsistent": int(ohlc_invalid),
            "extreme_abs_return_gt_50pct": int(len(extreme_positions)),
            "corporate_action_provenance": "UNVERIFIED",
            "listing_date_provenance": "FIRST_BAR_PROXY",
        })
    return pd.DataFrame(rows), pd.DataFrame(events)


def audit_fundamentals() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    rows, issues = [], []
    fallback_count = future_capital_fallback = 0
    total_records = fixed_records = 0
    for symbol in cfg.HISSELER:
        stem = symbol.replace(".IS", "")
        path = ROOT / "data" / "fundamentals" / f"{stem}_IS.parquet"
        tekil_path = cfg.DATA_RAW / "isyatirim_cache" / f"{stem}_tekil.parquet"
        if not path.exists():
            rows.append({"symbol": symbol, "status": "MISSING", "records": 0})
            continue
        df = pd.read_parquet(path).sort_values("gecerlilik_tarihi")
        valid = pd.to_datetime(df["gecerlilik_tarihi"], errors="coerce")
        period_end = pd.to_datetime(df.get("ceyrek_bitis"), errors="coerce")
        fixed = valid.dt.strftime("%m-%d").isin({"05-15", "08-15", "11-15", "03-15"})
        ordinals = [quarter_ordinal(x) for x in df["ceyrek"]]
        gaps = sum(1 for a, b in zip(ordinals, ordinals[1:]) if a is not None and b is not None and b - a != 1)
        lag = (valid - period_end).dt.days
        total_records += len(df); fixed_records += int(fixed.sum())
        symbol_fallback = symbol_future = 0
        if tekil_path.exists():
            tekil = pd.read_parquet(tekil_path).sort_index()
            tekil.index = pd.to_datetime(tekil.index)
            last_cap_date = tekil["SERMAYE"].dropna().index.max() if "SERMAYE" in tekil else pd.NaT
            for t in valid.dropna():
                prior = tekil[tekil.index <= t]
                pd_val = prior["PD"].dropna().iloc[-1] if not prior.empty and "PD" in prior and not prior["PD"].dropna().empty else np.nan
                if pd.isna(pd_val) or pd_val <= 0:
                    symbol_fallback += 1
                    if pd.notna(last_cap_date) and last_cap_date > t:
                        symbol_future += 1
                        issues.append({"symbol": symbol, "date": str(t.date()), "issue": "fallback_uses_future_last_capital", "status": "INVALID"})
        fallback_count += symbol_fallback; future_capital_fallback += symbol_future
        source_values = "|".join(sorted(map(str, df.get("kaynak", pd.Series(dtype=str)).dropna().unique())))
        rows.append({
            "symbol": symbol,
            "status": "PROXY_UNVERIFIED",
            "records": len(df),
            "fixed_schedule_records": int(fixed.sum()),
            "null_validity_date": int(valid.isna().sum()),
            "duplicate_quarter": int(df["ceyrek"].duplicated().sum()),
            "quarter_sequence_gaps": int(gaps),
            "min_proxy_lag_days": int(lag.min()) if lag.notna().any() else None,
            "max_proxy_lag_days": int(lag.max()) if lag.notna().any() else None,
            "market_cap_fallback_records": symbol_fallback,
            "future_last_capital_fallback_records": symbol_future,
            "source": source_values,
            "vintage_field_present": False,
            "restatement_field_present": False,
            "statement_basis_single_q_ytd_ttm_present": False,
        })
    summary = {
        "total_records": total_records,
        "fixed_schedule_records": fixed_records,
        "market_cap_fallback_records": fallback_count,
        "future_last_capital_fallback_records": future_capital_fallback,
        "actual_announcement_timestamp_coverage": 0,
        "vintage_or_restatement_coverage": 0,
        "statement_basis_coverage": 0,
    }
    return pd.DataFrame(rows), pd.DataFrame(issues), summary


def repository_evidence() -> dict[str, Any]:
    all_paths = [p.relative_to(ROOT).as_posix().lower() for p in ROOT.rglob("*") if p.is_file() and "venv" not in p.parts]
    universe_candidates = [p for p in all_paths if any(term in p for term in ("universe", "delist", "membership", "listing", "halka_arz"))]
    loader = (ROOT / "models/v3_ranking/data_loader.py").read_text(encoding="utf-8")
    builder = (ROOT / "features/kap_scraper/isyatirim_pit_builder.py").read_text(encoding="utf-8")
    return {
        "historical_universe_candidate_files": universe_candidates,
        "current_hardcoded_universe_present": "HISSELER" in (ROOT / "config.py").read_text(encoding="utf-8"),
        "macro_missing_month_fallback_present": "tufe_aylik.get(m, 2.0)" in loader,
        "fixed_fundamental_schedule_present": all(x in builder for x in ("05-15", "08-15", "11-15", "03-15")),
        "fundamental_builder_last_capital_fallback_present": 'dropna().iloc[-1]' in builder and '"SERMAYE"' in builder,
    }


def write_reports(price: pd.DataFrame, events: pd.DataFrame, fund: pd.DataFrame, fund_issues: pd.DataFrame, fund_summary: dict[str, Any], repo: dict[str, Any]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    price.to_csv(RESULTS / "EXP-DATA-001_price_coverage.csv", index=False)
    events.to_csv(RESULTS / "EXP-DATA-001_corporate_action_flags.csv", index=False)
    fund.to_csv(RESULTS / "EXP-DATA-002_fundamental_coverage.csv", index=False)
    fund_issues.to_csv(RESULTS / "EXP-DATA-002_fundamental_issues.csv", index=False)
    aggregate = {
        "price_status": price["status"].value_counts(dropna=False).to_dict(),
        "price_missing_during_life": int(price["missing_sessions_during_observed_life"].fillna(0).sum()),
        "price_pre_first_bar_sessions": int(price["pre_first_bar_sessions"].fillna(0).sum()),
        "price_zero_volume_after_first_positive": int(price["zero_volume_after_first_positive"].fillna(0).sum()),
        "corporate_action_flags": int(len(events)),
        "fundamental_status": fund["status"].value_counts(dropna=False).to_dict(),
        "fundamental_summary": fund_summary,
        "repository_evidence": repo,
    }
    (RESULTS / "EXP-DATA-001_002_summary.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    report = f"""# Phase A corrected data audit — EXP-DATA-001/002

## Gate result: PARTIAL

Price rows are mechanically usable for descriptive research, but remain `PROXY_UNVERIFIED` until listing/corporate-action provenance is reconciled. Fundamental and macro inputs are not eligible for model-selection evidence.

## Price evidence

- Symbols: {len(price)}; statuses: {aggregate['price_status']}.
- Sessions before each file's first bar: {aggregate['price_pre_first_bar_sessions']}; these are no longer called missing observations.
- Missing benchmark sessions between each symbol's first and last bar: {aggregate['price_missing_during_life']}.
- Zero/non-positive volume bars after first positive-volume bar: {aggregate['price_zero_volume_after_first_positive']}.
- Absolute daily return flags above 50%: {len(events)}. They remain INVESTIGATE until split/bedelsiz provenance is verified.
- First bar is only a listing-date proxy, not an official IPO date.

## Fundamental, accounting and vintage evidence

- Records: {fund_summary['total_records']}; fixed proxy schedule: {fund_summary['fixed_schedule_records']}.
- Actual announcement timestamp coverage: {fund_summary['actual_announcement_timestamp_coverage']}.
- Vintage/restatement coverage: {fund_summary['vintage_or_restatement_coverage']}.
- Single-quarter/YTD/TTM basis coverage: {fund_summary['statement_basis_coverage']}.
- Market-cap fallback candidates: {fund_summary['market_cap_fallback_records']}; records exposed to a later last-capital fallback: {fund_summary['future_last_capital_fallback_records']}.

## Universe and macro evidence

- Historical universe/delist/listing candidate files found: {len(repo['historical_universe_candidate_files'])}.
- Current hard-coded universe present: {repo['current_hardcoded_universe_present']}.
- Missing-month CPI fallback present: {repo['macro_missing_month_fallback_present']}.

## Acceptance

- Price-only descriptive baselines: CONTINUE with current-universe and corporate-action caveats.
- Fundamental/macro feature or model selection: INVESTIGATE; not accepted.
- V3/V4.1 and value/quality common-comparison baseline: N/A until inputs are verified.
"""
    (RESULTS / "EXP-DATA-001_002_phase_a_report.md").write_text(report, encoding="utf-8")


def write_source_matrix() -> None:
    matrix = """# Source and repair matrix

| Area | Current evidence | Local repair possible | External source required | Research disposition |
|---|---|---|---|---|
| Price OHLCV | Local adjusted-looking Yahoo files with dividends/splits fields | Mechanical integrity and event flags | Authoritative corporate-action/listing reconciliation | PROXY_UNVERIFIED |
| Listing/delisting/universe | Current hard-coded ticker list | First-bar proxy only | Dated BIST membership/listing/delist archive | PROXY_UNVERIFIED; survivorship caveat |
| Fundamental values | İş Yatırım cached statements | Field coverage and quarter-sequence audit | Filing-level KAP announcement timestamps and original/restated vintages | PROXY_UNVERIFIED |
| Accounting basis | Quarter label exists | Infer candidates for manual review only | Explicit single-quarter/YTD/TTM and TFRS29 comparable-basis metadata | INVESTIGATE |
| Market cap/capital | Tekil cache available | Measure fallback exposure | Historical capital/corporate-action confirmation for exposed rows | INVALID where future last-capital fallback is used |
| CPI/policy rate | Hard-coded values | Remove from eligible research scope | Release-dated, vintage-aware official series | INVESTIGATE |
| USDTRY | Local price series | Mechanical audit | Source provenance if used for verified claims | PROXY_UNVERIFIED |
| Liquidity | Local volume and adjusted price | Compute diagnostic ADV/zero-return metrics | Adjustment-consistent volume and spread/impact evidence | PROXY_UNVERIFIED |

No provider, package, or API installation is performed by this work package.
"""
    (RESEARCH / "SOURCE_REPAIR_MATRIX.md").write_text(matrix, encoding="utf-8")


def main() -> None:
    write_manifests()
    price, events = audit_prices()
    fund, fund_issues, fund_summary = audit_fundamentals()
    repo = repository_evidence()
    write_reports(price, events, fund, fund_issues, fund_summary, repo)
    write_source_matrix()
    print(RESULTS / "EXP-DATA-001_002_phase_a_report.md")


if __name__ == "__main__":
    main()
