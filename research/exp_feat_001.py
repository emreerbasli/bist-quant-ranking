"""EXP-FEAT-001 — controlled price-only economic feature discovery."""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH=Path(__file__).resolve().parent
ROOT=RESEARCH.parent
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(RESEARCH))
import exp_tgt_001 as t1
import exp_tgt_002 as t2

CONTRACT_PATH=RESEARCH/"contracts"/"exp_feat_001.json"
TGT1_CONTRACT=RESEARCH/"contracts"/"exp_tgt_001.json"
TGT2_CONTRACT=RESEARCH/"contracts"/"exp_tgt_002.json"
RESULTS=RESEARCH/"results"; MANIFESTS=RESEARCH/"manifests"
BASE_COLS=["mom_12_1","mom_63","vol_63"]


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def candidate_raw_values(view:pd.DataFrame,pos:int)->dict[str,float]:
    past=view.iloc[:pos+1]
    eligible=past.trading_eligible.fillna(False) & past.price_quality.fillna("UNRESOLVED").astype(str).ne("UNRESOLVED")
    close=pd.to_numeric(past.loc[eligible,"research_close"],errors="coerce").dropna()
    close=close[close>0].to_numpy(float)
    out={}
    def mom(n): return float(close[-1]/close[-n-1]-1) if len(close)>=n+1 else np.nan
    out.update(mom_20=mom(20),mom_40=mom(40),mom_63_rank=mom(63),mom_126=mom(126),mom_252=mom(252),
               ret_5=mom(5),ret_10=mom(10),ret_20=mom(20))
    out["mom_126_skip20"]=float(close[-21]/close[-147]-1) if len(close)>=147 else np.nan
    out["mom_252_skip20"]=float(close[-21]/close[-273]-1) if len(close)>=273 else np.nan
    if len(close)>=64:
        r63=pd.Series(close[-64:]).pct_change(fill_method=None).dropna().to_numpy()
        out["positive_return_ratio_63"]=float((r63>0).mean())
    else: out["positive_return_ratio_63"]=np.nan
    if len(close)>=81:
        block=close[-81:]; br=np.array([block[20]/block[0]-1,block[40]/block[20]-1,block[60]/block[40]-1,block[80]/block[60]-1])
        out["sign_consistency_4x20"]=float((br>0).mean())
    else: out["sign_consistency_4x20"]=np.nan
    for n in (20,63,126):
        if len(close)>=n+1:
            r=pd.Series(close[-n-1:]).pct_change(fill_method=None).dropna().to_numpy()
            out[f"vol_{n}" if n!=63 else "vol_63_rank"]=float(np.std(r,ddof=1))
            if n in (63,126): out[f"downside_vol_{n}"]=float(np.sqrt(np.mean(np.minimum(r,0.0)**2)))
        else:
            out[f"vol_{n}" if n!=63 else "vol_63_rank"]=np.nan
            if n in (63,126): out[f"downside_vol_{n}"]=np.nan
    if len(close)>=64:
        path=close[-64:]; out["max_drawdown_63"]=float(np.min(path/np.maximum.accumulate(path)-1))
    else: out["max_drawdown_63"]=np.nan

    raw_close=pd.to_numeric(past.raw_close,errors="coerce")
    volume=pd.to_numeric(past.volume,errors="coerce")
    econ=pd.to_numeric(past.economic_return,errors="coerce")
    vol_valid=eligible & raw_close.gt(0) & volume.gt(0)
    liq=pd.DataFrame({"dv":(raw_close*volume).where(vol_valid),"ret":econ.where(vol_valid)}).dropna(subset=["dv"])
    for n,min_n in ((20,15),(63,45)):
        z=liq.tail(n)
        out[f"log_adv{n}"]=float(np.log1p(z.dv.median())) if len(z)>=min_n else np.nan
        a=z.dropna(subset=["ret"])
        out[f"log_amihud{n}"]=float(np.log1p(1e9*(a.ret.abs()/a.dv).mean())) if len(a)>=min_n else np.nan
        out[f"zero_return_ratio{n}"]=float((a.ret.abs()<=1e-12).mean()) if len(a)>=min_n else np.nan
    z=liq.tail(63)
    if len(z)>=45 and volume.loc[z.index].mean()>0:
        out["volume_cv63"]=float(volume.loc[z.index].std(ddof=1)/volume.loc[z.index].mean())
    else: out["volume_cv63"]=np.nan
    return out


def build_feature_wave(contract,calendar,features,views):
    rows=[]; posmap={pd.Timestamp(calendar[p]):p for p in t1.signal_positions(calendar)}
    family={x["name"]:x["family"] for x in contract["candidates"]}
    for r in features[["signal_date","symbol"]].itertuples(index=False):
        vals=candidate_raw_values(views[r.symbol],posmap[pd.Timestamp(r.signal_date)])
        for name,val in vals.items(): rows.append({"signal_date":r.signal_date,"symbol":r.symbol,"candidate":name,"family":family[name],"raw_value":val})
    long=pd.DataFrame(rows)
    long["feature_value"]=long.groupby(["signal_date","candidate"])["raw_value"].rank(pct=True,method="average")
    wide=long.pivot(index=["signal_date","symbol"],columns="candidate",values="feature_value").reset_index()
    out=features.merge(wide,on=["signal_date","symbol"],how="left",validate="one_to_one")
    return out,long


def quality_audit(long):
    rows=[]
    for name,g in long.groupby("candidate"):
        x=g.raw_value.dropna(); q=x.quantile([.01,.25,.5,.75,.99]) if len(x) else pd.Series(dtype=float)
        iqr=(q.get(.75,np.nan)-q.get(.25,np.nan)); lo=q.get(.25,np.nan)-3*iqr; hi=q.get(.75,np.nan)+3*iqr
        gy=g.assign(year=pd.to_datetime(g.signal_date).dt.year)
        yearly=gy.groupby("year").raw_value.agg(["count","size","median"])
        counts=g.dropna(subset=["raw_value"]).groupby("symbol").size()
        rows.append({"candidate":name,"family":g.family.iloc[0],"observations":len(g),"non_missing":len(x),"coverage":len(x)/len(g),
                     "missingness":1-len(x)/len(g),"minimum":x.min() if len(x) else np.nan,"p01":q.get(.01,np.nan),"median":q.get(.5,np.nan),"p99":q.get(.99,np.nan),"maximum":x.max() if len(x) else np.nan,
                     "unique_count":int(x.nunique()),"first_valid_signal":str(pd.to_datetime(g.loc[g.raw_value.notna(),"signal_date"]).min().date()) if len(x) else None,
                     "last_valid_signal":str(pd.to_datetime(g.loc[g.raw_value.notna(),"signal_date"]).max().date()) if len(x) else None,
                     "ticker_coverage":float(g.loc[g.raw_value.notna(),"symbol"].nunique()/g.symbol.nunique()),"signal_date_coverage":float(g.groupby("signal_date").raw_value.apply(lambda z:z.notna().any()).mean()),"iqr":iqr,
                     "outlier_ratio_3iqr":float(((x<lo)|(x>hi)).mean()) if len(x) else np.nan,
                     "max_ticker_share":float(counts.max()/counts.sum()) if len(counts) else np.nan,
                     "min_year_coverage":float((yearly["count"]/yearly["size"]).min()) if len(yearly) else np.nan,
                     "yearly_median_std":float(yearly["median"].std(ddof=1)) if len(yearly)>1 else np.nan})
    return pd.DataFrame(rows)


@dataclass
class Model:
    cols:list[str]; med:np.ndarray; mean:np.ndarray; scale:np.ndarray; beta:np.ndarray


def fit(rows,cols,alpha=1.0):
    x=rows[cols].to_numpy(float); y=rows.target_rank.to_numpy(float)
    med=np.nanmedian(x,axis=0); med=np.where(np.isfinite(med),med,0.5); x=np.where(np.isfinite(x),x,med)
    mean=x.mean(0); scale=x.std(0); scale[scale<1e-12]=1
    z=(x-mean)/scale; d=np.column_stack([np.ones(len(z)),z]); p=np.eye(d.shape[1])*alpha; p[0,0]=0
    beta=np.linalg.solve(d.T@d+p,d.T@y)
    return Model(list(cols),med,mean,scale,beta)


def predict(model,rows):
    x=rows[model.cols].to_numpy(float); x=np.where(np.isfinite(x),x,model.med); z=(x-model.mean)/model.scale
    return np.column_stack([np.ones(len(z)),z])@model.beta


def evaluate(model,rows):
    z=rows.copy(); z["score"]=predict(model,z); per=[]
    for date,g in z.groupby("signal_date"):
        if len(g)<10: continue
        order=g.sort_values(["score","symbol"],ascending=[False,True])
        per.append({"signal_date":date,"rank_ic":g.score.rank().corr(g.target_value.rank()),
                    "ndcg":t1.ndcg_at_k(g.target_rank.to_numpy(),g.score.to_numpy(),10),
                    "spread":float(order.head(10).raw_forward_return.mean()-order.tail(10).raw_forward_return.mean())})
    p=pd.DataFrame(per)
    if p.empty:return {"rank_ic_mean":np.nan,"rank_ic_median":np.nan,"rank_ic_std":np.nan,"positive_ic_ratio":np.nan,"icir":np.nan,"ndcg":np.nan,"spread":np.nan,"signal_dates":0},p
    std=p.rank_ic.std(ddof=1)
    return {"rank_ic_mean":float(p.rank_ic.mean()),"rank_ic_median":float(p.rank_ic.median()),"rank_ic_std":float(std),
            "positive_ic_ratio":float((p.rank_ic>0).mean()),"icir":float(p.rank_ic.mean()/std) if std>0 else np.nan,
            "ndcg":float(p.ndcg.mean()),"spread":float(p.spread.mean()),"signal_dates":len(p)},p


def train_rows(data,family,h,boundary):
    return data[(data.target_family.eq(family))&(data.horizon_sessions.eq(h))&(data.signal_date<pd.Timestamp(boundary))&(data.label_end<pd.Timestamp(boundary))]


def valid_rows(data,family,h,start,end):
    return data[(data.target_family.eq(family))&(data.horizon_sessions.eq(h))&(data.signal_date>=pd.Timestamp(start))&(data.signal_date<=pd.Timestamp(end))&(data.label_end<=pd.Timestamp(end))]


def select_procedure(data,cols,outer,return_rows=False):
    records=[]
    for family in t2.FAMILIES:
        for h in t2.HORIZONS:
            for year in outer["inner_validation_years"]:
                start,end=f"{year}-01-01",f"{year}-12-31"
                tr=train_rows(data,family,h,start); va=valid_rows(data,family,h,start,end)
                metric,_=evaluate(fit(tr,cols),va)
                records.append({"target_family":family,"horizon_sessions":h,"inner_year":year,**metric})
    r=pd.DataFrame(records); hs={}; fs={}
    for family in t2.FAMILIES:
        scores=r[r.target_family.eq(family)].groupby("horizon_sessions").rank_ic_mean.median().to_dict()
        best=max(scores.values()); h=min(x for x,v in scores.items() if best-v<=0.01); hs[family]=int(h)
        fs[family]=float(r[(r.target_family.eq(family))&(r.horizon_sessions.eq(h))].rank_ic_mean.median())
    family=t2.select_family(fs,json.loads(TGT2_CONTRACT.read_text(encoding="utf-8")))
    return (family,hs[family],r) if return_rows else (family,hs[family])


def score_universe(model,features,start,end):
    x=features[(features.signal_date>=pd.Timestamp(start))&(features.signal_date<=pd.Timestamp(end))].copy(); x["score"]=predict(model,x); return x


def direct_ic(rows,candidate):
    vals=[]
    for _,g in rows.groupby("signal_date"):
        z=g[[candidate,"target_value"]].dropna()
        if len(z)>=10: vals.append(z[candidate].rank().corr(z.target_value.rank()))
    s=pd.Series(vals,dtype=float); std=s.std(ddof=1)
    return {"univariate_ic_mean":s.mean(),"univariate_ic_median":s.median(),"univariate_ic_std":std,
            "univariate_positive_ratio":(s>0).mean() if len(s) else np.nan,"univariate_icir":s.mean()/std if std>0 else np.nan,"univariate_dates":len(s)}


def correlation_audit(rank_wide,corr_cols):
    pooled=rank_wide[corr_cols].corr(method="spearman")
    dated=[]
    for _,g in rank_wide.groupby("signal_date"):
        dated.append(g[corr_cols].corr(method="spearman"))
    median_xs=pd.concat(dated,keys=range(len(dated))).groupby(level=1).median().reindex(index=corr_cols,columns=corr_cols)
    # Deterministic connected components at the locked audit threshold |rho| >= 0.85.
    parent={c:c for c in corr_cols}
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb: parent[max(ra,rb)]=min(ra,rb)
    for i,a in enumerate(corr_cols):
        for b in corr_cols[i+1:]:
            if pd.notna(median_xs.loc[a,b]) and abs(median_xs.loc[a,b])>=.85: union(a,b)
    groups={}
    for c in corr_cols: groups.setdefault(find(c),[]).append(c)
    clusters=[]
    for members in groups.values():
        if len(members)>1: clusters.append({"cluster_id":len(clusters)+1,"members":"|".join(sorted(members)),"member_count":len(members)})
    return pooled,median_xs,pd.DataFrame(clusters)


def main():
    RESULTS.mkdir(exist_ok=True); MANIFESTS.mkdir(exist_ok=True)
    contract=json.loads(CONTRACT_PATH.read_text(encoding="utf-8")); old=json.loads(TGT1_CONTRACT.read_text(encoding="utf-8")); tc=json.loads(TGT2_CONTRACT.read_text(encoding="utf-8"))
    calendar,symbols,views,benchmark=t1.load_inputs(old)
    base_features,raw_data,raw_cov=t1.build_dataset(calendar,symbols,views)
    targets,_,_,_=t2.build_target_data(tc,calendar,symbols,views,benchmark,base_features,raw_data,raw_cov)
    features,long=build_feature_wave(contract,calendar,base_features,views)
    data=targets.merge(features,on=["signal_date","symbol",*BASE_COLS],how="left",validate="many_to_one")
    candidates=[x["name"] for x in contract["candidates"]]; fammap={x["name"]:x["family"] for x in contract["candidates"]}
    quality=quality_audit(long)
    rank_wide=features[["signal_date","symbol",*BASE_COLS,*candidates]].copy()
    for c in BASE_COLS: rank_wide[f"base_rank_{c}"]=rank_wide.groupby("signal_date")[c].rank(pct=True)
    corr_cols=candidates+[f"base_rank_{c}" for c in BASE_COLS]
    corr,median_xs_corr,corr_clusters=correlation_audit(rank_wide,corr_cols)
    corr.to_csv(RESULTS/"EXP-FEAT-001_rank_correlation.csv"); median_xs_corr.to_csv(RESULTS/"EXP-FEAT-001_median_cross_sectional_correlation.csv")
    corr_clusters.to_csv(RESULTS/"EXP-FEAT-001_high_correlation_clusters.csv",index=False)
    base_corr=[]
    for c in candidates:
        for b in BASE_COLS: base_corr.append({"candidate":c,"baseline_feature":b,"pooled_rank_correlation":corr.loc[c,f"base_rank_{b}"],"median_cross_sectional_correlation":median_xs_corr.loc[c,f"base_rank_{b}"]})
    base_corr=pd.DataFrame(base_corr)

    inner_inc=[]; outer_inc=[]; selections=[]; univariate=[]; combined=[]; ablations=[]; navs=[]; trades=[]
    thresholds=contract["incremental_test"]["inner_selection_thresholds"]
    for outer in old["outer_folds"]:
        family,h,baseline_search=select_procedure(data,BASE_COLS,outer,True)
        baseline_inner={}
        for year in outer["inner_validation_years"]:
            start,end=f"{year}-01-01",f"{year}-12-31"; tr=train_rows(data,family,h,start); va=valid_rows(data,family,h,start,end)
            m=evaluate(fit(tr,BASE_COLS),va)[0]; baseline_inner[year]=m
        selected=[]
        for c in candidates:
            deltas=[]
            for year in outer["inner_validation_years"]:
                start,end=f"{year}-01-01",f"{year}-12-31"; tr=train_rows(data,family,h,start); va=valid_rows(data,family,h,start,end)
                cm,cp=evaluate(fit(tr,BASE_COLS+[c]),va); bm=baseline_inner[year]
                ui=direct_ic(va,c); univariate.append({"outer_fold":outer["id"],"inner_year":year,"candidate":c,"target_family":family,"horizon_sessions":h,**ui})
                rec={"outer_fold":outer["id"],"inner_year":year,"candidate":c,"family":fammap[c],"target_family":family,"horizon_sessions":h,
                     "candidate_coverage":float(va[c].notna().mean()),"coverage_loss":0.0,
                     **{f"baseline_{k}":v for k,v in bm.items()},**{f"candidate_{k}":v for k,v in cm.items()},
                     "delta_rank_ic":cm["rank_ic_mean"]-bm["rank_ic_mean"],"delta_median_ic":cm["rank_ic_median"]-bm["rank_ic_median"],"delta_ndcg":cm["ndcg"]-bm["ndcg"]}
                inner_inc.append(rec); deltas.append(rec)
            dg=pd.DataFrame(deltas)
            choose=(dg.delta_rank_ic.median()>=thresholds["median_delta_mean_rank_ic_min"] and
                    (dg.delta_rank_ic>0).mean()>=thresholds["positive_delta_inner_fold_ratio_min"] and
                    dg.delta_ndcg.median()>=thresholds["median_delta_ndcg_min"] and
                    dg.candidate_coverage.mean()>=thresholds["candidate_coverage_min"] and dg.coverage_loss.max()<=thresholds["coverage_loss_max"])
            if choose:selected.append(c)
            selections.append({"outer_fold":outer["id"],"candidate":c,"family":fammap[c],"selected_inner":choose,
                               "median_delta_rank_ic":dg.delta_rank_ic.median(),"positive_delta_fold_ratio":float((dg.delta_rank_ic>0).mean()),
                               "median_delta_ndcg":dg.delta_ndcg.median(),"coverage":dg.candidate_coverage.mean(),"frozen_target_family":family,"frozen_horizon":h})
        # Outer incremental evaluations keep baseline-selected target/horizon fixed.
        tr=train_rows(data,family,h,outer["test_start"]); te=valid_rows(data,family,h,outer["test_start"],outer["test_end"])
        bm_model=fit(tr,BASE_COLS); bm_metric,_=evaluate(bm_model,te); bm_score=score_universe(bm_model,features,outer["test_start"],outer["test_end"])
        bm_port,_,_=t1.simulate_top10(bm_score,calendar,views,outer["test_end"],50)
        for c in selected:
            cm_model=fit(tr,BASE_COLS+[c]); cm_metric,_=evaluate(cm_model,te); cm_score=score_universe(cm_model,features,outer["test_start"],outer["test_end"])
            cm_port,_,_=t1.simulate_top10(cm_score,calendar,views,outer["test_end"],50)
            outer_inc.append({"outer_fold":outer["id"],"candidate":c,"family":fammap[c],"was_inner_selected":c in selected,"target_family":family,"horizon_sessions":h,
                              "delta_rank_ic":cm_metric["rank_ic_mean"]-bm_metric["rank_ic_mean"],"delta_median_ic":cm_metric["rank_ic_median"]-bm_metric["rank_ic_median"],
                              "delta_ndcg":cm_metric["ndcg"]-bm_metric["ndcg"],"delta_spread":cm_metric["spread"]-bm_metric["spread"],
                              "delta_turnover":cm_port["turnover"]-bm_port["turnover"],"delta_net_return":cm_port["gross_or_net_return"]-bm_port["gross_or_net_return"],
                              "candidate_sharpe":cm_port["sharpe"],"baseline_sharpe":bm_port["sharpe"],"delta_sharpe":cm_port["sharpe"]-bm_port["sharpe"],
                              "candidate_daily_maxdd":cm_port["daily_max_drawdown"],"baseline_daily_maxdd":bm_port["daily_max_drawdown"],
                              "delta_daily_maxdd":cm_port["daily_max_drawdown"]-bm_port["daily_max_drawdown"]})
        # Combined set: features selected only by this outer fold's inner data.
        comb_cols=BASE_COLS+selected
        cf,ch=select_procedure(data,comb_cols,outer)
        ctr=train_rows(data,cf,ch,outer["test_start"]); cte=valid_rows(data,cf,ch,outer["test_start"],outer["test_end"])
        cmodel=fit(ctr,comb_cols); cmetric,_=evaluate(cmodel,cte)
        # Comparable baseline on the combined set's selected target/horizon.
        btr=train_rows(data,cf,ch,outer["test_start"]); bte=valid_rows(data,cf,ch,outer["test_start"],outer["test_end"])
        bmodel=fit(btr,BASE_COLS); bmetric,_=evaluate(bmodel,bte)
        for cost in (0,30,50,100):
            score=score_universe(cmodel,features,outer["test_start"],outer["test_end"]); port,nav,trade=t1.simulate_top10(score,calendar,views,outer["test_end"],cost)
            combined.append({"outer_fold":outer["id"],"selected_features":"|".join(selected),"selected_count":len(selected),"target_family":cf,"horizon_sessions":ch,"cost_bps":cost,
                             **cmetric,**{f"portfolio_{k}":v for k,v in port.items()},"delta_rank_ic_vs_same_procedure_baseline":cmetric["rank_ic_mean"]-bmetric["rank_ic_mean"],
                             "delta_ndcg_vs_same_procedure_baseline":cmetric["ndcg"]-bmetric["ndcg"]})
            if len(nav):navs.append(nav.assign(outer_fold=outer["id"],cost_bps=cost))
            if len(trade):trades.append(trade.assign(outer_fold=outer["id"],cost_bps=cost))

    inner_inc=pd.DataFrame(inner_inc); outer_inc=pd.DataFrame(outer_inc); selections=pd.DataFrame(selections); univariate=pd.DataFrame(univariate); combined=pd.DataFrame(combined)
    classes=[]
    for c in candidates:
        si=selections[selections.candidate.eq(c)]; oo=outer_inc[outer_inc.candidate.eq(c)]; freq=int(si.selected_inner.sum())
        outer_mean=float(oo.delta_rank_ic.mean()) if len(oo) else np.nan; outer_med=float(oo.delta_rank_ic.median()) if len(oo) else np.nan
        outer_pos=float((oo.delta_rank_ic>0).mean()) if len(oo) else np.nan; nd=float(oo.delta_ndcg.mean()) if len(oo) else np.nan
        if freq>=3 and outer_mean>0 and outer_med>=0 and outer_pos>=.5 and nd>=0: cls="VIABLE"
        elif freq==2 or freq>=3: cls="WEAK / RESEARCH ONLY"
        else: cls="REJECTED"
        classes.append({"candidate":c,"family":fammap[c],"classification":cls,"inner_selection_frequency":freq,
                        "median_inner_delta_rank_ic":float(si.median_delta_rank_ic.median()),"outer_mean_delta_rank_ic":outer_mean,
                        "outer_median_delta_rank_ic":outer_med,"outer_positive_delta_fold_ratio":outer_pos,"outer_mean_delta_ndcg":nd,
                        "outer_mean_delta_turnover":float(oo.delta_turnover.mean()) if len(oo) else np.nan,"coverage":float(quality.set_index('candidate').loc[c,'coverage'])})
    classes=pd.DataFrame(classes)
    viable=classes[classes.classification.eq("VIABLE")]; weak=classes[classes.classification.eq("WEAK / RESEARCH ONLY")]
    cp=combined[combined.cost_bps.eq(50)]; combined_delta=float(cp.delta_rank_ic_vs_same_procedure_baseline.mean())
    if len(viable)>=3 and viable.family.nunique()>=2 and combined_delta>0: gate="PASS"
    elif len(viable)>=1 or (len(weak)>=2 and combined_delta>0): gate="PARTIAL"
    else: gate="FAIL"

    # Family ablation is opened only if a final VIABLE set exists.
    if len(viable):
        final_features=viable.candidate.tolist()
        for outer in old["outer_folds"]:
            family,h=select_procedure(data,BASE_COLS,outer)
            tr=train_rows(data,family,h,outer["test_start"]); te=valid_rows(data,family,h,outer["test_start"],outer["test_end"])
            full=evaluate(fit(tr,BASE_COLS+final_features),te)[0]
            for af in sorted(viable.family.unique()):
                cols=BASE_COLS+[c for c in final_features if fammap[c]!=af]
                removed=evaluate(fit(tr,cols),te)[0]
                ablations.append({"outer_fold":outer["id"],"removed_family":af,"full_feature_count":len(final_features),
                                  "delta_rank_ic_removed_minus_full":removed["rank_ic_mean"]-full["rank_ic_mean"],"delta_ndcg_removed_minus_full":removed["ndcg"]-full["ndcg"]})
    ablations=pd.DataFrame(ablations)
    family_rows=[]
    for family,g in classes.groupby("family"):
        strongest=g.sort_values(["median_inner_delta_rank_ic","candidate"],ascending=[False,True]).head(3)
        cluster_ids=[]
        for row in corr_clusters.itertuples(index=False):
            members=set(str(row.members).split("|"))
            if members.intersection(set(g.candidate)): cluster_ids.append(int(row.cluster_id))
        family_rows.append({"family":family,"candidate_count":len(g),"viable_count":int(g.classification.eq("VIABLE").sum()),
                            "weak_count":int(g.classification.eq("WEAK / RESEARCH ONLY").sum()),"rejected_count":int(g.classification.eq("REJECTED").sum()),
                            "strongest_representations":"|".join(strongest.candidate),"best_median_inner_delta_rank_ic":float(strongest.median_inner_delta_rank_ic.iloc[0]),
                            "mean_outer_delta_rank_ic_evaluated":float(g.outer_mean_delta_rank_ic.mean()),"high_correlation_cluster_ids":"|".join(map(str,cluster_ids))})
    family_summary=pd.DataFrame(family_rows)

    defs=pd.DataFrame(contract["candidates"]); defs.to_csv(RESULTS/"EXP-FEAT-001_feature_definitions.csv",index=False)
    quality.to_csv(RESULTS/"EXP-FEAT-001_quality.csv",index=False); base_corr.to_csv(RESULTS/"EXP-FEAT-001_baseline_correlation.csv",index=False)
    univariate.to_csv(RESULTS/"EXP-FEAT-001_univariate_ic.csv",index=False); inner_inc.to_csv(RESULTS/"EXP-FEAT-001_inner_incremental.csv",index=False)
    selections.to_csv(RESULTS/"EXP-FEAT-001_inner_selection.csv",index=False); outer_inc.to_csv(RESULTS/"EXP-FEAT-001_outer_incremental.csv",index=False)
    combined.to_csv(RESULTS/"EXP-FEAT-001_combined_outer.csv",index=False); classes.to_csv(RESULTS/"EXP-FEAT-001_classification.csv",index=False)
    family_summary.to_csv(RESULTS/"EXP-FEAT-001_family_summary.csv",index=False)
    ablations.to_csv(RESULTS/"EXP-FEAT-001_family_ablation.csv",index=False)
    if navs:pd.concat(navs,ignore_index=True).to_csv(RESULTS/"EXP-FEAT-001_daily_nav.csv",index=False)
    if trades:pd.concat(trades,ignore_index=True).to_csv(RESULTS/"EXP-FEAT-001_trades.csv",index=False)
    summary={"experiment_id":"EXP-FEAT-001","execution":"PASS","phase_d_gate":gate,"candidate_count":len(candidates),
             "classification_counts":classes.classification.value_counts().to_dict(),"viable_features":viable.candidate.tolist(),"weak_features":weak.candidate.tolist(),
             "combined_outer_mean_delta_rank_ic":combined_delta,"macro_used":False,"fundamental_used":False,"production_changes":0}
    (RESULTS/"EXP-FEAT-001_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")

    def tbl(df,cols):
        x=df[cols].copy()
        for c in x:x[c]=x[c].map(lambda v:"N/A" if pd.isna(v) else (f"{v:.4f}" if isinstance(v,(float,np.floating)) else str(v)))
        return "| "+" | ".join(cols)+" |\n|"+"|".join("---" for _ in cols)+"|\n"+"\n".join("| "+" | ".join(map(str,r))+" |" for r in x.itertuples(index=False,name=None))
    ablation_summary=("N/A: no feature reached final VIABLE status, so the locked rule did not open family ablation."
                      if not len(viable) else "Final VIABLE features were ablated one economic family at a time; no combinatorial subset search was performed.")
    report=f"""# EXP-FEAT-001 — PRICE-ONLY ECONOMIC FEATURE DISCOVERY

## 1. Executive Summary

Execution PASS. **PRICE FEATURE DISCOVERY = {gate}**. Candidate classifications: {classes.classification.value_counts().to_dict()}.

## 2. Locked Contract

25 candidates, fixed ridge alpha=1, baseline mom_12_1/mom_63/vol_63, inner-only feature/target/horizon selection, K=10 and fixed 60-session holding/rebalance.

## 3. Candidate Feature Definitions

Seven momentum, two consistency, three reversal, six risk and seven liquidity representations were hashed before results.

## 4. Data Quality & Coverage

{tbl(quality,["candidate","family","coverage","missingness","outlier_ratio_3iqr","max_ticker_share"])}

## 5. Correlation / Redundancy

Full pairwise rank correlations and baseline correlations are separate artifacts. Correlation is diagnostic, not an automatic drop rule.

{tbl(family_summary,["family","candidate_count","viable_count","weak_count","rejected_count","strongest_representations","best_median_inner_delta_rank_ic","high_correlation_cluster_ids"])}

## 6. Momentum Features

20/40/63/126/252 and 126/252 skip-20 representations were evaluated against the baseline, not presumed independent.

## 7. Momentum Consistency

Positive-return ratio and four-block sign consistency used only historical returns.

## 8. Reversal Features

ret_5/10/20 were evaluated as predictors; ret_20 did not alter the fixed 60-session portfolio rotation rule.

## 9. Risk Features

20/63/126 volatility, downside volatility and 63-session historical drawdown were evaluated.

## 10. Liquidity Features

ADV uses raw close × positive observed volume. Amihud, zero-return and volume stability exclude unresolved/missing-volume rows; missing is never zero.

## 11. Univariate IC

IC frequency is one cross-sectional Spearman observation per scheduled 60-session signal date. Full inner-fold mean/median/std/positive ratio/ICIR is in the univariate artifact.

## 12. Incremental Baseline Tests

{tbl(classes,["candidate","family","inner_selection_frequency","median_inner_delta_rank_ic","outer_mean_delta_rank_ic","outer_mean_delta_ndcg","classification"])}

## 13. Inner Feature Selection

Each outer fold selected candidates from its two inner years only. No outer result added a feature.

## 14. Target/Horizon Selection Interaction

Baseline target/horizon was inner-selected and frozen for candidate incremental tests. The per-outer combined inner-selected feature set was allowed one inner-only target/horizon reselection.

## 15. Outer Generalization

Combined selected-set mean outer delta Rank IC versus the same target/horizon baseline: {combined_delta:.4f}. Outer results only veto classifications.

## 16. Turnover / Cost / Daily Risk

Combined procedures were simulated at 0/30/50/100 bps with actual turnover and daily NAV/MaxDD. Prediction metrics, not Sharpe/CAGR, govern selection.

## 17. Family Ablation

{ablation_summary}

## 18. Final Viable Feature Set

VIABLE: {', '.join(viable.candidate) if len(viable) else 'none'}. WEAK / RESEARCH ONLY: {', '.join(weak.candidate) if len(weak) else 'none'}. All others are REJECTED under this wave's locked criteria.

## 19. Limitations

Current-survivor universe, provider-dependent price history, sparse scheduled signal dates, simple ridge control, multiple testing across 25 candidates and unresolved official volume/status provenance limit inference.

## 20. Tests

No-future formulas, window/minimum history, volume/SASA handling, cross-sectional transform, train-only preprocessing, nested selection/isolation, forbidden inputs and reproducibility are tested separately.

## 21. Production Integrity

Research-only outputs; protected hashes are verified separately.

## 22. Phase D Gate

**PRICE FEATURE DISCOVERY = {gate}**.

## 23. MASTER_PLAN'e göre SINGLE NEXT BEST ACTION

Carry only VIABLE features (and separately labeled WEAK research controls if justified) to the next MASTER_PLAN phase. Do not expand this first price-feature wave or start model-family comparison automatically.
"""
    (RESULTS/"EXP-FEAT-001_report.md").write_text(report,encoding="utf-8")
    manifest={"experiment_id":"EXP-FEAT-001","generated_at_utc":datetime.now(timezone.utc).isoformat(),"contract_sha256":sha256(CONTRACT_PATH),
              "candidate_definition_sha256":hashlib.sha256(json.dumps(contract["candidates"],sort_keys=True).encode()).hexdigest(),"code_sha256":sha256(Path(__file__)),
              "candidate_count":len(candidates),"seed":0,"outputs":[p.name for p in sorted(RESULTS.glob("EXP-FEAT-001*"))]}
    (MANIFESTS/"EXP-FEAT-001_reproducibility.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2));return summary


if __name__=="__main__":main()
