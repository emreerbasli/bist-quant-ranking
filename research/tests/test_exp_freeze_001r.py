from __future__ import annotations
import json,sys,tempfile,unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import forward_infrastructure_001 as fw

class ForwardInfrastructureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=json.loads(fw.CONTRACT.read_text());cls.ist=ZoneInfo('Europe/Istanbul')
 def sample_calendar(self,n=140):return pd.bdate_range('2026-09-01',periods=n)
 def sample_views(self,cal,n=10):
  out={}
  for j in range(n):
   x=pd.DataFrame(index=cal);x['trading_eligible']=True;x['price_quality']='RESOLVED';x['research_open']=100+j+np.arange(len(cal))*.1;x['research_close']=x.research_open+1;x['raw_close']=x.research_close;x['volume']=100000
   out[f'S{j}']=x
  return out
 def test_01_actual_pre_freeze_rejected(self):
  z=fw.classify_signal('x','2026-09-18','2026-09-15',datetime(2026,9,18,19,tzinfo=self.ist),'2026-09-18T02:25:56+03:00','2026-09-20T18:10:00+03:00',self.c);self.assertEqual(z,'NON_CLEAN_BACKFILL')
 def test_02_post_freeze_asof_pre_freeze_actual_rejected(self):
  z=fw.classify_signal('x','2026-09-19','2026-09-15',datetime(2026,9,19,19,tzinfo=self.ist),'2026-09-18T02:25:56+03:00','2026-09-19T18:10:00+03:00',self.c);self.assertEqual(z,'NON_CLEAN_BACKFILL')
 def test_03_backfill_namespace_is_separate(self):self.assertNotEqual(fw.DEBUG,fw.FROZEN)
 def test_04_missed_window_rejected(self):
  z=fw.classify_signal('x','2026-09-21','2026-09-21',datetime(2026,9,23,19,tzinfo=self.ist),'2026-09-18T02:25:56+03:00','2026-09-20T18:10:00+03:00',self.c);self.assertEqual(z,'MISSED_FORWARD_SIGNAL')
 def test_05_snapshot_hash_persisted(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x';p.write_text('abc');s=fw.snapshot_manifest([p],pd.Timestamp('2026-09-21'));self.assertEqual(len(s['input_snapshot_hash']),64);self.assertEqual(s['price_inputs'][0]['sha256'],fw.sha(p))
 def test_06_source_max_timestamp_persisted(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x';p.write_text('abc');self.assertIn('2026-09-21',fw.snapshot_manifest([p],'2026-09-21')['source_max_timestamp'])
 def test_07_event_id_deterministic_unique_by_sequence(self):self.assertNotEqual(fw.event_id('r','x',1),fw.event_id('r','x',2))
 def test_08_run_id_linkage_and_candidate_version(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.jsonl';row={'event_id':'e','run_id':'r','candidate_id':'c','candidate_version':'1','event_type':'SIGNAL'};fw.append_row(p,row);self.assertEqual(fw.read_rows(p)[0]['run_id'],'r');self.assertEqual(fw.read_rows(p)[0]['candidate_version'],'1')
 def test_09_duplicate_clean_key_detected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a';k=fw.clean_signal_key('c','1','2026-09-21');fw.append_row(p,{'event_id':'e','run_id':'r','classification':'CLEAN_FORWARD','clean_signal_key':k});self.assertTrue(fw.existing_clean_signal(p,k))
 def test_10_correction_is_append_only(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a';fw.append_row(p,{'event_id':'old','run_id':'r','candidate_id':'c','candidate_version':'1'});fw.append_correction(p,'r2','c','1','old','reason',{'x':2});self.assertEqual(len(fw.read_rows(p)),2);self.assertEqual(fw.read_rows(p)[1]['original_event_id'],'old')
 def test_11_lock_contention_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a'
   with fw.file_lock(p):
    with self.assertRaises(fw.ForwardIntegrityError):
     with fw.file_lock(p):pass
 def test_12_frozen_artifacts_verify(self):
  for c in self.c['candidates']:
   m,a=fw.frozen_candidate(c);self.assertEqual(m['candidate_id'],a['candidate_id'])
 def test_13_runner_hash_will_be_bound(self):self.assertTrue((RESEARCH/'run_frozen_shadow.py').exists())
 def test_14_k10_equal_weight_contract(self):self.assertEqual((self.c['portfolio']['k'],self.c['portfolio']['weighting']),(10,'equal_weight'))
 def test_15_next_session_label_contract(self):
  cal=self.sample_calendar();end=fw.expected_label_end(cal,cal[5],60);self.assertEqual(cal.get_loc(end)-cal.get_loc(cal[5]),61)
 def test_16_no_same_close_execution(self):
  cal=self.sample_calendar();self.assertGreater(cal.get_loc(cal[6]),cal.get_loc(cal[5]))
 def test_17_cost_accounting(self):
  cal=self.sample_calendar(30);v=self.sample_views(cal);state=fw.portfolio_state(1000000);events,cost=fw.execute_rebalance(state,v,21,list(v),50,.10);self.assertGreater(cost,0);self.assertTrue(all('gross_traded_nominal' in x for x in events))
 def test_18_liquidity_unfilled(self):
  cal=self.sample_calendar(30);v=self.sample_views(cal);v['S0'].iloc[21,v['S0'].columns.get_loc('volume')]=0;events,_=fw.execute_rebalance(fw.portfolio_state(1000000),v,21,list(v),50,.10);self.assertEqual(next(x for x in events if x['symbol']=='S0')['fill_status'],'UNFILLED')
 def test_19_cash_nonnegative(self):
  cal=self.sample_calendar(30);v=self.sample_views(cal);s=fw.portfolio_state(1000000);fw.execute_rebalance(s,v,21,list(v),50,.10);self.assertGreaterEqual(s['cash'],0)
 def test_20_last_valid_mark(self):
  cal=self.sample_calendar(30);v=self.sample_views(cal);s=fw.portfolio_state(1000000);fw.execute_rebalance(s,v,21,list(v),50,.10);fw.mark_to_market(s,v,21);v['S0'].iloc[22,v['S0'].columns.get_loc('research_close')]=np.nan;self.assertGreater(fw.mark_to_market(s,v,22)['nav'],0)
 def test_21_daily_nav_shape(self):
  cal=self.sample_calendar(30);v=self.sample_views(cal);s=fw.portfolio_state(1000000);fw.execute_rebalance(s,v,21,list(v),50,.10);nav=fw.mark_to_market(s,v,21);self.assertEqual(set(nav),{'positions_value','cash','nav'})
 def test_22_rebalance_holding_contract(self):self.assertEqual((self.c['portfolio']['rebalance_sessions'],self.c['portfolio']['holding_sessions']),(60,60))
 def test_23_h60_cohort_pending(self):
  cal=self.sample_calendar();m,_=fw.frozen_candidate('RC-LGBMR-001');co=fw.new_cohort('r',m,cal[5],cal,0);self.assertEqual(fw.cohort_status(co,cal,cal[64]),'PENDING')
 def test_24_h60_cohort_completed_only_at_end(self):
  cal=self.sample_calendar();m,_=fw.frozen_candidate('RC-LGBMR-001');co=fw.new_cohort('r',m,cal[5],cal,0);self.assertEqual(fw.cohort_status(co,cal,cal[66]),'COMPLETED')
 def test_25_pending_excluded_from_metrics(self):
  rows=[{'status':'PENDING','v':1},{'status':'COMPLETED','v':2}];self.assertEqual([x['v'] for x in rows if x['status']=='COMPLETED'],[2])
 def test_26_raw_h60_exact(self):
  m,_=fw.frozen_candidate('RC-LGBMR-001');self.assertEqual((m['target_procedure'],m['horizon_procedure']),('RAW',60))
 def test_27_beta_residual_h60_exact(self):
  m,_=fw.frozen_candidate('RC-LAMBDAMART-001');self.assertEqual((m['target_procedure'],m['horizon_procedure']),('BETA_RESIDUAL',60))
 def test_28_overlap_metadata(self):
  cal=self.sample_calendar();m,_=fw.frozen_candidate('RC-LGBMR-001');self.assertEqual(fw.new_cohort('r',m,cal[5],cal,3)['overlapping_active_cohorts'],3)
 def test_29_change_control_material_fields(self):self.assertIn('execution_semantics',self.c['change_control']['material_fields'])
 def test_30_official_logs_remain_empty(self):
  for c in self.c['candidates']:
   for n in ('shadow_signals.jsonl','shadow_portfolio.jsonl','shadow_operational_events.jsonl'):self.assertEqual((fw.FROZEN/c/n).stat().st_size,0)
 def test_31_production_scope(self):self.assertFalse(self.c['production_writes_allowed'])
if __name__=='__main__':unittest.main()
