"""Write-once forward-infrastructure manifest; never alters EXP-FREEZE-001 artefacts."""
from __future__ import annotations
import json,sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
RESEARCH=Path(__file__).resolve().parent;ROOT=RESEARCH.parent;sys.path[:0]=[str(ROOT),str(RESEARCH)]
import forward_infrastructure_001 as fw
# v1 remains an immutable pre-regression-test record; v2 is the final remediation binding.
OUT=fw.FORWARD/'EXP-FREEZE-001R_forward_infrastructure_manifest_v2.json';SIDE=OUT.with_suffix('.json.sha256')
def payload():
 c=json.loads(fw.CONTRACT.read_text());items={}
 for cid in c['candidates']:
  m,a=fw.frozen_candidate(cid);items[cid]={'candidate_version':m['candidate_version'],'model_sha256':m['model_sha256'],'feature_schema_hash':m['feature_schema_hash'],'target_procedure':m['target_procedure'],'horizon_procedure':m['horizon_procedure']}
 paths=[RESEARCH/'exp_freeze_001.py',RESEARCH/'run_frozen_shadow.py',RESEARCH/'forward_infrastructure_001.py',RESEARCH/'exp_freeze_001r.py',fw.CONTRACT,RESEARCH/'tests'/'test_exp_freeze_001r.py']
 return {'experiment_id':'EXP-FREEZE-001R','status':'PENDING_INDEPENDENT_AUDIT','original_model_freeze_timestamp':c['original_model_freeze_timestamp'],'clean_forward_start':'PENDING_AUDIT','candidates':items,'code_hashes':{str(p.relative_to(ROOT)):fw.sha(p) for p in paths},'original_freeze_manifest_sha256':fw.sha(fw.FROZEN/'EXP-FREEZE-001_combined_manifest.json'),'remediation_timestamp':datetime.now(ZoneInfo('Europe/Istanbul')).isoformat(),'production_writes_allowed':False}
def main():
 data=payload();OUT.parent.mkdir(exist_ok=True)
 if OUT.exists():
  recorded=json.loads(OUT.read_text())
  if recorded['code_hashes']!=data['code_hashes'] or recorded['candidates']!=data['candidates']:raise fw.ForwardIntegrityError('FORWARD_INFRASTRUCTURE_MANIFEST_MISMATCH')
  if not SIDE.exists() or SIDE.read_text().strip()!=fw.sha(OUT):raise fw.ForwardIntegrityError('FORWARD_INFRASTRUCTURE_MANIFEST_HASH_MISMATCH')
  print('FORWARD_MANIFEST_READ_ONLY_REUSE');return
 OUT.write_text(json.dumps(data,indent=2),encoding='utf-8');SIDE.write_text(fw.sha(OUT)+'\n',encoding='utf-8');print('FORWARD_MANIFEST_CREATED',fw.sha(OUT))
if __name__=='__main__':main()
