"""
scratch/analyze_faz_c_factor_ic.py
==================================
FAKTÖR BİLGİ KATSAYISI (INFORMATION COEFFICIENT - IC) VE MONOTONLUK ANALİZİ
---------------------------------------------------------------------------
Her bir faktörün 60 günlük ileriye dönük getiri ile Spearman Rank Korelasyonu (IC):
  - Erken Dönem (2018-2021) IC
  - Geç Dönem (2022-2026) IC
  - Hangi faktörler OOS'ta ayakta kalıyor, hangileri aşırı uyum / gürültü yaratıyor?
"""

import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np
from scipy.stats import spearmanr

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

from scratch.run_faz_c_walk_forward_test import yukle_veriler, hizli_pit, hesapla_mom

def analyze_ic():
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    tarihler_60 = pd.date_range("2018-09-01", "2026-08-01", freq="3MS")
    hisseler = sorted(fiyat_dict.keys())

    records = []

    for i in range(len(tarihler_60) - 1):
        t0, t1 = tarihler_60[i], tarihler_60[i + 1]

        rets = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        mevcut = [s for s in hisseler if s in rets]
        if len(mevcut) < 32:
            continue

        donem_tipi = "IS (2018-2021)" if t0 < pd.Timestamp("2022-01-01") else "OOS (2022-2026)"

        rows = []
        for s in mevcut:
            curr, prev = hizli_pit(pit_bellek, s, t0)
            if not curr:
                continue
            mom = hesapla_mom(fiyat_dict[s], t0)
            pb = curr.get("pb", np.nan)
            roe = curr.get("roe", np.nan)
            roa = curr.get("roa", np.nan)
            cfo = curr.get("cfo", 0.0) or 0.0
            net_kar = curr.get("net_kar", 0.0) or 0.0
            fcf_verim = curr.get("fcf_verim", np.nan)
            ihracat = curr.get("ihracat_orani", np.nan)
            ebitda = curr.get("ebitda", 1.0) or 1.0
            net_borc = curr.get("net_borc", 0.0) or 0.0

            # F-Score bileşenleri
            cfo_accrual = 1.0 if cfo > net_kar else 0.0
            roa_pos = 1.0 if roa > 0 else 0.0
            f_score = cfo_accrual + roa_pos

            rows.append({
                "sembol": s, "fwd_ret": rets[s],
                "neg_pb": -pb if pd.notna(pb) else np.nan,
                "roe": roe if pd.notna(roe) else np.nan,
                "mom": mom,
                "fcf_verim": fcf_verim if pd.notna(fcf_verim) else np.nan,
                "ihracat": ihracat if pd.notna(ihracat) else np.nan,
                "cfo_accrual": cfo_accrual,
                "f_score": f_score,
                "borc_ebitda": -net_borc / max(1.0, abs(ebitda))
            })

        df_p = pd.DataFrame(rows)
        factors = ["neg_pb", "roe", "mom", "fcf_verim", "ihracat", "cfo_accrual", "f_score", "borc_ebitda"]

        ic_dict = {"t": t0, "donem": donem_tipi}
        for f in factors:
            sub = df_p[[f, "fwd_ret"]].dropna()
            if len(sub) >= 15:
                corr, _ = spearmanr(sub[f], sub["fwd_ret"])
                ic_dict[f] = corr
            else:
                ic_dict[f] = np.nan
        records.append(ic_dict)

    df_ic = pd.DataFrame(records)

    print("\n" + "=" * 95)
    print("FAKTÖR BİLGİ KATSAYISI (SPEARMAN IC) — IS vs OOS KARŞILAŞTIRMASI")
    print("=" * 95)
    print(f"{'Faktör Adı':<20} | {'Tüm Örneklem IC':<16} | {'IS IC (2018-2021)':<18} | {'OOS IC (2022-2026)':<18} | {'IC IR (Stabilite)':<18}")
    print("-" * 95)

    factors = ["neg_pb", "roe", "mom", "fcf_verim", "ihracat", "cfo_accrual", "f_score", "borc_ebitda"]
    for f in factors:
        mean_all = df_ic[f].mean()
        std_all  = df_ic[f].std()
        ir_all   = mean_all / std_all if std_all > 1e-6 else 0.0

        mean_is  = df_ic[df_ic["donem"] == "IS (2018-2021)"][f].mean()
        mean_oos = df_ic[df_ic["donem"] == "OOS (2022-2026)"][f].mean()

        print(f"{f:<20} | {mean_all:>14.3f}   | {mean_is:>16.3f}   | {mean_oos:>16.3f}   | {ir_all:>16.2f}")

if __name__ == "__main__":
    analyze_ic()
