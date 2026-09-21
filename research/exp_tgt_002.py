"""EXP-TGT-002 — nested target-family comparison with target-specific inner horizons."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH = Path(__file__).resolve().parent
ROOT = RESEARCH.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RESEARCH))
import config as cfg
import exp_tgt_001 as base

CONTRACT_PATH = RESEARCH / "contracts" / "exp_tgt_002.json"
TGT1_CONTRACT = RESEARCH / "contracts" / "exp_tgt_001.json"
RESULTS = RESEARCH / "results"
MANIFESTS = RESEARCH / "manifests"
FAMILIES = ("RAW", "SECTOR_RELATIVE", "BETA_RESIDUAL", "VOL_SCALED")
HORIZONS = (20, 40, 60)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def estimate_beta(view: pd.DataFrame, benchmark: pd.DataFrame, pos: int, window: int = 252,
                  minimum: int = 126, floor: float = -3.0, cap: float = 3.0) -> tuple[float, int]:
    """Estimate beta from observations ending at signal pos; never reads pos+1 onward."""
    start = max(0, pos - window)
    stock_close = pd.to_numeric(view.iloc[start:pos + 1]["research_close"], errors="coerce").copy()
    bench_close = pd.to_numeric(benchmark.iloc[start:pos + 1]["research_close"], errors="coerce").copy()
    quality = view.iloc[start:pos + 1]["price_quality"].fillna("UNRESOLVED").astype(str)
    stock_close[quality.eq("UNRESOLVED")] = np.nan
    pair = pd.concat([stock_close.pct_change(fill_method=None), bench_close.pct_change(fill_method=None)], axis=1).dropna()
    pair.columns = ["stock", "market"]
    if len(pair) < minimum or pair.market.var(ddof=1) <= 1e-12:
        return np.nan, len(pair)
    beta = pair.stock.cov(pair.market) / pair.market.var(ddof=1)
    return float(np.clip(beta, floor, cap)), len(pair)


def build_target_data(contract: dict, calendar, symbols, views, benchmark, features, raw_data, raw_coverage):
    positions = {pd.Timestamp(calendar[p]): p for p in base.signal_positions(calendar)}
    beta_rows = []
    for row in features[["signal_date", "symbol"]].itertuples(index=False):
        beta, n = estimate_beta(views[row.symbol], benchmark, positions[pd.Timestamp(row.signal_date)],
                                contract["beta_contract"]["estimation_window_sessions"],
                                contract["beta_contract"]["minimum_aligned_returns"],
                                contract["beta_contract"]["beta_floor"], contract["beta_contract"]["beta_cap"])
        beta_rows.append({"signal_date": row.signal_date, "symbol": row.symbol, "ex_ante_beta": beta, "beta_observations": n})
    betas = pd.DataFrame(beta_rows)
    data = raw_data.merge(betas, on=["signal_date", "symbol"], how="left", validate="many_to_one")
    mapping = {s: cfg.HISSE_SEKTOR.get(s, "UNCLASSIFIED") for s in symbols}
    data["sector"] = data.symbol.map(mapping)

    # Benchmark forward returns use the same close-to-close label endpoints.
    bclose = pd.to_numeric(benchmark["research_close"], errors="coerce")
    data["benchmark_forward_return"] = [float(bclose.loc[e] / bclose.loc[s] - 1.0)
                                         if s in bclose.index and e in bclose.index and bclose.loc[s] > 0 else np.nan
                                         for s, e in zip(data.label_start, data.label_end)]
    min_sector = contract["sector_contract"]["minimum_group_size"]
    grp = data.groupby(["signal_date", "horizon_sessions", "sector"])["raw_forward_return"]
    data["sector_count"] = grp.transform("size")
    data["sector_median"] = grp.transform("median")
    data["universe_median"] = data.groupby(["signal_date", "horizon_sessions"])["raw_forward_return"].transform("median")
    data["sector_fallback_used"] = data.sector_count.lt(min_sector) | data.sector.eq("UNCLASSIFIED")
    data["sector_reference"] = np.where(data.sector_fallback_used, data.universe_median, data.sector_median)
    data["vol_scale"] = data.vol_63.clip(contract["volatility_contract"]["daily_vol_floor"],
                                          contract["volatility_contract"]["daily_vol_cap"])

    frames = []
    formulas = {
        "RAW": data.raw_forward_return,
        "SECTOR_RELATIVE": data.raw_forward_return - data.sector_reference,
        "BETA_RESIDUAL": data.raw_forward_return - data.ex_ante_beta * data.benchmark_forward_return,
        "VOL_SCALED": data.raw_forward_return / data.vol_scale,
    }
    for family, values in formulas.items():
        tmp = data.copy(); tmp["target_family"] = family; tmp["target_value"] = values
        tmp = tmp[np.isfinite(tmp.target_value)].copy()
        tmp["target_rank"] = tmp.groupby(["signal_date", "horizon_sessions"])["target_value"].rank(pct=True, method="average")
        frames.append(tmp)
    targets = pd.concat(frames, ignore_index=True)

    raw_candidates = raw_coverage.groupby("horizon_sessions")["candidate_observations"].sum().to_dict()
    cov = targets.groupby(["target_family", "horizon_sessions"]).size().rename("usable_observations").reset_index()
    cov["candidate_observations"] = cov.horizon_sessions.map(raw_candidates)
    cov["coverage_pct"] = cov.usable_observations / cov.candidate_observations
    return targets, cov, betas, mapping


def evaluate(model: base.RidgeControl, rows: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    scored = rows.copy(); scored["score"] = base.predict(model, scored)
    per = []
    for date, grp in scored.groupby("signal_date"):
        if len(grp) < 10: continue
        ranked = grp.sort_values(["score", "symbol"], ascending=[False, True])
        ic = grp.score.rank().corr(grp.target_value.rank())
        per.append({"signal_date": date, "rank_ic": ic,
                    "ndcg_at_10": base.ndcg_at_k(grp.target_rank.to_numpy(), grp.score.to_numpy(), 10),
                    "top_k_spread_raw": float(ranked.head(10).raw_forward_return.mean() - ranked.tail(10).raw_forward_return.mean()),
                    "cross_section_size": len(grp)})
    per_date = pd.DataFrame(per)
    if per_date.empty:
        return {"signal_dates":0,"observations":len(rows),"rank_ic_mean":np.nan,"rank_ic_median":np.nan,
                "positive_ic_ratio":np.nan,"ndcg_at_10_mean":np.nan,"top_k_spread_raw_mean":np.nan}, per_date
    return {"signal_dates":len(per_date),"observations":len(rows),"rank_ic_mean":float(per_date.rank_ic.mean()),
            "rank_ic_median":float(per_date.rank_ic.median()),"positive_ic_ratio":float((per_date.rank_ic>0).mean()),
            "ndcg_at_10_mean":float(per_date.ndcg_at_10.mean()),"top_k_spread_raw_mean":float(per_date.top_k_spread_raw.mean())}, per_date


def rows_in_fold(data, family, horizon, start, end):
    return data[(data.target_family.eq(family)) & (data.horizon_sessions.eq(horizon)) &
                (data.signal_date >= pd.Timestamp(start)) & (data.signal_date <= pd.Timestamp(end)) &
                (data.label_end <= pd.Timestamp(end))].copy()


def training_rows(data, family, horizon, boundary):
    return data[(data.target_family.eq(family)) & (data.horizon_sessions.eq(horizon)) &
                (data.signal_date < pd.Timestamp(boundary)) & (data.label_end < pd.Timestamp(boundary))].copy()


def select_horizon(rows: pd.DataFrame) -> tuple[int, dict]:
    scores = rows.groupby("horizon_sessions").rank_ic_mean.median().to_dict()
    best = max(scores.values()); candidates = sorted(h for h,v in scores.items() if best-v <= 0.01)
    return int(candidates[0]), {int(k):float(v) for k,v in scores.items()}


def select_family(family_scores: dict, contract: dict) -> str:
    best = max(family_scores.values()); candidates = {f for f,v in family_scores.items() if best-v <= contract["inner_family_selection"]["tie_tolerance"]}
    return next(f for f in contract["inner_family_selection"]["tie_priority"] if f in candidates)


def run_nested(contract, folds, calendar, features, targets, views):
    inner_rows, selection_rows, outer_rows, nav_frames, trade_frames = [], [], [], [], []
    for outer in folds:
        for year in outer["inner_validation_years"]:
            start, end = f"{year}-01-01", f"{year}-12-31"
            for family in FAMILIES:
                for h in HORIZONS:
                    train = training_rows(targets, family, h, start); valid = rows_in_fold(targets, family, h, start, end)
                    model = base.fit_ridge(train); metric, _ = evaluate(model, valid)
                    inner_rows.append({"outer_fold":outer["id"],"inner_validation_year":year,"target_family":family,
                                       "horizon_sessions":h,"train_observations":len(train),"train_last_label_end":str(train.label_end.max().date()),**metric})
        current = pd.DataFrame([r for r in inner_rows if r["outer_fold"] == outer["id"]])
        chosen_h, family_scores = {}, {}
        selection = {"outer_fold":outer["id"]}
        for family in FAMILIES:
            h, scores = select_horizon(current[current.target_family.eq(family)])
            chosen_h[family] = h
            family_scores[family] = float(current[(current.target_family.eq(family)) & (current.horizon_sessions.eq(h))].rank_ic_mean.median())
            selection[f"{family.lower()}_selected_horizon"] = h
            selection[f"{family.lower()}_inner_score"] = family_scores[family]
        selected_family = select_family(family_scores, contract)
        selection["selected_family"] = selected_family; selection["selected_horizon"] = chosen_h[selected_family]
        selection_rows.append(selection)

        for family in FAMILIES:
            h = chosen_h[family]
            train = training_rows(targets, family, h, outer["test_start"])
            test = rows_in_fold(targets, family, h, outer["test_start"], outer["test_end"])
            model = base.fit_ridge(train); metric, _ = evaluate(model, test)
            scored = base.score_feature_universe(model, features, outer["test_start"], outer["test_end"])
            for cost in (0,30,50,100):
                port, nav, trades = base.simulate_top10(scored, calendar, views, outer["test_end"], cost)
                outer_rows.append({"outer_fold":outer["id"],"target_family":family,"inner_selected_horizon":h,
                                   "selected_family_by_inner":family==selected_family,"cost_bps":cost,
                                   "train_observations":len(train),"test_start":outer["test_start"],"test_end":outer["test_end"],
                                   **metric,**{f"portfolio_{k}":v for k,v in port.items()}})
                if len(nav): nav_frames.append(nav.assign(outer_fold=outer["id"],target_family=family,horizon_sessions=h,cost_bps=cost))
                if len(trades): trade_frames.append(trades.assign(outer_fold=outer["id"],target_family=family,horizon_sessions=h))
    return pd.DataFrame(inner_rows), pd.DataFrame(selection_rows), pd.DataFrame(outer_rows), nav_frames, trade_frames


def decide(selections: pd.DataFrame, outer: pd.DataFrame):
    primary = outer[outer.cost_bps.eq(50)]
    robust_rows, viable = [], []
    for family in FAMILIES:
        g = primary[primary.target_family.eq(family)]
        row = {"target_family":family,"mean_rank_ic":float(g.rank_ic_mean.mean()),
               "median_fold_rank_ic":float(g.rank_ic_mean.median()),"positive_fold_ratio":float((g.rank_ic_mean>0).mean()),
               "mean_ndcg_at_10":float(g.ndcg_at_10_mean.mean()),"mean_top_k_spread_raw":float(g.top_k_spread_raw_mean.mean()),
               "mean_turnover":float(g.portfolio_turnover.mean()),"worst_daily_maxdd":float(g.portfolio_daily_max_drawdown.min())}
        row["viable"] = row["mean_rank_ic"]>0 and row["median_fold_rank_ic"]>=0 and row["positive_fold_ratio"]>=0.5 and row["mean_ndcg_at_10"]>0.5
        if row["viable"]: viable.append(family)
        robust_rows.append(row)
    freq = selections.selected_family.value_counts().reindex(FAMILIES,fill_value=0).to_dict()
    labels = {"RAW":"RAW PREFERRED","SECTOR_RELATIVE":"SECTOR-RELATIVE PREFERRED","BETA_RESIDUAL":"BETA-RESIDUAL PREFERRED","VOL_SCALED":"VOL-SCALED PREFERRED"}
    if len(viable)>=2: decision="MULTIPLE VIABLE TARGETS"
    elif len(viable)==1 and freq[viable[0]]>=3: decision=labels[viable[0]]
    else: decision="NO CLEAR TARGET WINNER"
    return decision, pd.DataFrame(robust_rows), {k:int(v) for k,v in freq.items()}, viable


def table(df, cols):
    x=df[cols].copy()
    for c in x: x[c]=x[c].map(lambda v:"N/A" if pd.isna(v) else (f"{v:.4f}" if isinstance(v,(float,np.floating)) else str(v)))
    return "| "+" | ".join(cols)+" |\n|"+"|".join("---" for _ in cols)+"|\n"+"\n".join("| "+" | ".join(map(str,r))+" |" for r in x.itertuples(index=False,name=None))


def main():
    RESULTS.mkdir(exist_ok=True); MANIFESTS.mkdir(exist_ok=True)
    contract=json.loads(CONTRACT_PATH.read_text(encoding="utf-8")); old=json.loads(TGT1_CONTRACT.read_text(encoding="utf-8"))
    calendar,symbols,views,benchmark=base.load_inputs(old)
    features,raw_data,raw_cov=base.build_dataset(calendar,symbols,views)
    targets,coverage,betas,mapping=build_target_data(contract,calendar,symbols,views,benchmark,features,raw_data,raw_cov)
    sector_rows=targets[targets.target_family.eq("SECTOR_RELATIVE")]
    raw_rows=targets[targets.target_family.eq("RAW")]
    diagnostics=pd.DataFrame([
        {"diagnostic":"sector_fallback_observations","value":int(sector_rows.sector_fallback_used.sum()),"denominator":len(sector_rows),"ratio":float(sector_rows.sector_fallback_used.mean())},
        {"diagnostic":"beta_missing_feature_observations","value":int(betas.ex_ante_beta.isna().sum()),"denominator":len(betas),"ratio":float(betas.ex_ante_beta.isna().mean())},
        {"diagnostic":"beta_at_floor_or_cap","value":int((betas.ex_ante_beta.abs()>=3.0).sum()),"denominator":len(betas),"ratio":float((betas.ex_ante_beta.abs()>=3.0).mean())},
        {"diagnostic":"volatility_at_floor","value":int((raw_rows.vol_63<contract['volatility_contract']['daily_vol_floor']).sum()),"denominator":len(raw_rows),"ratio":float((raw_rows.vol_63<contract['volatility_contract']['daily_vol_floor']).mean())},
        {"diagnostic":"volatility_at_cap","value":int((raw_rows.vol_63>contract['volatility_contract']['daily_vol_cap']).sum()),"denominator":len(raw_rows),"ratio":float((raw_rows.vol_63>contract['volatility_contract']['daily_vol_cap']).mean())}
    ])
    inner,selections,outer,navs,trades=run_nested(contract,old["outer_folds"],calendar,features,targets,views)
    decision,robust,freq,viable=decide(selections,outer)
    inner.to_csv(RESULTS/"EXP-TGT-002_inner_metrics.csv",index=False); selections.to_csv(RESULTS/"EXP-TGT-002_inner_selections.csv",index=False)
    outer.to_csv(RESULTS/"EXP-TGT-002_outer_metrics.csv",index=False); coverage.to_csv(RESULTS/"EXP-TGT-002_coverage.csv",index=False)
    robust.to_csv(RESULTS/"EXP-TGT-002_outer_robustness.csv",index=False)
    diagnostics.to_csv(RESULTS/"EXP-TGT-002_target_diagnostics.csv",index=False)
    pd.DataFrame([{"symbol":s,"sector":mapping[s]} for s in symbols]).to_csv(RESULTS/"EXP-TGT-002_sector_mapping.csv",index=False)
    betas.to_csv(RESULTS/"EXP-TGT-002_ex_ante_beta.csv",index=False)
    if navs: pd.concat(navs,ignore_index=True).to_csv(RESULTS/"EXP-TGT-002_daily_nav.csv",index=False)
    if trades: pd.concat(trades,ignore_index=True).to_csv(RESULTS/"EXP-TGT-002_trades.csv",index=False)
    horizon_counts=[]
    for family in FAMILIES:
        col=f"{family.lower()}_selected_horizon"
        for h,n in selections[col].value_counts().reindex(HORIZONS,fill_value=0).items(): horizon_counts.append({"target_family":family,"horizon_sessions":h,"selection_count":n})
    pd.DataFrame(horizon_counts).to_csv(RESULTS/"EXP-TGT-002_horizon_selection_by_target.csv",index=False)
    summary={"experiment_id":"EXP-TGT-002","execution":"PASS","target_decision":decision,"viable_targets":viable,
             "inner_family_selection_frequency":freq,"horizon_selection_by_target":pd.DataFrame(horizon_counts).to_dict("records"),
             "dataset":{"symbols":len(symbols),"target_observations":len(targets)},"macro_used":False,"fundamental_used":False,
             "sector_mapping_quality":contract["sector_contract"]["mapping_quality"],"target_diagnostics":diagnostics.to_dict("records"),"production_changes":0}
    (RESULTS/"EXP-TGT-002_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    interpretation=("These target families did not separate under the current simple price-only predictor control; this is not evidence that all targets or price-only alpha fail."
                    if decision=="NO CLEAR TARGET WINNER" else "Decision follows the locked multi-metric viability and inner-selection rules; no single Sharpe or CAGR selected the family.")
    report=f"""# EXP-TGT-002 — TARGET FAMILY COMPARISON

## 1. Executive Summary

Execution **PASS**. Target decision: **{decision}**. {interpretation}

## 2. Locked Contract

Four target families, target-specific inner H=20/40/60 selection, fixed EXP-TGT-001 features/ridge, K=10, 60-session holding/rebalance, 50 bps primary cost. Macro and fundamentals excluded.

## 3. Target Definitions

RAW: raw close-to-close forward return. SECTOR_RELATIVE: raw minus sector median, with universe-median fallback below five names (actual fallback ratio {sector_rows.sector_fallback_used.mean():.2%}). BETA_RESIDUAL: raw minus signal-date ex-ante beta times BIST return. VOL_SCALED: raw divided by signal-date 63-return daily volatility clipped to [0.005, 0.10].

## 4. Fold Design

Same four outer and two-inner-year expanding folds as EXP-TGT-001. Each family selects its own horizon in inner data. Outer evaluates only that selected family procedure.

## 5. Sample Coverage

{table(coverage,["target_family","horizon_sessions","candidate_observations","usable_observations","coverage_pct"])}

## 6. RAW Results

See outer robustness table; horizon remained inner-selected.

## 7. Sector-Relative Results

Uses the locked time-invariant `PROXY_TAXONOMY`; no future reassignment occurs, but historical sector-vintage verification is unavailable.

## 8. Beta-Residual Results

Beta uses only up-to-signal returns with 252-session window, minimum 126 aligned observations and [-3,3] cap.

## 9. Volatility-Scaled Results

Scale uses only the 63 pre-signal returns and the locked daily floor/cap; forward volatility is never used.

## 10. Horizon Selection by Target

{table(pd.DataFrame(horizon_counts),["target_family","horizon_sessions","selection_count"])}

## 11. Outer Robustness

{table(robust,["target_family","mean_rank_ic","median_fold_rank_ic","positive_fold_ratio","mean_ndcg_at_10","mean_top_k_spread_raw","viable"])}

## 12. Cost / Turnover

0/30/50/100 bps and actual two-sided turnover are recorded per family/outer fold; no K or rebalance optimization was performed.

## 13. Daily Risk

Daily NAV and daily MaxDD were generated for every family-selected horizon and cost scenario.

## 14. Target Decision

**{decision}** under the locked inner-frequency plus multi-metric outer-veto rule.

## 15. Limitations

Current-survivor universe, provider-dependent research prices, sparse 60-session signal schedule, simple ridge/three-feature control and proxy sector taxonomy limit generalization. A negative result does not establish that all target definitions fail.

## 16. Tests

Formula, no-future sector/beta/volatility, dynamic labels, inner-only horizon selection, outer isolation, fixed model/features, forbidden inputs, reproducibility and production hash controls are tested separately.

## 17. Production Integrity

Research-only outputs. Final protected production hashes are verified separately.

## 18. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

If no clear target winner emerges, close Phase C without forcing a target and move to Phase D economic feature discovery while retaining target family and horizon as inner-selected procedure parameters. Otherwise carry only the viable target procedure(s) into Phase D. Do not start automatically.
"""
    (RESULTS/"EXP-TGT-002_report.md").write_text(report,encoding="utf-8")
    manifest={"experiment_id":"EXP-TGT-002","generated_at_utc":datetime.now(timezone.utc).isoformat(),"contract_sha256":sha256(CONTRACT_PATH),
              "code_sha256":sha256(Path(__file__)),"exp_tgt_001_code_sha256":sha256(RESEARCH/"exp_tgt_001.py"),"config_sector_mapping_sha256":hashlib.sha256(json.dumps(mapping,sort_keys=True).encode()).hexdigest(),
              "seed":0,"outputs":[p.name for p in sorted(RESULTS.glob("EXP-TGT-002*"))]}
    (MANIFESTS/"EXP-TGT-002_reproducibility.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2)); return summary


if __name__=="__main__": main()
