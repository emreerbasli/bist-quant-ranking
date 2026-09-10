"""
scratch/check_baseline_scores.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Load rankings cache
cache_path = ROOT_DIR / "scratch" / "rankings_cache_2018_2025.joblib"
rankings_cache = joblib.load(cache_path)

all_scores = []
quarterly_means = []
quarterly_stds = []

for t, data in rankings_cache.items():
    sc = data["scores"]
    all_scores.extend(sc)
    quarterly_means.append(np.mean(sc))
    quarterly_stds.append(np.std(sc))

all_scores = np.array(all_scores)
print(f"Total historical stock-score observations: {len(all_scores)}")
print(f"Overall Score Mean: {np.mean(all_scores):.4f}, Std: {np.std(all_scores):.4f}")
print(f"Overall Score Min: {np.min(all_scores):.4f}, Max: {np.max(all_scores):.4f}")
print(f"Quarterly Batch Mean Scores -> Mean: {np.mean(quarterly_means):.4f}, Std: {np.std(quarterly_means):.4f}")
print(f"Quarterly Batch Std Scores  -> Mean: {np.mean(quarterly_stds):.4f}, Std: {np.std(quarterly_stds):.4f}")
