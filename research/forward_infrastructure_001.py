"""Fail-closed, research-only clean-forward evidence primitives for EXP-FREEZE-001R."""
from __future__ import annotations
import hashlib, json, os, time, uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

RESEARCH=Path(__file__).resolve().parent; ROOT=RESEARCH.parent
FROZEN=RESEARCH/'frozen_candidates'; FORWARD=RESEARCH/'forward_infrastructure'; DEBUG=RESEARCH/'forward_debug_backfill'
CONTRACT=RESEARCH/'contracts'/'exp_freeze_001r.json'; IST=ZoneInfo('Europe/Istanbul')
_HELD_LOCKS=set()

class ForwardIntegrityError(RuntimeError): pass
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def canonical_hash(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def now_ist(): return datetime.now(IST)
def event_id(run_id, kind, sequence): return str(uuid.uuid5(uuid.NAMESPACE_URL,f'EXP-FREEZE-001R:{run_id}:{kind}:{sequence}'))
def read_rows(path):
 if not Path(path).exists() or Path(path).stat().st_size==0:return []
 return [json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]
@contextmanager
def file_lock(path):
 """Windows non-blocking lock; failure is evidence-safe and fails closed."""
 import msvcrt
 lock=Path(str(path)+'.lock'); lock.parent.mkdir(parents=True,exist_ok=True); key=str(lock.resolve())
 if key in _HELD_LOCKS: raise ForwardIntegrityError(f'LOCK_UNAVAILABLE:{path}')
 fd=os.open(lock,os.O_CREAT|os.O_RDWR)
 try:
  _HELD_LOCKS.add(key)
  os.write(fd,b'0') if os.path.getsize(lock)==0 else None
  try: msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
  except OSError as exc: raise ForwardIntegrityError(f'LOCK_UNAVAILABLE:{path}') from exc
  yield
 finally:
  try: msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
  except OSError: pass
  os.close(fd)
  _HELD_LOCKS.discard(key)
def append_row(path,row):
 if not row.get('event_id') or not row.get('run_id'): raise ForwardIntegrityError('EVENT_AND_RUN_ID_REQUIRED')
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with file_lock(path):
  with path.open('a',encoding='utf-8',newline='\n') as f:
   f.write(json.dumps(row,ensure_ascii=False,sort_keys=True,default=str)+'\n');f.flush();os.fsync(f.fileno())
def append_correction(path,run_id,candidate_id,candidate_version,original_event_id,reason,corrected_fields,at=None):
 at=at or now_ist(); row={'event_id':event_id(run_id,'CORRECTION',original_event_id),'run_id':run_id,'event_type':'CORRECTION','candidate_id':candidate_id,'candidate_version':candidate_version,'original_event_id':original_event_id,'reason':reason,'corrected_at':at.isoformat(),'corrected_fields':corrected_fields};append_row(path,row);return row
def frozen_candidate(candidate_id):
 p=FROZEN/candidate_id; manifest=json.loads((p/'candidate_manifest.json').read_text()); model=p/'model.joblib'
 if sha(model)!=manifest['model_sha256']: raise ForwardIntegrityError('FROZEN_ARTIFACT_MISMATCH')
 import joblib
 art=joblib.load(model)
 if art['candidate_id']!=manifest['candidate_id'] or art['version']!=manifest['candidate_version'] or art['target_family']!=manifest['target_procedure'] or art['horizon_sessions']!=manifest['horizon_procedure'] or art['features']!=[x['name'] for x in manifest['features']]: raise ForwardIntegrityError('FROZEN_ARTIFACT_MANIFEST_MISMATCH')
 return manifest,art
def snapshot_manifest(input_files, source_max_timestamp, provider_snapshot_id='LOCAL_RESEARCH_PRICE_VIEW'):
 def display(p):
  p=Path(p).resolve()
  try:return str(p.relative_to(ROOT))
  except ValueError:return str(p)
 rows=[{'path':display(p),'sha256':sha(p)} for p in sorted(map(Path,input_files))]
 out={'provider_snapshot_id':provider_snapshot_id,'price_inputs':rows,'source_max_timestamp':pd.Timestamp(source_max_timestamp).isoformat(),'input_snapshot_hash':canonical_hash(rows)}
 return out
def actual_signal_date(calendar, views):
 cal=pd.DatetimeIndex(calendar).sort_values().unique()
 for d in cal[::-1]:
  if any(bool(v.loc[d,'trading_eligible']) if d in v.index and pd.notna(v.loc[d,'trading_eligible']) else False for v in views.values()): return pd.Timestamp(d)
 raise ForwardIntegrityError('NO_ELIGIBLE_MARKET_SESSION')
def classify_signal(candidate, requested_asof, actual_date, generated_at, model_freeze, clean_start, contract):
 requested=pd.Timestamp(requested_asof).normalize(); actual=pd.Timestamp(actual_date).normalize(); generated=pd.Timestamp(generated_at)
 freeze=pd.Timestamp(model_freeze).tz_localize(None).normalize(); start=pd.Timestamp(clean_start).tz_localize(None).normalize()
 if actual<=freeze or actual<start:return 'NON_CLEAN_BACKFILL'
 if contract['timeliness']['require_actual_signal_date_equals_requested_asof'] and requested!=actual:return 'NON_CLEAN_BACKFILL'
 local=generated.tz_convert(IST) if generated.tzinfo else generated.tz_localize(IST)
 close=pd.Timestamp(f'{actual.date()} {contract["timeliness"]["market_close_local"]}').tz_localize(IST)
 if local<close or local>close+timedelta(hours=contract['timeliness']['permitted_operational_window_hours']):return 'MISSED_FORWARD_SIGNAL'
 return 'CLEAN_FORWARD'
def clean_signal_key(candidate_id,version,signal_date): return f'{candidate_id}|{version}|{pd.Timestamp(signal_date).date()}'
def existing_clean_signal(path,key): return any(r.get('clean_signal_key')==key and r.get('classification')=='CLEAN_FORWARD' for r in read_rows(path))
def expected_label_end(calendar, signal_date, horizon):
 from temporal_validation import build_label_interval
 return build_label_interval(pd.DatetimeIndex(calendar),pd.Timestamp(signal_date),int(horizon)).label_end
def new_cohort(run_id,manifest,signal_date,calendar,overlap_count):
 h=int(manifest['horizon_procedure']); cid=manifest['candidate_id'];version=manifest['candidate_version']; end=expected_label_end(calendar,signal_date,h)
 return {'event_id':event_id(run_id,'COHORT',str(signal_date)),'run_id':run_id,'event_type':'COHORT_CREATED','candidate_id':cid,'candidate_version':version,'cohort_id':str(uuid.uuid5(uuid.NAMESPACE_URL,clean_signal_key(cid,version,signal_date))),'signal_date':str(pd.Timestamp(signal_date).date()),'configured_target':manifest['target_procedure'],'configured_horizon':h,'expected_label_end_date':str(pd.Timestamp(end).date()),'status':'PENDING','overlapping_active_cohorts':int(overlap_count)}
def cohort_status(cohort, calendar, asof): return 'COMPLETED' if pd.Timestamp(asof)>=pd.Timestamp(cohort['expected_label_end_date']) else 'PENDING'
def target_realization(family, stock_view, benchmark, signal_date, label_end):
 start=pd.DatetimeIndex(benchmark.index).get_loc(pd.Timestamp(signal_date))+1; end=pd.DatetimeIndex(benchmark.index).get_loc(pd.Timestamp(label_end)); raw=float(stock_view.iloc[end].research_close/stock_view.iloc[start].research_close-1)
 if family=='RAW':return raw
 if family!='BETA_RESIDUAL':raise ForwardIntegrityError('UNSUPPORTED_FROZEN_TARGET')
 from exp_tgt_002 import estimate_beta
 beta,_=estimate_beta(stock_view,benchmark,pd.DatetimeIndex(benchmark.index).get_loc(pd.Timestamp(signal_date)))
 if not np.isfinite(beta): return np.nan
 bench=float(benchmark.iloc[end].research_close/benchmark.iloc[start].research_close-1);return raw-float(beta)*bench
def portfolio_state(capital): return {'cash':float(capital),'units':{},'marks':{},'positions':{}}
def adv20(view,pos):
 x=view.iloc[max(0,pos-20):pos];x=x[(x.trading_eligible.fillna(False))&(x.price_quality.astype(str)!='UNRESOLVED')];x=x[pd.to_numeric(x.volume,errors='coerce').gt(0)&pd.to_numeric(x.raw_close,errors='coerce').gt(0)]
 return float((pd.to_numeric(x.raw_close)*pd.to_numeric(x.volume)).median()) if len(x)>=15 else np.nan
def eligible_fill(row,adv,order,limit): return bool(row.trading_eligible) and str(row.price_quality)!='UNRESOLVED' and pd.notna(row.research_open) and row.research_open>0 and pd.notna(row.volume) and row.volume>0 and np.isfinite(adv) and abs(order)<=adv*limit
def execute_rebalance(state, views, pos, selected, cost_bps, limit):
 """Same sells-first, cost-reserve, no-borrow policy as EXP-PORT-001."""
 equity=state['cash'];openvals={}
 for s,q in state['units'].items():
  op=views[s].iloc[pos].research_open;px=float(op) if pd.notna(op) and op>0 else state['marks'].get(s,np.nan);px=0. if not np.isfinite(px) else px;openvals[s]=q*px;equity+=q*px
 target=equity*(1-2*cost_bps/10000)/10;desired={s:(target if s in selected else 0.) for s in set(state['units'])|set(selected)};events=[];cost=0.
 for s in sorted(desired,key=lambda z:(desired[z]-openvals.get(z,0)>0,z)):
  delta=desired[s]-openvals.get(s,0.);row=views[s].iloc[pos];ad=adv20(views[s],pos);ok=eligible_fill(row,ad,delta,limit) and not(delta>0 and state['cash']<delta*(1+cost_bps/10000))
  ev={'symbol':s,'gross_traded_nominal':abs(delta),'adv20':ad,'order_adv_ratio':abs(delta)/ad if np.isfinite(ad) and ad else np.nan,'fill_status':'FILLED' if ok else 'UNFILLED','fill_fraction':1. if ok else 0.,'block_reason':None if ok else 'LIQUIDITY_OR_CASH'}
  if ok:
   state['units'][s]=desired[s]/float(row.research_open) if desired[s]>0 else 0.;state['cash']-=delta;cost+=abs(delta)*cost_bps/10000
   if state['units'][s]==0:state['units'].pop(s,None)
  events.append(ev)
 state['cash']-=cost
 if state['cash']<-1e-7:raise ForwardIntegrityError('NEGATIVE_CASH')
 return events,cost
def mark_to_market(state,views,pos):
 value=state['cash']
 for s,q in state['units'].items():
  row=views[s].iloc[pos];px=float(row.research_close) if pd.notna(row.research_close) and row.research_close>0 and str(row.price_quality)!='UNRESOLVED' else state['marks'].get(s,np.nan)
  if not np.isfinite(px):raise ForwardIntegrityError('NO_LAST_VALID_MARK')
  state['marks'][s]=px;value+=q*px
 return {'positions_value':value-state['cash'],'cash':state['cash'],'nav':value}
