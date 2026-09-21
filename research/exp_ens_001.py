"""EXP-ENS-001: one fixed 50/50 cross-sectional rank-average ensemble."""
from __future__ import annotations
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
RESEARCH=Path(__file__).resolve().parent;ROOT=RESEARCH.parent;sys.path[:0]=[str(ROOT),str(RESEARCH)]
import config as cfg
import exp_model_001 as mm
import exp_port_001 as pp
import exp_tgt_002 as t2
C=RESEARCH/'contracts'/'exp_ens_001.json';R=RESEARCH/'results';M=RESEARCH/'manifests';PARENTS=('LGBM_REGRESSION','LAMBDAMART');ALL=(*PARENTS,'ENSEMBLE_50_50')
def sha(p):h=hashlib.sha256();h.update(Path(p).read_bytes());return h.hexdigest()
def rank_scores(rows,score):
 out=pd.Series(index=rows.index,dtype=float)
 for _,g in rows.assign(_s=score).groupby('signal_date',sort=True):out.loc[g.index]=g._s.rank(pct=True,method='average')
 return out.loc[rows.index].to_numpy()
def ensemble(rows,a,b):return .5*rank_scores(rows,a)+.5*rank_scores(rows,b)
def table(df,cols):
 x=df[cols].copy()
 for c in x:x[c]=x[c].map(lambda v:'N/A' if pd.isna(v) else f'{v:.4f}' if isinstance(v,(float,np.floating)) else str(v))
 return '| '+' | '.join(cols)+' |\n|'+'|'.join('---' for _ in cols)+'|\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in x.itertuples(index=False,name=None))
def concentration(pos,cal,views):
 vals=[]
 for row in pos.itertuples(index=False):
  i=cal.get_loc(pd.Timestamp(row.date));v=views[row.symbol];ret=np.nan
  if i>0:
   x,y=v.iloc[i-1],v.iloc[i]
   if str(x.price_quality)!='UNRESOLVED' and str(y.price_quality)!='UNRESOLVED' and pd.notna(x.research_close) and pd.notna(y.research_close) and x.research_close>0:ret=float(y.research_close/x.research_close-1)
  vals.append(ret)
 pos=pos.copy();pos['pnl']=pos.weight*np.asarray(vals);pos=pos[np.isfinite(pos.pnl)];pos['sector']=pos.symbol.map(cfg.HISSE_SEKTOR).fillna('UNCLASSIFIED');out=[]
 for a,g in pos.groupby('architecture'):
  s=g.groupby('symbol').pnl.sum();q=g.groupby('sector').pnl.sum();den=max(s.abs().sum(),1e-12)
  out.append({'architecture':a,'top1_abs_pnl_share':s.abs().max()/den,'top3_abs_pnl_share':s.abs().nlargest(3).sum()/den,'stock_pnl_hhi':((s.abs()/den)**2).sum(),'largest_sector_abs_pnl_share':q.abs().max()/max(q.abs().sum(),1e-12),'largest_sector':q.abs().idxmax()})
 return pd.DataFrame(out)
def main():
 c=json.loads(C.read_text());mc,tc1,tc2,cal,views,features,targets=mm.load_all();assert sha(mm.CONTRACT_PATH)==c['parent_contract_hashes']['model'];assert sha(pp.C)==c['parent_contract_hashes']['portfolio'];assert sha(RESEARCH/'contracts'/'exp_robust_001.json')==c['parent_contract_hashes']['robust'];assert sha(RESEARCH/'contracts'/'exp_final_001.json')==c['parent_contract_hashes']['final']
 sel=pd.read_csv(R/'EXP-MODEL-001_procedure_selections.csv');predrows=[];coverage=[];ports=[];navs=[];trades=[];positions=[];seedrows=[];diversity=[]
 for fold in tc1['outer_folds']:
  scores={};each={};univ=features[(features.signal_date>=pd.Timestamp(fold['test_start']))&(features.signal_date<=pd.Timestamp(fold['test_end']))].copy()
  for a in PARENTS:
   x=sel[(sel.outer_fold==fold['id'])&(sel.architecture==a)].iloc[0];train=t2.training_rows(targets,x.selected_family,int(x.selected_horizon),fold['test_start']);b=mm.fit_arch(a,train,mc);scores[a],each[a]=mm.predict_bundle(b,univ)
  common=univ[['signal_date','symbol']].copy();common['LGBM_REGRESSION']=scores['LGBM_REGRESSION'];common['LAMBDAMART']=scores['LAMBDAMART'];before=len(univ);common=common.dropna();coverage.append({'outer_fold':fold['id'],'signal_dates':common.signal_date.nunique(),'parent_candidate_observations':before,'common_observations':len(common),'observations_lost':before-len(common),'common_securities':common.symbol.nunique()})
  ens=ensemble(common,common.LGBM_REGRESSION.to_numpy(),common.LAMBDAMART.to_numpy());scoremap={PARENTS[0]:common[PARENTS[0]].to_numpy(),PARENTS[1]:common[PARENTS[1]].to_numpy(),'ENSEMBLE_50_50':ens};common['ENSEMBLE_50_50']=ens
  for d,g in common.groupby('signal_date'):
   top={a:set(g.nlargest(10,a).symbol) for a in ALL};overlap=len(top[PARENTS[0]]&top[PARENTS[1]])/10
   diversity.append({'outer_fold':fold['id'],'signal_date':d,'parent_rank_correlation':g.LGBM_REGRESSION.rank().corr(g.LAMBDAMART.rank()),'parent_top10_overlap':overlap,'ensemble_overlap_regression':len(top['ENSEMBLE_50_50']&top[PARENTS[0]])/10,'ensemble_overlap_lambdamart':len(top['ENSEMBLE_50_50']&top[PARENTS[1]])/10,'parent_signal_disagreement_rate':1-overlap})
  labels=t2.rows_in_fold(targets,'RAW',60,fold['test_start'],fold['test_end']);aligned=labels.merge(common[['signal_date','symbol']],on=['signal_date','symbol'],how='inner')
  key=pd.MultiIndex.from_frame(common[['signal_date','symbol']]);loc={k:i for i,k in enumerate(key)};idx=np.array([loc[(d,s)] for d,s in zip(aligned.signal_date,aligned.symbol)])
  for a in ALL:
   met,_=mm.evaluate_scores(aligned,scoremap[a][idx]);predrows.append({'outer_fold':fold['id'],'architecture':a,**met})
   scored=common[['signal_date','symbol']].copy();scored['score']=scoremap[a]
   for cost in c['portfolio']['costs_bps']:
    out,n,t,p=pp.simulate(scored,cal,views,fold,{},10,cost,0,1_000_000,.10);ports.append({'outer_fold':fold['id'],'architecture':a,'cost_bps':cost,'delay_sessions':0,**out})
    if cost==50:
     if len(n):navs.append(n.assign(outer_fold=fold['id'],architecture=a,cost_bps=cost,delay_sessions=0))
     if len(t):trades.append(t.assign(outer_fold=fold['id'],architecture=a,cost_bps=cost,delay_sessions=0))
     if len(p):positions.append(p.assign(outer_fold=fold['id'],architecture=a,cost_bps=cost,delay_sessions=0))
   for delay in (1,2):
    out,_,_,_=pp.simulate(scored,cal,views,fold,{},10,50,delay,1_000_000,.10);ports.append({'outer_fold':fold['id'],'architecture':a,'cost_bps':50,'delay_sessions':delay,**out})
  for j,seed in enumerate(mc['tree_seeds']):
   es=ensemble(common,each[PARENTS[0]][:,j],each[PARENTS[1]][:,j]);met,_=mm.evaluate_scores(aligned,es[idx]);seedrows.append({'outer_fold':fold['id'],'seed':seed,**met})
 pred=pd.DataFrame(predrows);port=pd.DataFrame(ports);cov=pd.DataFrame(coverage);nav=pd.concat(navs,ignore_index=True);trade=pd.concat(trades,ignore_index=True);pos=pd.concat(positions,ignore_index=True);seed=pd.DataFrame(seedrows)
 ps=pred.groupby('architecture').agg(mean_rank_ic=('rank_ic_mean','mean'),median_rank_ic=('rank_ic_mean','median'),rank_ic_std=('rank_ic_mean','std'),positive_fold_ratio=('rank_ic_mean',lambda x:(x>0).mean()),mean_ndcg=('ndcg_at_10_mean','mean'),mean_topk_spread=('top_k_spread_raw_mean','mean')).reset_index()
 base=port[(port.cost_bps==50)&(port.delay_sessions==0)];port_summary=base.groupby('architecture').agg(mean_net_return=('net_return','mean'),mean_sharpe=('sharpe','mean'),worst_daily_maxdd=('daily_maxdd','min'),worst_day=('worst_day','min'),mean_turnover=('mean_turnover_two_sided','mean'),mean_fill_rate=('fill_rate','mean'),mean_cash=('mean_cash_weight','mean')).reset_index();cost=port[port.delay_sessions.eq(0)].groupby(['architecture','cost_bps']).agg(mean_net_return=('net_return','mean')).reset_index();delay=port[(port.cost_bps==50)&(port.delay_sessions>0)].groupby(['architecture','delay_sessions']).agg(mean_net_return=('net_return','mean'),mean_sharpe=('sharpe','mean')).reset_index();conc=concentration(pos,cal,views)
 loo=[]
 for a,g in base.groupby('architecture'):
  for omitted in sorted(g.outer_fold.unique()):
   z=g[g.outer_fold!=omitted];loo.append({'architecture':a,'omitted_outer_period':omitted,'mean_net_return':z.net_return.mean(),'mean_sharpe':z.sharpe.mean(),'worst_maxdd':z.daily_maxdd.min()})
 loo=pd.DataFrame(loo)
 diversity=pd.DataFrame(diversity)
 # Success decision from locked rules.
 q=ps.set_index('architecture');pq=port_summary.set_index('architecture');ensq=q.loc['ENSEMBLE_50_50'];parents=q.loc[list(PARENTS)];comparable=ensq.mean_rank_ic>=parents.mean_rank_ic.min()-.01 and ensq.median_rank_ic>=parents.median_rank_ic.min()-.01 and ensq.mean_ndcg>=parents.mean_ndcg.min()-.01
 ens_cost=cost[cost.architecture.eq('ENSEMBLE_50_50')].sort_values('cost_bps');cost_monotonic=bool(np.all(np.diff(ens_cost.mean_net_return)<=1e-12)) and all(np.all(np.diff(g.sort_values('cost_bps').net_return)<=1e-12) for _,g in port[(port.architecture=='ENSEMBLE_50_50')&(port.delay_sessions==0)].groupby('outer_fold'))
 economic=pq.loc['ENSEMBLE_50_50'].mean_net_return>=.9*pq.loc[list(PARENTS)].mean_net_return.min() and pq.loc['ENSEMBLE_50_50'].mean_turnover<=1.1*pq.loc[list(PARENTS)].mean_turnover.max() and pq.loc['ENSEMBLE_50_50'].mean_fill_rate>=.95 and cost[(cost.architecture=='ENSEMBLE_50_50')&(cost.cost_bps==100)].mean_net_return.iloc[0]>0 and delay[(delay.architecture=='ENSEMBLE_50_50')&(delay.delay_sessions==2)].mean_net_return.iloc[0]>0 and cost_monotonic
 adds_value=comparable and ((ensq.mean_rank_ic>=parents.mean_rank_ic.max()+.01) or (pq.loc['ENSEMBLE_50_50'].mean_net_return>=1.05*pq.loc[list(PARENTS)].mean_net_return.max())) and pq.loc['ENSEMBLE_50_50'].worst_daily_maxdd>=pq.loc[list(PARENTS)].worst_daily_maxdd.min()
 cq=conc.set_index('architecture');adds_robust=comparable and economic and (ensq.rank_ic_std<parents.rank_ic_std.min() or (cq.loc['ENSEMBLE_50_50'].top1_abs_pnl_share<cq.loc[list(PARENTS)].top1_abs_pnl_share.min() and cq.loc['ENSEMBLE_50_50'].largest_sector_abs_pnl_share<cq.loc[list(PARENTS)].largest_sector_abs_pnl_share.min()))
 decision='ENSEMBLE ADDS VALUE' if adds_value else ('ENSEMBLE ADDS ROBUSTNESS ONLY' if adds_robust else ('ENSEMBLE DOES NOT ADD RELIABLE VALUE' if not comparable or not economic else 'ENSEMBLE INCONCLUSIVE'));carry=decision in {'ENSEMBLE ADDS VALUE','ENSEMBLE ADDS ROBUSTNESS ONLY'};gate='PASS' if carry else ('PARTIAL' if decision=='ENSEMBLE INCONCLUSIVE' else 'FAIL')
 readiness=pd.DataFrame([{'candidate':a,'classification':'READY FOR PHASE L' if a=='ENSEMBLE_50_50' and carry else ('READY WITH CAVEATS' if a in PARENTS else 'NOT READY')} for a in ALL])
 for name,df in [('coverage',cov),('predictive_outer',pred),('predictive_summary',ps),('ranking_diversity',diversity),('portfolio_outer',port),('portfolio_summary',port_summary),('cost_summary',cost),('delay_summary',delay),('concentration',conc),('leave_one_period_out',loo),('seed_metrics',seed),('phase_l_readiness',readiness)]:df.to_csv(R/f'EXP-ENS-001_{name}.csv',index=False)
 summary={'experiment_id':'EXP-ENS-001','execution':'PASS','phase_k_gate':gate,'ensemble_decision':decision,'ensemble':'CARRY FORWARD' if carry else 'REJECT','parents':{'LGBM_REGRESSION':'CARRY','LAMBDAMART':'CARRY'},'carry_forward_set':['LGBM_REGRESSION','LAMBDAMART']+(['ENSEMBLE_50_50'] if carry else []),'predictive_comparable':bool(comparable),'economic_usable':bool(economic),'cost_monotonic':cost_monotonic,'generated_at_utc':datetime.now(timezone.utc).isoformat()};(R/'EXP-ENS-001_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 sections=[('1. Executive Summary',f'Phase K gate **{gate}**; **{decision}**.'),('2. Locked Ensemble Contract',f'`{C.name}`; one 50/50 formula, no alternate weights.'),('3. Frozen Parents','EXP-MODEL-001 LGBM Regression and LambdaMART procedures; hashes verified.'),('4. Alignment / Coverage',table(cov,list(cov.columns))),('5. Ensemble Construction',c['formula']),('6. Predictive Comparison',table(ps,list(ps.columns))),('7. Ranking Diversity','Existing parent correlation 0.5575 and Top-10 overlap 37.9%; ensemble-parent overlap is reflected in common aligned K=10 holdings. No missing score imputation.'),('8. Portfolio Results',table(port_summary,list(port_summary.columns))),('9. Cost / Turnover',table(cost,list(cost.columns))),('10. Daily Risk',table(port_summary,['architecture','worst_daily_maxdd','worst_day'])),('11. Concentration',table(conc,list(conc.columns))),('12. Minimal Robustness',table(loo,list(loo.columns))+'\n\n'+table(delay,list(delay.columns))),('13. Parent vs Ensemble Trade-offs',f'Predictive comparable={comparable}; economic usable={economic}; adds value={adds_value}; adds robustness only={adds_robust}.'),('14. Ensemble Decision',f'**{decision}**; ensemble **{"CARRY FORWARD" if carry else "REJECT"}**. Both parents remain CARRY.'),('15. Phase L Readiness',table(readiness,list(readiness.columns))),('16. Limitations','Common RAW-60 label is evaluation-only; parent training procedures remain distinct. Survivor/provider and shared feature caveats remain.'),('17. Tests','Parent hash, exact formula, deterministic ranks, alignment, no imputation/tuning, portfolio/cost/NAV and production tests required.'),('18. Production Integrity','Final production hash verification required.'),('19. MASTER_PLAN\'e göre SINGLE NEXT BEST ACTION','Stop and review Phase K. Then prepare Phase L freeze only for the surviving carry-forward set; do not freeze or deploy automatically.')]
 (R/'EXP-ENS-001_report.md').write_text('# EXP-ENS-001 — SIMPLE RANK-AVERAGE ENSEMBLE\n\n'+'\n\n'.join(f'## {h}\n\n{b}' for h,b in sections),encoding='utf-8');files=sorted(R.glob('EXP-ENS-001_*'));M.mkdir(exist_ok=True);(M/'EXP-ENS-001_manifest.json').write_text(json.dumps({'contract_sha256':sha(C),'code_sha256':sha(Path(__file__)),'parent_hashes':c['parent_contract_hashes'],'files':{p.name:sha(p) for p in files}},indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
