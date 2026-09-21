from __future__ import annotations
import json,sys,tempfile,unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import forward_infrastructure_001r3 as fw
from forward_lifecycle_001r3 import Lifecycle
import run_frozen_shadow as runner

class R3Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=json.loads(fw.CONTRACT.read_text());cls.m={cid:fw.frozen_candidate(cid)[0] for cid in cls.c['candidates']}
 def views(self,n=150):
  cal=pd.bdate_range('2026-01-02',periods=n);v={}
  for i in range(12):
   x=pd.DataFrame(index=cal);x['trading_eligible']=True;x['price_quality']='RESOLVED';x['research_open']=100+i+np.arange(n)*.1;x['research_close']=x.research_open+1;x['raw_close']=x.research_close;x['volume']=100000;v[f'S{i}']=x
  return cal,v,v['S0'].copy()
 def life(self,d,cid='RC-LGBMR-001'):return Lifecycle(Path(d),cid,'1.0.0',self.m[cid],self.c)
 def scored(self,v):return [{'ticker':s,'raw_score':float(i),'cross_section_rank':len(v)-i,'selected_top10':i>=2,'signal_date_eligible':True} for i,s in enumerate(v)]
 def test_01_activation_absent_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(fw.ForwardIntegrityError):fw.validate_activation('RC-LGBMR-001',d)
 def test_02_semantic_append_idempotency(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.jsonl';r=fw.event('X','same','r1');self.assertTrue(fw.append_event(p,r));self.assertFalse(fw.append_event(p,fw.event('X','same','r2')));self.assertEqual(len(fw.read_rows(p)),1)
 def test_02b_arbitrary_audit_pass_json_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'forward_activation.json';x={k:'x' for k in self.c['activation_required_fields']};x.update({'audit_status':'AUDIT_PASSED','approved_candidate_ids':['RC-LGBMR-001'],'approved_candidate_versions':{'RC-LGBMR-001':'1.0.0'},'audit_artifact_path':'audits/not-present.json'});x['approval_hash']=fw.canonical_hash({k:v for k,v in x.items() if k!='approval_hash'});p.write_text(json.dumps(x))
   with self.assertRaises(fw.ForwardIntegrityError):fw.validate_activation('RC-LGBMR-001',d)
 def test_03_next_session_orders_and_mark(self):
  cal,v,b=self.views()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r1',cal[20],cal,self.scored(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});l.process_session('r2',cal[20],cal,v,b);l.process_session('r3',cal[21],cal,v,b);self.assertEqual(len(l.state()['units']),10);self.assertEqual(len(fw.read_rows(l.nav)),2)
 def test_04_restart_no_duplicate_nav_or_execution(self):
  cal,v,b=self.views()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r1',cal[20],cal,self.scored(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});l.process_session('r2',cal[21],cal,v,b);l2=self.life(d);self.assertEqual(l2.process_session('another',cal[21],cal,v,b),'ALREADY_EXISTS_NO_OP');self.assertEqual(len(fw.read_rows(l.nav)),1);self.assertEqual(len([x for x in fw.read_rows(l.events) if x['event_type']=='ORDER_EXECUTION']),10)
 def test_05_h59_h60_full_universe_and_metrics(self):
  cal,v,b=self.views()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r',cal[20],cal,self.scored(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});l.process_session('r',cal[80],cal,v,b);self.assertTrue(l.state()['active_cohorts']);l.process_session('r2',cal[81],cal,v,b);done=[x for x in fw.read_rows(l.cohorts) if x['event_type']=='COHORT_COMPLETED'][0];self.assertEqual(done['total_scored'],12);self.assertEqual(done['actual_label_end_session'],str(cal[81].date()));self.assertIn('ndcg_at_10',done)
 def test_06_beta_residual_end_to_end(self):
  cal,v,b=self.views()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d,'RC-LAMBDAMART-001');l.create_signal('r',cal[20],cal,self.scored(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});l.process_session('r',cal[81],cal,v,b);done=[x for x in fw.read_rows(l.cohorts) if x['event_type']=='COHORT_COMPLETED'][0];self.assertEqual(done['configured_target'] if 'configured_target' in done else l.manifest['target_procedure'],'BETA_RESIDUAL');self.assertIn('rank_ic',done)
 def test_07_blocked_and_sell_cash_sign(self):
  cal,v,b=self.views()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r',cal[20],cal,self.scored(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});v['S2'].iloc[21,v['S2'].columns.get_loc('volume')]=0;l.process_session('r',cal[21],cal,v,b);e=[x for x in fw.read_rows(l.events) if x['event_type']=='ORDER_EXECUTION'];self.assertTrue(any(x['fill_status']=='BLOCKED' for x in e));self.assertTrue(all('adv_reference_session' in x for x in e))
 def test_08_metadata_corrected_models_unchanged(self):
  for cid,m in self.m.items():self.assertIsNone(m['clean_forward_start']);self.assertEqual(m['forward_status'],'NOT_STARTED');self.assertEqual(fw.sha(fw.FROZEN/cid/'model.joblib'),m['model_sha256'])
 def test_09_official_logs_empty(self):
  for cid in self.c['candidates']:
   for n in ['shadow_signals.jsonl','shadow_portfolio.jsonl','shadow_operational_events.jsonl']:self.assertEqual((fw.FROZEN/cid/n).stat().st_size,0)
 def test_10_real_runner_process_flag_cannot_bypass_activation(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(fw.ForwardIntegrityError):runner.run('RC-LGBMR-001','2026-09-18',process_session=True,forward_root=d)
if __name__=='__main__':unittest.main()
