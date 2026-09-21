from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
import numpy as np,pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import forward_infrastructure_001 as fw
from forward_lifecycle_001r2 import Lifecycle
class LifecycleE2ETests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=json.loads(fw.CONTRACT.read_text());cls.m,_=fw.frozen_candidate('RC-LGBMR-001')
 def setup(self,n=150):
  cal=pd.bdate_range('2026-10-01',periods=n);views={}
  for i in range(10):
   x=pd.DataFrame(index=cal);x['trading_eligible']=True;x['price_quality']='RESOLVED';x['research_open']=100+i+np.arange(n)*.1;x['research_close']=x.research_open+1;x['raw_close']=x.research_close;x['volume']=100000;views[f'S{i}']=x
  b=views['S0'].copy();return cal,views,b
 def life(self,d):return Lifecycle(Path(d),'RC-LGBMR-001','1.0.0',self.m,self.c)
 def test_01_signal_to_next_session_execution(self):
  cal,v,b=self.setup()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r',cal[20],cal,[{'ticker':s,'raw_score':i} for i,s in enumerate(v)],{'input_snapshot_hash':'h'});self.assertEqual(l.process_session('r',cal[20],cal,v,b),'PROCESSED');self.assertEqual(l.process_session('r',cal[21],cal,v,b),'PROCESSED');self.assertEqual(len(l.state()['units']),10)
 def test_02_same_close_no_fill(self):
  cal,v,b=self.setup()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r',cal[20],cal,[{'ticker':s,'raw_score':i} for i,s in enumerate(v)],{'input_snapshot_hash':'h'});l.process_session('r',cal[20],cal,v,b);self.assertEqual(len(l.state()['units']),0)
 def test_03_restart_and_nav_idempotency(self):
  cal,v,b=self.setup()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r',cal[20],cal,[{'ticker':s,'raw_score':i} for i,s in enumerate(v)],{'input_snapshot_hash':'h'});l.process_session('r',cal[21],cal,v,b);l2=self.life(d);self.assertEqual(l2.process_session('r2',cal[21],cal,v,b),'ALREADY_EXISTS_NO_OP');self.assertEqual(len(fw.read_rows(l.nav)),1)
 def test_04_adv_block_and_cash(self):
  cal,v,b=self.setup();v['S0'].iloc[21,v['S0'].columns.get_loc('volume')]=0
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r',cal[20],cal,[{'ticker':s,'raw_score':i} for i,s in enumerate(v)],{'input_snapshot_hash':'h'});l.process_session('r',cal[21],cal,v,b);self.assertGreaterEqual(l.state()['cash'],0);self.assertNotIn('S0',l.state()['units'])
 def test_05_last_valid_mark_persists_position(self):
  cal,v,b=self.setup()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r',cal[20],cal,[{'ticker':s,'raw_score':i} for i,s in enumerate(v)],{'input_snapshot_hash':'h'});l.process_session('r',cal[21],cal,v,b);v['S1'].iloc[22,v['S1'].columns.get_loc('research_close')]=np.nan;l.process_session('r',cal[22],cal,v,b);self.assertIn('S1',l.state()['units'])
 def test_06_cohort_created_pending_then_completed_once(self):
  cal,v,b=self.setup()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r',cal[20],cal,[{'ticker':s,'raw_score':i} for i,s in enumerate(v)],{'input_snapshot_hash':'h'});l.process_session('r',cal[79],cal,v,b);self.assertTrue(l.state()['active_cohorts']);l.process_session('r',cal[81],cal,v,b);self.assertFalse(l.state()['active_cohorts']);n=len([x for x in fw.read_rows(l.cohorts) if x['event_type']=='COHORT_COMPLETED']);l.process_session('r2',cal[81],cal,v,b);self.assertEqual(n,len([x for x in fw.read_rows(l.cohorts) if x['event_type']=='COHORT_COMPLETED']))
 def test_07_partial_outcome_is_explicit(self):
  cal,v,b=self.setup()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);l.create_signal('r',cal[20],cal,[{'ticker':s,'raw_score':i} for i,s in enumerate(v)],{'input_snapshot_hash':'h'});l.process_session('r',cal[21],cal,v,b);v['S0'].iloc[81,v['S0'].columns.get_loc('research_close')]=np.nan;l.process_session('r',cal[81],cal,v,b);done=[x for x in fw.read_rows(l.cohorts) if x['event_type']=='COHORT_COMPLETED'][0];self.assertTrue(any(not x['eligible'] for x in done['outcomes']))
 def test_08_overlap_metadata_and_raw_contract(self):
  cal,v,b=self.setup()
  with tempfile.TemporaryDirectory() as d:
   l=self.life(d);co=l.create_signal('r',cal[20],cal,[{'ticker':s,'raw_score':i} for i,s in enumerate(v)],{'input_snapshot_hash':'h'});self.assertEqual(co['configured_target'],'RAW');self.assertEqual(co['configured_horizon'],60)
 def test_09_activation_absent_runner_contract(self):self.assertFalse((fw.FORWARD/'forward_activation.json').exists())
 def test_10_official_roots_untouched(self):
  for c in self.c['candidates']:self.assertEqual((fw.FROZEN/c/'shadow_signals.jsonl').stat().st_size,0)
if __name__=='__main__':unittest.main()
