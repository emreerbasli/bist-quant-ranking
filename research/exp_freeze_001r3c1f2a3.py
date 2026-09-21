import json,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
R=Path(__file__).resolve().parent;ROOT=R.parent;sys.path[:0]=[str(ROOT),str(R)]
import forward_infrastructure_001r3 as fw
O=R/'forward_infrastructure'/'FORWARD_INFRASTRUCTURE_MANIFEST_V9.json'
def main():
 c=json.loads(fw.CONTRACT.read_text());cs={}
 for i in c['candidates']:
  m,_=fw.frozen_candidate(i);cs[i]={'version':m['candidate_version'],'model_sha256':m['model_sha256'],'feature_schema_hash':m['feature_schema_hash']}
 ps=[R/'run_frozen_shadow.py',R/'runner_data_sources.py',R/'forward_infrastructure_001r3.py',R/'forward_lifecycle_001r3.py',R/'exp_freeze_001r3c1f2a3.py',fw.CONTRACT,R/'tests'/'test_runner_data_sources.py']
 x={'experiment_id':'EXP-FREEZE-001R3C1F2A3','status':'PENDING_INDEPENDENT_AUDIT','clean_forward_start':'NOT_STARTED','candidates':cs,'hashes':{str(p.relative_to(ROOT)):fw.sha(p) for p in ps},'v8_manifest_sha256':fw.sha(R/'forward_infrastructure'/'FORWARD_INFRASTRUCTURE_MANIFEST_V8.json'),'created_at':datetime.now(ZoneInfo('Europe/Istanbul')).isoformat(),'production_writes_allowed':False};s=O.with_suffix('.json.sha256')
 if O.exists():
  if s.read_text().strip()!=fw.sha(O) or json.loads(O.read_text())['hashes']!=x['hashes']:raise fw.ForwardIntegrityError('V9_MANIFEST_MISMATCH')
  print('V9_READ_ONLY_REUSE');return
 fw.atomic_json(O,x);s.write_text(fw.sha(O)+'\n');print(fw.sha(O))
if __name__=='__main__':main()
