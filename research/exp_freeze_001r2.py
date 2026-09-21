"""Create the write-once V3 lifecycle manifest without activating clean-forward monitoring."""
from __future__ import annotations
import json,sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
RESEARCH=Path(__file__).resolve().parent;ROOT=RESEARCH.parent;sys.path[:0]=[str(ROOT),str(RESEARCH)]
import forward_infrastructure_001 as fw
OUT=fw.FORWARD/'FORWARD_INFRASTRUCTURE_MANIFEST_V3.json';SIDE=OUT.with_suffix('.json.sha256')
def build():
 c=json.loads(fw.CONTRACT.read_text());candidates={}
 for cid in c['candidates']:
  m,_=fw.frozen_candidate(cid);candidates[cid]={'version':m['candidate_version'],'model_sha256':m['model_sha256'],'target':m['target_procedure'],'horizon':m['horizon_procedure']}
 paths=[RESEARCH/'run_frozen_shadow.py',RESEARCH/'forward_infrastructure_001.py',RESEARCH/'forward_lifecycle_001r2.py',RESEARCH/'exp_freeze_001r2.py',fw.CONTRACT,RESEARCH/'tests'/'test_exp_freeze_001r.py',RESEARCH/'tests'/'test_exp_freeze_001r2.py']
 return {'experiment_id':'EXP-FREEZE-001R2','status':'PENDING_INDEPENDENT_AUDIT','clean_forward_start':'NOT_STARTED','original_model_freeze_timestamp':c['original_model_freeze_timestamp'],'candidates':candidates,'hashes':{str(p.relative_to(ROOT)):fw.sha(p) for p in paths},'v2_manifest_sha256':fw.sha(fw.FORWARD/'EXP-FREEZE-001R_forward_infrastructure_manifest_v2.json'),'created_at':datetime.now(ZoneInfo('Europe/Istanbul')).isoformat(),'production_writes_allowed':False}
def main():
 x=build();OUT.parent.mkdir(exist_ok=True)
 if OUT.exists():
  if not SIDE.exists() or SIDE.read_text().strip()!=fw.sha(OUT):raise fw.ForwardIntegrityError('V3_MANIFEST_HASH_MISMATCH')
  if json.loads(OUT.read_text())['hashes']!=x['hashes']:raise fw.ForwardIntegrityError('V3_MANIFEST_CODE_MISMATCH')
  print('V3_READ_ONLY_REUSE');return
 OUT.write_text(json.dumps(x,indent=2),encoding='utf-8');SIDE.write_text(fw.sha(OUT)+'\n',encoding='utf-8');print(fw.sha(OUT))
if __name__=='__main__':main()
