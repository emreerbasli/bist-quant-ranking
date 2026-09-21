"""Persistent event-sourced research shadow lifecycle; activation is enforced by the runner."""
from __future__ import annotations
import json,os,uuid
from pathlib import Path
import numpy as np,pandas as pd
import forward_infrastructure_001 as fw

class Lifecycle:
 def __init__(self,root,candidate,version,manifest,contract):
  self.root=Path(root);self.candidate=candidate;self.version=version;self.manifest=manifest;self.contract=contract
  self.events=self.root/'events'/f'{candidate}.jsonl';self.state_path=self.root/'state'/f'{candidate}.json';self.cohorts=self.root/'cohorts'/f'{candidate}.jsonl';self.nav=self.root/'nav'/f'{candidate}.jsonl'
 def state(self):
  if self.state_path.exists():return json.loads(self.state_path.read_text())
  return {'candidate_id':self.candidate,'candidate_version':self.version,'cash':float(self.contract['portfolio']['capital_try']),'units':{},'marks':{},'pending_orders':[],'last_rebalance_date':None,'last_processed_market_session':None,'current_nav':float(self.contract['portfolio']['capital_try']),'processed_sessions':{},'active_cohorts':{}}
 def save(self,state):
  if state['candidate_id']!=self.candidate or state['candidate_version']!=self.version:raise fw.ForwardIntegrityError('STATE_CANDIDATE_MISMATCH')
  body={k:v for k,v in state.items() if k!='checkpoint_hash'};state['checkpoint_hash']=fw.canonical_hash(body);self.state_path.parent.mkdir(parents=True,exist_ok=True);tmp=self.state_path.with_suffix('.tmp');tmp.write_text(json.dumps(state,sort_keys=True),encoding='utf-8');os.replace(tmp,self.state_path)
 def emit(self,path,run_id,kind,payload):
  sequence=payload.get('event_key',kind);row={'event_id':fw.event_id(run_id,kind,sequence),'run_id':run_id,'event_type':kind,'candidate_id':self.candidate,'candidate_version':self.version,**payload}
  if any(x.get('event_id')==row['event_id'] for x in fw.read_rows(path)):return row
  fw.append_row(path,row);return row
 def create_signal(self,run_id,signal_date,calendar,selected,snapshot):
  s=self.state();key=fw.clean_signal_key(self.candidate,self.version,signal_date)
  if any(x.get('clean_signal_key')==key for x in fw.read_rows(self.events)):return 'ALREADY_EXISTS_NO_OP'
  pos=pd.DatetimeIndex(calendar).get_loc(pd.Timestamp(signal_date));due=pd.Timestamp(calendar[pos+1]);orders=[]
  for r in selected:
   oid=str(uuid.uuid5(uuid.NAMESPACE_URL,f'{key}:{r["ticker"]}:BUY'));orders.append({'order_id':oid,'signal_date':str(pd.Timestamp(signal_date).date()),'created_at':fw.now_ist().isoformat(),'side':'BUY_TARGET','ticker':r['ticker'],'target_weight':.1,'current_weight':0.,'intended_notional':None,'execution_session':str(due.date()),'status':'PENDING_EXECUTION','reason':'NEXT_APPLICABLE_ELIGIBLE_SESSION'})
  s['pending_orders']=orders;s['last_rebalance_date']=str(pd.Timestamp(signal_date).date())
  cohort=fw.new_cohort(run_id,self.manifest,signal_date,calendar,len(s['active_cohorts']));cohort.update({'created_at':fw.now_ist().isoformat(),'signal_event_id':fw.event_id(run_id,'SIGNAL',key),'data_snapshot_hash':snapshot['input_snapshot_hash'],'members':selected})
  s['active_cohorts'][cohort['cohort_id']]=cohort;self.emit(self.events,run_id,'SIGNAL',{'event_key':key,'clean_signal_key':key,'signal_date':str(pd.Timestamp(signal_date).date()),'data_snapshot_hash':snapshot['input_snapshot_hash']})
  for o in orders:self.emit(self.events,run_id,'ORDER_INTENDED',{'event_key':o['order_id'],**o})
  self.emit(self.cohorts,run_id,'COHORT_CREATED',{'event_key':cohort['cohort_id'],**cohort});self.save(s);return cohort
 def process_session(self,run_id,session,calendar,views,benchmark):
  d=pd.Timestamp(session);s=self.state();key=str(d.date())
  if key in s['processed_sessions']:return 'ALREADY_EXISTS_NO_OP'
  pos=pd.DatetimeIndex(calendar).get_loc(d);due=[o for o in s['pending_orders'] if pd.Timestamp(o['execution_session'])<=d]
  cost=0.
  if due:
   selected=[o['ticker'] for o in due];events,cost=fw.execute_rebalance(s,views,pos,selected,self.contract['portfolio']['one_way_cost_bps'],self.contract['portfolio']['max_order_adv_pct'])
   for e in events:self.emit(self.events,run_id,'ORDER_EXECUTION',{'event_key':f'{key}:{e["symbol"]}','execution_session':key,'net_cash_delta':-e['gross_traded_nominal']-(e['gross_traded_nominal']*self.contract['portfolio']['one_way_cost_bps']/10000 if e['fill_status']=='FILLED' else 0.),**e})
   s['pending_orders']=[]
  mark=fw.mark_to_market(s,views,pos);nav={'event_key':key,'nav_date':key,'positions_market_value':mark['positions_value'],'cash':mark['cash'],'gross_nav':mark['nav'],'transaction_cost':cost,'net_nav':mark['nav'],'number_positions':len(s['units']),'pending_orders':len(s['pending_orders']),'mark_status':'LAST_VALID_MARK_ALLOWED'};self.emit(self.nav,run_id,'DAILY_NAV',nav)
  for cid,c in list(s['active_cohorts'].items()):
   if fw.cohort_status(c,calendar,d)=='PENDING':self.emit(self.cohorts,run_id,'COHORT_STILL_PENDING',{'event_key':f'{cid}:{key}','cohort_id':cid,'status':'PENDING','asof':key});continue
   outcomes=[]
   for m in c['members']:
    try:v=fw.target_realization(c['configured_target'],views[m['ticker']],benchmark,c['signal_date'],c['expected_label_end_date']);ok=np.isfinite(v)
    except Exception:v=np.nan;ok=False
    outcomes.append({'ticker':m['ticker'],'score':m['raw_score'],'target_realization':v,'eligible':bool(ok),'reason':None if ok else 'LABEL_UNAVAILABLE'})
   good=[x for x in outcomes if x['eligible']];ic=float(pd.Series([x['score'] for x in good]).rank().corr(pd.Series([x['target_realization'] for x in good]).rank())) if len(good)>=2 else np.nan
   self.emit(self.cohorts,run_id,'COHORT_COMPLETED',{'event_key':cid,'cohort_id':cid,'status':'COMPLETED','actual_label_end_date':key,'outcomes':outcomes,'rank_ic_contribution':ic,'overlapping_active_cohorts':c['overlapping_active_cohorts']});s['active_cohorts'].pop(cid)
  s['last_processed_market_session']=key;s['current_nav']=mark['nav'];s['processed_sessions'][key]=fw.canonical_hash(nav);self.save(s);return 'PROCESSED'
