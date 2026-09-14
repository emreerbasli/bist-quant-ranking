"""
scratch/test_v6_formulations.py
Exploratory test for Reel PEG formulation & Monotonic constraints on BIST dataset.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg
from models.v3_ranking.data_loader import yukle_veriler, hizli_pit, hesapla_mom, getir_tcmb_reel_faiz
from models.v3_ranking.ranking_pipeline import hesapla_sektor_zscore
from scratch.faz1_ic_tarama import extract_candidate_features

fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
t = pd.Timestamp("2024-03-01")
hisseler = sorted(fiyat_dict.keys())

rows = []
for s in hisseler:
    curr, _ = hizli_pit(pit_bellek, s, t)
    if not curr:
        continue
    is_bank = bool(curr.get("is_bank", False))
    sektor = cfg.HISSE_SEKTOR.get(s, "XBANK.IS" if is_bank else "XUSIN.IS")
    pb = curr.get("pb", np.nan)
    net_kar = curr.get("net_kar", 0.0) or 0.0
    cand = extract_candidate_features(t, s, fiyat_dict[s], seri_usdtry, pit_bellek.get(s, []), tufe_aylik)
    reel_eps = cand.get("reel_eps_growth", np.nan)
    rows.append({
        "sembol": s, "sektor": sektor, "is_bank": is_bank, "pb": pb, "net_kar": net_kar, "reel_eps": reel_eps
    })

df = pd.DataFrame(rows)
df["z_pb_raw"] = hesapla_sektor_zscore(df, "pb", min_grup=4).fillna(0.0) # raw z-score of PB (higher = expensive)
df["z_pb_value"] = -df["z_pb_raw"] # value z-score (higher = cheap)

# Formulation 1: Classical PEG using raw PB / reel_eps
# If reel_eps > 0.01 and net_kar > 0 -> pb / reel_eps
# If reel_eps <= 0.01 or net_kar <= 0 -> penalty ceiling
p_ceiling = 100.0
df["peg_raw"] = np.where(
    (df["reel_eps"] > 0.01) & (df["net_kar"] > 0) & (df["pb"] > 0),
    df["pb"] / np.clip(df["reel_eps"], 0.01, 2.0),
    p_ceiling
)
df["peg_raw"] = df["peg_raw"].clip(0.0, p_ceiling)

# Formulation 2: User's literal suggestion using z_pb / reel_eps
# Note: z_pb can be negative or positive.
# If we do: z_pb_raw (higher = more expensive PB) / max(0.01, reel_eps)
# Or: Sektörel z-skor of peg_raw
df["z_reel_peg"] = hesapla_sektor_zscore(df, "peg_raw", min_grup=4).fillna(0.0)

print(df[["sembol", "pb", "reel_eps", "peg_raw", "z_reel_peg"]].dropna().head(20))
print("\nSummary of peg_raw:")
print(df["peg_raw"].describe())
print("\nSummary of z_reel_peg:")
print(df["z_reel_peg"].describe())
