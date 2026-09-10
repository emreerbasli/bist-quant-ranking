"""
scratch/time_feature_computation.py
"""
import sys
import time
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scratch.run_faz_c_walk_forward_test import yukle_veriler
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline

fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
pipeline = LGBMRankingPipeline()

t0 = pd.Timestamp("2022-06-01")
start = time.perf_counter()
df_f = pipeline.compute_features(t0, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
df_r = pipeline.rank_stocks(df_f)
elapsed = time.perf_counter() - start

print(f"Time for 1 date: {elapsed*1000:.2f} ms. Stocks ranked: {len(df_r)}")
