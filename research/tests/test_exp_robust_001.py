from __future__ import annotations
import json,sys,unittest
from pathlib import Path
import numpy as np
import pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import exp_robust_001 as rob
class RobustnessTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=json.loads(rob.C.read_text());cls.st=pd.read_csv(rob.R/'EXP-ROBUST-001_stress_metrics.csv');cls.summary=pd.read_csv(rob.R/'EXP-ROBUST-001_stress_summary.csv');cls.boot=pd.read_csv(rob.R/'EXP-ROBUST-001_bootstrap.csv');cls.cl=pd.read_csv(rob.R/'EXP-ROBUST-001_classification.csv')
 def test_frozen_hashes(self): self.assertEqual(rob.sha(rob.mm.CONTRACT_PATH),self.c['frozen']['model_contract_sha256']);self.assertEqual(rob.sha(rob.pp.C),self.c['frozen']['portfolio_contract_sha256'])
 def test_only_two_finalists(self): self.assertEqual(set(self.st.architecture),set(rob.ARCHS))
 def test_ablation_isolation(self):
  x=self.summary[self.summary.family.eq('ABLATION')];self.assertEqual(set(x.case),{f'WITHOUT_{z}' for z in rob.FEATURES});self.assertEqual(len(x),6)
 def test_no_feature_leakage_or_new_features(self): self.assertEqual(set(self.c['frozen']['features']),set(rob.FEATURES))
 def test_noise_reproducibility(self):
  x=pd.DataFrame({z:[1.,2.,3.] for z in rob.FEATURES});a=rob.noise_rows(x,rob.FEATURES,x,.01,1701);b=rob.noise_rows(x,rob.FEATURES,x,.01,1701);pd.testing.assert_frame_equal(a,b)
 def test_rank_noise_reproducibility(self):
  x=pd.DataFrame({'signal_date':pd.to_datetime(['2020-01-01']*3)});s=np.array([1.,2.,3.]);np.testing.assert_array_equal(rob.rank_noise(x,s,.1,[11,29,47]),rob.rank_noise(x,s,.1,[11,29,47]))
 def test_delay_and_liquidity_reused(self): self.assertEqual(self.c['delay_sessions'],[0,1,2]);self.assertEqual(self.c['liquidity_capacity']['capital_try'],[1_000_000,10_000_000,50_000_000])
 def test_leave_one_period_and_sector_outputs(self): self.assertTrue((rob.R/'EXP-ROBUST-001_leave_one_period_out.csv').exists());self.assertTrue((rob.R/'EXP-ROBUST-001_leave_one_sector_out.csv').exists())
 def test_concentration_math(self):
  x=pd.read_csv(rob.R/'EXP-ROBUST-001_concentration.csv');self.assertTrue(x.top1_abs_pnl_share.between(0,1).all());self.assertTrue((x.top1_abs_pnl_share<=x.top3_abs_pnl_share).all())
 def test_bootstrap_block_not_one(self): self.assertGreater(self.c['bootstrap']['block_length_signal_cohorts'],1);self.assertTrue((self.boot.block_length>1).all());self.assertEqual(set(self.boot.replications),{2000})
 def test_seed_policy_unchanged(self): self.assertEqual(self.c['seeds'],[11,29,47])
 def test_price_only_regimes(self): self.assertTrue(self.c['regimes']['macro_labels_forbidden']);self.assertTrue((rob.R/'EXP-ROBUST-001_price_regimes.csv').exists())
 def test_daily_nav_and_production_scope(self): self.assertFalse(self.c['production_writes_allowed']);self.assertTrue((rob.R/'EXP-PORT-001_daily_nav.csv').exists())
 def test_classification_allowed(self): self.assertTrue(set(self.cl.classification).issubset({'ROBUST','ROBUST WITH CAVEATS','FRAGILE','REJECTED'}))
if __name__=='__main__':unittest.main()
