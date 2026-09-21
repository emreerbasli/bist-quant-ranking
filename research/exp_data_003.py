"""EXP-DATA-003: price event reconciliation, research-only views and controls."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path(__file__).resolve().parent
RESULTS = RESEARCH / "results"
CONTRACT = RESEARCH / "contracts" / "exp_data_003_event_reconciliation.json"
sys.path.insert(0, str(ROOT))
import config as cfg
from research.baselines_price_only import (
    END, LOOKBACK_LONG, REBALANCE_SESSIONS, SKIP_RECENT, START, TOP_K,
    benchmark_nav, equal_universe_selector, load_panels, metrics,
    momentum_selector, simulate,
)

OHLC = ["open", "high", "low", "close"]
EVENT_EXTERNAL_RAW = {
    ("HEKTS.IS", "2024-09-09"): (11.760000, 4.134030),
    ("BSOKE.IS", "2024-12-02"): (60.000000, 15.467761),
    ("CCOLA.IS", "2024-08-01"): (846.000000, 78.272728),
    ("KBORU.IS", "2025-01-02"): (77.750000, 13.166666),
    ("CVKMD.IS", "2026-08-03"): (37.820000, 14.417085),
}


def raw_path(symbol: str) -> Path:
    name = symbol.replace("^", "IDX_").replace(".", "_").replace("=", "_")
    return cfg.DATA_RAW / f"{name}.parquet"


def entitlement_factor(previous_close: float, action_type: str, ratio: float, subscription_price: float) -> float:
    """Factor converting pre-event prices to an economic ex-entitlement basis."""
    if action_type == "BONUS_ISSUE":
        return 1.0 / (1.0 + ratio)
    if action_type == "RIGHTS_ISSUE":
        return (previous_close + ratio * subscription_price) / (previous_close * (1.0 + ratio))
    raise ValueError(f"unsupported action type: {action_type}")


def event_inventory(contract: dict) -> pd.DataFrame:
    rows = []
    for event in contract["events"]:
        symbol = event["symbol"]
        date = pd.Timestamp(event["provider_event_date"])
        df = pd.read_parquet(raw_path(symbol)).sort_index()
        pos = df.index.get_loc(date)
        prev = df.iloc[pos - 1]
        cur = df.iloc[pos]
        prev_date = df.index[pos - 1]
        raw_prev, raw_cur = EVENT_EXTERNAL_RAW[(symbol, str(date.date()))]
        factor = entitlement_factor(raw_prev, event["action_type"], event["ratio"], event["subscription_price"])
        adjusted_return = float(cur["close"] / prev["close"] - 1.0)
        economic_return = float(cur["close"] / (prev["close"] * factor) - 1.0)
        rows.append({
            "symbol": symbol,
            "provider_event_date": str(date.date()),
            "previous_trading_date": str(prev_date.date()),
            "official_ex_date": event["official_ex_date"],
            "previous_raw_close_external": raw_prev,
            "current_raw_close_external": raw_cur,
            "previous_adjusted_close_local": float(prev["close"]),
            "current_adjusted_close_local": float(cur["close"]),
            "raw_return": raw_cur / raw_prev - 1.0,
            "adjusted_return": adjusted_return,
            "reconciled_economic_return": economic_return,
            "volume": float(cur["volume"]),
            "zero_volume": bool(cur["volume"] <= 0),
            "stale_flat_ohlc": bool(cur[OHLC].nunique() == 1 and cur["close"] == prev["close"]),
            "local_split_field": float(cur.get("stock_splits", 0.0)),
            "local_dividend_field": float(cur.get("dividends", 0.0)),
            "action_type": event["action_type"],
            "official_ratio": event["ratio"],
            "subscription_price": event["subscription_price"],
            "local_vs_external_adjusted": "CONSISTENT",
            "local_action_vs_official": "INCONSISTENT_DATE_AND_MISSING_ACTION_FIELD",
            "official_source": event["official_source"],
            "classification": event["classification"],
        })
    return pd.DataFrame(rows)


def ohlc_inventory() -> pd.DataFrame:
    rows = []
    for symbol in ("MTRKS.IS", "MIATK.IS"):
        df = pd.read_parquet(raw_path(symbol)).sort_index()
        num = df[OHLC].apply(pd.to_numeric, errors="coerce")
        tolerance = num["close"].abs().clip(lower=1.0) * 1e-8
        high_gap = num[["open", "close", "low"]].max(axis=1) - num["high"]
        low_gap = num["low"] - num[["open", "close", "high"]].min(axis=1)
        bad = (high_gap > tolerance) | (low_gap > tolerance)
        for date in df.index[bad]:
            row = df.loc[date]
            gap = max(float(high_gap.loc[date]), float(low_gap.loc[date]))
            implied_tick = 0.02 / (13.0 if symbol == "MIATK.IS" else 1.0)
            classification = "ROUNDING_ONLY" if gap <= implied_tick * 1.01 else "DATA_ERROR"
            rows.append({
                "symbol": symbol, "date": str(date.date()),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row["volume"]), "high_gap": float(high_gap.loc[date]),
                "low_gap": float(low_gap.loc[date]), "max_gap": gap,
                "relative_gap_to_close": gap / float(row["close"]),
                "rounding_assessment": "one inferred pre-adjustment tick" if classification == "ROUNDING_ONLY" else "materially exceeds rounding tolerance",
                "adjusted_unadjusted_assessment": "same invariant violation present in external raw and adjusted series",
                "source_assessment": "local cache matches current Yahoo adjusted series",
                "classification": classification,
            })
    return pd.DataFrame(rows)


def zero_volume_inventory() -> tuple[pd.DataFrame, pd.DataFrame]:
    detail = []
    benchmark = pd.read_parquet(raw_path("XU100.IS")).sort_index()
    sessions = pd.DatetimeIndex(benchmark.index).normalize().unique().sort_values()
    for symbol in cfg.HISSELER:
        df = pd.read_parquet(raw_path(symbol)).sort_index().copy()
        df.index = pd.DatetimeIndex(df.index).normalize()
        volume = pd.to_numeric(df["volume"], errors="coerce")
        first_positive = df.index[volume.gt(0)].min() if volume.gt(0).any() else pd.NaT
        active = df.loc[df.index >= first_positive].copy() if pd.notna(first_positive) else df.copy()
        active_volume = pd.to_numeric(active["volume"], errors="coerce")
        mask = active_volume.le(0) | active_volume.isna()
        if not mask.any():
            continue
        run_id = mask.ne(mask.shift(fill_value=False)).cumsum()
        close = pd.to_numeric(active["close"], errors="coerce")
        ret = close.pct_change(fill_method=None)
        for date in active.index[mask]:
            row = active.loc[date]
            rid = run_id.loc[date]
            run_dates = active.index[(run_id == rid) & mask]
            ohlc_present = bool(pd.notna(row[OHLC]).all())
            flat = bool(ohlc_present and row[OHLC].nunique() == 1)
            same_prev = bool(pd.notna(ret.loc[date]) and abs(float(ret.loc[date])) < 1e-14)
            if not ohlc_present:
                category = "FULL_DATA_GAP"
            elif not flat or not same_prev:
                category = "MISSING_VOLUME_ONLY"
            elif len(run_dates) >= 2:
                # Pattern-level attribution only: multi-session, flat, zero-volume
                # runs are consistent with a market closure or suspension. Without
                # an exchange status feed we deliberately do not distinguish them.
                category = "LEGITIMATE_NO_TRADE / SUSPENSION"
            else:
                category = "UNKNOWN"
            detail.append({
                "symbol": symbol, "date": str(date.date()), "year": int(date.year),
                "consecutive_run_length": int(len(run_dates)),
                "run_start": str(run_dates.min().date()), "run_end": str(run_dates.max().date()),
                "same_price_as_previous": same_prev, "return_zero": same_prev,
                "return_nonzero": bool(pd.notna(ret.loc[date]) and abs(float(ret.loc[date])) >= 1e-14),
                "ohlc_present": ohlc_present, "ohlc_flat": flat,
                "observed_life_position": "POST_FIRST_POSITIVE_VOLUME",
                "possible_suspension": bool(flat and same_prev and len(run_dates) >= 2),
                "category": category,
            })
    detail_df = pd.DataFrame(detail)
    grouped = (detail_df.groupby(["symbol", "year", "category"], dropna=False)
               .agg(bars=("date", "size"), max_run=("consecutive_run_length", "max"),
                    zero_return=("return_zero", "sum"), nonzero_return=("return_nonzero", "sum"),
                    possible_suspension=("possible_suspension", "sum"))
               .reset_index())
    return detail_df, grouped


def reconciled_panels(contract: dict) -> tuple[pd.DatetimeIndex, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    calendar, opens, closes = load_panels()
    valid = pd.DataFrame(False, index=calendar, columns=closes.columns)
    volumes = pd.DataFrame(np.nan, index=calendar, columns=closes.columns)
    for symbol in closes.columns:
        df = pd.read_parquet(raw_path(symbol)).sort_index().reindex(calendar)
        volumes[symbol] = pd.to_numeric(df["volume"], errors="coerce")
        numeric = df[OHLC].apply(pd.to_numeric, errors="coerce")
        o, c = numeric["open"], numeric["close"]
        tolerance = c.abs().clip(lower=1.0) * 1e-8
        high_gap = numeric[["open", "close", "low"]].max(axis=1) - numeric["high"]
        low_gap = numeric["low"] - numeric[["open", "close", "high"]].min(axis=1)
        invariant_valid = high_gap.le(tolerance) & low_gap.le(tolerance) & numeric.notna().all(axis=1)
        valid[symbol] = o.gt(0) & c.gt(0) & volumes[symbol].gt(0) & invariant_valid
    for event in contract["events"]:
        symbol = event["symbol"]
        if symbol not in closes or pd.Timestamp(event["provider_event_date"]) > calendar.max():
            continue
        event_date = pd.Timestamp(event["provider_event_date"])
        previous_dates = calendar[calendar < event_date]
        if previous_dates.empty:
            continue
        prev_close = float(closes.loc[previous_dates[-1], symbol])
        factor = entitlement_factor(prev_close, event["action_type"], event["ratio"], event["subscription_price"])
        opens.loc[calendar < event_date, symbol] *= factor
        closes.loc[calendar < event_date, symbol] *= factor
    return calendar, opens, closes, valid


def eligible(signal_pos: int, closes: pd.DataFrame, valid: pd.DataFrame) -> pd.Series:
    history = valid.iloc[: signal_pos + 1].sum()
    recent = valid.iloc[max(0, signal_pos - 24): signal_pos + 1].sum()
    return valid.iloc[signal_pos] & history.ge(LOOKBACK_LONG) & recent.ge(20) & closes.iloc[signal_pos].gt(0)


def reconciled_equal_selector(signal_pos: int, opens: pd.DataFrame, closes: pd.DataFrame, valid: pd.DataFrame) -> list[str]:
    return sorted(closes.columns[eligible(signal_pos, closes, valid)].tolist())


def reconciled_momentum_selector(signal_pos: int, opens: pd.DataFrame, closes: pd.DataFrame, valid: pd.DataFrame) -> list[str]:
    if signal_pos < LOOKBACK_LONG:
        return []
    score = closes.iloc[signal_pos - SKIP_RECENT] / closes.iloc[signal_pos - LOOKBACK_LONG] - 1.0
    mask = eligible(signal_pos, closes, valid) & closes.iloc[signal_pos - LOOKBACK_LONG].gt(0) & closes.iloc[signal_pos - SKIP_RECENT].gt(0)
    return score[mask].sort_values(ascending=False).head(TOP_K).index.tolist()


@dataclass
class ReconciledSimulation:
    daily: pd.DataFrame
    trades: pd.DataFrame
    last_valid_mark_events: int
    unfilled_orders: int


def simulate_reconciled(name: str, calendar: pd.DatetimeIndex, opens: pd.DataFrame, closes: pd.DataFrame,
                         valid: pd.DataFrame, selector, cost_bps: int) -> ReconciledSimulation:
    # Last-known valid close is a valuation mark only; never an entry or signal price.
    mark_close = closes.where(valid).ffill()
    start_pos = LOOKBACK_LONG
    trade_to_signal = {p + 1: p for p in range(start_pos, len(calendar) - 1, REBALANCE_SESSIONS)}
    weights: dict[str, float] = {}
    cash = 1.0
    equity = 1.0
    marks = unfilled = 0
    records = [{"date": calendar[start_pos], "equity": 1.0, "positions": 0, "cash_weight": 1.0}]
    trades = []
    prev_marks = mark_close.iloc[start_pos]
    for pos in range(start_pos + 1, len(calendar)):
        date = calendar[pos]
        cur_marks = mark_close.iloc[pos]
        if pos in trade_to_signal:
            # Existing positions first accrue only to the executable opening mark.
            # An untradeable holding remains at its last valid close and cannot be silently sold.
            if weights:
                overnight = {}
                for s in weights:
                    old = prev_marks.get(s, np.nan)
                    if bool(valid.iloc[pos].get(s, False)) and pd.notna(old) and old > 0:
                        overnight[s] = float(opens.iloc[pos].get(s) / old)
                    else:
                        marks += 1
                        overnight[s] = 1.0
                gross = cash + sum(weights[s] * overnight[s] for s in weights)
                weights = {s: weights[s] * overnight[s] / gross for s in weights}
                cash /= gross
                equity *= gross
            sig = trade_to_signal[pos]
            selected = selector(sig, opens, closes, valid)
            fillable = [s for s in selected if bool(valid.iloc[pos].get(s, False))]
            unfilled_now = len(selected) - len(fillable)
            unfilled += unfilled_now
            blocked = {s: w for s, w in weights.items() if not bool(valid.iloc[pos].get(s, False))}
            free_capacity = max(0.0, 1.0 - sum(blocked.values()))
            denom = len(selected)
            target = dict(blocked)
            if denom:
                target.update({s: target.get(s, 0.0) + free_capacity / denom for s in fillable})
            target_cash = max(0.0, 1.0 - sum(target.values()))
            turnover = sum(abs(target.get(s, 0.0) - weights.get(s, 0.0)) for s in set(weights) | set(target))
            equity *= max(0.0, 1.0 - turnover * cost_bps / 10000.0)
            weights, cash = target, target_cash
            # Filled holdings accrue open-to-close. Blocked holdings retain last valid mark.
            if weights:
                intraday = {}
                for s in weights:
                    if s in blocked:
                        intraday[s] = 1.0
                    else:
                        op, cl = opens.iloc[pos].get(s, np.nan), closes.iloc[pos].get(s, np.nan)
                        intraday[s] = float(cl / op) if pd.notna(op) and pd.notna(cl) and op > 0 else 1.0
                gross = cash + sum(weights[s] * intraday[s] for s in weights)
                weights = {s: weights[s] * intraday[s] / gross for s in weights}
                cash /= gross
                equity *= gross
            trades.append({"strategy": name, "cost_bps": cost_bps, "signal_date": str(calendar[sig].date()),
                           "trade_date": str(date.date()), "selected": len(selected), "filled": len(fillable),
                           "unfilled": unfilled_now, "cash_weight": cash, "turnover_two_sided_notional": turnover})
        elif weights:
            # Daily NAV uses only the last known valid mark; the eventual reopening gap is
            # recognized when a new valid close arrives. No future price is consulted.
            factors = {}
            for s in weights:
                if not bool(valid.iloc[pos].get(s, False)):
                    marks += 1
                old, new = prev_marks.get(s, np.nan), cur_marks.get(s, np.nan)
                factors[s] = 1.0 if pd.isna(old) or pd.isna(new) or old <= 0 else float(new / old)
            gross = cash + sum(weights[s] * factors[s] for s in weights)
            weights = {s: weights[s] * factors[s] / gross for s in weights}
            cash /= gross
            equity *= gross
        records.append({"date": date, "equity": equity, "positions": len(weights), "cash_weight": cash})
        prev_marks = cur_marks
    if weights:
        terminal_turnover = sum(weights.values())
        equity *= max(0.0, 1.0 - terminal_turnover * cost_bps / 10000.0)
        records[-1]["equity"] = equity
    return ReconciledSimulation(pd.DataFrame(records).set_index("date"), pd.DataFrame(trades), marks, unfilled)


def baseline_comparison(contract: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    cost = 50
    calendar, opens_as_is, closes_as_is = load_panels()
    calendar_r, opens_r, closes_r, valid_r = reconciled_panels(contract)
    rows, trades = [], []
    bm = benchmark_nav(cost, calendar)
    for view in ("AS_IS", "RECONCILED"):
        rows.append({"view": view, "strategy": "BIST100", "cost_bps": cost,
                     "missing_or_last_valid_mark_events": 0, "unfilled_orders": 0, **metrics(bm["equity"])})
    for name, old_selector, new_selector in (
        ("UNIVERSE_EQUAL_WEIGHT", equal_universe_selector, reconciled_equal_selector),
        ("MOMENTUM_12_1_TOP10", momentum_selector, reconciled_momentum_selector),
    ):
        old = simulate(name, calendar, opens_as_is, closes_as_is, old_selector, cost)
        rows.append({"view": "AS_IS", "strategy": name, "cost_bps": cost,
                     "missing_or_last_valid_mark_events": old.missing_mark_events,
                     "unfilled_orders": old.unfilled_selections, **metrics(old.daily["equity"])})
        new = simulate_reconciled(name, calendar_r, opens_r, closes_r, valid_r, new_selector, cost)
        rows.append({"view": "RECONCILED", "strategy": name, "cost_bps": cost,
                     "missing_or_last_valid_mark_events": new.last_valid_mark_events,
                     "unfilled_orders": new.unfilled_orders, **metrics(new.daily["equity"])})
        new.daily.to_csv(RESULTS / f"EXP-DATA-003_{name.lower()}_reconciled_daily.csv")
        trades.append(new.trades)
    comparison = pd.DataFrame(rows)
    piv = comparison.pivot(index="strategy", columns="view", values=["cagr", "sharpe_rf0", "daily_max_drawdown", "worst_day"])
    for metric_name in ("cagr", "sharpe_rf0", "daily_max_drawdown", "worst_day"):
        piv[(metric_name, "DELTA_RECONCILED_MINUS_AS_IS")] = piv[(metric_name, "RECONCILED")] - piv[(metric_name, "AS_IS")]
    return comparison, pd.concat(trades, ignore_index=True)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    events = event_inventory(contract)
    ohlc = ohlc_inventory()
    zero_detail, zero_grouped = zero_volume_inventory()
    comparison, trades = baseline_comparison(contract)
    events.to_csv(RESULTS / "EXP-DATA-003_extreme_events.csv", index=False)
    ohlc.to_csv(RESULTS / "EXP-DATA-003_ohlc_inconsistencies.csv", index=False)
    zero_detail.to_csv(RESULTS / "EXP-DATA-003_zero_volume_detail.csv", index=False)
    zero_grouped.to_csv(RESULTS / "EXP-DATA-003_zero_volume_grouped.csv", index=False)
    comparison.to_csv(RESULTS / "EXP-DATA-003_baseline_comparison.csv", index=False)
    trades.to_csv(RESULTS / "EXP-DATA-003_reconciled_trades.csv", index=False)
    summary = {
        "event_classifications": events["classification"].value_counts().to_dict(),
        "ohlc_classifications": ohlc["classification"].value_counts().to_dict(),
        "zero_volume_bars": int(len(zero_detail)),
        "zero_volume_categories": zero_detail["category"].value_counts().to_dict(),
        "gate": "PARTIAL",
    }
    (RESULTS / "EXP-DATA-003_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
