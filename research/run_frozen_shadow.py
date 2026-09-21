"""R3 official-like runner. Every mode crosses the same activation and integrity gate."""
from __future__ import annotations
import argparse,json,sys,uuid
from pathlib import Path
import numpy as np,pandas as pd
RESEARCH=Path(__file__).resolve().parent;ROOT=RESEARCH.parent;sys.path[:0]=[str(ROOT),str(RESEARCH)]
import exp_tgt_001 as t1
import forward_infrastructure_001r3 as fw
from forward_lifecycle_001r3 import Lifecycle
from runner_data_sources import CanonicalRunnerDataSources,SandboxRunnerDataSources

def inputs(symbols):
 out=[]
 for s in ['XU100.IS',*symbols]:
  o=t1.OVERLAY_VIEW/t1.file_name(s);out.append(o if o.exists() else t1.BASE_VIEW/t1.file_name(s))
 return out
def operational(root,cid,version,run_id,session,kind,stage,error):
 stamp=fw.now_ist().isoformat();row=fw.event(kind,f'{cid}|{version}|{session}|{kind}',run_id,candidate_id=cid,candidate_version=version,market_session=str(session),session=str(session),generated_at=stamp,timestamp=stamp,failure_type=kind,failure_stage=stage,error_type=type(error).__name__,message=str(error));fw.append_event(Path(root)/'operational'/f'{cid}.jsonl',row)
FAILURE_BY_STAGE={'ACTIVATION':'ACTIVATION_FAILURE','SNAPSHOT':'SNAPSHOT_HASH_FAILURE','DATA':'DATA_NOT_READY','SIGNAL':'SIGNAL_FAILURE','ORDER':'ORDER_FAILURE','EXECUTION':'EXECUTION_FAILURE','NAV':'NAV_FAILURE','COHORT':'COHORT_EVAL_FAILURE','COMMIT':'TRANSACTION_RECOVERY_REQUIRED'}
def failure_kind(stage,error):
 text=str(error)
 if 'LOCK_' in text:return 'LOCK_FAILURE','LOCK'
 if 'MANIFEST' in text:return 'MANIFEST_MISMATCH','MANIFEST'
 if 'ACTIVATION' in text:return 'ACTIVATION_FAILURE','ACTIVATION'
 if text=='DATA_NOT_READY':return 'DATA_NOT_READY','DATA'
 if stage not in FAILURE_BY_STAGE:raise fw.ForwardIntegrityError('UNMAPPED_FAILURE_STAGE')
 return FAILURE_BY_STAGE[stage],stage
def run(candidate,asof,process_session=False,forward_root=None,generated_at=None,test_fault_stage=None,test_data_root=None):
 root=Path(forward_root) if forward_root else RESEARCH/'forward_infrastructure';run_id=str(uuid.uuid4());manifest,_=fw.frozen_candidate(candidate);version=manifest['candidate_version'];generated=generated_at or fw.now_ist();session='UNKNOWN';stage='ACTIVATION';life=None
 if test_fault_stage and root.resolve()==(RESEARCH/'forward_infrastructure').resolve():raise fw.ForwardIntegrityError('TEST_FAULT_INJECTION_FORBIDDEN')
 if test_data_root and root.resolve()==(RESEARCH/'forward_infrastructure').resolve():raise fw.ForwardIntegrityError('TEST_DATA_SOURCE_OVERRIDE_FORBIDDEN')
 try:
  activation,_=fw.validate_activation(candidate,root);stage='DATA';contract=json.loads(fw.CONTRACT.read_text())
  data=SandboxRunnerDataSources(test_data_root) if test_data_root else CanonicalRunnerDataSources();braw=data.benchmark();symbols=data.symbols();raw={s:data.view(s) for s in symbols}
  cal=pd.DatetimeIndex(braw.index[braw.index<=pd.Timestamp(asof)]).sort_values().unique();views={s:v.reindex(cal) for s,v in raw.items()};benchmark=braw.reindex(cal);actual=fw.actual_signal_date(cal,views);session=str(actual.date());stage='SNAPSHOT';snapshot=fw.snapshot_manifest(data.input_paths(symbols),raw,braw,data.provider_id,test_data_root)
  if test_fault_stage=='SNAPSHOT':raise RuntimeError('TEST_FAULT_SNAPSHOT_HASH')
  stage='DATA'
  if pd.Timestamp(snapshot['source_max_session'])<actual:raise fw.ForwardIntegrityError('DATA_NOT_READY')
  cls=fw.classify(actual,asof,generated,activation,contract)
  if cls!='CLEAN_FORWARD':
   if cls=='MISSED_FORWARD_SIGNAL':operational(root,candidate,version,run_id,session,'MISSED_FORWARD_SIGNAL','TIMELINESS',RuntimeError(cls))
   else:fw.append_event(root/'debug_backfill'/f'{candidate}.jsonl',fw.event('NON_CLEAN_BACKFILL',f'{candidate}|{version}|{actual.date()}',run_id,candidate_id=candidate,candidate_version=version,requested_asof=str(pd.Timestamp(asof).date()),actual_signal_date=session,reason=cls,**snapshot))
   raise fw.ForwardIntegrityError(cls)
  stage='SIGNAL';life=Lifecycle(root,candidate,version,manifest,contract);life.test_fault_stage=test_fault_stage
  with fw.file_lock(root/'locks'/f'{candidate}-{version}-{session}'):
   state=life.state()
   if life.signal_due(state,actual):
    if test_fault_stage=='SIGNAL':raise RuntimeError('TEST_FAULT_SIGNAL')
    rows=[];pos=cal.get_loc(actual)
    for sym,v in views.items():
     r=t1.feature_row(v,pos)
     if r is not None:rows.append({'ticker':sym,**r})
    if len(rows)<10:raise fw.ForwardIntegrityError('DATA_NOT_READY')
    x=pd.DataFrame(rows);art=fw.frozen_candidate(candidate)[1];pred=np.median(np.column_stack([m.predict(x[art['features']].to_numpy(float)) for m in art['bundle']['models']]),axis=1);x['raw_score']=pred;x['cross_section_rank']=x.raw_score.rank(ascending=False,method='first').astype(int);x['selected_top10']=x.cross_section_rank.le(10)
    scored=[{'ticker':r.ticker,'raw_score':float(r.raw_score),'cross_section_rank':int(r.cross_section_rank),'selected_top10':bool(r.selected_top10),'signal_date_eligible':True} for r in x.itertuples(index=False)]
    stage='ORDER'
    if test_fault_stage=='ORDER':raise RuntimeError('TEST_FAULT_ORDER')
    life.create_signal(run_id,actual,cal,scored,snapshot)
   stage='EXECUTION';return life.process_session(run_id,actual,cal,views,benchmark)
 except Exception as exc:
  actual_stage=getattr(life,'failure_stage',None) or stage;kind,actual_stage=failure_kind(actual_stage,exc)
  try:operational(root,candidate,version,run_id,session,kind,actual_stage,exc)
  except Exception:pass
  raise
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--asof',required=True);p.add_argument('--process-session',action='store_true');p.add_argument('--sandbox-root');p.add_argument('--test-fault-stage',choices=['SNAPSHOT','SIGNAL','ORDER','EXECUTION','NAV','COHORT']);p.add_argument('--test-data-root');a=p.parse_args();print(run(a.candidate,a.asof,a.process_session,a.sandbox_root,test_fault_stage=a.test_fault_stage,test_data_root=a.test_data_root))
if __name__=='__main__':main()
