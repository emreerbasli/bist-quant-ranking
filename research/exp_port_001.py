"""EXP-PORT-001: portfolio/cost/capacity layer for frozen EXP-MODEL-001 finalists."""
from __future__ import annotations
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
RESEARCH=Path(__file__).resolve().parent; ROOT=RESEARCH.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(RESEARCH))
import config as cfg
import exp_model_001 as m
import exp_tgt_001 as t1
import exp_tgt_002 as t2

C=RESEARCH/'contracts'/'exp_port_001.json'; R=RESEARCH/'results'; M=RESEARCH/'manifests'
ARCHS=('LGBM_REGRESSION','LAMBDAMART')
def sha(p):
 h=hashlib.sha256();h.update(Path(p).read_bytes());return h.hexdigest()
def metrics(nav):
 nav=nav.dropna();ret=nav.pct_change(fill_method=None).dropna();dd=nav/nav.cummax()-1
 yrs=max(len(ret)/252,1/252)
 return {'net_return':float(nav.iloc[-1]-1),'cagr':float(nav.iloc[-1]**(1/yrs)-1) if len(nav)>1 and nav.iloc[-1]>0 else np.nan,'sharpe':float(np.sqrt(252)*ret.mean()/ret.std(ddof=1)) if len(ret)>1 and ret.std(ddof=1)>0 else np.nan,'daily_maxdd':float(dd.min()),'worst_day':float(ret.min()) if len(ret) else np.nan,'daily_observations':len(ret)}
def good(row): return bool(row.trading_eligible) and str(row.price_quality)!='UNRESOLVED' and pd.notna(row.research_open) and row.research_open>0 and pd.notna(row.volume) and row.volume>0
def adv20(view,pos):
 x=view.iloc[max(0,pos-20):pos].copy();x=x[(x.trading_eligible.fillna(False))&(x.price_quality.astype(str)!='UNRESOLVED')]
 x=x[pd.to_numeric(x.volume,errors='coerce').gt(0)&pd.to_numeric(x.raw_close,errors='coerce').gt(0)]
 return float((pd.to_numeric(x.raw_close)*pd.to_numeric(x.volume)).median()) if len(x)>=15 else np.nan
def score_for(arch,outer,features,targets,contract,c2):
 sel=pd.read_csv(R/'EXP-MODEL-001_procedure_selections.csv');x=sel[(sel.outer_fold==outer['id'])&(sel.architecture==arch)].iloc[0]
 train=t2.training_rows(targets,x.selected_family,int(x.selected_horizon),outer['test_start'])
 b=m.fit_arch(arch,train,contract); z=features[(features.signal_date>=pd.Timestamp(outer['test_start']))&(features.signal_date<=pd.Timestamp(outer['test_end']))].copy();z['score']=m.predict_bundle(b,z)[0]
 return z,{'target_family':x.selected_family,'horizon_sessions':int(x.selected_horizon),'train_observations':len(train)}
def simulate(scored,calendar,views,fold,contract,k,cost,delay,capital,limit):
 end=pd.Timestamp(fold['test_end']); foldend=int(calendar.searchsorted(end,side='right')-1)
 signals=[]
 for d,g in scored.groupby('signal_date'):
  p=calendar.get_loc(pd.Timestamp(d)); execute=p+1+delay
  if execute+60<=foldend: signals.append((execute,pd.Timestamp(d),g.sort_values(['score','symbol'],ascending=[False,True]).head(k).symbol.tolist()))
 if not signals:return {},pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
 emap={e:(s,n) for e,s,n in signals}; start=signals[0][0]; last=signals[-1][0]+60
 units={}; cash=float(capital); marks={}; nav=[];tr=[];positions=[];unfilled=attempted=filled=delayed=0; order_adv=[]; adv_missing=0
 for pos in range(start,last+1):
  date=calendar[pos]
  if pos in emap:
   signal,names=emap[pos]; openvals={}; equity=cash
   for s,q in units.items():
    op=views[s].iloc[pos].research_open; px=float(op) if pd.notna(op) and op>0 else marks.get(s,np.nan)
    px=0 if not np.isfinite(px) else px;openvals[s]=q*px;equity+=q*px
   # Reserve the maximum possible two-sided transaction cost before setting equal-weight targets.
   target_each=equity*(1.0-2.0*cost/10000.0)/k; turnover=0.; costval=0.; fillnow=0;unfillnow=0
   desired_map={s:(target_each if s in names else 0.) for s in set(units)|set(names)}
   # Sells first; a buy is not permitted to borrow cash when an exit is unfilled.
   order=sorted(desired_map,key=lambda s:(desired_map[s]-openvals.get(s,0.)>0,s))
   for s in order:
    current=openvals.get(s,0.);desired=desired_map[s];delta=desired-current
    if abs(delta)<1e-9:continue
    attempted+=1;row=views[s].iloc[pos];ad=adv20(views[s],pos)
    if np.isfinite(ad): order_adv.append(abs(delta)/ad)
    else: adv_missing+=1
    executable=good(row) and np.isfinite(ad) and abs(delta)<=ad*limit and not (delta>0 and cash < delta*(1.0+cost/10000.0))
    if not executable:
     unfilled+=1;unfillnow+=1;continue
    px=float(row.research_open);units[s]=desired/px if desired>0 else 0.
    if units[s]==0:units.pop(s,None)
    cash-=delta;turnover+=abs(delta)/equity;costval+=abs(delta)*cost/10000.;filled+=1;fillnow+=1
   cash-=costval
   tr.append({'signal_date':signal,'trade_date':date,'k':k,'cost_bps':cost,'delay_sessions':delay,'capital_try':capital,'adv_limit_pct':limit,'attempted_trades':attempted,'filled_now':fillnow,'unfilled_now':unfillnow,'turnover_two_sided_notional':turnover,'cost_try':costval,'cash_after':cash,'selected':len(names)})
  equity=cash; weights={}
  for s,q in units.items():
   row=views[s].iloc[pos];cl=row.research_close
   px=float(cl) if pd.notna(cl) and cl>0 and str(row.price_quality)!='UNRESOLVED' else marks.get(s,np.nan)
   px=0 if not np.isfinite(px) else px;marks[s]=px;equity+=q*px;weights[s]=q*px
  nav.append({'date':date,'nav':equity/capital,'cash_weight':cash/equity if equity>0 else 1.,'holdings':len(units)})
  for s,v in weights.items():positions.append({'date':date,'symbol':s,'weight':v/equity if equity>0 else 0.})
 # explicit terminal liquidation cost on final marked holdings
 terminal=sum(units[s]*marks.get(s,0) for s in units);terminal_cost=terminal*cost/10000.;nav[-1]['nav']-=terminal_cost/capital
 if tr:tr.append({'signal_date':None,'trade_date':calendar[last],'k':k,'cost_bps':cost,'delay_sessions':delay,'capital_try':capital,'adv_limit_pct':limit,'attempted_trades':0,'filled_now':len(units),'unfilled_now':0,'turnover_two_sided_notional':terminal/(nav[-1]['nav']*capital+terminal_cost) if nav[-1]['nav']>0 else np.nan,'cost_try':terminal_cost,'cash_after':np.nan,'selected':0,'terminal_liquidation':True})
 n=pd.DataFrame(nav);out=metrics(n.nav);out.update({'mean_turnover_two_sided':float(pd.DataFrame(tr).turnover_two_sided_notional.mean()) if tr else np.nan,'total_turnover_two_sided':float(pd.DataFrame(tr).turnover_two_sided_notional.sum()) if tr else 0,'attempted_trades':attempted,'filled_trades':filled,'unfilled_trades':unfilled,'fill_rate':filled/attempted if attempted else np.nan,'terminal_liquidation_cost_try':terminal_cost,'mean_cash_weight':float(n.cash_weight.mean()),'mean_holdings':float(n.holdings.mean()),'adv_missing_checks':adv_missing,'order_adv_median':float(np.median(order_adv)) if order_adv else np.nan,'order_adv_p90':float(np.quantile(order_adv,.90)) if order_adv else np.nan,'order_adv_p95':float(np.quantile(order_adv,.95)) if order_adv else np.nan,'order_adv_max':float(np.max(order_adv)) if order_adv else np.nan,'order_adv_gt_10pct':float(np.mean(np.asarray(order_adv)>.10)) if order_adv else np.nan})
 return out,n,pd.DataFrame(tr),pd.DataFrame(positions)
def table(df,cols):
 x=df[cols].copy()
 for c in x:x[c]=x[c].map(lambda v:'N/A' if pd.isna(v) else f'{v:.4f}' if isinstance(v,(float,np.floating)) else str(v))
 return '| '+' | '.join(cols)+' |\n|'+'|'.join('---' for _ in cols)+'|\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in x.itertuples(index=False,name=None))
def main():
 R.mkdir(exist_ok=True);M.mkdir(exist_ok=True);c=json.loads(C.read_text());mc,tc1,tc2,cal,views,features,targets=m.load_all();assert c['frozen_finalists']['LGBM_REGRESSION']['exp_model_contract_sha256']==sha(m.CONTRACT_PATH)
 rows=[];navs=[];trades=[];poss=[]
 for fold in tc1['outer_folds']:
  for arch in ARCHS:
   scored,meta=score_for(arch,fold,features,targets,mc,tc2)
   cases=[]
   cases += [('K_SENSITIVITY',k,cost,0,c['capacity']['base_capital_try'],c['liquidity']['base_max_order_adv_pct']) for k in c['portfolio']['k_sensitivity'] for cost in c['costs']['one_way_bps']]
   cases += [('DELAY',10,50,d,c['capacity']['base_capital_try'],c['liquidity']['base_max_order_adv_pct']) for d in c['execution']['delay_sensitivity_sessions'][1:]]
   cases += [('CAPACITY',10,50,0,cap,lim) for cap in c['capacity']['scenarios_try'] for lim in c['capacity']['thresholds_pct_adv'] if not(cap==c['capacity']['base_capital_try'] and lim==c['liquidity']['base_max_order_adv_pct'])]
   for case,k,cost,delay,cap,lim in cases:
    out,n,t,p=simulate(scored,cal,views,fold,c,k,cost,delay,cap,lim)
    row={'outer_fold':fold['id'],'architecture':arch,'case':case,'k':k,'cost_bps':cost,'delay_sessions':delay,'capital_try':cap,'adv_limit_pct':lim,**meta,**out};rows.append(row)
    if len(n):navs.append(n.assign(outer_fold=fold['id'],architecture=arch,case=case,k=k,cost_bps=cost,delay_sessions=delay,capital_try=cap,adv_limit_pct=lim))
    if len(t):trades.append(t.assign(outer_fold=fold['id'],architecture=arch,case=case))
    if len(p):poss.append(p.assign(outer_fold=fold['id'],architecture=arch,case=case,k=k,cost_bps=cost,delay_sessions=delay,capital_try=cap,adv_limit_pct=lim))
 out=pd.DataFrame(rows);nav=pd.concat(navs,ignore_index=True);trade=pd.concat(trades,ignore_index=True);pos=pd.concat(poss,ignore_index=True)
 base=out[(out.case=='K_SENSITIVITY')&(out.cost_bps==50)&(out.delay_sessions==0)&(out.capital_try==c['capacity']['base_capital_try'])&(out.adv_limit_pct==c['liquidity']['base_max_order_adv_pct'])]
 summary=base.groupby(['architecture','k']).agg(mean_net_return=('net_return','mean'),mean_cagr=('cagr','mean'),mean_sharpe=('sharpe','mean'),worst_daily_maxdd=('daily_maxdd','min'),worst_day=('worst_day','min'),mean_turnover=('mean_turnover_two_sided','mean'),mean_fill_rate=('fill_rate','mean'),mean_cash=('mean_cash_weight','mean'),mean_holdings=('mean_holdings','mean')).reset_index()
 costs=out[(out.case=='K_SENSITIVITY')&(out.k==10)&(out.delay_sessions==0)&(out.capital_try==c['capacity']['base_capital_try'])].groupby(['architecture','cost_bps']).agg(mean_net_return=('net_return','mean'),mean_turnover=('mean_turnover_two_sided','mean')).reset_index()
 delay=out[out.case=='DELAY'].groupby(['architecture','delay_sessions']).agg(mean_net_return=('net_return','mean'),mean_sharpe=('sharpe','mean'),worst_daily_maxdd=('daily_maxdd','min'),mean_fill_rate=('fill_rate','mean')).reset_index()
 capacity=out[out.case.eq('CAPACITY')].groupby(['architecture','capital_try','adv_limit_pct']).agg(mean_net_return=('net_return','mean'),mean_fill_rate=('fill_rate','mean'),unfilled=('unfilled_trades','sum'),mean_cash=('mean_cash_weight','mean'),median_order_adv=('order_adv_median','median'),p95_order_adv=('order_adv_p95','max'),max_order_adv=('order_adv_max','max'),pct_orders_gt_10pct_adv=('order_adv_gt_10pct','mean')).reset_index()
 classes=[]
 for a in ARCHS:
  x=summary[(summary.architecture==a)&(summary.k==10)].iloc[0];cs=costs[costs.architecture==a].sort_values('cost_bps');mono=bool(np.all(np.diff(cs.mean_net_return)<=1e-12));viable=x.mean_net_return>=0 and x.mean_fill_rate>=.95 and x.worst_daily_maxdd>=-.60 and mono
  classes.append({'architecture':a,'classification':'VIABLE' if viable else ('FRAGILE' if x.mean_net_return>=0 else 'REJECTED'),'cost_monotonic':mono,**x.to_dict()})
 classes=pd.DataFrame(classes);gate='PASS' if (classes.classification=='VIABLE').any() else ('PARTIAL' if (classes.classification=='FRAGILE').any() else 'FAIL')
 for name,df in [('outer_metrics',out),('k_summary',summary),('cost_summary',costs),('delay_summary',delay),('capacity_summary',capacity),('classification',classes)]:df.to_csv(R/f'EXP-PORT-001_{name}.csv',index=False)
 nav.to_csv(R/'EXP-PORT-001_daily_nav.csv',index=False);trade.to_csv(R/'EXP-PORT-001_trades.csv',index=False);pos.to_csv(R/'EXP-PORT-001_positions.csv',index=False)
 sections=[('1. Executive Summary',f'Phase H gate: **{gate}**.'),('2. MASTER_PLAN Phase Mapping','Phase G is substantively satisfied by EXP-MODEL-001 locked outer evidence; no duplicate outer evaluation was created.'),('3. Locked Portfolio Contract',f'`{C.name}` frozen before results.'),('4. Frozen Alpha Finalists','LGBM Regression and LambdaMART only; same EXP-MODEL-001 features, target/horizon selections, seeds and fixed hyperparameters.'),('5. Execution Contract',c['execution']['price']+'. '+c['execution']['invalid_fill']+'.'),('6. Turnover Accounting',c['turnover']['definition']),('7. Transaction Costs','One-way cost on every traded nominal including terminal liquidation: 0/30/50/100 bps.'),('8. K Sensitivity',table(summary,list(summary.columns))),('9. LGBM Regression Results',table(summary[summary.architecture.eq('LGBM_REGRESSION')],list(summary.columns))),('10. LambdaMART Results',table(summary[summary.architecture.eq('LAMBDAMART')],list(summary.columns))),('11. Daily Risk',table(summary,['architecture','k','worst_daily_maxdd','worst_day'])),('12. Liquidity','ADV20 uses only resolved positive-volume history. '+table(capacity,list(capacity.columns))),('13. Capacity Scenarios',table(capacity,list(capacity.columns))),('14. Fill / Delay Stress',table(delay,list(delay.columns))),('15. Concentration','Equal-weight target maximum single-name weight is 1/K; holdings and cash exposure are reported in K sensitivity. Sector/stock PnL concentration is descriptive-only under the current survivor universe caveat.'),('16. Cost Survival',table(costs,list(costs.columns))),('17. Architecture Comparison',table(classes,list(classes.columns))),('18. Limitations','Current universe is survivorship-limited; price/volume and corporate-action evidence remains provider-dependent. Fundamental, macro and USDTRY are excluded.'),('19. Tests','Dedicated portfolio contract, frozen-model, turnover, cost, terminal, fill, liquidity, NAV, K-isolation, capacity and delay tests.'),('20. Production Integrity','Final protected-production hash verification required; research-only outputs.'),('21. Phase H Gate',f'**{gate}**\n\n'+table(classes,list(classes.columns))),('22. MASTER_PLAN\'e göre SINGLE NEXT BEST ACTION','Stop after this package. Review the Phase H gate before any Phase I stress/ablation work; do not initiate it automatically.')]
 (R/'EXP-PORT-001_report.md').write_text('# EXP-PORT-001 — PORTFOLIO, COST & CAPACITY CONTROL\n\n'+'\n\n'.join(f'## {h}\n\n{b}' for h,b in sections),encoding='utf-8')
 summaryj={'experiment_id':'EXP-PORT-001','phase_g_mapping':c['phase_mapping']['phase_g'],'execution':'PASS','phase_h_gate':gate,'classifications':classes.to_dict('records'),'generated_at_utc':datetime.now(timezone.utc).isoformat()};(R/'EXP-PORT-001_summary.json').write_text(json.dumps(summaryj,indent=2),encoding='utf-8')
 files=sorted(R.glob('EXP-PORT-001_*'));(M/'EXP-PORT-001_manifest.json').write_text(json.dumps({'contract_sha256':sha(C),'model_contract_sha256':sha(m.CONTRACT_PATH),'code_sha256':sha(Path(__file__)),'files':{p.name:sha(p) for p in files}},indent=2),encoding='utf-8');print(json.dumps(summaryj,indent=2))
if __name__=='__main__':main()
