"""R3A acceptance checks.  All state is confined to TemporaryDirectory sandboxes."""
from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
import numpy as np,pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import forward_infrastructure_001r3 as fw
from forward_lifecycle_001r3 import Lifecycle
import run_frozen_shadow as runner

class Acceptance(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=json.loads(fw.CONTRACT.read_text());cls.m=fw.frozen_candidate('RC-LGBMR-001')[0]
 def fixture(self,n=150,k=12):
  cal=pd.bdate_range('2026-01-02',periods=n);v={}
  for i in range(k):
   x=pd.DataFrame(index=cal);x['trading_eligible']=True;x['price_quality']='RESOLVED';x['research_open']=100+i+np.arange(n)*.1;x['research_close']=x.research_open+1;x['raw_close']=x.research_close;x['volume']=100000;v[f'S{i}']=x
  return cal,v,v['S0'].copy()
 def scores(self,v):return [{'ticker':s,'raw_score':float(i),'cross_section_rank':len(v)-i,'selected_top10':i>=len(v)-10,'signal_date_eligible':True} for i,s in enumerate(v)]
 def life(self,d):return Lifecycle(Path(d),'RC-LGBMR-001','1.0.0',self.m,self.c)
 def test_01_runner_rejects_wrong_or_missing_activation_and_manifest(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(fw.ForwardIntegrityError):runner.run('RC-LGBMR-001','2026-09-18',False,d)
   p=Path(d)/'forward_activation.json';p.write_text('{"audit_status":"AUDIT_PASSED"}')
   with self.assertRaises(fw.ForwardIntegrityError):runner.run('RC-LGBMR-001','2026-09-18',True,d)
 def test_02_source_baseline_and_timing_classes(self):
  a={'activation_baseline_source_max':'2026-02-10'};self.assertEqual(fw.classify('2026-02-10','2026-02-10',pd.Timestamp('2026-02-10 18:11',tz='Europe/Istanbul'),a,self.c),'NON_CLEAN_BACKFILL');self.assertEqual(fw.classify('2026-02-11','2026-02-11',pd.Timestamp('2026-02-12 18:11',tz='Europe/Istanbul'),a,self.c),'MISSED_FORWARD_SIGNAL')
 def test_03_snapshot_source_max_is_independent(self):
  cal,v,b=self.fixture();s=fw.snapshot_manifest([fw.CONTRACT],v,b);self.assertEqual(s['source_max_session'],str(cal[-1].date()));self.assertIn('source_file_mtime_ns_max',s)
 def test_04_transaction_journal_recovery_and_scheduler(self):
  cal,v,b=self.fixture()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('a',cal[20],cal,self.scores(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});self.assertEqual(l.process_session('b',cal[21],cal,v,b),'COMMITTED');self.assertEqual(l.process_session('c',cal[21],cal,v,b),'ALREADY_EXISTS_NO_OP');s=l.state();s['eligible_session_count']=59;l.save(s);l.process_session('d',cal[22],cal,v,b);self.assertEqual(l.state()['next_signal_session'],str(cal[22].date()))
 def test_05_execution_accounting_and_provenance(self):
  cal,v,b=self.fixture()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('a',cal[20],cal,self.scores(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});l.process_session('b',cal[21],cal,v,b);e=[x for x in fw.read_rows(l.events) if x['event_type']=='ORDER_EXECUTION'];n=fw.read_rows(l.nav)[0];self.assertTrue(all(x['order_id'] and x['adv_reference_session'] for x in e));self.assertTrue(all(x['fill_status'] in {'FILLED','BLOCKED'} for x in e));self.assertAlmostEqual(n['gross_nav']-n['transaction_cost'],n['net_nav']);self.assertTrue(n['mark_provenance'])
 def test_06_eligibility_partial_and_pending_exclusion(self):
  cal,v,b=self.fixture()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('a',cal[20],cal,self.scores(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});v['S0'].iloc[81,v['S0'].columns.get_loc('trading_eligible')]=False;v['S1'].iloc[50,v['S1'].columns.get_loc('price_quality')]='UNRESOLVED';l.process_session('b',cal[80],cal,v,b);self.assertTrue(l.state()['active_cohorts']);l.process_session('c',cal[81],cal,v,b);x=[z for z in fw.read_rows(l.cohorts) if z['event_type']=='COHORT_COMPLETED'][0];self.assertGreater(x['ineligible'],0);self.assertIn('TRADING_INELIGIBLE',x['reason_distribution']);self.assertIn('PRICE_QUALITY_FAIL',x['reason_distribution'])
 def test_07_cross_section_metrics_and_overlap(self):
  cal,v,b=self.fixture()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('a',cal[20],cal,self.scores(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});l.process_session('b',cal[81],cal,v,b);x=[z for z in fw.read_rows(l.cohorts) if z['event_type']=='COHORT_COMPLETED'][0];self.assertEqual(x['total_scored'],12);self.assertIn('rank_ic',x);self.assertIn('ndcg_at_10',x);self.assertIn('top_k_spread_raw',x)
 def test_08_candidate_and_official_isolation(self):
  expected={'RC-LGBMR-001':'350fb049f7f2e392a62fc89516acbb00676e1b1ef922559fc2f1dc3bfe9e81f6','RC-LAMBDAMART-001':'4744a5109bc3f97b11f2ef6f890cdded5672fd5a25a9a8252f9e1ad7fb31d849'}
  for c,h in expected.items():
   self.assertEqual(fw.sha(fw.FROZEN/c/'model.joblib'),h)
   self.assertTrue(all((fw.FROZEN/c/n).stat().st_size==0 for n in ['shadow_signals.jsonl','shadow_portfolio.jsonl','shadow_operational_events.jsonl']))
if __name__=='__main__':unittest.main()
