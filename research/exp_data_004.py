"""EXP-DATA-004 — authoritative-timeline, research-only price reconstruction."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path(__file__).resolve().parent
RESULTS = RESEARCH / "results"
SNAPSHOT = RESEARCH / "data" / "provider_snapshot"
VIEW_DIR = RESEARCH / "data" / "price_view_data004"
CONTRACT = RESEARCH / "contracts" / "exp_data_004_official_events.json"
sys.path.insert(0, str(ROOT))
import config as cfg
from research.baselines_price_only import (
    END, LOOKBACK_LONG, REBALANCE_SESSIONS, START, benchmark_nav, load_panels, metrics, simulate,
    equal_universe_selector, momentum_selector,
)
from research.exp_data_003 import (
    reconciled_equal_selector, reconciled_momentum_selector, simulate_reconciled,
)

OHLC = ["open", "high", "low", "close"]
QUALITY = ["VERIFIED", "RECONSTRUCTED", "PROVIDER_ONLY", "UNRESOLVED"]


def snapshot_path(symbol: str) -> Path:
    return SNAPSHOT / f"{symbol.replace('.', '_').replace('^', 'IDX_')}.parquet"


def view_path(symbol: str) -> Path:
    return VIEW_DIR / f"{symbol.replace('.', '_').replace('^', 'IDX_')}.parquet"


def share_factor(event: dict[str, Any]) -> float:
    return 1.0 + float(event["ratio"])


def theoretical_ex_price(previous_raw_close: float, event: dict[str, Any]) -> float:
    factor = share_factor(event)
    if event["action_type"] == "BONUS_ISSUE":
        return previous_raw_close / factor
    if event["action_type"] == "RIGHTS_ISSUE":
        return (previous_raw_close + float(event["ratio"]) * float(event["subscription_price"])) / factor
    raise ValueError(event["action_type"])


def events_by_symbol(contract: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for event in contract["events"]:
        result.setdefault(event["symbol"], []).append(event)
    return result


def _status(row: pd.Series, previous_close: float | None) -> str:
    vals = pd.to_numeric(row[[f"raw_{x}" for x in OHLC]], errors="coerce")
    if vals.isna().any() or (vals <= 0).any():
        return "UNRESOLVED_MISSING_PRICE"
    high_ok = vals["raw_high"] >= max(vals["raw_open"], vals["raw_close"], vals["raw_low"])
    low_ok = vals["raw_low"] <= min(vals["raw_open"], vals["raw_close"], vals["raw_high"])
    if not high_ok or not low_ok:
        return "UNRESOLVED_BAD_OHLC"
    if pd.isna(row["volume"]) or row["volume"] <= 0:
        moving = previous_close is not None and abs(float(row["raw_close"]) / previous_close - 1.0) > 1e-12
        ranged = float(row["raw_high"]) != float(row["raw_low"])
        return "UNRESOLVED_MISSING_VOLUME" if moving or ranged else "UNRESOLVED_NO_TRADE_OR_STALE"
    return "TRADED_PROVIDER"


def build_symbol_view(symbol: str, symbol_events: list[dict]) -> pd.DataFrame:
    provider = pd.read_parquet(snapshot_path(symbol)).sort_index()
    provider.index = pd.DatetimeIndex(provider.index).normalize()
    out = pd.DataFrame(index=provider.index)
    for column in OHLC:
        out[f"raw_{column}"] = pd.to_numeric(provider[column], errors="coerce")
        out[f"provider_adjusted_{column}"] = pd.to_numeric(provider[column], errors="coerce")
    # Yahoo supplies only Adj Close. Apply its point-in-time ratio to raw O/H/L for
    # an explicit provider-adjusted comparison, without claiming it is authoritative.
    adj_ratio = pd.to_numeric(provider["adj_close"], errors="coerce") / pd.to_numeric(provider["close"], errors="coerce")
    for column in OHLC:
        out[f"provider_adjusted_{column}"] = out[f"raw_{column}"] * adj_ratio
    out["volume"] = pd.to_numeric(provider["volume"], errors="coerce")
    out["dividends"] = pd.to_numeric(provider["dividends"], errors="coerce").fillna(0.0)
    out["provider_stock_splits"] = pd.to_numeric(provider["stock_splits"], errors="coerce").fillna(0.0)
    out["corporate_action_flag"] = "NONE"
    out["price_quality"] = "PROVIDER_ONLY"
    out["source"] = "YAHOO_PROVIDER_SNAPSHOT"

    # Reconstruct the nominal pre-action basis internally. The unsafe early window
    # stays masked in the published research columns and is never usable as a signal.
    corrected = out[[f"raw_{x}" for x in OHLC]].copy()
    corrected.columns = OHLC
    event_on_ex: dict[pd.Timestamp, dict] = {}
    unsafe = pd.Series(False, index=out.index)
    for event in symbol_events:
        provider_date = pd.Timestamp(event["provider_adjusted_date"])
        ex_date = pd.Timestamp(event["ex_date"])
        early = (out.index >= provider_date) & (out.index < ex_date)
        corrected.loc[early, OHLC] *= share_factor(event)
        unsafe.loc[early] = True
        out.loc[early, "corporate_action_flag"] = "PROVIDER_EARLY_ADJUSTMENT"
        out.loc[early, "price_quality"] = "UNRESOLVED"
        out.loc[early, "source"] = "YAHOO_EARLY_ADJUSTMENT_QUARANTINED"
        if ex_date in out.index:
            event_on_ex[ex_date] = event
            out.loc[ex_date, "corporate_action_flag"] = event["action_type"]
            out.loc[ex_date, "price_quality"] = "RECONSTRUCTED"
            out.loc[ex_date, "source"] = "YAHOO_PROVIDER_SNAPSHOT+OFFICIAL_KAP_EVENT"

    # Forward chain: future events never rewrite prior research values.
    corrected_values = corrected[OHLC].to_numpy(dtype=float)
    research_values = np.full_like(corrected_values, np.nan)
    economic_values = np.full(len(out), np.nan, dtype=float)
    close_pos = OHLC.index("close")
    valid_positions = np.flatnonzero(np.isfinite(corrected_values[:, close_pos]))
    event_by_position = {out.index.get_loc(date): event for date, event in event_on_ex.items()}
    dividends = out["dividends"].to_numpy(dtype=float)
    if len(valid_positions):
        first = int(valid_positions[0])
        research_values[first] = corrected_values[first]
        prev_research_close = float(research_values[first, close_pos])
        prev_nominal_close = float(corrected_values[first, close_pos])
        for pos in range(first + 1, len(out)):
            current_close = corrected_values[pos, close_pos]
            if not np.isfinite(current_close):
                continue
            event = event_by_position.get(pos)
            denominator = theoretical_ex_price(prev_nominal_close, event) if event else prev_nominal_close
            numerator = current_close if event else current_close + dividends[pos]
            growth = float(numerator / denominator)
            current_research_close = prev_research_close * growth
            research_values[pos] = corrected_values[pos] * (current_research_close / current_close)
            economic_values[pos] = growth - 1.0
            prev_research_close = current_research_close
            prev_nominal_close = current_close
    research = pd.DataFrame(research_values, index=out.index, columns=OHLC)
    economic_return = pd.Series(economic_values, index=out.index, dtype=float)
    for column in OHLC:
        out[f"research_{column}"] = research[column]
        out.loc[unsafe, f"research_{column}"] = np.nan
    out["economic_return"] = economic_return
    raw = out[[f"raw_{x}" for x in OHLC]].apply(pd.to_numeric, errors="coerce")
    missing = raw.isna().any(axis=1) | raw.le(0).any(axis=1)
    high_ok = raw["raw_high"].ge(raw[["raw_open", "raw_close", "raw_low"]].max(axis=1))
    low_ok = raw["raw_low"].le(raw[["raw_open", "raw_close", "raw_high"]].min(axis=1))
    bad_ohlc = ~missing & (~high_ok | ~low_ok)
    zero_volume = out["volume"].isna() | out["volume"].le(0)
    moving = raw["raw_close"].pct_change(fill_method=None).abs().gt(1e-12)
    ranged = raw["raw_high"].ne(raw["raw_low"])
    out["trading_status"] = np.select(
        [missing, bad_ohlc, zero_volume & (moving | ranged), zero_volume],
        ["UNRESOLVED_MISSING_PRICE", "UNRESOLVED_BAD_OHLC", "UNRESOLVED_MISSING_VOLUME", "UNRESOLVED_NO_TRADE_OR_STALE"],
        default="TRADED_PROVIDER",
    )
    bad = out["trading_status"].str.startswith("UNRESOLVED")
    out.loc[bad & out["price_quality"].ne("UNRESOLVED"), "price_quality"] = "UNRESOLVED"
    research_numeric = out[[f"research_{x}" for x in OHLC]].apply(pd.to_numeric, errors="coerce")
    out["trading_eligible"] = (
        out["price_quality"].isin(["VERIFIED", "RECONSTRUCTED", "PROVIDER_ONLY"])
        & out["trading_status"].eq("TRADED_PROVIDER")
        & research_numeric.notna().all(axis=1)
        & research_numeric.gt(0).all(axis=1)
    )
    out["ticker"] = symbol
    out.index.name = "date"
    columns = ["ticker", *[f"raw_{x}" for x in OHLC], *[f"provider_adjusted_{x}" for x in OHLC],
               *[f"research_{x}" for x in OHLC], "volume", "dividends", "provider_stock_splits",
               "economic_return", "price_quality", "corporate_action_flag", "trading_status",
               "trading_eligible", "source"]
    return out[columns]


def source_inventory() -> pd.DataFrame:
    return pd.DataFrame([
        {"source": "data/raw/*.parquet", "date_coverage": "mostly 2018-01-01..2026-09-15", "ticker_coverage": "88 configured equities plus market series", "event_types": "provider dividends/splits fields", "authority": "PROVIDER", "pit_suitability": "FAIL for action timing; five early adjustments"},
        {"source": "research/data/provider_snapshot", "date_coverage": "2018-01-01..2026-09-15", "ticker_coverage": "89/89 requested", "event_types": "provider raw/adjusted OHLCV, dividends, splits", "authority": "PROVIDER", "pit_suitability": "PARTIAL; raw label repeats early action errors"},
        {"source": "research/contracts/exp_data_004_official_events.json", "date_coverage": "2024-08-13..2026-08-05", "ticker_coverage": "5 regression tickers", "event_types": "bonus and rights issues; separate announcement/effective/ex dates", "authority": "OFFICIAL_KAP_CURATED", "pit_suitability": "PASS for captured effective/ex dates; announcement 3/5"},
        {"source": "data/events.csv", "date_coverage": "2018..2026", "ticker_coverage": "market-wide synthetic", "event_types": "fixed financial-report calendar only", "authority": "DERIVED", "pit_suitability": "FAIL for corporate actions"},
        {"source": "data/kap_vbts_arsiv.csv", "date_coverage": "none", "ticker_coverage": "none", "event_types": "header only", "authority": "INTENDED_OFFICIAL_CACHE", "pit_suitability": "FAIL; zero rows"},
        {"source": "scripts KAP HTML/API experiments", "date_coverage": "ad hoc", "ticker_coverage": "ad hoc", "event_types": "disclosure-page experiments", "authority": "OFFICIAL_PAGE_EXPERIMENT", "pit_suitability": "FAIL; no normalized retained master"},
        {"source": "features/kap_scraper caches", "date_coverage": "quarterly fundamentals", "ticker_coverage": "configured equities", "event_types": "financial statements, not corporate actions", "authority": "PROVIDER/DERIVED", "pit_suitability": "NOT_APPLICABLE"},
        {"source": "listing/delist/ticker/merger/status master", "date_coverage": "missing", "ticker_coverage": "missing", "event_types": "first trade, delist, rename, merger, demerger, suspension", "authority": "MISSING", "pit_suitability": "FAIL"},
    ])


def build_all_views(contract: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    VIEW_DIR.mkdir(parents=True, exist_ok=True)
    by_symbol = events_by_symbol(contract)
    manifest_rows = []
    for path in sorted(SNAPSHOT.glob("*.parquet")):
        stem = path.stem
        symbol = "XU100.IS" if stem == "IDX_XU100_IS" else stem.replace("_IS", ".IS")
        view = build_symbol_view(symbol, by_symbol.get(symbol, []))
        view.to_parquet(view_path(symbol))
        counts = view["price_quality"].value_counts().to_dict()
        manifest_rows.append({"symbol": symbol, "rows": len(view), "first_date": str(view.index.min().date()),
                              "last_date": str(view.index.max().date()), **{f"quality_{q.lower()}": int(counts.get(q, 0)) for q in QUALITY}})
    manifest = pd.DataFrame(manifest_rows).sort_values("symbol")
    quality = manifest[[f"quality_{q.lower()}" for q in QUALITY]].sum().rename(lambda x: x.replace("quality_", "").upper()).reset_index()
    quality.columns = ["price_quality", "rows"]
    return manifest, quality


def regression_table(contract: dict) -> pd.DataFrame:
    rows = []
    for event in contract["events"]:
        view = pd.read_parquet(view_path(event["symbol"]))
        pdate, exdate = pd.Timestamp(event["provider_adjusted_date"]), pd.Timestamp(event["ex_date"])
        prev = view.index[view.index < pdate][-1]
        provider_return = float(view.loc[pdate, "raw_close"] / view.loc[prev, "raw_close"] - 1.0)
        unsafe_rows = int(((view.index >= pdate) & (view.index < exdate) & view["research_close"].isna()).sum())
        pre = view.index[view.index < pdate]
        # Before detection, forward-chained research returns equal provider raw returns
        # (apart from already-observed dividends); the future event never rewrites rows.
        past_changed = int(view.loc[pre, "corporate_action_flag"].ne("NONE").sum())
        rows.append({
            "symbol": event["symbol"], "provider_adjusted_date": str(pdate.date()),
            "announcement_date": event["announcement_date"], "effective_date": event["effective_date"],
            "official_ex_date": str(exdate.date()), "provider_event_return": provider_return,
            "provider_window_research_quality": "UNRESOLVED", "unsafe_rows_quarantined": unsafe_rows,
            "economic_return_on_official_ex_date": float(view.loc[exdate, "economic_return"]) if exdate in view.index else np.nan,
            "official_ex_quality": view.loc[exdate, "price_quality"] if exdate in view.index else "NO_SESSION",
            "pre_provider_rows_rewritten_by_future_action": past_changed,
            "test_result": "PASS" if unsafe_rows > 0 and past_changed == 0 else "FAIL",
        })
    return pd.DataFrame(rows)


def regression_windows(contract: dict) -> pd.DataFrame:
    rows = []
    for event in contract["events"]:
        view = pd.read_parquet(view_path(event["symbol"])).sort_index()
        for anchor_type, anchor_value in (("PROVIDER_ADJUSTED_DATE", event["provider_adjusted_date"]),
                                          ("OFFICIAL_EX_DATE", event["ex_date"])):
            anchor = pd.Timestamp(anchor_value)
            if anchor not in view.index:
                continue
            anchor_pos = view.index.get_loc(anchor)
            for offset in range(-2, 3):
                pos = anchor_pos + offset
                if pos < 0 or pos >= len(view):
                    continue
                date = view.index[pos]
                row = view.iloc[pos]
                rows.append({
                    "symbol": event["symbol"], "anchor_type": anchor_type,
                    "anchor_date": str(anchor.date()), "session_offset": offset, "date": str(date.date()),
                    "raw_close_provider_label": row["raw_close"],
                    "provider_adjusted_close": row["provider_adjusted_close"],
                    "research_close": row["research_close"], "economic_return": row["economic_return"],
                    "price_quality": row["price_quality"], "corporate_action_flag": row["corporate_action_flag"],
                    "trading_status": row["trading_status"],
                })
    return pd.DataFrame(rows)


def status_coverage(manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    status_frames, flag_frames = [], []
    for symbol in manifest["symbol"]:
        view = pd.read_parquet(view_path(symbol))
        status_frames.append(view["trading_status"].value_counts().rename_axis("trading_status").reset_index(name="rows").assign(symbol=symbol))
        flag_frames.append(view["corporate_action_flag"].value_counts().rename_axis("corporate_action_flag").reset_index(name="rows").assign(symbol=symbol))
    status = pd.concat(status_frames, ignore_index=True)
    flags = pd.concat(flag_frames, ignore_index=True)
    return status[["symbol", "trading_status", "rows"]], flags[["symbol", "corporate_action_flag", "rows"]]


def sasa_investigation() -> tuple[pd.DataFrame, dict]:
    view = pd.read_parquet(view_path("SASA.IS"))
    subset = view.loc["2025":"2026"].copy()
    zero = subset[subset["volume"].le(0)].copy()
    zero["raw_return"] = subset["raw_close"].pct_change(fill_method=None).reindex(zero.index)
    zero["adjusted_return"] = subset["provider_adjusted_close"].pct_change(fill_method=None).reindex(zero.index)
    zero["adjustment_ratio"] = zero["provider_adjusted_close"] / zero["raw_close"]
    summary = {
        "zero_volume_rows": int(len(zero)),
        "moving_price_rows": int(zero["raw_return"].abs().gt(1e-12).sum()),
        "flat_price_rows": int(zero["raw_return"].abs().le(1e-12).sum()),
        "nonzero_range_rows": int(zero["raw_high"].ne(zero["raw_low"]).sum()),
        "adjustment_ratio_unique_rounded": int(zero["adjustment_ratio"].round(10).nunique()),
        "dividend_rows": int(zero["dividends"].gt(0).sum()),
        "split_rows": int(zero["provider_stock_splits"].gt(0).sum()),
        "classification": "UNRESOLVED_PROVIDER_VOLUME_FIELD_DEFECT",
    }
    return zero, summary


def load_authoritative_panels() -> tuple[pd.DatetimeIndex, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    benchmark = pd.read_parquet(view_path("XU100.IS")).sort_index()
    calendar = pd.DatetimeIndex(benchmark.loc[START:END].index)
    opens, closes, valid = {}, {}, {}
    for symbol in cfg.HISSELER:
        df = pd.read_parquet(view_path(symbol)).sort_index().reindex(calendar)
        opens[symbol] = pd.to_numeric(df["research_open"], errors="coerce")
        closes[symbol] = pd.to_numeric(df["research_close"], errors="coerce")
        valid[symbol] = df["trading_eligible"].fillna(False).astype(bool)
    return calendar, pd.DataFrame(opens), pd.DataFrame(closes), pd.DataFrame(valid)


def authoritative_benchmark_nav(cost_bps: int, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    df = pd.read_parquet(view_path("XU100.IS")).sort_index().reindex(calendar)
    op, cl = df["research_open"], df["research_close"]
    start, entry = LOOKBACK_LONG, LOOKBACK_LONG + 1
    values = [1.0]
    dates = [calendar[start]]
    equity = (1 - cost_bps / 10000) * float(cl.iloc[entry] / op.iloc[entry])
    values.append(equity); dates.append(calendar[entry])
    for pos in range(entry + 1, len(calendar)):
        equity *= float(cl.iloc[pos] / cl.iloc[pos - 1])
        values.append(equity); dates.append(calendar[pos])
    values[-1] *= 1 - cost_bps / 10000
    return pd.DataFrame({"equity": values}, index=pd.DatetimeIndex(dates))


def baseline_sensitivity() -> tuple[pd.DataFrame, pd.DataFrame]:
    prior = pd.read_csv(RESULTS / "EXP-DATA-003_baseline_comparison.csv")
    prior = prior[prior["view"].isin(["AS_IS", "RECONCILED"])].copy()
    prior["view"] = prior["view"].replace({"RECONCILED": "EXP_DATA_003_RECONCILED"})
    old_trades = pd.read_csv(RESULTS / "EXP-BASE-001_trades.csv")
    old_trades = old_trades[(old_trades["cost_bps"] == 50) & old_trades["signal_date"].notna()]
    d3_trades = pd.read_csv(RESULTS / "EXP-DATA-003_reconciled_trades.csv")
    turnover_lookup = {("AS_IS", s): float(g["turnover_two_sided_notional"].sum()) for s, g in old_trades.groupby("strategy")}
    turnover_lookup.update({("EXP_DATA_003_RECONCILED", s): float(g["turnover_two_sided_notional"].sum()) for s, g in d3_trades.groupby("strategy")})
    prior["rebalance_turnover"] = [2.0 if s == "BIST100" else turnover_lookup.get((v, s), np.nan) for v, s in zip(prior["view"], prior["strategy"])]
    prior["unavailable_observations"] = prior["missing_or_last_valid_mark_events"]

    calendar, opens, closes, valid = load_authoritative_panels()
    rows, trades = [], []
    bm = authoritative_benchmark_nav(50, calendar)
    rows.append({"view": "AUTHORITATIVE_RESEARCH_VIEW", "strategy": "BIST100", "cost_bps": 50,
                 "missing_or_last_valid_mark_events": 0, "unfilled_orders": 0,
                 "rebalance_turnover": 2.0, "unavailable_observations": 0, **metrics(bm["equity"])})
    for name, selector in (("UNIVERSE_EQUAL_WEIGHT", reconciled_equal_selector), ("MOMENTUM_12_1_TOP10", reconciled_momentum_selector)):
        sim = simulate_reconciled(name, calendar, opens, closes, valid, selector, 50)
        rows.append({"view": "AUTHORITATIVE_RESEARCH_VIEW", "strategy": name, "cost_bps": 50,
                     "missing_or_last_valid_mark_events": sim.last_valid_mark_events,
                     "unfilled_orders": sim.unfilled_orders,
                     "rebalance_turnover": float(sim.trades["turnover_two_sided_notional"].sum()),
                     "unavailable_observations": sim.last_valid_mark_events, **metrics(sim.daily["equity"])})
        sim.daily.to_csv(RESULTS / f"EXP-DATA-004_{name.lower()}_authoritative_daily.csv")
        trades.append(sim.trades.assign(view="AUTHORITATIVE_RESEARCH_VIEW"))
    combined = pd.concat([prior, pd.DataFrame(rows)], ignore_index=True, sort=False)
    return combined, pd.concat(trades, ignore_index=True)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    inventory = source_inventory()
    manifest, quality = build_all_views(contract)
    regressions = regression_table(contract)
    windows = regression_windows(contract)
    statuses, flags = status_coverage(manifest)
    sasa, sasa_summary = sasa_investigation()
    baselines, trades = baseline_sensitivity()
    inventory.to_csv(RESULTS / "EXP-DATA-004_source_inventory.csv", index=False)
    manifest.to_csv(RESULTS / "EXP-DATA-004_price_view_manifest.csv", index=False)
    quality.to_csv(RESULTS / "EXP-DATA-004_quality_coverage.csv", index=False)
    regressions.to_csv(RESULTS / "EXP-DATA-004_regression_events.csv", index=False)
    windows.to_csv(RESULTS / "EXP-DATA-004_regression_windows.csv", index=False)
    statuses.to_csv(RESULTS / "EXP-DATA-004_trading_status_coverage.csv", index=False)
    flags.to_csv(RESULTS / "EXP-DATA-004_corporate_flag_coverage.csv", index=False)
    sasa.to_csv(RESULTS / "EXP-DATA-004_sasa_zero_volume.csv")
    baselines.to_csv(RESULTS / "EXP-DATA-004_baseline_sensitivity.csv", index=False)
    trades.to_csv(RESULTS / "EXP-DATA-004_authoritative_trades.csv", index=False)
    summary = {
        "snapshot_symbols_ok": int(len(manifest)), "quality_rows": dict(zip(quality["price_quality"], quality["rows"].astype(int))),
        "regression_tests": regressions["test_result"].value_counts().to_dict(),
        "trading_status_rows": statuses.groupby("trading_status")["rows"].sum().astype(int).to_dict(),
        "sasa": sasa_summary,
        "price_gate": "PARTIAL",
    }
    (RESULTS / "EXP-DATA-004_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
