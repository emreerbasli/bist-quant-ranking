from __future__ import annotations
import json,sys,unittest
from pathlib import Path
import numpy as np
import pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import exp_port_001 as port
class PortfolioControlTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=json.loads(port.C.read_text());cls.out=pd.read_csv(port.R/'EXP-PORT-001_outer_metrics.csv');cls.nav=pd.read_csv(port.R/'EXP-PORT-001_daily_nav.csv');cls.trade=pd.read_csv(port.R/'EXP-PORT-001_trades.csv');cls.classes=pd.read_csv(port.R/'EXP-PORT-001_classification.csv')
 def test_phase_mapping_prevents_duplicate_g(self): self.assertEqual(self.c['phase_mapping']['phase_g'],'SUBSTANTIVELY_SATISFIED_BY_EXP_MODEL_001_LOCKED_NESTED_OUTER_EVIDENCE')
 def test_only_frozen_finalists(self): self.assertEqual(set(self.out.architecture),set(port.ARCHS));self.assertEqual(set(self.c['features']),set(port.m.FEATURES))
 def test_no_forbidden_alpha_redesign(self): self.assertIn('alpha_retraining',self.c['forbidden']);self.assertFalse(self.c['production_writes_allowed'])
 def test_k_is_sensitivity_not_outer_selection(self): self.assertEqual(self.c['portfolio']['k_policy'],'SENSITIVITY_ONLY_NO_OUTER_SELECTION');self.assertEqual(set(self.out[self.out.case.eq('K_SENSITIVITY')].k),{5,10,15,20})
 def test_turnover_is_two_sided(self): self.assertIn('two_sided',self.c['turnover']['definition']);self.assertTrue((self.trade.turnover_two_sided_notional.dropna()>=0).all())
 def test_cost_monotonicity(self):
  x=self.out[(self.out.case=='K_SENSITIVITY')&(self.out.k==10)].groupby(['architecture','outer_fold','cost_bps']).net_return.mean().unstack()
  self.assertTrue(((x[0]>=x[30])&(x[30]>=x[50])&(x[50]>=x[100])).all())
 def test_terminal_liquidation_is_charged(self):
  x=self.trade[self.trade.get('terminal_liquidation',False).fillna(False)]
  self.assertGreater(len(x),0);self.assertTrue((x.cost_try>=0).all())
 def test_no_negative_cash_or_impossible_fills(self):
  self.assertGreaterEqual(self.nav.cash_weight.min(),-1e-12);self.assertTrue((self.out.filled_trades<=self.out.attempted_trades).all())
 def test_volume_and_adv_are_required(self): self.assertIn('positive-volume',self.c['liquidity']['adv']);self.assertTrue((self.out.adv_missing_checks>=0).all())
 def test_capacity_metrics_present(self):
  for col in ('order_adv_median','order_adv_p90','order_adv_p95','order_adv_max','order_adv_gt_10pct'): self.assertIn(col,self.out)
 def test_delay_stress_is_fixed_small_set(self): self.assertEqual(self.c['execution']['delay_sensitivity_sessions'],[0,1,2]);self.assertEqual(set(self.out[self.out.case.eq('DELAY')].delay_sessions),{1,2})
 def test_daily_nav_integrity(self):
  self.assertTrue(np.isfinite(self.nav.nav).all());self.assertFalse(self.nav.duplicated(['outer_fold','architecture','case','k','cost_bps','delay_sessions','capital_try','adv_limit_pct','date']).any())
 def test_final_classification_and_costs(self): self.assertEqual(set(self.classes.classification),{'VIABLE'});self.assertTrue(self.classes.cost_monotonic.all())
if __name__=='__main__':unittest.main()
