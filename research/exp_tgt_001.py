"""EXP-TGT-001 — nested, price-only raw-return horizon comparison."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from temporal_validation import build_label_interval

RESEARCH = Path(__file__).resolve().parent
ROOT = RESEARCH.parent
CONTRACT_PATH = RESEARCH / "contracts" / "exp_tgt_001.json"
BASE_VIEW = RESEARCH / "data" / "price_view_data004"
OVERLAY_VIEW = RESEARCH / "data" / "price_view_data005_overlay"
RESULTS = RESEARCH / "results"
MANIFESTS = RESEARCH / "manifests"
FEATURES = ["mom_12_1", "mom_63", "vol_63"]
HORIZONS = (20, 40, 60)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_name(symbol: str) -> str:
    return symbol.replace("^", "IDX_").replace(".", "_") + ".parquet"


def symbol_from_path(path: Path) -> str:
    return "XU100.IS" if path.stem == "IDX_XU100_IS" else path.stem.replace("_IS", ".IS")


def load_view(symbol: str) -> pd.DataFrame:
    overlay = OVERLAY_VIEW / file_name(symbol)
    path = overlay if overlay.exists() else BASE_VIEW / file_name(symbol)
    return pd.read_parquet(path).sort_index()


def load_inputs(contract: dict):
    benchmark = load_view("XU100.IS")
    end = pd.Timestamp(contract["data_scope"]["end_date"])
    calendar = pd.DatetimeIndex(benchmark.index[benchmark.index <= end]).sort_values().unique()
    symbols = sorted(symbol_from_path(p) for p in BASE_VIEW.glob("*_IS.parquet") if p.stem not in {"IDX_XU100_IS", "XU100_IS"})
    views = {s: load_view(s).reindex(calendar) for s in symbols}
    return calendar, symbols, views, benchmark.reindex(calendar)


def signal_positions(calendar: pd.DatetimeIndex, warmup: int = 252, step: int = 60) -> list[int]:
    return list(range(warmup, len(calendar) - 1, step))


def feature_row(view: pd.DataFrame, pos: int) -> dict | None:
    eligible = view["trading_eligible"].fillna(False).to_numpy(bool)
    if not eligible[pos] or int(eligible[: pos + 1].sum()) < 252 or int(eligible[max(0, pos - 24):pos + 1].sum()) < 20:
        return None
    close = pd.to_numeric(view["research_close"], errors="coerce").to_numpy(float)
    past = close[: pos + 1][eligible[: pos + 1] & np.isfinite(close[: pos + 1]) & (close[: pos + 1] > 0)]
    if len(past) < 253:
        return None
    rets = pd.Series(past[-64:]).pct_change(fill_method=None).dropna()
    if len(rets) != 63:
        return None
    return {
        "mom_12_1": float(past[-22] / past[-253] - 1.0),
        "mom_63": float(past[-1] / past[-64] - 1.0),
        "vol_63": float(rets.std(ddof=1)),
    }


def build_dataset(calendar, symbols, views) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    feature_rows, label_rows, coverage_rows = [], [], []
    positions = signal_positions(calendar)
    for pos in positions:
        signal = calendar[pos]
        features_at_signal = []
        for symbol in symbols:
            row = feature_row(views[symbol], pos)
            if row is not None:
                row.update({"signal_date": signal, "symbol": symbol, "signal_pos": pos})
                feature_rows.append(row); features_at_signal.append((symbol, row))
        for horizon in HORIZONS:
            if pos + 1 + horizon >= len(calendar):
                continue
            interval = build_label_interval(calendar, signal, horizon)
            candidate = usable = 0
            start_pos = pos + 1; end_pos = start_pos + horizon
            for symbol, _ in features_at_signal:
                candidate += 1
                view = views[symbol]
                eligible = view["trading_eligible"].fillna(False).to_numpy(bool)
                quality = view["price_quality"].fillna("UNRESOLVED").astype(str).to_numpy()
                close = pd.to_numeric(view["research_close"], errors="coerce").to_numpy(float)
                ok = (eligible[start_pos] and eligible[end_pos] and
                      np.all(quality[start_pos:end_pos + 1] != "UNRESOLVED") and
                      np.isfinite(close[start_pos]) and np.isfinite(close[end_pos]) and
                      close[start_pos] > 0 and close[end_pos] > 0)
                if not ok:
                    continue
                usable += 1
                label_rows.append({"signal_date": signal, "symbol": symbol,
                                   "entry_date": interval.entry_date, "label_start": interval.label_start,
                                   "label_end": interval.label_end, "horizon_sessions": horizon,
                                   "raw_forward_return": float(close[end_pos] / close[start_pos] - 1.0)})
            coverage_rows.append({"signal_date": signal, "horizon_sessions": horizon,
                                  "candidate_observations": candidate, "usable_observations": usable,
                                  "coverage_pct": usable / candidate if candidate else np.nan})
    features = pd.DataFrame(feature_rows)
    labels = pd.DataFrame(label_rows)
    data = labels.merge(features, on=["signal_date", "symbol"], how="left", validate="many_to_one")
    data["target_rank"] = data.groupby(["signal_date", "horizon_sessions"])["raw_forward_return"].rank(pct=True, method="average")
    return features, data, pd.DataFrame(coverage_rows)


@dataclass
class RidgeControl:
    medians: np.ndarray
    means: np.ndarray
    scales: np.ndarray
    beta: np.ndarray


def fit_ridge(rows: pd.DataFrame, alpha: float = 1.0) -> RidgeControl:
    if rows.empty:
        raise ValueError("empty training data")
    x = rows[FEATURES].to_numpy(float); y = rows["target_rank"].to_numpy(float)
    med = np.nanmedian(x, axis=0); x = np.where(np.isfinite(x), x, med)
    mean = x.mean(axis=0); scale = x.std(axis=0, ddof=0); scale[scale < 1e-12] = 1.0
    z = (x - mean) / scale; design = np.column_stack([np.ones(len(z)), z])
    penalty = np.eye(design.shape[1]) * alpha; penalty[0, 0] = 0.0
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    return RidgeControl(med, mean, scale, beta)


def predict(model: RidgeControl, rows: pd.DataFrame) -> np.ndarray:
    x = rows[FEATURES].to_numpy(float); x = np.where(np.isfinite(x), x, model.medians)
    z = (x - model.means) / model.scales
    return np.column_stack([np.ones(len(z)), z]) @ model.beta


def ndcg_at_k(actual: np.ndarray, score: np.ndarray, k: int = 10) -> float:
    n = min(k, len(actual))
    if n == 0: return np.nan
    discounts = 1.0 / np.log2(np.arange(2, n + 2))
    chosen = actual[np.argsort(-score)[:n]]
    ideal = np.sort(actual)[::-1][:n]
    denom = float(np.sum(ideal * discounts))
    return float(np.sum(chosen * discounts) / denom) if denom > 0 else np.nan


def evaluate_predictions(model: RidgeControl, rows: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    scored = rows.copy(); scored["score"] = predict(model, scored)
    daily = []
    for date, grp in scored.groupby("signal_date"):
        if len(grp) < 10: continue
        ic = grp["score"].rank().corr(grp["raw_forward_return"].rank())
        daily.append({"signal_date": date, "rank_ic": ic,
                      "ndcg_at_10": ndcg_at_k(grp["target_rank"].to_numpy(), grp["score"].to_numpy(), 10),
                      "top10_forward_return": grp.nlargest(10, "score")["raw_forward_return"].mean(),
                      "cross_section_size": len(grp)})
    per_date = pd.DataFrame(daily)
    if per_date.empty:
        return {"signal_dates": 0, "observations": len(rows), "rank_ic_mean": np.nan, "rank_ic_median": np.nan,
                "positive_ic_ratio": np.nan, "ndcg_at_10_mean": np.nan}, per_date
    return {"signal_dates": len(per_date), "observations": len(rows),
            "rank_ic_mean": float(per_date.rank_ic.mean()), "rank_ic_median": float(per_date.rank_ic.median()),
            "positive_ic_ratio": float((per_date.rank_ic > 0).mean()),
            "ndcg_at_10_mean": float(per_date.ndcg_at_10.mean())}, per_date


def nav_metrics(nav: pd.Series) -> dict:
    nav = nav.dropna(); ret = nav.pct_change(fill_method=None).dropna()
    dd = nav / nav.cummax() - 1.0
    years = max(len(ret) / 252.0, 1 / 252.0)
    return {"gross_or_net_return": float(nav.iloc[-1] / nav.iloc[0] - 1) if len(nav) else np.nan,
            "cagr": float((nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1) if len(nav) > 1 else np.nan,
            "sharpe": float(np.sqrt(252) * ret.mean() / ret.std(ddof=1)) if len(ret) > 1 and ret.std(ddof=1) > 0 else np.nan,
            "daily_max_drawdown": float(dd.min()) if len(dd) else np.nan,
            "daily_observations": int(len(ret))}


def score_feature_universe(model: RidgeControl, features: pd.DataFrame, start, end) -> pd.DataFrame:
    rows = features[(features.signal_date >= pd.Timestamp(start)) & (features.signal_date <= pd.Timestamp(end))].copy()
    rows["score"] = predict(model, rows)
    return rows


def simulate_top10(scored: pd.DataFrame, calendar, views, fold_end, cost_bps: int, top_k: int | None = 10) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    if scored.empty: return {**nav_metrics(pd.Series(dtype=float)), "turnover": np.nan, "trade_not_filled": 0}, pd.DataFrame(), pd.DataFrame()
    dates = sorted(pd.to_datetime(scored.signal_date.unique()))
    # Require the fixed 60-session holding to complete inside the fold.
    dates = [d for d in dates if calendar.get_loc(d) + 61 < len(calendar) and calendar[calendar.get_loc(d) + 61] <= pd.Timestamp(fold_end)]
    if not dates: return {**nav_metrics(pd.Series(dtype=float)), "turnover": np.nan, "trade_not_filled": 0}, pd.DataFrame(), pd.DataFrame()
    selected = {d: (scored[scored.signal_date.eq(d)].sort_values(["score", "symbol"], ascending=[False, True]).symbol.tolist()
                    if top_k is None else scored[scored.signal_date.eq(d)].sort_values(["score", "symbol"], ascending=[False, True]).head(top_k).symbol.tolist()) for d in dates}
    entry_map = {calendar.get_loc(d) + 1: d for d in dates}
    fold_end_pos = int(calendar.searchsorted(pd.Timestamp(fold_end), side="right") - 1)
    last_pos = min(calendar.get_loc(dates[-1]) + 61, fold_end_pos)
    first_pos = calendar.get_loc(dates[0]) + 1
    units: dict[str, float] = {}; cash = 1.0; last_marks: dict[str, float] = {}
    nav_rows = [{"date": calendar[first_pos - 1], "nav": 1.0}]; trades = []; missing_marks = unfilled = 0
    for pos in range(first_pos, last_pos + 1):
        date = calendar[pos]
        # Revalue old holdings to the opening mark before a rebalance.
        if pos in entry_map:
            open_values = {}; equity_open = cash
            for symbol, qty in units.items():
                op = views[symbol].iloc[pos]["research_open"]
                price = float(op) if pd.notna(op) and op > 0 else last_marks.get(symbol, np.nan)
                if not np.isfinite(price): missing_marks += 1; price = 0.0
                open_values[symbol] = qty * price; equity_open += qty * price
            target_names = selected[entry_map[pos]]; target_each = equity_open / len(target_names) if target_names else 0.0
            turnover = 0.0
            for symbol in sorted(set(units) | set(target_names)):
                row = views[symbol].iloc[pos]; op = row["research_open"]
                tradable = bool(row["trading_eligible"]) and pd.notna(op) and op > 0
                current = open_values.get(symbol, 0.0); desired = target_each if symbol in target_names else 0.0
                if not tradable:
                    if symbol in target_names and symbol not in units: unfilled += 1
                    continue
                delta = desired - current; turnover += abs(delta) / equity_open if equity_open > 0 else 0.0
                cash -= delta; units[symbol] = desired / float(op) if desired > 0 else 0.0
                if units[symbol] == 0: units.pop(symbol, None)
            cost = turnover * cost_bps / 10000.0 * equity_open; cash -= cost
            trades.append({"signal_date": entry_map[pos], "trade_date": date, "cost_bps": cost_bps,
                           "turnover_two_sided_notional": turnover, "cost_value": cost,
                           "selected": len(target_names), "unfilled_total": unfilled})
        equity = cash
        for symbol, qty in units.items():
            cl = views[symbol].iloc[pos]["research_close"]
            reliable = str(views[symbol].iloc[pos]["price_quality"]) != "UNRESOLVED"
            if pd.notna(cl) and cl > 0 and reliable:
                mark = float(cl); last_marks[symbol] = mark
            else:
                mark = last_marks.get(symbol, np.nan)
                if not np.isfinite(mark): missing_marks += 1; mark = 0.0
            equity += qty * mark
        nav_rows.append({"date": date, "nav": equity})
    nav = pd.DataFrame(nav_rows).set_index("date")
    trade_df = pd.DataFrame(trades)
    out = nav_metrics(nav.nav); out.update({"turnover": float(trade_df.turnover_two_sided_notional.mean()) if len(trade_df) else np.nan,
                                           "total_turnover": float(trade_df.turnover_two_sided_notional.sum()) if len(trade_df) else 0.0,
                                           "trade_not_filled": unfilled, "missing_mark_events": missing_marks})
    return out, nav.reset_index(), trade_df


def choose_horizon(inner_rows: pd.DataFrame, contract: dict) -> tuple[int, dict]:
    scores = inner_rows.groupby("horizon_sessions")["rank_ic_mean"].median().to_dict()
    best = max(scores.values()); candidates = sorted(h for h, v in scores.items() if best - v <= 0.01)
    return int(candidates[0]), {int(k): float(v) for k, v in scores.items()}


def fold_rows(data, horizon, start, end):
    return data[(data.horizon_sessions.eq(horizon)) & (data.signal_date >= pd.Timestamp(start)) &
                (data.signal_date <= pd.Timestamp(end)) & (data.label_end <= pd.Timestamp(end))].copy()


def train_rows(data, horizon, boundary):
    return data[(data.horizon_sessions.eq(horizon)) & (data.signal_date < pd.Timestamp(boundary)) &
                (data.label_end < pd.Timestamp(boundary))].copy()


def run_nested(contract, calendar, features, data, views):
    inner_out, outer_out, selections, navs, trade_frames = [], [], [], [], []
    for outer in contract["outer_folds"]:
        for year in outer["inner_validation_years"]:
            start, end = f"{year}-01-01", f"{year}-12-31"
            for h in HORIZONS:
                train = train_rows(data, h, start); valid = fold_rows(data, h, start, end)
                model = fit_ridge(train); pred, _ = evaluate_predictions(model, valid)
                scored = score_feature_universe(model, features, start, end)
                port, _, _ = simulate_top10(scored, calendar, views, end, 50)
                inner_out.append({"outer_fold": outer["id"], "inner_validation_year": year, "horizon_sessions": h,
                                  "train_observations": len(train), "train_last_label_end": str(train.label_end.max().date()),
                                  "validation_start": start, "validation_end": end, **pred, **{f"portfolio_{k}": v for k,v in port.items()}})
        current_inner = pd.DataFrame([r for r in inner_out if r["outer_fold"] == outer["id"]])
        chosen, scores = choose_horizon(current_inner, contract)
        selections.append({"outer_fold": outer["id"], "selected_horizon": chosen,
                           **{f"inner_median_ic_h{h}": scores[h] for h in HORIZONS}})
        for h in HORIZONS:
            train = train_rows(data, h, outer["test_start"]); test = fold_rows(data, h, outer["test_start"], outer["test_end"])
            model = fit_ridge(train); pred, per_date = evaluate_predictions(model, test)
            scored = score_feature_universe(model, features, outer["test_start"], outer["test_end"])
            for cost in (0, 30, 50, 100):
                port, nav, trades = simulate_top10(scored, calendar, views, outer["test_end"], cost)
                outer_out.append({"outer_fold": outer["id"], "horizon_sessions": h, "selected_by_inner": h == chosen,
                                  "cost_bps": cost, "train_observations": len(train), "test_start": outer["test_start"],
                                  "test_end": outer["test_end"], **pred, **{f"portfolio_{k}": v for k,v in port.items()}})
                if h == chosen:
                    if len(nav): nav.assign(outer_fold=outer["id"], horizon_sessions=h, cost_bps=cost).pipe(navs.append)
                    if len(trades): trades.assign(outer_fold=outer["id"], horizon_sessions=h).pipe(trade_frames.append)
    return pd.DataFrame(inner_out), pd.DataFrame(outer_out), pd.DataFrame(selections), navs, trade_frames


def baseline_results(calendar, features, views, benchmark):
    rows = []
    base_scores = features.copy()
    base_scores["momentum_score"] = base_scores["mom_12_1"]
    for _, g in base_scores.groupby("signal_date"):
        idx = g.index
        base_scores.loc[idx, "composite_score"] = (g.mom_12_1.rank(pct=True) + g.mom_63.rank(pct=True) - g.vol_63.rank(pct=True)) / 3
        base_scores.loc[idx, "equal_score"] = 1.0
    end = calendar[-1]
    for name, col in (("INVESTABLE_UNIVERSE_EQUAL_WEIGHT", "equal_score"), ("MOMENTUM_12_1_TOP10", "momentum_score"), ("PRICE_ONLY_MOMENTUM_COMPOSITE_TOP10", "composite_score")):
        scored = base_scores[["signal_date","symbol",col]].rename(columns={col:"score"})
        for cost in (0,30,50,100):
            metric, _, _ = simulate_top10(scored, calendar, views, end, cost, top_k=None if name == "INVESTABLE_UNIVERSE_EQUAL_WEIGHT" else 10)
            rows.append({"baseline":name,"cost_bps":cost,"status":"DESCRIPTIVE_RESEARCH_CONTROL",**metric})
    bm = benchmark["research_close"].dropna(); bm = bm[bm.index >= features.signal_date.min()]
    for cost in (0,30,50,100):
        nav = bm / bm.iloc[0] * (1-cost/10000.0); nav.iloc[-1] *= 1-cost/10000.0
        rows.append({"baseline":"BIST100_RESEARCH_RETURN_PROXY","cost_bps":cost,"status":"DESCRIPTIVE_RESEARCH_CONTROL",**nav_metrics(nav)})
    unavailable = pd.DataFrame([
      {"baseline":"V3_FROZEN_BEHAVIOR","status":"N/A_DESCRIPTIVE_REFERENCE_ONLY","reason":"unsafe legacy fundamental and macro dependencies cannot enter common contract"},
      {"baseline":"V4_1_FROZEN_BEHAVIOR","status":"N/A_DESCRIPTIVE_REFERENCE_ONLY","reason":"unsafe legacy fundamental/macro plus inflation-adjusted real EPS double-adjustment risk"},
      {"baseline":"VALUE_QUALITY","status":"N/A","reason":"signal-date market-cap/capital gate is not open"},
    ])
    return pd.DataFrame(rows), unavailable


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    shown = frame[columns].copy()
    for c in shown: shown[c] = shown[c].map(lambda x: "N/A" if pd.isna(x) else (f"{x:.4f}" if isinstance(x,(float,np.floating)) else str(x)))
    return "| " + " | ".join(columns) + " |\n|" + "|".join("---" for _ in columns) + "|\n" + "\n".join("| " + " | ".join(map(str,r)) + " |" for r in shown.itertuples(index=False,name=None))


def main() -> dict:
    RESULTS.mkdir(exist_ok=True); MANIFESTS.mkdir(exist_ok=True)
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    calendar, symbols, views, benchmark = load_inputs(contract)
    features, data, coverage = build_dataset(calendar, symbols, views)
    inner, outer, selections, navs, trades = run_nested(contract, calendar, features, data, views)
    baselines, unavailable = baseline_results(calendar, features, views, benchmark)
    coverage_agg = coverage.groupby("horizon_sessions").agg(candidate_observations=("candidate_observations","sum"), usable_observations=("usable_observations","sum")).reset_index()
    coverage_agg["coverage_pct"] = coverage_agg.usable_observations / coverage_agg.candidate_observations
    counts = selections.selected_horizon.value_counts().reindex(HORIZONS, fill_value=0).to_dict()
    selected_outer = outer[(outer.selected_by_inner) & (outer.cost_bps.eq(50))]
    dominant = max(counts, key=counts.get); dominant_count = counts[dominant]
    positive_ratio = float((selected_outer.rank_ic_mean > 0).mean())
    robustness = {"mean_rank_ic":float(selected_outer.rank_ic_mean.mean()), "median_fold_rank_ic":float(selected_outer.rank_ic_mean.median()), "positive_fold_ratio":positive_ratio}
    preferred = dominant_count >= 3 and robustness["mean_rank_ic"] > 0 and robustness["median_fold_rank_ic"] >= 0 and positive_ratio >= 0.5
    decision = f"H{dominant} PREFERRED" if preferred else "NO CLEAR WINNER"
    coverage.to_csv(RESULTS/"EXP-TGT-001_coverage_by_signal.csv",index=False); coverage_agg.to_csv(RESULTS/"EXP-TGT-001_coverage.csv",index=False)
    inner.to_csv(RESULTS/"EXP-TGT-001_inner_metrics.csv",index=False); outer.to_csv(RESULTS/"EXP-TGT-001_outer_metrics.csv",index=False)
    selections.to_csv(RESULTS/"EXP-TGT-001_inner_selections.csv",index=False); baselines.to_csv(RESULTS/"EXP-TGT-001_baselines.csv",index=False)
    unavailable.to_csv(RESULTS/"EXP-TGT-001_unavailable_legacy_baselines.csv",index=False)
    if navs: pd.concat(navs,ignore_index=True).to_csv(RESULTS/"EXP-TGT-001_selected_outer_daily_nav.csv",index=False)
    if trades: pd.concat(trades,ignore_index=True).to_csv(RESULTS/"EXP-TGT-001_selected_outer_trades.csv",index=False)
    fold_manifest = outer[["outer_fold","test_start","test_end"]].drop_duplicates().merge(selections,on="outer_fold")
    fold_manifest.to_csv(RESULTS/"EXP-TGT-001_fold_manifest.csv",index=False)
    summary = {"experiment_id":"EXP-TGT-001","hypothesis":contract["hypothesis"],"dataset":{"symbols":len(symbols),"calendar_first":str(calendar[0].date()),"calendar_last":str(calendar[-1].date()),"feature_observations":len(features),"labeled_observations":len(data)},"coverage":coverage_agg.to_dict("records"),"inner_selection_frequency":{f"H{k}":int(v) for k,v in counts.items()},"selected_procedure_outer_robustness":robustness,"horizon_decision":decision,"macro_used":False,"fundamental_used":False,"production_changes":0}
    (RESULTS/"EXP-TGT-001_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    primary = outer[outer.cost_bps.eq(50)].groupby("horizon_sessions").agg(rank_ic_mean=("rank_ic_mean","mean"),rank_ic_median=("rank_ic_median","median"),positive_ic_ratio=("positive_ic_ratio","mean"),ndcg_at_10=("ndcg_at_10_mean","mean"),net_return=("portfolio_gross_or_net_return","mean"),sharpe=("portfolio_sharpe","mean"),daily_maxdd=("portfolio_daily_max_drawdown","min"),turnover=("portfolio_turnover","mean")).reset_index()
    report = f"""# EXP-TGT-001 — RAW RETURN HORIZON COMPARISON

## 1. Executive Summary

Decision: **{decision}**. Horizon selection used inner folds only; outer folds evaluated the selected procedure and could only veto, never replace, the inner choice.

## 2. Locked Research Contract

Contract was written before results: price-only DATA-005 view, raw return rank target, fixed ridge control, K=10, 60-session rebalance/holding, 50 bps primary cost.

## 3. Dataset Scope

{len(symbols)} current-universe symbols; macro, USDTRY, fundamentals, value and legacy approximate fundamentals excluded. V3/V4.1 are N/A under the common safe contract; frozen behavior is not clean OOS.

## 4. Fold Design

Four expanding outer folds (2022, 2023, 2024, 2025 through May); each has two prior-year inner validations. Every training set is purged using that horizon's actual `label_end`.

## 5. Eligible Sample Coverage

{markdown_table(coverage_agg,["horizon_sessions","candidate_observations","usable_observations","coverage_pct"])}

## 6. H20 Results

See common 50 bps table below; full fold metrics are in `EXP-TGT-001_outer_metrics.csv`.

## 7. H40 Results

Same fixed features/model/config; only the raw-return label horizon changes.

## 8. H60 Results

Same fixed features/model/config; 60 is not presumed optimal.

{markdown_table(primary,["horizon_sessions","rank_ic_mean","rank_ic_median","positive_ic_ratio","ndcg_at_10","net_return","sharpe","daily_maxdd","turnover"])}

## 9. Inner Selection Frequency

H20={counts[20]}, H40={counts[40]}, H60={counts[60]} across four outer procedures.

## 10. Outer Robustness

Selected-procedure mean Rank IC={robustness['mean_rank_ic']:.4f}, median fold Rank IC={robustness['median_fold_rank_ic']:.4f}, positive-fold ratio={robustness['positive_fold_ratio']:.2%}. Outer results did not choose a horizon.

## 11. Cost / Turnover

0/30/50/100 bps results and two-sided turnover are recorded per outer fold/horizon. 50 bps is primary.

## 12. Daily Risk

Daily NAV and true daily MaxDD are recorded for the inner-selected outer procedure; no cohort-only drawdown substitute is used.

## 13. Coverage Sensitivity

Coverage differences are reported as data availability, not performance. Universe formation uses signal-date history only; future label availability is not an eligibility feature.

## 14. Horizon Decision

**{decision}** under the precommitted frequency-plus-veto rule. A single Sharpe did not determine the result.

## 15. Tests

Dynamic labels, leakage/purge, nested separation, fixed model/features, forbidden fields, future eligibility, reproducibility and production integrity are covered by the EXP-TGT-001 suite.

## 16. Production Integrity

Research-only outputs; final protected-file hash verification is run separately.

## 17. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Apply the next Phase C target-type step only to inner-supported horizon(s); if the decision is NO CLEAR WINNER, first report that gate outcome and do not silently broaden the grid.
"""
    (RESULTS/"EXP-TGT-001_report.md").write_text(report,encoding="utf-8")
    manifest = {"experiment_id":"EXP-TGT-001","generated_at_utc":datetime.now(timezone.utc).isoformat(),"contract_sha256":sha256(CONTRACT_PATH),"code_sha256":sha256(Path(__file__)),"input_view":"EXP-DATA-004 base + EXP-DATA-005 overlay","seed":0,"outputs":[p.name for p in sorted(RESULTS.glob("EXP-TGT-001*"))]}
    (MANIFESTS/"EXP-TGT-001_reproducibility.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2)); return summary


if __name__ == "__main__": main()
