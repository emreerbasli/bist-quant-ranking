from __future__ import annotations
import json,sys,unittest
from pathlib import Path
import pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import exp_final_001 as final
class ParetoDecisionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=json.loads(final.C.read_text());cls.s=json.loads((final.R/'EXP-FINAL-001_summary.json').read_text());cls.d=pd.read_csv(final.R/'EXP-FINAL-001_dimensions.csv');cls.h=pd.read_csv(final.R/'EXP-FINAL-001_evidence_hashes.csv')
 def test_all_cited_artifacts_exist_and_hash(self):
  for r in self.h.itertuples(index=False):self.assertEqual(final.sha(final.RESEARCH/r.path),r.sha256)
 def test_no_fit_or_portfolio_execution_in_decision_script(self):
  src=Path(final.__file__).read_text();self.assertNotIn('.fit(',src);self.assertNotIn('simulate(',src);self.assertNotIn('LGBMRegressor',src)
 def test_no_numeric_score(self): self.assertTrue(self.c['pareto']['no_numeric_score']);self.assertNotIn('score',self.d.columns)
 def test_only_frozen_evidence(self): self.assertEqual(self.c['evidence_only'],['EXP-MODEL-001','EXP-PORT-001','EXP-ROBUST-001']);self.assertEqual(set(self.d.architecture),set(final.ARCHS))
 def test_pareto_rules_and_result(self): self.assertEqual(self.s['dominance'],'BOTH NON-DOMINATED');self.assertEqual(self.s['decision'],'BOTH FINALISTS CARRIED FORWARD')
 def test_no_hard_rejection(self): self.assertFalse(self.d.hard_rejection.any());self.assertTrue(self.d.carry_forward.all())
 def test_ensemble_is_assessment_only(self): self.assertEqual(self.s['ensemble_justification'],'YES');self.assertIn('ensemble_backtest',self.c['no_new_computation'])
 def test_freeze_readiness_and_production_scope(self): self.assertEqual(set(self.d.freeze_readiness),{'READY WITH CAVEATS'});self.assertFalse(self.c['production_writes_allowed'])
if __name__=='__main__':unittest.main()
