"""Write-once V5 successor manifest for the R3A bound acceptance suite."""
from __future__ import annotations
import json,sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
RESEARCH=Path(__file__).resolve().parent;ROOT=RESEARCH.parent;sys.path[:0]=[str(ROOT),str(RESEARCH)]
import forward_infrastructure_001r3 as fw
OUT=RESEARCH/'forward_infrastructure'/'FORWARD_INFRASTRUCTURE_MANIFEST_V5.json'
def build():
 c=json.loads(fw.CONTRACT.read_text());cs={}
 for cid in c['candidates']:
  m,_=fw.frozen_candidate(cid);cs[cid]={'version':m['candidate_version'],'model_sha256':m['model_sha256'],'feature_schema_hash':m['feature_schema_hash'],'target':m['target_procedure'],'horizon':m['horizon_procedure']}
 ps=[RESEARCH/'run_frozen_shadow.py',RESEARCH/'forward_infrastructure_001r3.py',RESEARCH/'forward_lifecycle_001r3.py',RESEARCH/'exp_freeze_001r3a.py',fw.CONTRACT,RESEARCH/'tests'/'test_exp_freeze_001r3.py',RESEARCH/'tests'/'test_exp_freeze_001r3a.py',RESEARCH/'contracts'/'exp_tgt_001.json',RESEARCH/'contracts'/'exp_tgt_002.json',RESEARCH/'contracts'/'exp_port_001.json']
 return {'experiment_id':'EXP-FREEZE-001R3A','status':'PENDING_INDEPENDENT_AUDIT','clean_forward_start':'NOT_STARTED','original_model_freeze_timestamp':c['original_model_freeze_timestamp'],'candidates':cs,'hashes':{str(p.relative_to(ROOT)):fw.sha(p) for p in ps},'v4_manifest_sha256':fw.sha(RESEARCH/'forward_infrastructure'/'FORWARD_INFRASTRUCTURE_MANIFEST_V4.json'),'created_at':datetime.now(ZoneInfo('Europe/Istanbul')).isoformat(),'production_writes_allowed':False}
def main():
 x=build();side=OUT.with_suffix('.json.sha256');OUT.parent.mkdir(exist_ok=True)
 if OUT.exists():
  if not side.exists() or side.read_text().strip()!=fw.sha(OUT):raise fw.ForwardIntegrityError('V5_MANIFEST_HASH_MISMATCH')
  if json.loads(OUT.read_text()).get('hashes')!=x['hashes']:raise fw.ForwardIntegrityError('V5_MANIFEST_CODE_MISMATCH')
  print('V5_READ_ONLY_REUSE');return
 fw.atomic_json(OUT,x);side.write_text(fw.sha(OUT)+'\n',encoding='utf-8');print(fw.sha(OUT))
if __name__=='__main__':main()
