"""Price-only diagnostic baselines under the precommitted control contract."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path(__file__).resolve().parent
RESULTS = RESEARCH / "results"
sys.path.insert(0, str(ROOT))
import config as cfg

START = pd.Timestamp("2019-01-01")
END = pd.Timestamp("2025-05-30")
REBALANCE_SESSIONS = 60
LOOKBACK_LONG = 252
SKIP_RECENT = 21
TOP_K = 10
COSTS_BPS = (0, 30, 50, 100)


def _path(symbol: str) -> Path:
    name = symbol.replace("^", "IDX_").replace(".", "_").replace("=", "_")
    return cfg.DATA_RAW / f"{name}.parquet"


def load_panels() -> tuple[pd.DatetimeIndex, pd.DataFrame, pd.DataFrame]:
    benchmark = pd.read_parquet(_path("XU100.IS")).sort_index()
    calendar = pd.DatetimeIndex(benchmark.loc[START:END].index).sort_values().unique()
    opens, closes = {}, {}
    for symbol in cfg.HISSELER:
        path = _path(symbol)
        if not path.exists():
            continue
        df = pd.read_parquet(path).sort_index()
        opens[symbol] = pd.to_numeric(df["open"], errors="coerce").reindex(calendar)
        closes[symbol] = pd.to_numeric(df["close"], errors="coerce").reindex(calendar)
    return calendar, pd.DataFrame(opens, index=calendar), pd.DataFrame(closes, index=calendar)


def equal_universe_selector(signal_pos: int, opens: pd.DataFrame, closes: pd.DataFrame) -> list[str]:
    signal = closes.iloc[signal_pos]
    history = closes.iloc[: signal_pos + 1].notna().sum()
    return sorted(signal.index[(signal > 0) & (history >= LOOKBACK_LONG)].tolist())


def momentum_selector(signal_pos: int, opens: pd.DataFrame, closes: pd.DataFrame) -> list[str]:
    if signal_pos < LOOKBACK_LONG:
        return []
    p_long = closes.iloc[signal_pos - LOOKBACK_LONG]
    p_skip = closes.iloc[signal_pos - SKIP_RECENT]
    history = closes.iloc[: signal_pos + 1].notna().sum()
    momentum = p_skip / p_long - 1.0
    eligible = (p_long > 0) & (p_skip > 0) & (history >= LOOKBACK_LONG)
    return momentum[eligible].sort_values(ascending=False).head(TOP_K).index.tolist()


@dataclass
class Simulation:
    daily: pd.DataFrame
    trades: pd.DataFrame
    missing_mark_events: int
    unfilled_selections: int


def simulate(
    name: str,
    calendar: pd.DatetimeIndex,
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    selector: Callable[[int, pd.DataFrame, pd.DataFrame], list[str]],
    cost_bps: int,
) -> Simulation:
    start_pos = LOOKBACK_LONG
    signal_positions = list(range(start_pos, len(calendar) - 1, REBALANCE_SESSIONS))
    trade_to_signal = {pos + 1: pos for pos in signal_positions}
    weights: dict[str, float] = {}
    equity = 1.0
    records = [{"date": calendar[start_pos], "equity_before_terminal_liquidation": 1.0, "equity": 1.0, "positions": 0}]
    trade_records = []
    missing_marks = unfilled = 0
    prev_close: pd.Series | None = None

    for pos in range(start_pos + 1, len(calendar)):
        date = calendar[pos]
        current_open = opens.iloc[pos]
        current_close = closes.iloc[pos]

        if prev_close is None:
            prev_close = closes.iloc[pos - 1]

        if pos in trade_to_signal:
            # Old holdings participate in the overnight move before the new trade.
            if weights:
                factors = []
                for symbol, weight in weights.items():
                    old = prev_close.get(symbol, np.nan)
                    new = current_open.get(symbol, np.nan)
                    if pd.isna(old) or pd.isna(new) or old <= 0 or new <= 0:
                        missing_marks += 1
                        factor = 1.0
                    else:
                        factor = float(new / old)
                    factors.append((symbol, weight, factor))
                gross = sum(weight * factor for _, weight, factor in factors)
                equity *= gross
                weights = {symbol: weight * factor / gross for symbol, weight, factor in factors} if gross > 0 else {}

            selected = selector(trade_to_signal[pos], opens, closes)
            fillable = [s for s in selected if pd.notna(current_open.get(s)) and current_open.get(s) > 0]
            unfilled += len(selected) - len(fillable)
            target = {s: 1.0 / len(fillable) for s in fillable} if fillable else {}
            symbols = set(weights) | set(target)
            turnover = sum(abs(target.get(s, 0.0) - weights.get(s, 0.0)) for s in symbols)
            cost = turnover * cost_bps / 10000.0
            equity *= max(0.0, 1.0 - cost)
            weights = target

            # New holdings participate in the entry-day open-to-close move.
            if weights:
                factors = []
                for symbol, weight in weights.items():
                    op = current_open.get(symbol, np.nan)
                    cl = current_close.get(symbol, np.nan)
                    if pd.isna(op) or pd.isna(cl) or op <= 0 or cl <= 0:
                        missing_marks += 1
                        factor = 1.0
                    else:
                        factor = float(cl / op)
                    factors.append((symbol, weight, factor))
                gross = sum(weight * factor for _, weight, factor in factors)
                equity *= gross
                weights = {symbol: weight * factor / gross for symbol, weight, factor in factors} if gross > 0 else {}
            trade_records.append({
                "strategy": name, "cost_bps": cost_bps,
                "signal_date": str(calendar[trade_to_signal[pos]].date()), "trade_date": str(date.date()),
                "selected": len(selected), "filled": len(fillable), "turnover_two_sided_notional": turnover,
                "cost_fraction": cost,
            })
        else:
            if weights:
                factors = []
                for symbol, weight in weights.items():
                    old = prev_close.get(symbol, np.nan)
                    new = current_close.get(symbol, np.nan)
                    if pd.isna(old) or pd.isna(new) or old <= 0 or new <= 0:
                        missing_marks += 1
                        factor = 1.0
                    else:
                        factor = float(new / old)
                    factors.append((symbol, weight, factor))
                gross = sum(weight * factor for _, weight, factor in factors)
                equity *= gross
                weights = {symbol: weight * factor / gross for symbol, weight, factor in factors} if gross > 0 else {}

        records.append({"date": date, "equity_before_terminal_liquidation": equity, "positions": len(weights)})
        prev_close = current_close

    if records and weights:
        terminal_turnover = sum(weights.values())
        terminal_cost = terminal_turnover * cost_bps / 10000.0
        equity *= max(0.0, 1.0 - terminal_cost)
        records[-1]["terminal_liquidation_cost"] = terminal_cost
        records[-1]["equity"] = equity
        trade_records.append({
            "strategy": name, "cost_bps": cost_bps, "signal_date": None,
            "trade_date": str(calendar[-1].date()), "selected": 0, "filled": 0,
            "turnover_two_sided_notional": terminal_turnover, "cost_fraction": terminal_cost,
        })
    daily = pd.DataFrame(records).set_index("date")
    if "equity" not in daily:
        daily["equity"] = daily["equity_before_terminal_liquidation"]
    else:
        daily["equity"] = daily["equity"].fillna(daily["equity_before_terminal_liquidation"])
    return Simulation(daily, pd.DataFrame(trade_records), missing_marks, unfilled)


def benchmark_nav(cost_bps: int, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    df = pd.read_parquet(_path("XU100.IS")).sort_index().reindex(calendar)
    op = pd.to_numeric(df["open"], errors="coerce")
    cl = pd.to_numeric(df["close"], errors="coerce")
    start_pos = LOOKBACK_LONG
    entry_pos = start_pos + 1
    dates = [calendar[start_pos]]
    values = [1.0]
    equity = (1.0 - cost_bps / 10000.0) * float(cl.iloc[entry_pos] / op.iloc[entry_pos])
    dates.append(calendar[entry_pos]); values.append(equity)
    for pos in range(entry_pos + 1, len(calendar)):
        equity *= float(cl.iloc[pos] / cl.iloc[pos - 1])
        dates.append(calendar[pos]); values.append(equity)
    values[-1] *= 1.0 - cost_bps / 10000.0
    return pd.DataFrame({"equity": values}, index=pd.DatetimeIndex(dates))


def metrics(nav: pd.Series) -> dict[str, float | int | None]:
    nav = nav.dropna()
    returns = nav.pct_change(fill_method=None).dropna()
    years = max(len(returns) / 252.0, 1 / 252.0)
    drawdown = nav / nav.cummax() - 1.0
    downside = returns[returns < 0]
    return {
        "observations": int(len(returns)),
        "cumulative_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
        "cagr": float((nav.iloc[-1] / nav.iloc[0]) ** (1.0 / years) - 1.0),
        "sharpe_rf0": float(np.sqrt(252) * returns.mean() / returns.std(ddof=1)) if returns.std(ddof=1) > 0 else None,
        "sortino_rf0": float(np.sqrt(252) * returns.mean() / downside.std(ddof=1)) if len(downside) > 1 and downside.std(ddof=1) > 0 else None,
        "daily_max_drawdown": float(drawdown.min()),
        "worst_day": float(returns.min()),
    }


def markdown_table(frame: pd.DataFrame) -> str:
    """Render a small report table without optional third-party dependencies."""
    shown = frame.copy()
    for column in shown.columns:
        shown[column] = shown[column].map(
            lambda value: "N/A" if pd.isna(value) else (f"{value:.6g}" if isinstance(value, (float, np.floating)) else str(value))
        )
    header = "| " + " | ".join(map(str, shown.columns)) + " |"
    divider = "|" + "|".join("---" for _ in shown.columns) + "|"
    rows = ["| " + " | ".join(row) + " |" for row in shown.astype(str).itertuples(index=False, name=None)]
    return "\n".join([header, divider, *rows])


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    calendar, opens, closes = load_panels()
    result_rows, all_trades = [], []
    for cost in COSTS_BPS:
        bm = benchmark_nav(cost, calendar)
        result_rows.append({"strategy": "BIST100", "cost_bps": cost, "evidence": "PROXY_UNVERIFIED", **metrics(bm["equity"])})
        for name, selector in (("UNIVERSE_EQUAL_WEIGHT", equal_universe_selector), ("MOMENTUM_12_1_TOP10", momentum_selector)):
            sim = simulate(name, calendar, opens, closes, selector, cost)
            result_rows.append({
                "strategy": name, "cost_bps": cost, "evidence": "PROXY_UNVERIFIED",
                "missing_mark_events": sim.missing_mark_events, "unfilled_selections": sim.unfilled_selections,
                **metrics(sim.daily["equity"]),
            })
            all_trades.append(sim.trades)
            sim.daily.to_csv(RESULTS / f"EXP-BASE-001_{name.lower()}_{cost}bps_daily.csv")
    results = pd.DataFrame(result_rows)
    results.to_csv(RESULTS / "EXP-BASE-001_price_baselines.csv", index=False)
    pd.concat(all_trades, ignore_index=True).to_csv(RESULTS / "EXP-BASE-001_trades.csv", index=False)
    unavailable = pd.DataFrame([
        {"baseline": "VALUE_QUALITY", "status": "N/A", "reason": "fundamental PIT/accounting gate not passed"},
        {"baseline": "V3", "status": "N/A", "reason": "common refit comparison requires unverified fundamental/macro inputs"},
        {"baseline": "V4_1", "status": "N/A", "reason": "common refit comparison requires unverified fundamental/macro inputs and old lockbox is contaminated"},
    ])
    unavailable.to_csv(RESULTS / "EXP-BASE-001_unavailable_baselines.csv", index=False)
    report = "# EXP-BASE-001 — Price-only diagnostic baselines\n\n**Gate: PARTIAL.** Results are descriptive and `PROXY_UNVERIFIED`; they cannot select a model, feature, target, horizon, or production change. The universe is the currently configured survivor list and corporate-action provenance is incomplete.\n\n" + markdown_table(results) + "\n\n## Unavailable common baselines\n\n" + markdown_table(unavailable) + "\n"
    (RESULTS / "EXP-BASE-001_report.md").write_text(report, encoding="utf-8")
    print(RESULTS / "EXP-BASE-001_report.md")


if __name__ == "__main__":
    main()
