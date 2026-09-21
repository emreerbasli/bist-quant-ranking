"""Narrow data boundary for the forward runner; no feature or model semantics live here."""
from pathlib import Path
import pandas as pd
import exp_tgt_001 as t1

class CanonicalRunnerDataSources:
 provider_id='LOCAL_RESEARCH_PRICE_VIEW'
 def symbols(self): return sorted(t1.symbol_from_path(p) for p in t1.BASE_VIEW.glob('*_IS.parquet') if p.stem not in {'IDX_XU100_IS','XU100_IS'})
 def view(self,symbol): return t1.load_view(symbol)
 def benchmark(self): return self.view('XU100.IS')
 def input_paths(self,symbols):
  out=[]
  for s in ['XU100.IS',*symbols]:
   o=t1.OVERLAY_VIEW/t1.file_name(s);out.append(o if o.exists() else t1.BASE_VIEW/t1.file_name(s))
  return out
class SandboxRunnerDataSources:
 provider_id='SANDBOX_TEST'
 forbidden={'mom_12_1','mom_63','vol_63','model_score','raw_score','rank','selected_top10','target','target_label'}
 def __init__(self,root): self.root=Path(root)
 def _path(self,s): return self.root/('IDX_XU100_IS.parquet' if s=='XU100.IS' else s.replace('.','_')+'.parquet')
 def view(self,symbol):
  p=self._path(symbol)
  if not p.exists():raise FileNotFoundError(p)
  x=pd.read_parquet(p)
  if self.forbidden & set(x.columns):raise ValueError('SANDBOX_PRECOMPUTED_INPUT_FORBIDDEN')
  return x.sort_index()
 def benchmark(self):return self.view('XU100.IS')
 def symbols(self):return sorted(p.stem.replace('_IS','.IS') for p in self.root.glob('*_IS.parquet') if p.stem not in {'IDX_XU100_IS','XU100_IS'})
 def input_paths(self,symbols):return [self._path(s) for s in ['XU100.IS',*symbols]]
