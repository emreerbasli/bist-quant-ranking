from __future__ import annotations
import json,sys
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime
RESEARCH=Path(__file__).resolve().parent;ROOT=RESEARCH.parent;sys.path[:0]=[str(ROOT),str(RESEARCH)]
import forward_infrastructure_001r3 as fw
OUT=RESEARCH/'forward_infrastructure'/'FORWARD_INFRASTRUCTURE_MANIFEST_V8.json'
def main():
 c=json.loads(fw.CONTRACT.read_text());cs={}
 for cid in c['candidates']:
  m,_=fw.frozen_candidate(cid);cs[cid]={'version':m['candidate_version'],'model_sha256':m['model_sha256'],'feature_schema_hash':m['feature_schema_hash'],'target':m['target_procedure'],'horizon':m['horizon_procedure']}
 ps=[RESEARCH/'run_frozen_shadow.py',RESEARCH/'forward_infrastructure_001r3.py',RESEARCH/'forward_lifecycle_001r3.py',RESEARCH/'exp_freeze_001r3c1d.py',fw.CONTRACT,RESEARCH/'tests'/'test_exp_freeze_001r3.py',RESEARCH/'tests'/'test_exp_freeze_001r3a.py',RESEARCH/'tests'/'test_exp_freeze_001r3b.py']
 x={'experiment_id':'EXP-FREEZE-001R3C1D','status':'PENDING_INDEPENDENT_AUDIT','clean_forward_start':'NOT_STARTED','candidates':cs,'hashes':{str(p.relative_to(ROOT)):fw.sha(p) for p in ps},'v7_manifest_sha256':fw.sha(RESEARCH/'forward_infrastructure'/'FORWARD_INFRASTRUCTURE_MANIFEST_V7.json'),'created_at':datetime.now(ZoneInfo('Europe/Istanbul')).isoformat(),'production_writes_allowed':False};side=OUT.with_suffix('.json.sha256')
 if OUT.exists():
  if side.read_text().strip()!=fw.sha(OUT) or json.loads(OUT.read_text())['hashes']!=x['hashes']:raise fw.ForwardIntegrityError('V8_MANIFEST_MISMATCH')
  print('V8_READ_ONLY_REUSE');return
 fw.atomic_json(OUT,x);side.write_text(fw.sha(OUT)+'\n');print(fw.sha(OUT))
if __name__=='__main__':main()
