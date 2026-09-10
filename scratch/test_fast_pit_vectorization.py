"""
scratch/test_fast_pit_vectorization.py
"""
import sys
import time
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scratch.run_faz_c_walk_forward_test import yukle_veriler, hizli_pit
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline

fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
pipeline = LGBMRankingPipeline()

t0 = pd.Timestamp("2022-06-01")

# Baseline from pipeline
t_start = time.perf_counter()
df_orig = pipeline.compute_features(t0, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
df_orig_ranked = pipeline.rank_stocks(df_orig)
time_orig = time.perf_counter() - t_start

print(f"Original pipeline took: {time_orig:.3f}s")
print(f"Top 5 stocks: {df_orig_ranked.head(5)['sembol'].tolist()}")
