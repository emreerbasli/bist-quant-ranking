"""EXP-ROBUST-001: locked finalist stress, ablation and concentration."""
from __future__ import annotations
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
import lightgbm as lgb
import numpy as np
import pandas as pd
RESEARCH=Path(__file__).resolve().parent;ROOT=RESEARCH.parent;sys.path[:0]=[str(ROOT),str(RESEARCH)]
import config as cfg
import exp_model_001 as mm
import exp_port_001 as pp
import exp_tgt_001 as t1
import exp_tgt_002 as t2
C=RESEARCH/'contracts'/'exp_robust_001.json';R=RESEARCH/'results';M=RESEARCH/'manifests';ARCHS=('LGBM_REGRESSION','LAMBDAMART');FEATURES=('mom_12_1','mom_63','vol_63')
def sha(p):h=hashlib.sha256();h.update(Path(p).read_bytes());return h.hexdigest()
def params(mc,arch,seed,override=None):
 p=mm.tree_params(mc['models'][arch],seed);p.update(override or {});return p
def fit(arch,train,cols,mc,override=None):
 x=train[list(cols)].to_numpy(float);models=[]
 for seed in mc['tree_seeds']:
  if arch=='LGBM_REGRESSION':q=lgb.LGBMRegressor(**params(mc,arch,seed,override));q.fit(x,train.target_value.to_numpy(float))
  else:
   z=train.sort_values(['signal_date','symbol']);groups=z.groupby('signal_date',sort=True).size().to_numpy();q=lgb.LGBMRanker(**params(mc,arch,seed,override));q.fit(z[list(cols)].to_numpy(float),mm.relevance(z.target_rank),group=groups)
  models.append(q)
 return models
def predict(models,rows,cols):return np.median(np.column_stack([x.predict(rows[list(cols)].to_numpy(float)) for x in models]),axis=1)
def eval_scores(rows,s):
 met,per=mm.evaluate_scores(rows,s);return met,per
def noise_rows(rows,cols,train,scale,seed):
 z=rows.copy();rng=np.random.default_rng(seed);sd=train[list(cols)].std(ddof=0)
 for c in cols:z[c]=z[c]+rng.normal(0,scale*sd[c],len(z))
 return z
def rank_noise(rows,score,level,seeds):
 allp=[]
 for seed in seeds:
  rng=np.random.default_rng(seed);p=pd.Series(score,index=rows.index,dtype=float)
  for _,g in rows.groupby('signal_date'):
   sd=float(p.loc[g.index].std(ddof=0));p.loc[g.index]+=rng.normal(0,level*sd,len(g))
  allp.append(p.to_numpy())
 return np.median(np.column_stack(allp),axis=1)
def run_port(scored,cal,views,fold,cost=50,delay=0,capital=1_000_000,limit=.10):return pp.simulate(scored,cal,views,fold,{},10,cost,delay,capital,limit)[0]
def table(df,cols):
 x=df[cols].copy()
 for c in x:x[c]=x[c].map(lambda v:'N/A' if pd.isna(v) else f'{v:.4f}' if isinstance(v,(float,np.floating)) else str(v))
 return '| '+' | '.join(cols)+' |\n|'+'|'.join('---' for _ in cols)+'|\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in x.itertuples(index=False,name=None))
def concentration(cal,views):
 p=pd.read_csv(R/'EXP-PORT-001_positions.csv',parse_dates=['date']);p=p[(p.case=='K_SENSITIVITY')&(p.k==10)&(p.cost_bps==50)&(p.delay_sessions==0)&(p.capital_try==1_000_000)&(np.isclose(p.adv_limit_pct,.10))].copy();p['sector']=p.symbol.map(cfg.HISSE_SEKTOR).fillna('UNCLASSIFIED')
 vals=[]
 for row in p.itertuples(index=False):
  pos=cal.get_loc(pd.Timestamp(row.date));v=views[row.symbol];ret=np.nan
  if pos>0:
   a,b=v.iloc[pos-1],v.iloc[pos];
   if str(a.price_quality)!='UNRESOLVED' and str(b.price_quality)!='UNRESOLVED' and pd.notna(a.research_close) and pd.notna(b.research_close) and a.research_close>0:ret=float(b.research_close/a.research_close-1)
  vals.append(ret)
 p['contribution']=p.weight*np.asarray(vals);p=p[np.isfinite(p.contribution)]
 out=[]
 for arch,g in p.groupby('architecture'):
  stock=g.groupby('symbol').contribution.sum();sector=g.groupby('sector').contribution.sum();den=max(float(stock.abs().sum()),1e-12);ss=stock.abs().sort_values(ascending=False)
  out.append({'architecture':arch,'top1_abs_pnl_share':float(ss.head(1).sum()/den),'top3_abs_pnl_share':float(ss.head(3).sum()/den),'top5_abs_pnl_share':float(ss.head(5).sum()/den),'top10_abs_pnl_share':float(ss.head(10).sum()/den),'stock_pnl_hhi':float(((stock.abs()/den)**2).sum()),'largest_sector_abs_pnl_share':float(sector.abs().max()/max(sector.abs().sum(),1e-12)),'largest_sector':sector.abs().idxmax()})
 return pd.DataFrame(out),p
def bootstrap(cohorts,c):
 rng=np.random.default_rng(c['bootstrap']['seed']);B=c['bootstrap']['replications'];L=c['bootstrap']['block_length_signal_cohorts'];rows=[]
 for arch,g in cohorts.groupby('architecture'):
  g=g.sort_values('order');x=g[['rank_ic','net_return']].to_numpy();n=len(x);starts=np.arange(max(1,n-L+1));sim=[]
  for _ in range(B):
   z=[]
   while len(z)<n:z.extend(x[rng.choice(starts):][:L])
   a=np.asarray(z[:n]);mu=a[:,1].mean();sd=a[:,1].std(ddof=1);sim.append((a[:,0].mean(),mu,np.sqrt(252/60)*mu/sd if sd>0 else np.nan))
  s=np.asarray(sim);rows.append({'architecture':arch,'replications':B,'block_length':L,'ic_p05':np.quantile(s[:,0],.05),'ic_median':np.median(s[:,0]),'ic_p95':np.quantile(s[:,0],.95),'prob_ic_positive':np.mean(s[:,0]>0),'net_p05':np.quantile(s[:,1],.05),'net_median':np.median(s[:,1]),'net_p95':np.quantile(s[:,1],.95),'prob_net_positive':np.mean(s[:,1]>0),'sharpe_p05':np.nanquantile(s[:,2],.05),'sharpe_median':np.nanmedian(s[:,2]),'sharpe_p95':np.nanquantile(s[:,2],.95)})
 return pd.DataFrame(rows)
def main():
 R.mkdir(exist_ok=True);M.mkdir(exist_ok=True);c=json.loads(C.read_text());mc,tc1,tc2,cal,views,features,targets=mm.load_all();assert sha(mm.CONTRACT_PATH)==c['frozen']['model_contract_sha256'];assert sha(pp.C)==c['frozen']['portfolio_contract_sha256']
 sel=pd.read_csv(R/'EXP-MODEL-001_procedure_selections.csv');stress=[];perdates=[];base_scored=[];scores_store={}
 for fold in tc1['outer_folds']:
  for arch in ARCHS:
   x=sel[(sel.outer_fold==fold['id'])&(sel.architecture==arch)].iloc[0];family=x.selected_family;h=int(x.selected_horizon);train=t2.training_rows(targets,family,h,fold['test_start']);test=t2.rows_in_fold(targets,family,h,fold['test_start'],fold['test_end']);univ=features[(features.signal_date>=pd.Timestamp(fold['test_start']))&(features.signal_date<=pd.Timestamp(fold['test_end']))].copy()
   base_models=fit(arch,train,FEATURES,mc);basep=predict(base_models,test,FEATURES);met,per=eval_scores(test,basep);scores_store[(fold['id'],arch)]=(univ,predict(base_models,univ,FEATURES));perdates.append(per.assign(outer_fold=fold['id'],architecture=arch));base_scored.append(test.assign(score=basep,outer_fold=fold['id'],architecture=arch))
   stress.append({'outer_fold':fold['id'],'architecture':arch,'family':'BASE','case':'BASE',**met,**run_port(univ.assign(score=scores_store[(fold['id'],arch)][1]),cal,views,fold)})
   for removed in c['feature_ablation']:
    cols=[z for z in FEATURES if z!=removed];mods=fit(arch,train,cols,mc);pred=predict(mods,test,cols);met,_=eval_scores(test,pred);up=predict(mods,univ,cols);stress.append({'outer_fold':fold['id'],'architecture':arch,'family':'ABLATION','case':f'WITHOUT_{removed}',**met,**run_port(univ.assign(score=up),cal,views,fold)})
   for name,level in c['feature_noise']['levels'].items():
    nt=noise_rows(test,FEATURES,train,level,c['feature_noise']['seed']);nu=noise_rows(univ,FEATURES,train,level,c['feature_noise']['seed']);met,_=eval_scores(test,predict(base_models,nt,FEATURES));stress.append({'outer_fold':fold['id'],'architecture':arch,'family':'FEATURE_NOISE','case':name,**met,**run_port(univ.assign(score=predict(base_models,nu,FEATURES)),cal,views,fold)})
   for name,level in c['rank_perturbation']['levels'].items():
    pred=rank_noise(test,basep,level,c['rank_perturbation']['seeds']);met,_=eval_scores(test,pred);up=rank_noise(univ,scores_store[(fold['id'],arch)][1],level,c['rank_perturbation']['seeds']);stress.append({'outer_fold':fold['id'],'architecture':arch,'family':'RANK_NOISE','case':name,**met,**run_port(univ.assign(score=up),cal,views,fold)})
   for name,over in c['parameter_perturbation'].items():
    if not isinstance(over,dict): continue
    mods=fit(arch,train,FEATURES,mc,over);pred=predict(mods,test,FEATURES);met,_=eval_scores(test,pred);stress.append({'outer_fold':fold['id'],'architecture':arch,'family':'PARAMETER','case':name,**met,**run_port(univ.assign(score=predict(mods,univ,FEATURES)),cal,views,fold)})
 st=pd.DataFrame(stress);agg=st.groupby(['architecture','family','case']).agg(mean_rank_ic=('rank_ic_mean','mean'),median_rank_ic=('rank_ic_mean','median'),mean_net_return=('net_return','mean'),mean_sharpe=('sharpe','mean'),worst_maxdd=('daily_maxdd','min')).reset_index()
 # Leave-one-outer-period evidence, without redesign or refit.
 base=st[st.family.eq('BASE')];loo=[]
 for arch,g in base.groupby('architecture'):
  for omitted in sorted(g.outer_fold.unique()):
   z=g[g.outer_fold!=omitted];loo.append({'architecture':arch,'omitted_outer_period':omitted,'mean_rank_ic':z.rank_ic_mean.mean(),'mean_net_return':z.net_return.mean(),'mean_sharpe':z.sharpe.mean(),'worst_maxdd':z.daily_maxdd.min()})
 loo=pd.DataFrame(loo)
 # Cohort returns from frozen primary daily NAV and signal-date ICs.
 pn=pd.read_csv(R/'EXP-PORT-001_daily_nav.csv',parse_dates=['date']);pn=pn[(pn.case=='K_SENSITIVITY')&(pn.k==10)&(pn.cost_bps==50)&(pn.delay_sessions==0)&(pn.capital_try==1_000_000)&(np.isclose(pn.adv_limit_pct,.10))]
 per=pd.concat(perdates,ignore_index=True);scored_base=pd.concat(base_scored,ignore_index=True);co=[];order=0
 for (arch,fold),g in pn.groupby(['architecture','outer_fold']):
  g=g.sort_values('date').reset_index(drop=True);ic=per[(per.architecture==arch)&(per.outer_fold==fold)].sort_values('signal_date').rank_ic.to_numpy()
  for j,start in enumerate(range(0,len(g)-1,60)):
   end=min(start+60,len(g)-1);co.append({'architecture':arch,'outer_fold':fold,'order':order,'rank_ic':float(ic[min(j,len(ic)-1)]),'net_return':float(g.nav.iloc[end]/g.nav.iloc[start]-1)});order+=1
 cohorts=pd.DataFrame(co);boot=bootstrap(cohorts,c)
 conc,pnl=concentration(cal,views)
 sector_rows=[]
 for (arch,fold),g in scored_base.groupby(['architecture','outer_fold']):
  for omitted in sorted(g.sector.dropna().unique()):
   z=g[g.sector.ne(omitted)];met,_=eval_scores(z,z.score.to_numpy());sector_rows.append({'architecture':arch,'outer_fold':fold,'omitted_sector':omitted,**met})
 sector=pd.DataFrame(sector_rows);sector_summary=sector.groupby(['architecture','omitted_sector']).agg(mean_rank_ic=('rank_ic_mean','mean'),mean_ndcg=('ndcg_at_10_mean','mean')).reset_index()
 benchmark=t1.load_view('XU100.IS').reindex(cal);bclose=pd.to_numeric(benchmark.research_close,errors='coerce');bret=bclose.pct_change(fill_method=None);signal_dates=sorted(per.signal_date.unique());vol_values={d:float(bret.loc[:d].tail(63).std(ddof=1)) for d in signal_dates};vol_cut=float(np.nanmedian(list(vol_values.values())))
 regime_map={}
 for d in signal_dates:
  loc=cal.get_loc(pd.Timestamp(d));trend=float(bclose.iloc[loc]/bclose.iloc[loc-63]-1) if loc>=63 and bclose.iloc[loc-63]>0 else np.nan;regime_map[pd.Timestamp(d)]={'trend_regime':'TREND_UP' if trend>0 else 'TREND_DOWN','vol_regime':'VOL_HIGH' if vol_values[d]>vol_cut else 'VOL_LOW'}
 reg=per.copy();reg['trend_regime']=[regime_map[pd.Timestamp(d)]['trend_regime'] for d in reg.signal_date];reg['vol_regime']=[regime_map[pd.Timestamp(d)]['vol_regime'] for d in reg.signal_date]
 regime=pd.concat([reg.groupby(['architecture','trend_regime']).agg(mean_rank_ic=('rank_ic','mean'),observations=('rank_ic','size')).reset_index().rename(columns={'trend_regime':'regime'}),reg.groupby(['architecture','vol_regime']).agg(mean_rank_ic=('rank_ic','mean'),observations=('rank_ic','size')).reset_index().rename(columns={'vol_regime':'regime'})],ignore_index=True)
 # Reuse frozen Phase H cost/delay/capacity and Phase F seed evidence.
 costs=pd.read_csv(R/'EXP-PORT-001_cost_summary.csv');delay=pd.read_csv(R/'EXP-PORT-001_delay_summary.csv');cap=pd.read_csv(R/'EXP-PORT-001_capacity_summary.csv');seed=pd.read_csv(R/'EXP-MODEL-001_seed_metrics.csv')
 similarity=[]
 for fold in [x['id'] for x in tc1['outer_folds']]:
  a,sa=scores_store[(fold,'LGBM_REGRESSION')];b,sb=scores_store[(fold,'LAMBDAMART')];z=a[['signal_date','symbol']].copy();z['a']=sa;z['b']=sb
  for d,g in z.groupby('signal_date'):
   similarity.append({'outer_fold':fold,'signal_date':d,'rank_correlation':g.a.rank().corr(g.b.rank()),'top10_overlap':len(set(g.nlargest(10,'a').symbol)&set(g.nlargest(10,'b').symbol))/10})
 similarity=pd.DataFrame(similarity)
 dims=[];classes=[]
 for arch in ARCHS:
  aa=agg[agg.architecture==arch];cc=conc[conc.architecture==arch].iloc[0];bb=boot[boot.architecture==arch].iloc[0];lo=loo[loo.architecture==arch];co100=costs[(costs.architecture==arch)&(costs.cost_bps==100)].mean_net_return.iloc[0];de2=delay[(delay.architecture==arch)&(delay.delay_sessions==2)].mean_net_return.iloc[0];liq=cap[(cap.architecture==arch)&(cap.capital_try==50_000_000)&(np.isclose(cap.adv_limit_pct,.10))].mean_fill_rate.iloc[0];ss=seed[seed.architecture==arch].groupby('outer_fold').rank_ic_mean.std(ddof=0).mean()
  checks={'alpha':aa[aa.family.isin(['ABLATION','FEATURE_NOISE','PARAMETER'])].mean_rank_ic.min()>=0,'feature':(aa[aa.family=='ABLATION'].mean_rank_ic>=0).sum()>=2,'time':(lo.mean_net_return>0).all(),'sector':cc.largest_sector_abs_pnl_share<=.50,'stock':cc.top1_abs_pnl_share<=.25,'cost':co100>0,'delay':de2>0,'liquidity':liq>=.80,'seed_parameter':ss<=.05 and (aa[aa.family=='PARAMETER'].mean_rank_ic>=0).all()};passed=sum(checks.values())
  if not checks['cost'] or not checks['delay'] or (bb.prob_ic_positive<.5 and bb.prob_net_positive<.5):cl='REJECTED'
  elif passed==9:cl='ROBUST'
  elif passed>=6 and bb.prob_ic_positive>=.5 and bb.prob_net_positive>=.5:cl='ROBUST WITH CAVEATS'
  else:cl='FRAGILE'
  classes.append({'architecture':arch,'classification':cl,'dimensions_passed':passed,'bootstrap_prob_ic_positive':bb.prob_ic_positive,'bootstrap_prob_net_positive':bb.prob_net_positive,**{f'{k}_pass':v for k,v in checks.items()}})
 classes=pd.DataFrame(classes);gate='PASS' if classes.classification.isin(['ROBUST','ROBUST WITH CAVEATS']).all() else ('PARTIAL' if classes.classification.isin(['ROBUST','ROBUST WITH CAVEATS']).any() else 'FAIL')
 for name,df in [('stress_metrics',st),('stress_summary',agg),('leave_one_period_out',loo),('leave_one_sector_out',sector_summary),('concentration',conc),('pnl_contributions',pnl),('bootstrap',boot),('cohorts',cohorts),('price_regimes',regime),('ranking_similarity',similarity),('classification',classes)]:df.to_csv(R/f'EXP-ROBUST-001_{name}.csv',index=False)
 sections=[('1. Executive Summary',f'Phase I gate: **{gate}**.'),('2. Locked Stress Contract',f'`{C.name}` locked before results.'),('3. Frozen Finalists','LGBM Regression and LambdaMART; exact Phase F/H contracts and portfolio rules.'),('4. Feature Ablation',table(agg[agg.family.eq('ABLATION')],list(agg.columns))),('5. Feature Noise',table(agg[agg.family.eq('FEATURE_NOISE')],list(agg.columns))),('6. Rank Perturbation',table(agg[agg.family.eq('RANK_NOISE')],list(agg.columns))),('7. Delay Stress',table(delay,list(delay.columns))),('8. Cost Stress',table(costs,list(costs.columns))),('9. Liquidity / Capacity Stress',table(cap,list(cap.columns))),('10. Leave-One-Year-Out',table(loo,list(loo.columns))),('11. Sector Concentration',table(conc,['architecture','largest_sector','largest_sector_abs_pnl_share'])),('12. Stock / PnL Concentration',table(conc,list(conc.columns))),('13. Jackpot Dependence','Top contribution shares are absolute mark-to-market PnL shares; main results remain uncensored. '+table(conc,list(conc.columns))),('14. Block Bootstrap',table(boot,list(boot.columns))),('15. Parameter Perturbation',table(agg[agg.family.eq('PARAMETER')],list(agg.columns))),('16. Seed Stability','Fixed three-seed evidence reused; no best seed selection. '+table(seed.groupby('architecture').agg(mean_ic=('rank_ic_mean','mean'),std_ic=('rank_ic_mean','std')).reset_index(),['architecture','mean_ic','std_ic'])),('17. Price-Derived Regimes','Only pre-locked BIST price trend/volatility regimes are permitted; macro/FX labels excluded. Regime sample remains small and descriptive.'),('18. Model Similarity / Ranking Overlap',table(similarity.groupby(lambda _:True).agg(rank_correlation=('rank_correlation','mean'),top10_overlap=('top10_overlap','mean')).reset_index(drop=True),['rank_correlation','top10_overlap'])),('19. Robustness Classification',table(classes,list(classes.columns))),('20. Limitations','Signals/folds are dependent; bootstrap is uncertainty analysis, not independent market histories. Survivor universe, provider data and proxy sector taxonomy remain.'),('21. Tests','Dedicated robustness tests plus full research regression suite required.'),('22. Production Integrity','Final protected-production hash verification required.'),('23. Phase I Gate',f'**{gate}**\n\n'+table(classes,list(classes.columns))),('24. MASTER_PLAN\'e göre SINGLE NEXT BEST ACTION','Stop and review Phase I evidence before Phase J Pareto finalist decision; do not start it automatically.')]
 (R/'EXP-ROBUST-001_report.md').write_text('# EXP-ROBUST-001 — FINALIST STRESS, ABLATION & CONCENTRATION\n\n'+'\n\n'.join(f'## {h}\n\n{b}' for h,b in sections),encoding='utf-8')
 sj={'experiment_id':'EXP-ROBUST-001','execution':'PASS','phase_i_gate':gate,'classifications':classes.to_dict('records'),'generated_at_utc':datetime.now(timezone.utc).isoformat()};(R/'EXP-ROBUST-001_summary.json').write_text(json.dumps(sj,indent=2),encoding='utf-8');files=sorted(R.glob('EXP-ROBUST-001_*'));(M/'EXP-ROBUST-001_manifest.json').write_text(json.dumps({'contract_sha256':sha(C),'model_contract_sha256':sha(mm.CONTRACT_PATH),'portfolio_contract_sha256':sha(pp.C),'code_sha256':sha(Path(__file__)),'files':{p.name:sha(p) for p in files}},indent=2),encoding='utf-8');print(json.dumps(sj,indent=2))
if __name__=='__main__':main()
