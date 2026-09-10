"""
scratch/profile_pipeline.py
"""
import sys
import time
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

from scratch.run_faz_c_walk_forward_test import yukle_veriler, hizli_pit, hesapla_mom, getir_tcmb_reel_faiz
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline

fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
pipeline = LGBMRankingPipeline()
t0 = pd.Timestamp("2022-06-01")

t_start = time.perf_counter()
t1 = time.perf_counter()
reel_faiz = getir_tcmb_reel_faiz(t0, tufe_aylik)
sub_u = seri_usdtry[seri_usdtry.index <= t0]
mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0
t_macro = time.perf_counter() - t1

t_pit_sum = 0
t_mom_sum = 0
t_loop_start = time.perf_counter()
satirlar = []
for s in sorted(fiyat_dict.keys()):
    t_p0 = time.perf_counter()
    curr, _ = hizli_pit(pit_bellek, s, t0)
    t_pit_sum += (time.perf_counter() - t_p0)
    if not curr:
        continue
    is_bank = bool(curr.get("is_bank", False))
    sektor = cfg.HISSE_SEKTOR.get(s, "XBANK.IS" if is_bank else "XUSIN.IS")

    t_m0 = time.perf_counter()
    mom = hesapla_mom(fiyat_dict[s], t0)
    t_mom_sum += (time.perf_counter() - t_m0)

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

t_loop = time.perf_counter() - t_loop_start

print(f"Macro time: {t_macro*1000:.2f} ms")
print(f"Total loop time: {t_loop*1000:.2f} ms")
print(f"  - PIT lookup time: {t_pit_sum*1000:.2f} ms")
print(f"  - Momentum time:   {t_mom_sum*1000:.2f} ms")
