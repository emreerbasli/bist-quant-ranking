"""R3 fail-closed primitives.  All paths are research-only and activation-gated."""
from __future__ import annotations
import hashlib,json,os,time,uuid
from contextlib import contextmanager
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

RESEARCH=Path(__file__).resolve().parent; ROOT=RESEARCH.parent; FROZEN=RESEARCH/'frozen_candidates'; IST=ZoneInfo('Europe/Istanbul')
CONTRACT=RESEARCH/'contracts'/'exp_freeze_001r3.json'
class ForwardIntegrityError(RuntimeError): pass
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def canonical_hash(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def now_ist(): return datetime.now(IST)
def atomic_json(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,sort_keys=True,indent=2,default=str),encoding='utf-8');os.replace(tmp,path)
@contextmanager
def file_lock(path):
 import msvcrt
 p=Path(str(path)+'.lock');p.parent.mkdir(parents=True,exist_ok=True);fd=os.open(p,os.O_CREAT|os.O_RDWR)
 try:
  if os.path.getsize(p)==0:os.write(fd,b'0')
  try:msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
  except OSError as e:raise ForwardIntegrityError('LOCK_UNAVAILABLE') from e
  yield
 finally:
  try:msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
  except OSError:pass
  os.close(fd)
def read_rows(path):
 p=Path(path)
 return [] if not p.exists() or not p.stat().st_size else [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def append_event(path,row):
 """Append once by durable semantic key; run_id is provenance, never identity."""
 if not row.get('semantic_key') or not row.get('run_id'):raise ForwardIntegrityError('SEMANTIC_KEY_AND_RUN_ID_REQUIRED')
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 with file_lock(p):
  if any(x.get('semantic_key')==row['semantic_key'] for x in read_rows(p)):return False
  with p.open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(row,sort_keys=True,default=str)+'\n');f.flush();os.fsync(f.fileno())
 return True
def semantic_id(kind,key):return str(uuid.uuid5(uuid.NAMESPACE_URL,f'EXP-FREEZE-001R3|{kind}|{key}'))
def event(kind,key,run_id,**payload):return {'event_id':semantic_id(kind,key),'semantic_key':f'{kind}|{key}','event_type':kind,'run_id':run_id,**payload}
def candidate_manifest(cid):return json.loads((FROZEN/cid/'candidate_manifest.json').read_text())
def frozen_candidate(cid):
 m=candidate_manifest(cid);p=FROZEN/cid/'model.joblib'
 if sha(p)!=m['model_sha256']:raise ForwardIntegrityError('FROZEN_ARTIFACT_MISMATCH')
 import joblib
 a=joblib.load(p)
 if a['candidate_id']!=cid or a['version']!=m['candidate_version'] or a['target_family']!=m['target_procedure'] or a['horizon_sessions']!=m['horizon_procedure'] or a['features']!=[x['name'] for x in m['features']]:raise ForwardIntegrityError('FROZEN_ARTIFACT_MANIFEST_MISMATCH')
 return m,a
def resolve_approved_manifest(forward_root,approved_hash,approved_reference=None):
 root=Path(forward_root).resolve()
 if not isinstance(approved_hash,str) or len(approved_hash)!=64:raise ForwardIntegrityError('FORWARD_MANIFEST_MISMATCH')
 if approved_reference:
  ref=Path(approved_reference)
  candidate=(root/ref).resolve()
  if ref.is_absolute() or candidate.parent!=root or candidate.suffix.lower()!='.json' or not candidate.exists():raise ForwardIntegrityError('FORWARD_MANIFEST_MISMATCH')
  matches=[candidate] if sha(candidate)==approved_hash else []
 else:
  matches=[p for p in root.glob('FORWARD_INFRASTRUCTURE_MANIFEST_V*.json') if p.is_file() and sha(p)==approved_hash]
 if len(matches)!=1:raise ForwardIntegrityError('FORWARD_MANIFEST_MISMATCH')
 return matches[0]
def validate_manifest(cid,forward_root,approved_hash,approved_reference=None):
 manifest_path=resolve_approved_manifest(forward_root,approved_hash,approved_reference)
 side=manifest_path.with_suffix('.json.sha256')
 if not side.exists() or side.read_text().strip()!=approved_hash or sha(manifest_path)!=approved_hash:raise ForwardIntegrityError('FORWARD_MANIFEST_MISMATCH')
 m=json.loads(manifest_path.read_text())
 if m.get('status')!='PENDING_INDEPENDENT_AUDIT' or cid not in m.get('candidates',{}):raise ForwardIntegrityError('FORWARD_MANIFEST_MISMATCH')
 for rel,expected in m.get('hashes',{}).items():
  if sha(ROOT/rel)!=expected:raise ForwardIntegrityError('FORWARD_MANIFEST_MISMATCH')
 cm,_=frozen_candidate(cid);bound=m['candidates'][cid]
 if bound['version']!=cm['candidate_version'] or bound['model_sha256']!=cm['model_sha256'] or bound['feature_schema_hash']!=cm['feature_schema_hash']:raise ForwardIntegrityError('FORWARD_MANIFEST_MISMATCH')
 return m
def validate_activation(cid,forward_root):
 c=json.loads(CONTRACT.read_text());p=Path(forward_root)/'forward_activation.json'
 if not p.exists():raise ForwardIntegrityError('ACTIVATION_FAILURE')
 x=json.loads(p.read_text());missing=[k for k in c['activation_required_fields'] if not x.get(k)]
 if missing or x.get('audit_status')!='AUDIT_PASSED':raise ForwardIntegrityError('ACTIVATION_FAILURE')
 given=x.get('approval_hash');body={k:v for k,v in x.items() if k!='approval_hash'}
 if given!=canonical_hash(body):raise ForwardIntegrityError('ACTIVATION_FAILURE')
 audit_path=(Path(forward_root)/x['audit_artifact_path']).resolve()
 audit_root=(Path(forward_root)/'audits').resolve()
 if audit_root not in audit_path.parents or not audit_path.exists() or sha(audit_path)!=x['audit_artifact_hash']:raise ForwardIntegrityError('ACTIVATION_FAILURE')
 audit=json.loads(audit_path.read_text())
 if audit.get('audit_status')!='AUDIT_PASSED' or audit.get('approved_forward_manifest_hash')!=x['approved_forward_manifest_hash']:raise ForwardIntegrityError('ACTIVATION_FAILURE')
 references={x.get('approved_forward_manifest_reference'),x.get('approved_forward_manifest_path')}-{None,''}
 if len(references)>1:raise ForwardIntegrityError('FORWARD_MANIFEST_MISMATCH')
 m=validate_manifest(cid,forward_root,x['approved_forward_manifest_hash'],next(iter(references),None))
 if cid not in x['approved_candidate_ids'] or x['approved_candidate_versions'].get(cid)!=m['candidates'][cid]['version']:raise ForwardIntegrityError('ACTIVATION_FAILURE')
 return x,m
def snapshot_manifest(input_files,views,benchmark,provider_snapshot_id='LOCAL_RESEARCH_PRICE_VIEW',sandbox_root=None):
 root=Path(sandbox_root).resolve() if sandbox_root else None;rows=[]
 for p in sorted(map(Path,input_files)):
  q=p.resolve()
  if root:
   try: logical='sandbox://'+q.relative_to(root).as_posix()
   except ValueError: raise ForwardIntegrityError('SANDBOX_PATH_ESCAPE')
  else:
   try: logical=str(q.relative_to(ROOT))
   except ValueError: logical=str(q)
  rows.append({'path':logical,'sha256':sha(q),'file_size':q.stat().st_size})
 maxima=[]
 for v in [benchmark,*views.values()]:
  if len(v.index):maxima.append(pd.Timestamp(v.index.max()))
 if not maxima:raise ForwardIntegrityError('DATA_NOT_READY')
 source_max=max(maxima);file_times=[Path(p).stat().st_mtime_ns for p in input_files]
 return {'provider_snapshot_id':provider_snapshot_id,'price_inputs':rows,'source_max_session':str(source_max.date()),'source_max_timestamp':pd.Timestamp(source_max).isoformat(),'source_file_mtime_ns_max':max(file_times),'input_snapshot_hash':canonical_hash({'files':rows,'source_max_session':str(source_max.date())})}
def actual_signal_date(calendar,views):
 for d in pd.DatetimeIndex(calendar).sort_values().unique()[::-1]:
  if any(d in v.index and bool(v.loc[d,'trading_eligible']) for v in views.values()):return pd.Timestamp(d)
 raise ForwardIntegrityError('DATA_NOT_READY')
def classify(actual,requested,generated,activation,contract):
 a=pd.Timestamp(actual).normalize();r=pd.Timestamp(requested).normalize();base=pd.Timestamp(activation['activation_baseline_source_max']).normalize()
 if a<=base:return 'NON_CLEAN_BACKFILL'
 if contract['timeliness']['require_actual_signal_date_equals_requested_asof'] and a!=r:return 'NON_CLEAN_BACKFILL'
 g=pd.Timestamp(generated);g=g.tz_convert(IST) if g.tzinfo else g.tz_localize(IST);close=pd.Timestamp(f'{a.date()} {contract["timeliness"]["market_close_local"]}').tz_localize(IST)
 return 'CLEAN_FORWARD' if close<=g<=close+timedelta(hours=contract['timeliness']['permitted_operational_window_hours']) else 'MISSED_FORWARD_SIGNAL'
def expected_label_end(calendar,signal,h):
 from temporal_validation import build_label_interval
 return build_label_interval(pd.DatetimeIndex(calendar),pd.Timestamp(signal),int(h)).label_end
def label_outcome(family,view,benchmark,calendar,signal,end):
 start=pd.DatetimeIndex(calendar).get_loc(pd.Timestamp(signal))+1;finish=pd.DatetimeIndex(calendar).get_loc(pd.Timestamp(end));q=view['price_quality'].fillna('UNRESOLVED').astype(str).iloc[start:finish+1];eligible=view['trading_eligible'].fillna(False).iloc[[start,finish]]
 close=pd.to_numeric(view['research_close'],errors='coerce')
 if not bool(eligible.all()):return np.nan,'TRADING_INELIGIBLE',np.nan
 if (q=='UNRESOLVED').any():return np.nan,'PRICE_QUALITY_FAIL',np.nan
 if not np.isfinite(close.iloc[start]) or not np.isfinite(close.iloc[finish]) or close.iloc[start]<=0 or close.iloc[finish]<=0:return np.nan,'LABEL_UNAVAILABLE',np.nan
 raw=float(close.iloc[finish]/close.iloc[start]-1)
 if family=='RAW':return raw,'ELIGIBLE',raw
 from exp_tgt_002 import estimate_beta
 beta,_=estimate_beta(view,benchmark,pd.DatetimeIndex(calendar).get_loc(pd.Timestamp(signal)))
 if not np.isfinite(beta):return np.nan,'INSUFFICIENT_HISTORY',raw
 b=pd.to_numeric(benchmark['research_close'],errors='coerce');br=float(b.iloc[finish]/b.iloc[start]-1)
 return raw-float(beta)*br,'ELIGIBLE',raw
