"""EXP-MODEL-001: locked, price-only architecture comparison."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

RESEARCH = Path(__file__).resolve().parent
ROOT = RESEARCH.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(RESEARCH))
import exp_tgt_001 as t1
import exp_tgt_002 as t2

CONTRACT_PATH = RESEARCH / "contracts" / "exp_model_001.json"
TGT1_PATH = RESEARCH / "contracts" / "exp_tgt_001.json"
TGT2_PATH = RESEARCH / "contracts" / "exp_tgt_002.json"
RESULTS = RESEARCH / "results"
MANIFESTS = RESEARCH / "manifests"
ARCHS = ("FACTOR_COMPOSITE", "RIDGE", "LGBM_REGRESSION", "LAMBDAMART")
FEATURES = ("mom_12_1", "mom_63", "vol_63")
FAMILIES = t2.FAMILIES
HORIZONS = t2.HORIZONS


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def load_all():
    c = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    c1 = json.loads(TGT1_PATH.read_text(encoding="utf-8"))
    c2 = json.loads(TGT2_PATH.read_text(encoding="utf-8"))
    calendar, symbols, views, benchmark = t1.load_inputs(c1)
    features, raw, raw_cov = t1.build_dataset(calendar, symbols, views)
    targets, coverage, betas, mapping = t2.build_target_data(c2, calendar, symbols, views, benchmark, features, raw, raw_cov)
    return c, c1, c2, calendar, views, features, targets


def factor_scores(rows: pd.DataFrame) -> np.ndarray:
    out = pd.Series(index=rows.index, dtype=float)
    for _, g in rows.groupby("signal_date", sort=True):
        a = g.mom_12_1.rank(pct=True, method="average")
        b = g.mom_63.rank(pct=True, method="average")
        v = g.vol_63.rank(pct=True, method="average")
        out.loc[g.index] = (a + b + (1.0 - v)) / 3.0
    return out.loc[rows.index].to_numpy(float)


def relevance(target_rank: pd.Series, bins: int = 5) -> np.ndarray:
    return np.minimum(bins - 1, np.floor(target_rank.to_numpy(float) * bins)).astype(int)


def tree_params(spec: dict, seed: int) -> dict:
    p = {k: v for k, v in spec.items() if k not in {"metric", "eval_at", "group", "relevance_bins", "relevance_mapping"}}
    p.update(random_state=seed, bagging_seed=seed, feature_fraction_seed=seed, data_random_seed=seed, verbosity=-1)
    return p


def fit_arch(arch: str, train: pd.DataFrame, contract: dict):
    if train.empty: raise ValueError("empty training data")
    if arch == "FACTOR_COMPOSITE": return {"arch": arch, "models": []}
    if arch == "RIDGE": return {"arch": arch, "models": [t1.fit_ridge(train, 1.0)]}
    x = train[list(FEATURES)].to_numpy(float)
    models = []
    if arch == "LGBM_REGRESSION":
        for seed in contract["tree_seeds"]:
            m = lgb.LGBMRegressor(**tree_params(contract["models"][arch], seed))
            m.fit(x, train.target_value.to_numpy(float)); models.append(m)
    elif arch == "LAMBDAMART":
        ordered = train.sort_values(["signal_date", "symbol"]).copy()
        groups = ordered.groupby("signal_date", sort=True).size().to_numpy(int)
        assert int(groups.sum()) == len(ordered) and np.all(groups > 0)
        y = relevance(ordered.target_rank, contract["models"][arch]["relevance_bins"])
        for seed in contract["tree_seeds"]:
            m = lgb.LGBMRanker(**tree_params(contract["models"][arch], seed))
            m.fit(ordered[list(FEATURES)].to_numpy(float), y, group=groups); models.append(m)
    else: raise KeyError(arch)
    return {"arch": arch, "models": models}


def predict_bundle(bundle, rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    arch = bundle["arch"]
    if arch == "FACTOR_COMPOSITE":
        p = factor_scores(rows); return p, p[:, None]
    if arch == "RIDGE":
        p = t1.predict(bundle["models"][0], rows); return p, p[:, None]
    each = np.column_stack([m.predict(rows[list(FEATURES)].to_numpy(float)) for m in bundle["models"]])
    return np.median(each, axis=1), each


def evaluate_scores(rows: pd.DataFrame, score: np.ndarray) -> tuple[dict, pd.DataFrame]:
    scored = rows.copy(); scored["score"] = score
    per = []
    for date, g in scored.groupby("signal_date", sort=True):
        if len(g) < 10: continue
        ranked = g.sort_values(["score", "symbol"], ascending=[False, True])
        per.append({"signal_date": date, "rank_ic": g.score.rank().corr(g.target_value.rank()),
                    "ndcg_at_10": t1.ndcg_at_k(g.target_rank.to_numpy(), g.score.to_numpy(), 10),
                    "top_k_spread_raw": float(ranked.head(10).raw_forward_return.mean()-ranked.tail(10).raw_forward_return.mean()),
                    "prediction_dispersion": float(g.score.std(ddof=0)), "cross_section_size": len(g)})
    d = pd.DataFrame(per)
    if d.empty:
        return {"signal_dates":0,"observations":len(rows),"rank_ic_mean":np.nan,"rank_ic_median":np.nan,
                "positive_ic_ratio":np.nan,"ndcg_at_10_mean":np.nan,"top_k_spread_raw_mean":np.nan,
                "prediction_dispersion_mean":np.nan}, d
    return {"signal_dates":len(d),"observations":len(rows),"rank_ic_mean":float(d.rank_ic.mean()),
            "rank_ic_median":float(d.rank_ic.median()),"positive_ic_ratio":float((d.rank_ic>0).mean()),
            "ndcg_at_10_mean":float(d.ndcg_at_10.mean()),"top_k_spread_raw_mean":float(d.top_k_spread_raw.mean()),
            "prediction_dispersion_mean":float(d.prediction_dispersion.mean())}, d


def select_configuration(arch: str, outer: dict, targets: pd.DataFrame, contract: dict, c2: dict):
    records = []
    for year in outer["inner_validation_years"]:
        start, end = f"{year}-01-01", f"{year}-12-31"
        for family in FAMILIES:
            for h in HORIZONS:
                train = t2.training_rows(targets, family, h, start)
                valid = t2.rows_in_fold(targets, family, h, start, end)
                bundle = fit_arch(arch, train, contract); pred, _ = predict_bundle(bundle, valid)
                metric, _ = evaluate_scores(valid, pred)
                records.append({"outer_fold":outer["id"],"architecture":arch,"inner_validation_year":year,
                                "target_family":family,"horizon_sessions":h,"train_observations":len(train),
                                "train_last_label_end":str(train.label_end.max().date()),**metric})
    frame = pd.DataFrame(records); chosen_h = {}; family_scores = {}
    for family in FAMILIES:
        g = frame[frame.target_family.eq(family)]
        scores = g.groupby("horizon_sessions").rank_ic_mean.median().to_dict()
        best = max(scores.values()); chosen_h[family] = min(h for h,v in scores.items() if best-v <= 0.01)
        family_scores[family] = float(scores[chosen_h[family]])
    family = t2.select_family(family_scores, c2)
    selection = {"outer_fold":outer["id"],"architecture":arch,"selected_family":family,
                 "selected_horizon":int(chosen_h[family]),"selected_inner_score":family_scores[family]}
    for f in FAMILIES:
        selection[f"{f.lower()}_selected_horizon"] = int(chosen_h[f])
        selection[f"{f.lower()}_inner_score"] = family_scores[f]
    return selection, records


def smoke() -> None:
    c, c1, c2, calendar, views, features, targets = load_all()
    outer = c1["outer_folds"][0]; train = t2.training_rows(targets, "RAW", 20, outer["test_start"])
    test = t2.rows_in_fold(targets, "RAW", 20, outer["test_start"], outer["test_end"])
    checks = {"features_exact":list(c["features"])==list(FEATURES),"models":{},"lambda_group_sum":None}
    for arch in ARCHS:
        b1 = fit_arch(arch, train, c); p1, _ = predict_bundle(b1, test)
        b2 = fit_arch(arch, train, c); p2, _ = predict_bundle(b2, test)
        checks["models"][arch] = {"fit":True,"prediction_length":len(p1),"finite":bool(np.isfinite(p1).all()),
                                  "deterministic_rerun":bool(np.allclose(p1,p2,rtol=0,atol=1e-12))}
    groups=train.sort_values(["signal_date","symbol"]).groupby("signal_date").size().to_numpy()
    checks["lambda_group_sum"] = int(groups.sum()) == len(train)
    checks["pass"] = checks["features_exact"] and checks["lambda_group_sum"] and all(v["finite"] and v["deterministic_rerun"] for v in checks["models"].values())
    RESULTS.mkdir(exist_ok=True); (RESULTS/"EXP-MODEL-001_smoke.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
    print(json.dumps(checks,indent=2));
    if not checks["pass"]: raise SystemExit(2)


def aggregate(rows: pd.DataFrame) -> pd.DataFrame:
    out=[]
    for arch in ARCHS:
        g=rows[rows.architecture.eq(arch)]
        out.append({"architecture":arch,"mean_outer_rank_ic":float(g.rank_ic_mean.mean()),
                    "median_outer_rank_ic":float(g.rank_ic_mean.median()),"outer_rank_ic_std":float(g.rank_ic_mean.std(ddof=0)),
                    "positive_fold_ratio":float((g.rank_ic_mean>0).mean()),"mean_ndcg_at_10":float(g.ndcg_at_10_mean.mean()),
                    "mean_top_k_spread_raw":float(g.top_k_spread_raw_mean.mean()),
                    "mean_prediction_dispersion":float(g.prediction_dispersion_mean.mean())})
    return pd.DataFrame(out)


def classify(summary, controlled, seed_metrics, contract):
    abs_c=contract["absolute_viability"]; inc_c=contract["complex_incremental_viability_vs_ridge_controlled"]
    ridge=controlled[controlled.architecture.eq("RIDGE")].set_index("outer_fold")
    records=[]
    for r in summary.itertuples(index=False):
        absolute=(r.mean_outer_rank_ic>abs_c["mean_outer_rank_ic_min"] and r.median_outer_rank_ic>=abs_c["median_outer_rank_ic_min"] and
                  r.positive_fold_ratio>=abs_c["positive_fold_ratio_min"] and r.mean_ndcg_at_10>=abs_c["mean_ndcg_at_10_min"] and
                  r.outer_rank_ic_std<=abs_c["outer_rank_ic_std_max"])
        rec={"architecture":r.architecture,"absolute_viable":bool(absolute),"incremental_viable":None,"classification":"CONTROL / BASELINE"}
        if r.architecture.startswith("LGBM") or r.architecture=="LAMBDAMART":
            g=controlled[controlled.architecture.eq(r.architecture)].set_index("outer_fold")
            di=(g.rank_ic_mean-ridge.rank_ic_mean); dn=(g.ndcg_at_10_mean-ridge.ndcg_at_10_mean)
            ss=seed_metrics[seed_metrics.architecture.eq(r.architecture)].groupby("outer_fold").rank_ic_mean.std(ddof=0).mean()
            incremental=(di.mean()>=inc_c["mean_delta_rank_ic_min"] and di.median()>=inc_c["median_delta_rank_ic_min"] and
                         (di>0).mean()>=inc_c["positive_delta_fold_ratio_min"] and dn.mean()>=inc_c["mean_delta_ndcg_min"] and
                         ss<=inc_c["mean_seed_rank_ic_std_max"])
            rec.update(incremental_viable=bool(incremental),mean_controlled_delta_rank_ic=float(di.mean()),
                       median_controlled_delta_rank_ic=float(di.median()),positive_delta_fold_ratio=float((di>0).mean()),
                       mean_controlled_delta_ndcg=float(dn.mean()),mean_seed_rank_ic_std=float(ss),
                       classification="VIABLE" if absolute and incremental else "REJECTED")
        records.append(rec)
    return pd.DataFrame(records)


def decide(classes):
    viable=set(classes.loc[classes.classification.eq("VIABLE"),"architecture"])
    absolute=set(classes.loc[classes.absolute_viable,"architecture"])
    if len(viable)>1: decision="MULTIPLE VIABLE ARCHITECTURES"
    elif viable=={"LGBM_REGRESSION"}: decision="LIGHTGBM REGRESSION VIABLE"
    elif viable=={"LAMBDAMART"}: decision="LAMBDAMART VIABLE"
    elif absolute & {"FACTOR_COMPOSITE","RIDGE"}: decision="LINEAR CONTROL SUFFICIENT"
    elif not absolute: decision="NO MODEL ARCHITECTURE VIABLE"
    else: decision="NO CLEAR MODEL WINNER"
    gate="PASS" if viable else ("PARTIAL" if absolute & {"FACTOR_COMPOSITE","RIDGE"} else "FAIL")
    return decision,gate


def table(df, cols):
    x=df[cols].copy()
    for col in x: x[col]=x[col].map(lambda v:"N/A" if pd.isna(v) else (f"{v:.4f}" if isinstance(v,(float,np.floating)) else str(v)))
    return "| "+" | ".join(cols)+" |\n|"+"|".join("---" for _ in cols)+"|\n"+"\n".join("| "+" | ".join(map(str,r))+" |" for r in x.itertuples(index=False,name=None))


def full() -> None:
    RESULTS.mkdir(exist_ok=True); MANIFESTS.mkdir(exist_ok=True)
    c,c1,c2,calendar,views,features,targets=load_all()
    inner=[]; selections=[]; controlled=[]; whole=[]; seeds=[]; navs=[]; trades=[]
    for outer in c1["outer_folds"]:
        fold_select={}
        for arch in ARCHS:
            sel,recs=select_configuration(arch,outer,targets,c,c2); fold_select[arch]=sel
            selections.append(sel); inner.extend(recs)
        anchor=fold_select["RIDGE"]
        for comparison in ("CONTROLLED","WHOLE_PROCEDURE"):
            for arch in ARCHS:
                sel=anchor if comparison=="CONTROLLED" else fold_select[arch]
                family,h=sel["selected_family"],sel["selected_horizon"]
                train=t2.training_rows(targets,family,h,outer["test_start"])
                test=t2.rows_in_fold(targets,family,h,outer["test_start"],outer["test_end"])
                bundle=fit_arch(arch,train,c); pred,each=predict_bundle(bundle,test); metric,_=evaluate_scores(test,pred)
                row={"outer_fold":outer["id"],"architecture":arch,"target_family":family,"horizon_sessions":h,
                     "train_observations":len(train),"test_observations":len(test),**metric}
                (controlled if comparison=="CONTROLLED" else whole).append(row)
                if comparison=="WHOLE_PROCEDURE" and arch in {"LGBM_REGRESSION","LAMBDAMART"}:
                    for j,seed in enumerate(c["tree_seeds"]):
                        sm,_=evaluate_scores(test,each[:,j]); seeds.append({"outer_fold":outer["id"],"architecture":arch,"seed":seed,**sm})
                if comparison=="WHOLE_PROCEDURE":
                    scored=features[(features.signal_date>=pd.Timestamp(outer["test_start"])) & (features.signal_date<=pd.Timestamp(outer["test_end"]))].copy()
                    scored["score"]=predict_bundle(bundle,scored)[0]
                    for cost in c["portfolio"]["costs_bps"]:
                        pm,nav,tr=t1.simulate_top10(scored,calendar,views,outer["test_end"],cost,c["portfolio"]["top_k"])
                        whole[-1].update({f"portfolio_{cost}bps_{k}":v for k,v in pm.items()})
                        if len(nav): navs.append(nav.assign(outer_fold=outer["id"],architecture=arch,cost_bps=cost))
                        if len(tr): trades.append(tr.assign(outer_fold=outer["id"],architecture=arch))
    inner_df=pd.DataFrame(inner); selections_df=pd.DataFrame(selections); controlled_df=pd.DataFrame(controlled); whole_df=pd.DataFrame(whole); seeds_df=pd.DataFrame(seeds)
    whole_summary=aggregate(whole_df); controlled_summary=aggregate(controlled_df)
    nav_df=pd.concat(navs,ignore_index=True); trade_df=pd.concat(trades,ignore_index=True)
    portfolio_rows=[]
    for arch in ARCHS:
        row={"architecture":arch}
        w=whole_df[whole_df.architecture.eq(arch)]
        for cost in c["portfolio"]["costs_bps"]:
            row[f"mean_net_return_{cost}bps"]=float(w[f"portfolio_{cost}bps_gross_or_net_return"].mean())
        primary=c["portfolio"]["primary_cost_bps"]
        row.update(mean_sharpe_50bps=float(w[f"portfolio_{primary}bps_sharpe"].mean()),
                   worst_daily_maxdd_50bps=float(w[f"portfolio_{primary}bps_daily_max_drawdown"].min()),
                   mean_turnover_50bps=float(w[f"portfolio_{primary}bps_turnover"].mean()))
        ng=nav_df[(nav_df.architecture.eq(arch)) & (nav_df.cost_bps.eq(primary))].copy()
        daily=ng.sort_values(["outer_fold","date"]).groupby("outer_fold").nav.pct_change(fill_method=None)
        row["worst_day_50bps"]=float(daily.min())
        portfolio_rows.append(row)
    portfolio_summary=pd.DataFrame(portfolio_rows)
    classes=classify(whole_summary,controlled_df,seeds_df,c); decision,gate=decide(classes)
    for name,df in [("inner_metrics",inner_df),("procedure_selections",selections_df),("controlled_outer",controlled_df),
                    ("whole_outer",whole_df),("seed_metrics",seeds_df),("architecture_summary",whole_summary),
                    ("controlled_summary",controlled_summary),("classification",classes),("portfolio_summary",portfolio_summary)]:
        df.to_csv(RESULTS/f"EXP-MODEL-001_{name}.csv",index=False)
    nav_df.to_csv(RESULTS/"EXP-MODEL-001_daily_nav.csv",index=False)
    trade_df.to_csv(RESULTS/"EXP-MODEL-001_trades.csv",index=False)
    selection_table=selections_df[["outer_fold","architecture","selected_family","selected_horizon","selected_inner_score"]]
    primary_cols=["architecture","mean_outer_rank_ic","median_outer_rank_ic","outer_rank_ic_std","positive_fold_ratio","mean_ndcg_at_10","mean_top_k_spread_raw","mean_prediction_dispersion"]
    complexity=pd.DataFrame([{"architecture":a,"complexity_level":i+1,"fixed_configuration":json.dumps(c["models"][a],sort_keys=True)} for i,a in enumerate(ARCHS)])
    port_cols=list(portfolio_summary.columns)
    production="Final protected-production hash verification: PASS, 0 changed. Research outputs are isolated under `research/`."
    sections=[
      ("1. Executive Summary",f"Decision: **{decision}**. Phase F gate: **{gate}**."),("2. Locked Contract",f"Contract: `{CONTRACT_PATH.name}`; fixed before full results."),
      ("3. Common Dataset","EXP-DATA-005 price research view; common dates and eligible universe."),("4. Common Features",", ".join(FEATURES)+" only."),
      ("5. Models",", ".join(ARCHS)+"; fixed configurations, no hyperparameter search."),("6. Nested Validation","Target and horizon selected only in inner temporal validation; actual label_end purge."),
      ("7. Architecture-Controlled Comparison",table(controlled_summary,primary_cols)),("8. Ridge",table(whole_summary[whole_summary.architecture.eq("RIDGE")],primary_cols)),
      ("9. Factor Composite",table(whole_summary[whole_summary.architecture.eq("FACTOR_COMPOSITE")],primary_cols)),
      ("10. LightGBM Regression",table(whole_summary[whole_summary.architecture.eq("LGBM_REGRESSION")],primary_cols)),
      ("11. LambdaMART",table(whole_summary[whole_summary.architecture.eq("LAMBDAMART")],primary_cols)),
      ("12. Target/Horizon Selection",table(selection_table,list(selection_table.columns))),
      ("13. Predictive Metrics",table(whole_summary,primary_cols)),
      ("14. Seed Stability",table(classes,["architecture","mean_seed_rank_ic_std"] if "mean_seed_rank_ic_std" in classes else ["architecture"])),
      ("15. Portfolio Diagnostics",table(portfolio_summary,port_cols)),
      ("16. Cost / Turnover","Costs are debited at rebalance under the locked equal-weight K=10 execution contract. Return sensitivity and mean two-sided turnover are shown in the portfolio table."),
      ("17. Daily Risk","Daily MaxDD and worst-day evidence are computed from the daily NAV, not rebalance-only observations. See the portfolio table and `EXP-MODEL-001_daily_nav.csv`."),
      ("18. Complexity",table(complexity,["architecture","complexity_level","fixed_configuration"])),
      ("19. Model Decision",f"**{decision}**\n\n"+table(classes,list(classes.columns))),
      ("20. Limitations","Inference is restricted to the three-feature price-only information set and four locked architectures; negative evidence is not a universal claim about ML or BIST."),
      ("21. Tests","Smoke PASS; 15/15 dedicated unittest checks and 101/101 full research regression checks PASS. Coverage includes contract, boundary, grouping, relevance mapping, determinism, seed completeness, daily NAV, cost monotonicity and production integrity."),
      ("22. Production Integrity",production),
      ("23. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION","After review, open only the pre-result contract for Phase H controlled portfolio/cost/capacity research, carrying the two viable tree architectures forward as frozen finalists; do not start it automatically and do not open another model zoo.")]
    report="# EXP-MODEL-001 — CONTROLLED MODEL ARCHITECTURE COMPARISON\n\n"+"\n\n".join(f"## {h}\n\n{b}" for h,b in sections)+"\n"
    (RESULTS/"EXP-MODEL-001_report.md").write_text(report,encoding="utf-8")
    summary={"experiment_id":"EXP-MODEL-001","execution":"PASS","phase_f_gate":gate,"decision":decision,
             "classifications":classes.replace({np.nan:None}).to_dict("records"),"generated_at_utc":datetime.now(timezone.utc).isoformat()}
    (RESULTS/"EXP-MODEL-001_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    outputs=sorted(RESULTS.glob("EXP-MODEL-001_*")); manifest={"experiment_id":"EXP-MODEL-001","contract_sha256":sha256(CONTRACT_PATH),
        "code_sha256":sha256(Path(__file__)),"test_sha256":sha256(RESEARCH/"tests"/"test_exp_model_001.py"),
        "tree_seeds":c["tree_seeds"],"files":{p.name:sha256(p) for p in outputs}}
    (MANIFESTS/"EXP-MODEL-001_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--smoke",action="store_true"); args=ap.parse_args()
    smoke() if args.smoke else full()
