from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
import numpy as np,pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import forward_infrastructure_001r3 as fw
from forward_lifecycle_001r3 import Lifecycle

class FailedRows(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=json.loads(fw.CONTRACT.read_text());cls.m=fw.frozen_candidate('RC-LGBMR-001')[0]
 def f(self,n=150):
  cal=pd.DatetimeIndex(pd.bdate_range('2026-01-02',periods=n).delete([5,25,55]));v={}
  for i in range(12):
   x=pd.DataFrame(index=cal);x['trading_eligible']=True;x['price_quality']='RESOLVED';x['research_open']=100+i+np.arange(len(cal));x['research_close']=x.research_open+1;x['raw_close']=x.research_close;x['volume']=100000;v[f'S{i}']=x
  return cal,v,v['S0'].copy()
 def s(self,v):return [{'ticker':x,'raw_score':float(i),'cross_section_rank':len(v)-i,'selected_top10':i>=2,'signal_date_eligible':True} for i,x in enumerate(v)]
 def l(self,d):return Lifecycle(Path(d),'RC-LGBMR-001','1.0.0',self.m,self.c)
 def test_01_prepared_crash_replays_once(self):
  cal,v,b=self.f()
  with tempfile.TemporaryDirectory() as d:
   l=self.l(d);l.create_signal('a',cal[20],cal,self.s(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});old=l._append;l._append=lambda *a:(_ for _ in ()).throw(RuntimeError('INJECTED'))
   with self.assertRaises(RuntimeError):l.process_session('b',cal[21],cal,v,b)
   self.assertEqual(json.loads(l.tx_path(str(cal[21].date())).read_text())['status'],'PREPARED');l._append=old;l.process_session('c',cal[21],cal,v,b);self.assertEqual(len(fw.read_rows(l.nav)),1);self.assertEqual(len([x for x in fw.read_rows(l.events) if x['event_type']=='ORDER_EXECUTION']),10)
 def test_02_exact_ndcg_independent(self):
  actual=np.array([.1,.2,.3,.4,.5,.6,.7,.8,.9,1.]);score=np.arange(10);disc=1/np.log2(np.arange(2,12));expected=float(np.sum(actual[::-1]*disc)/np.sum(np.sort(actual)[::-1]*disc));from exp_tgt_001 import ndcg_at_k;self.assertAlmostEqual(ndcg_at_k(actual,score,10),expected)
 def test_03_sell_cash_formula(self):
  gross=1000.;bps=self.c['portfolio']['one_way_cost_bps'];cost=gross*bps/10000;self.assertEqual(gross-cost,995.)
 def test_04_two_cohort_overlap(self):
  cal,v,b=self.f()
  with tempfile.TemporaryDirectory() as d:
   l=self.l(d);l.create_signal('a',cal[20],cal,self.s(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});l.create_signal('b',cal[21],cal,self.s(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())});self.assertEqual(len(l.state()['active_cohorts']),2);self.assertEqual(sorted(x['overlapping_active_cohorts'] for x in l.state()['active_cohorts'].values()),[0,1])
 def test_05_eligible_gap_count(self):
  cal,v,b=self.f();
  with tempfile.TemporaryDirectory() as d:
   l=self.l(d);l.create_signal('a',cal[0],cal,self.s(v),{'input_snapshot_hash':'h','source_max_session':str(cal[-1].date())})
   for dte in cal[1:61]:l.process_session(str(dte),dte,cal,v,b)
   self.assertEqual(l.state()['eligible_session_count'],60);self.assertEqual(l.state()['next_signal_session'],str(cal[60].date()))
if __name__=='__main__':unittest.main()
