"""Crash-safe, candidate/session transactional lifecycle for R3."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd
import forward_infrastructure_001r3 as fw
from exp_port_001 import adv20

class Lifecycle:
 def __init__(self,root,candidate,version,manifest,contract):
  self.root=Path(root);self.candidate=candidate;self.version=version;self.manifest=manifest;self.contract=contract
  self.events=self.root/'events'/f'{candidate}.jsonl';self.nav=self.root/'nav'/f'{candidate}.jsonl';self.cohorts=self.root/'cohorts'/f'{candidate}.jsonl';self.ops=self.root/'operational'/f'{candidate}.jsonl';self.state_path=self.root/'state'/f'{candidate}.json';self.txdir=self.root/'transactions'/candidate
  self.failure_stage=None
  self.test_fault_stage=None
 def state(self):
  if self.state_path.exists():return json.loads(self.state_path.read_text())
  return {'candidate_id':self.candidate,'candidate_version':self.version,'cash':float(self.contract['portfolio']['capital_try']),'units':{},'marks':{},'pending_orders':[],'active_cohorts':{},'processed_sessions':{},'last_signal_session':None,'next_signal_session':None,'rebalance_cycle_id':None,'eligible_session_count':0}
 def save(self,s):fw.atomic_json(self.state_path,s)
 def tx_path(self,session):return self.txdir/f'{session}.json'
 def _append(self,path,rows):
  for row in rows:fw.append_event(path,row)
 def commit(self,session,run_id,state_after,streams):
  """PREPARED journal is deterministic; replay is safe because all writes use semantic keys."""
  p=self.tx_path(session);p.parent.mkdir(parents=True,exist_ok=True)
  with fw.file_lock(p):
   tx=json.loads(p.read_text()) if p.exists() else None
   if tx and tx.get('status')=='COMMITTED':return 'ALREADY_EXISTS_NO_OP'
   if not tx:
    tx={'status':'PREPARED','candidate_id':self.candidate,'candidate_version':self.version,'session':str(session),'run_id':run_id,'state_after':state_after,'streams':streams};fw.atomic_json(p,tx)
   for name,rows in tx['streams'].items():self._append(getattr(self,name),rows)
   self.save(tx['state_after']);tx['status']='COMMITTED';fw.atomic_json(p,tx);return 'COMMITTED'
 def operation(self,run_id,session,kind,stage,error):
  row=fw.event(kind,f'{self.candidate}|{self.version}|{session}|{kind}',run_id,candidate_id=self.candidate,candidate_version=self.version,market_session=str(session),generated_at=fw.now_ist().isoformat(),stage=stage,error_class=type(error).__name__,message=str(error));fw.append_event(self.ops,row)
 def signal_due(self,s,actual):
  return s['last_signal_session'] is None or s.get('next_signal_session')==str(pd.Timestamp(actual).date())
 def create_signal(self,run_id,signal,calendar,scored,snapshot):
  key=f'{self.candidate}|{self.version}|{pd.Timestamp(signal).date()}';s=self.state()
  if any(x.get('semantic_key')==f'SIGNAL|{key}' for x in fw.read_rows(self.events)):return 'ALREADY_EXISTS_NO_OP'
  pos=pd.DatetimeIndex(calendar).get_loc(pd.Timestamp(signal));due=pd.Timestamp(calendar[pos+1]) if pos+1<len(calendar) else None;cycle=fw.semantic_id('REBALANCE',key);selected=[x for x in scored if x['selected_top10']]
  signal_event=fw.event('SIGNAL',key,run_id,candidate_id=self.candidate,candidate_version=self.version,signal_date=str(pd.Timestamp(signal).date()),snapshot_hash=snapshot['input_snapshot_hash'],source_max_session=snapshot['source_max_session'],cross_section=scored)
  orders=[]
  for x in selected:
   oid=fw.semantic_id('ORDER',f'{key}|{x["ticker"]}|BUY_TARGET|{cycle}')
   orders.append({'order_id':oid,'signal_event_id':signal_event['event_id'],'rebalance_id':cycle,'signal_date':str(pd.Timestamp(signal).date()),'ticker':x['ticker'],'side':'BUY_TARGET','target_weight':.1,'execution_session':str(due.date()) if due is not None else None,'status':'PENDING_EXECUTION' if due is not None else 'PENDING_SESSION','reason':'NEXT_APPLICABLE_ELIGIBLE_SESSION'})
  h=self.manifest['horizon_procedure'];end=fw.expected_label_end(calendar,signal,h) if pos+1+h<len(calendar) else None;coid=fw.semantic_id('COHORT',key)
  cohort={'cohort_id':coid,'signal_event_id':signal_event['event_id'],'signal_date':str(pd.Timestamp(signal).date()),'configured_target':self.manifest['target_procedure'],'configured_horizon':h,'expected_label_end_session':str(pd.Timestamp(end).date()) if end is not None else None,'eligible_sessions_elapsed':0,'last_counted_session':None,'status':'PENDING','members':scored,'snapshot_hash':snapshot['input_snapshot_hash'],'overlapping_active_cohorts':len(s['active_cohorts'])}
  s['pending_orders']=orders;s['active_cohorts'][coid]=cohort;s['last_signal_session']=str(pd.Timestamp(signal).date());s['next_signal_session']=None;s['rebalance_cycle_id']=cycle;s['eligible_session_count']=0
  streams={'events':[signal_event]+[fw.event('ORDER_INTENDED',o['order_id'],run_id,candidate_id=self.candidate,candidate_version=self.version,**o) for o in orders],'cohorts':[fw.event('COHORT_CREATED',coid,run_id,candidate_id=self.candidate,candidate_version=self.version,**cohort)],'nav':[],'ops':[]}
  return self.commit(f'signal-{pd.Timestamp(signal).date()}',run_id,s,streams)
 def _mark(self,s,views,pos):
  pv=0.;marks=[]
  for ticker,q in s['units'].items():
   r=views[ticker].iloc[pos];usable=pd.notna(r.research_close) and r.research_close>0 and str(r.price_quality)!='UNRESOLVED'
   px=float(r.research_close) if usable else s['marks'].get(ticker,{}).get('price',np.nan)
   if not np.isfinite(px):raise fw.ForwardIntegrityError('NO_LAST_VALID_MARK')
   source=str(views[ticker].index[pos].date()) if usable else s['marks'][ticker]['source_session'];status='CURRENT_ELIGIBLE_MARK' if usable else 'LAST_VALID_MARK'
   s['marks'][ticker]={'price':px,'source_session':source,'status':status,'price_quality':str(r.price_quality)};pv+=q*px;marks.append({'ticker':ticker,**s['marks'][ticker]})
  return pv,marks
 def process_session(self,run_id,session,calendar,views,benchmark):
  key=str(pd.Timestamp(session).date());s=self.state()
  p=self.tx_path(key)
  if p.exists() and json.loads(p.read_text()).get('status')=='COMMITTED':return 'ALREADY_EXISTS_NO_OP'
  pos=pd.DatetimeIndex(calendar).get_loc(pd.Timestamp(session));execution=[];cost=0.
  for o in s['pending_orders']:
   if o.get('execution_session') is None and pd.Timestamp(session)>pd.Timestamp(o['signal_date']):o['execution_session']=key;o['status']='PENDING_EXECUTION'
  due=[o for o in s['pending_orders'] if o.get('execution_session') and pd.Timestamp(o['execution_session'])<=pd.Timestamp(session)]
  if due:
   self.failure_stage='EXECUTION'
   # Full target rebalance: existing nonselected positions are exit candidates.
   selected=[o['ticker'] for o in due];equity=s['cash']+sum(q*(float(views[t].iloc[pos].research_open) if pd.notna(views[t].iloc[pos].research_open) else s['marks'].get(t,{}).get('price',0)) for t,q in s['units'].items());target=equity*(1-2*self.contract['portfolio']['one_way_cost_bps']/10000)/10
   if self.test_fault_stage=='EXECUTION':raise RuntimeError('TEST_FAULT_EXECUTION')
   desired={t:(target if t in selected else 0.) for t in set(s['units'])|set(selected)}
   order_by={o['ticker']:o for o in due}
   for t in sorted(desired,key=lambda z:(desired[z]-(s['units'].get(z,0)*float(views[z].iloc[pos].research_open if pd.notna(views[z].iloc[pos].research_open) else s['marks'].get(z,{}).get('price',0)))>0,z)):
    r=views[t].iloc[pos];openpx=float(r.research_open) if pd.notna(r.research_open) and r.research_open>0 else np.nan;current=s['units'].get(t,0)*openpx if np.isfinite(openpx) else 0.;delta=desired[t]-current;adv=adv20(views[t],pos);allowed=adv*self.contract['portfolio']['max_order_adv_pct'] if np.isfinite(adv) else np.nan;liq=bool(r.trading_eligible) and str(r.price_quality)!='UNRESOLVED' and np.isfinite(openpx) and pd.notna(r.volume) and r.volume>0 and np.isfinite(allowed) and abs(delta)<=allowed;cashok=not(delta>0 and s['cash']<delta*(1+self.contract['portfolio']['one_way_cost_bps']/10000));status='FILLED' if liq and cashok else 'BLOCKED';reason=None if status=='FILLED' else ('LIQUIDITY' if not liq else 'CASH')
    oid=order_by.get(t,{}).get('order_id',fw.semantic_id('ORDER',f'{s.get("rebalance_cycle_id")}|{t}|EXIT'))
    trade=abs(delta) if status=='FILLED' else 0.;fee=trade*self.contract['portfolio']['one_way_cost_bps']/10000 if status=='FILLED' else 0.
    if status=='FILLED':s['cash']-=delta+fee;s['units'][t]=desired[t]/openpx if desired[t]>0 else 0.;s['units']={a:b for a,b in s['units'].items() if b};cost+=fee
    cash_delta=(-(trade+fee) if delta>0 else (trade-fee)) if status=='FILLED' else 0.
    execution.append(fw.event('ORDER_EXECUTION',f'{oid}|{key}|0',run_id,candidate_id=self.candidate,candidate_version=self.version,order_id=oid,signal_event_id=order_by.get(t,{}).get('signal_event_id'),rebalance_id=s.get('rebalance_cycle_id'),execution_session=key,ticker=t,side='BUY' if delta>0 else 'SELL',order_notional=abs(delta),gross_traded_nominal=trade,net_cash_delta=cash_delta,cost_amount=fee,cost_rate_bps=self.contract['portfolio']['one_way_cost_bps'],adv_value=adv,adv_window_sessions=20,adv_reference_session=str(pd.Timestamp(calendar[pos-1]).date()) if pos else None,participation_limit=self.contract['portfolio']['max_order_adv_pct'],allowed_notional=allowed,order_adv_ratio=abs(delta)/adv if np.isfinite(adv) and adv else np.nan,fill_fraction=1. if status=='FILLED' else 0.,fill_status=status,block_reason=reason))
   s['pending_orders']=[]
  if s['cash']<-1e-7:raise fw.ForwardIntegrityError('NEGATIVE_CASH')
  self.failure_stage='NAV';
  if self.test_fault_stage=='NAV':raise RuntimeError('TEST_FAULT_NAV')
  pv,marks=self._mark(s,views,pos);gross=pv+s['cash']+cost;net=pv+s['cash'];nav=fw.event('DAILY_NAV',f'{self.candidate}|{self.version}|{key}',run_id,candidate_id=self.candidate,candidate_version=self.version,nav_date=key,positions_market_value=pv,cash=s['cash'],gross_nav=gross,transaction_cost=cost,net_nav=net,accounting_identity=round(gross-cost-net,10),number_positions=len(s['units']),pending_orders=len(s['pending_orders']),mark_provenance=marks)
  cohort_events=[]
  for cid,c in list(s['active_cohorts'].items()):
   self.failure_stage='COHORT'
   if self.test_fault_stage=='COHORT':raise RuntimeError('TEST_FAULT_COHORT')
   if c.get('expected_label_end_session') is not None:
    if pd.Timestamp(session)<pd.Timestamp(c['expected_label_end_session']):continue
    c['eligible_sessions_elapsed']=int(c['configured_horizon'])
   elif pd.Timestamp(session)>pd.Timestamp(c['signal_date']) and c.get('last_counted_session')!=key:
    c['eligible_sessions_elapsed']=int(c.get('eligible_sessions_elapsed',0))+1;c['last_counted_session']=key
   if c['eligible_sessions_elapsed']<int(c['configured_horizon']):continue
   if c.get('expected_label_end_session') is None:c['expected_label_end_session']=key
   outcomes=[]
   for m in c['members']:
    val,reason,raw=fw.label_outcome(c['configured_target'],views[m['ticker']],benchmark,calendar,c['signal_date'],c['expected_label_end_session']);outcomes.append({**m,'target_realization':val,'raw_forward_return':raw,'eligibility_reason':reason,'eligible':reason=='ELIGIBLE'})
   good=[x for x in outcomes if x['eligible']];scores=np.array([x['raw_score'] for x in good]);vals=np.array([x['target_realization'] for x in good]);rankic=float(pd.Series(scores).rank().corr(pd.Series(vals).rank())) if len(good)>1 else np.nan
   from exp_tgt_001 import ndcg_at_k
   ranks=pd.Series(vals).rank(pct=True).to_numpy() if len(good) else np.array([]);ndcg=ndcg_at_k(ranks,scores,10);ordered=sorted(good,key=lambda x:(-x['raw_score'],x['ticker']));bottom=sorted(good,key=lambda x:(x['raw_score'],x['ticker']));spread=float(np.mean([x['raw_forward_return'] for x in ordered[:10]])-np.mean([x['raw_forward_return'] for x in bottom[:10]])) if len(good)>=10 else np.nan
   cohort_events.append(fw.event('COHORT_COMPLETED',f'{self.candidate}|{self.version}|{cid}',run_id,candidate_id=self.candidate,candidate_version=self.version,cohort_id=cid,status='COMPLETED',expected_label_end_session=c['expected_label_end_session'],actual_label_end_session=c['expected_label_end_session'],evaluation_processed_at=fw.now_ist().isoformat(),total_scored=len(outcomes),eligible_completed=len(good),ineligible=len(outcomes)-len(good),reason_distribution={r:sum(x['eligibility_reason']==r for x in outcomes) for r in sorted({x['eligibility_reason'] for x in outcomes})},outcomes=outcomes,rank_ic=rankic,ndcg_at_10=ndcg,top_k_spread_raw=spread,overlapping_active_cohorts=c['overlapping_active_cohorts']));s['active_cohorts'].pop(cid)
  if s['last_signal_session'] and key!=s['last_signal_session']:
   s['eligible_session_count']+=1
   if s['eligible_session_count']>=self.contract['portfolio']['rebalance_sessions']:s['next_signal_session']=key
  s['processed_sessions'][key]=fw.canonical_hash({'nav':nav['net_nav'],'cost':cost});streams={'events':execution,'nav':[nav],'cohorts':cohort_events,'ops':[]}
  self.failure_stage='COMMIT';return self.commit(key,run_id,s,streams)
