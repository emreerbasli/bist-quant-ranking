from __future__ import annotations
import json,sys,unittest
from pathlib import Path
import numpy as np
import pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import exp_ens_001 as ens
class EnsembleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=json.loads(ens.C.read_text());cls.s=json.loads((ens.R/'EXP-ENS-001_summary.json').read_text());cls.cov=pd.read_csv(ens.R/'EXP-ENS-001_coverage.csv');cls.port=pd.read_csv(ens.R/'EXP-ENS-001_portfolio_outer.csv')
 def test_parent_hashes_unchanged(self): self.assertEqual(ens.sha(ens.mm.CONTRACT_PATH),self.c['parent_contract_hashes']['model']);self.assertEqual(ens.sha(ens.pp.C),self.c['parent_contract_hashes']['portfolio'])
 def test_exact_50_50_formula_and_no_tuning(self): self.assertEqual(self.c['weights'],{'LGBM_REGRESSION':.5,'LAMBDAMART':.5});self.assertFalse(self.c['weight_tuning']);self.assertEqual(self.c['alternate_weights'],[])
 def test_rank_normalization_deterministic(self):
  x=pd.DataFrame({'signal_date':pd.to_datetime(['2020-01-01']*3)});a=np.array([3.,1.,2.]);np.testing.assert_array_equal(ens.rank_scores(x,a),ens.rank_scores(x.copy(),a.copy()))
 def test_ensemble_arithmetic(self):
  x=pd.DataFrame({'signal_date':pd.to_datetime(['2020-01-01']*3)});a=np.array([3.,1.,2.]);b=np.array([1.,2.,3.]);np.testing.assert_allclose(ens.ensemble(x,a,b),.5*ens.rank_scores(x,a)+.5*ens.rank_scores(x,b))
 def test_same_date_alignment_no_imputation(self): self.assertTrue((self.cov.observations_lost==0).all());self.assertIn('never impute',self.c['alignment']['missing'])
 def test_portfolio_contract_unchanged(self): self.assertEqual(self.c['portfolio']['k'],10);self.assertEqual(self.c['portfolio']['costs_bps'],[0,30,50,100]);self.assertEqual(self.c['portfolio']['delay_sessions'],[0,1,2])
 def test_cost_monotonicity_failure_is_not_hidden(self): self.assertFalse(self.s['cost_monotonic']);self.assertEqual(self.s['ensemble'],'REJECT');self.assertEqual(self.s['phase_k_gate'],'FAIL')
 def test_daily_nav(self):
  x=pd.read_csv(ens.R/'EXP-ENS-001_portfolio_outer.csv');self.assertTrue(np.isfinite(x.net_return).all());self.assertTrue((ens.R/'EXP-ENS-001_portfolio_summary.csv').exists())
 def test_no_weight_search_or_stacking(self): self.assertIn('weight_search',self.c['forbidden']);self.assertIn('stacking',self.c['forbidden'])
 def test_production_scope(self): self.assertFalse(self.c['production_writes_allowed'])
if __name__=='__main__':unittest.main()
