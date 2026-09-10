"""
scratch/test_vectorized_match.py
"""
import sys
import time
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

from scratch.run_faz_c_walk_forward_test import yukle_veriler, getir_tcmb_reel_faiz
from scratch.run_lockbox_evaluation import hesapla_sektor_zscore
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline

fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
pipeline = LGBMRankingPipeline()

# Align all prices into one DataFrame
df_prices = pd.DataFrame(fiyat_dict).sort_index().ffill()
trading_days = df_prices.index

# Pre-process PIT dates for binary search
pit_lookup = {}
for s, recs in pit_bellek.items():
    dates = np.array([r["gecerlilik_tarihi"] for r in recs])
    pit_lookup[s] = (dates, recs)

def fast_compute_features(t, df_prices, pit_lookup, seri_usdtry, tufe_aylik, hisseler):
    # Find t in trading_days
    idx = trading_days.searchsorted(t, side="right") - 1
    if idx < 273: # not enough price history for momentum
        return pd.DataFrame()

    reel_faiz = getir_tcmb_reel_faiz(t, tufe_aylik)
    sub_u = seri_usdtry[seri_usdtry.index <= t]
    mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
    mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

    p_curr = df_prices.iloc[idx]
    p_lag = df_prices.iloc[idx - 21]
    p_long = df_prices.iloc[idx - 252]

    satirlar = []
    for s in hisseler:
        if s not in pit_lookup:
            continue
        p_dates, recs = pit_lookup[s]
        p_idx = np.searchsorted(p_dates, t, side="right") - 1
        if p_idx < 0:
            continue
        curr = recs[p_idx]
        is_bank = bool(curr.get("is_bank", False))
        sektor = cfg.HISSE_SEKTOR.get(s, "XBANK.IS" if is_bank else "XUSIN.IS")

        # Momentum calculation
        f_lag = p_lag[s]
        f_long = p_long[s]
        if np.isnan(f_lag) or np.isnan(f_long) or f_lag <= 0 or f_long <= 0:
            mom = 0.0
        else:
            mom = float(np.clip((f_lag - f_long) / f_long, -0.9, 10.0))

        pb = curr.get("pb", np.nan)
        roe = curr.get("roe", np.nan)
        fcf_v = curr.get("fcf_verim", np.nan)
        net_b = curr.get("net_borc", 0.0) or 0.0
        ebit = curr.get("ebitda", 1.0) or 1.0
        borc_ebitda = -net_b / max(1.0, abs(ebit)) if not is_bank else np.nan

        satirlar.append({
            "sembol": s, "sektor": sektor, "is_bank": is_bank,
            "fcf_v": fcf_v, "roe": roe, "mom": mom,
            "borc_ebitda": borc_ebitda, "pb": pb
        })

    df = pd.DataFrame(satirlar)
    if df.empty:
        return df

    df["z_fcf"]  = hesapla_sektor_zscore(df, "fcf_v", min_grup=4).fillna(0.0)
    df["z_roe"]  = hesapla_sektor_zscore(df, "roe", min_grup=4).fillna(0.0)
    df["z_mom"]  = hesapla_sektor_zscore(df, "mom", min_grup=4).fillna(0.0)
    df["z_borc"] = hesapla_sektor_zscore(df, "borc_ebitda", min_grup=4).fillna(0.0)
    df["z_pb"]   = -hesapla_sektor_zscore(df, "pb", min_grup=4).fillna(0.0)

    df["reel_faiz"]  = reel_faiz
    df["usd_mom_60"] = mom_60_usd
    df["usd_mom_90"] = mom_90_usd
    return df

t0 = pd.Timestamp("2022-06-01")
t_start = time.perf_counter()
df_fast = fast_compute_features(t0, df_prices, pit_lookup, seri_usdtry, tufe_aylik, sorted(fiyat_dict.keys()))
df_fast_ranked = pipeline.rank_stocks(df_fast)
t_elapsed = time.perf_counter() - t_start

df_orig = pipeline.compute_features(t0, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
df_orig_ranked = pipeline.rank_stocks(df_orig)

print(f"Fast computation took: {t_elapsed*1000:.2f} ms")
print(f"Original pipeline Top-5: {df_orig_ranked.head(5)['sembol'].tolist()}")
print(f"Fast pipeline Top-5:     {df_fast_ranked.head(5)['sembol'].tolist()}")
diff = np.abs(df_orig_ranked["ml_score"] - df_fast_ranked["ml_score"]).max()
print(f"Max score diff: {diff:.10e}")
