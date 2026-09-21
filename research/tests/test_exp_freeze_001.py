from __future__ import annotations
import hashlib,json,sys,unittest
from pathlib import Path
import joblib
import pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import exp_freeze_001 as freeze
class FreezeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=json.loads(freeze.C.read_text());cls.f=freeze.F
  cls.combined=json.loads((cls.f/'EXP-FREEZE-001_combined_manifest.json').read_text())
  cls.items={cid:json.loads((cls.f/cid/'candidate_manifest.json').read_text()) for cid in cls.c['candidates']}
 def test_candidate_ids_and_status(self):
  self.assertEqual(set(self.items),{'RC-LGBMR-001','RC-LAMBDAMART-001'})
  self.assertTrue(all(x['status']==self.c['status'] for x in self.items.values()))
 def test_locked_o4_procedures(self):
  self.assertEqual((self.items['RC-LGBMR-001']['target_procedure'],self.items['RC-LGBMR-001']['horizon_procedure']),('RAW',60))
  self.assertEqual((self.items['RC-LAMBDAMART-001']['target_procedure'],self.items['RC-LAMBDAMART-001']['horizon_procedure']),('BETA_RESIDUAL',60))
 def test_global_horizon_is_not_rewritten(self): self.assertEqual(self.c['target_horizon']['global_winner'],'NOT_FIXED')
 def test_artifact_hashes_match(self):
  for cid,x in self.items.items():self.assertEqual(freeze.sha(self.f/cid/'model.joblib'),x['model_sha256'])
 def test_fitted_artifacts_are_candidate_specific(self):
  for cid,x in self.items.items():
   a=joblib.load(self.f/cid/'model.joblib');self.assertEqual(a['candidate_id'],cid);self.assertEqual(a['target_family'],x['target_procedure'])
 def test_schema_and_formulae_are_frozen(self):
  for x in self.items.values():
   self.assertEqual([f['name'] for f in x['features']],self.c['features']['columns'])
   self.assertTrue(all(f['formula'] for f in x['features']))
 def test_training_is_pre_cutoff(self):
  for x in self.items.values():self.assertLessEqual(pd.Timestamp(x['training_last_label_end']),pd.Timestamp(x['training_cutoff']))
 def test_seeds_and_determinism(self):
  self.assertTrue(all(t['deterministic_predictions'] and t['top10_reproducible'] for t in self.combined['tests']))
  self.assertEqual(self.items['RC-LGBMR-001']['seed_policy']['values'],[11,29,47])
 def test_portfolio_contract_is_locked(self):
  p=self.c['portfolio'];self.assertEqual((p['k'],p['weighting'],p['rebalance_sessions'],p['holding_sessions']),(10,'equal_weight',60,60))
 def test_ensemble_is_excluded(self): self.assertEqual(self.combined['ensemble_status'],'REJECTED / EXCLUDED')
 def test_clean_forward_timestamp_and_timezone(self):
  self.assertEqual(self.combined['timezone'],'Europe/Istanbul');self.assertTrue(self.combined['freeze_timestamp'].endswith('+03:00'))
  self.assertEqual(self.combined['clean_forward_start'],self.combined['freeze_timestamp'])
 def test_logs_are_initialized_and_empty(self):
  for cid in self.items:
   for name in ['shadow_signals.jsonl','shadow_portfolio.jsonl','shadow_operational_events.jsonl']:
    self.assertTrue((self.f/cid/name).exists());self.assertEqual((self.f/cid/name).read_text(), '')
 def test_shadow_runner_is_append_only_and_blocks_retroactive(self):
  s=(RESEARCH/'run_frozen_shadow.py').read_text();infra=(RESEARCH/'forward_infrastructure_001.py').read_text()
  self.assertIn('validate_activation',s);self.assertIn('NON_CLEAN_BACKFILL',s);self.assertIn("path.open('a'",infra);self.assertIn('LOCK_UNAVAILABLE',infra)
 def test_data_and_code_hashes_present(self):
  for x in self.items.values():
   self.assertEqual(len(x['code_hashes']['research\\contracts\\exp_model_001.json']),64);self.assertEqual(len(x['data_hashes']['feature_input_dataframe_sha256']),64)
 def test_production_scope(self): self.assertFalse(self.combined['production_writes_allowed'])
if __name__=='__main__':unittest.main()
