from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
import pandas as pd
RESEARCH=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RESEARCH))
import forward_infrastructure_001r3 as fw
from runner_data_sources import CanonicalRunnerDataSources,SandboxRunnerDataSources
import run_frozen_shadow as runner

def fixture(root, bad=None):
 root=Path(root);root.mkdir(parents=True,exist_ok=True);idx=pd.bdate_range('2026-01-02',periods=4)
 for sym in ['XU100.IS','AAA.IS']:
  x=pd.DataFrame({'research_open':[100,101,102,103],'research_close':[101,102,103,104],'raw_close':[101,102,103,104],'volume':[1000]*4,'trading_eligible':[True]*4,'price_quality':['RESOLVED']*4},index=idx);x.index.name='date'
  if bad:x[bad]=1
  x.to_parquet(root/('IDX_XU100_IS.parquet' if sym=='XU100.IS' else 'AAA_IS.parquet'))

class DataBoundaryTests(unittest.TestCase):
 def test_01_canonical_default(self):
  self.assertIsInstance(CanonicalRunnerDataSources(),CanonicalRunnerDataSources);self.assertTrue(CanonicalRunnerDataSources().symbols())
 def test_02_sandbox_load_benchmark(self):
  with tempfile.TemporaryDirectory() as d:
   fixture(d);s=SandboxRunnerDataSources(d);self.assertIn('AAA.IS',s.symbols());self.assertEqual(len(s.benchmark()),4)
 def test_03_provenance_and_source_max(self):
  with tempfile.TemporaryDirectory() as d:
   fixture(d);s=SandboxRunnerDataSources(d);v={'AAA.IS':s.view('AAA.IS')};b=s.benchmark();m=fw.snapshot_manifest(s.input_paths(['AAA.IS']),v,b,'SANDBOX_TEST',d);self.assertTrue(all(x['path'].startswith('sandbox://') for x in m['price_inputs']));p=s.input_paths(['AAA.IS'])[0];self.assertEqual(m['price_inputs'][0]['sha256'],hashlib.sha256(p.read_bytes()).hexdigest());self.assertEqual(m['source_max_session'],'2026-01-07');self.assertEqual(m['input_snapshot_hash'],fw.snapshot_manifest(s.input_paths(['AAA.IS']),v,b,'SANDBOX_TEST',d)['input_snapshot_hash'])
 def test_04_snapshot_changes_and_escape(self):
  with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
   fixture(d);s=SandboxRunnerDataSources(d);v={'AAA.IS':s.view('AAA.IS')};b=s.benchmark();a=fw.snapshot_manifest(s.input_paths(['AAA.IS']),v,b,'SANDBOX_TEST',d)['input_snapshot_hash'];Path(d,'AAA_IS.parquet').write_bytes(Path(d,'AAA_IS.parquet').read_bytes()+b'x');z=fw.snapshot_manifest(s.input_paths(['AAA.IS']),v,b,'SANDBOX_TEST',d)['input_snapshot_hash'];self.assertNotEqual(a,z)
   with self.assertRaises(fw.ForwardIntegrityError):fw.snapshot_manifest([Path(out)/'x'],v,b,'SANDBOX_TEST',d)
 def test_05_missing_and_forbidden(self):
  with tempfile.TemporaryDirectory() as d:
   s=SandboxRunnerDataSources(d)
   with self.assertRaises(FileNotFoundError):s.view('AAA.IS')
   fixture(d,'mom_63')
   with self.assertRaises(ValueError):s.view('AAA.IS')
 def test_06_official_override_refused(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(fw.ForwardIntegrityError) as e:runner.run('RC-LGBMR-001','2026-09-18',test_data_root=d)
   self.assertEqual(str(e.exception),'TEST_DATA_SOURCE_OVERRIDE_FORBIDDEN')
 def test_07_candidate_hashes_and_logs(self):
  expected={'RC-LGBMR-001':'350fb049f7f2e392a62fc89516acbb00676e1b1ef922559fc2f1dc3bfe9e81f6','RC-LAMBDAMART-001':'4744a5109bc3f97b11f2ef6f890cdded5672fd5a25a9a8252f9e1ad7fb31d849'}
  for c,h in expected.items():self.assertEqual(fw.sha(fw.FROZEN/c/'model.joblib'),h);self.assertTrue(all((fw.FROZEN/c/n).stat().st_size==0 for n in ['shadow_signals.jsonl','shadow_portfolio.jsonl','shadow_operational_events.jsonl']))
