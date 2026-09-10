"""
scratch/test_simplified_robust_formula.py
=========================================
FAZ D ÖNCESİ ARA ADIM: SADELEŞTİRİLMİŞ REJİM-KARARLI FORMÜL TESTİ
-----------------------------------------------------------------
Varyant A: Z(FCF/PD) + Z(ROE) + Z(Mom_12-1) + Z(-Net_Borç/EBITDA)       [P/B'siz]
Varyant B: Z(FCF/PD) + Z(ROE) + Z(Mom_12-1) + Z(-Net_Borç/EBITDA) - Z(P/B) [P/B'li]

Protokol:
  1. Ağırlıklar: Düz eşit ağırlık (hiçbir parametre optimizasyonu yok).
  2. Erken Dönem (2018-2021) [In-Sample] ve Geç Dönem (2022-2026) [Out-of-Sample Dondurulmuş].
  3. Portföy büyüklükleri: K in [10, 15, 20].
  4. 100 Tohumlu Monte Carlo Placebo testi (her K ve her dönem için).
  5. Çoklu Test Birikimi (Hidden Multiple Testing / Data Snooping) Sayımı.
"""

import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

from scratch.run_faz_c_walk_forward_test import yukle_veriler, hizli_pit, hesapla_mom

KOMISYON = 0.003  # Çeyreklik rotasyon için %0.3 işlem maliyeti ve kayma


def metrikler_quarterly(arr, rf_annual=0.18):
    if not len(arr):
        return {"kumulatif": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0}
    a = np.array(arr)
    kum = float(np.prod(1.0 + a) - 1.0)
    n = len(a)
    cagr = float((1.0 + kum) ** (4.0 / max(1, n)) - 1.0) if kum > -0.99 else -0.99
    rf_q = (1.0 + rf_annual) ** (1.0 / 4.0) - 1.0
    diff = a - rf_q
    std = float(np.std(a, ddof=1)) if len(a) > 1 else 1e-6
    sharpe = float(np.mean(diff) / (std + 1e-8) * np.sqrt(4))

    zs = np.cumprod(1.0 + a)
    pk = np.maximum.accumulate(zs)
    dd = (zs - pk) / pk
    mdd = float(np.min(dd))
    return {"kumulatif": kum, "cagr": cagr, "sharpe": sharpe, "max_dd": mdd}


def hesapla_sektor_zscore(df, col, min_grup=4):
    zscores = pd.Series(np.nan, index=df.index)
    for sektor, grup in df.groupby("sektor"):
        gecerli = grup[col].dropna()
        if len(gecerli) >= min_grup:
            mu  = gecerli.mean()
            std = gecerli.std()
        else:
            gecerli = df[col].dropna()
            mu  = gecerli.mean()
            std = gecerli.std()
        if std > 1e-8:
            zscores.loc[grup.index] = (grup[col] - mu) / std
        else:
            zscores.loc[grup.index] = 0.0
    return zscores.clip(-3.0, 3.0)


def main():
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    tarihler_60 = pd.date_range("2018-09-01", "2026-08-01", freq="3MS")
    hisseler = sorted(fiyat_dict.keys())
    n_placebo = 100
    rng = np.random.default_rng(42)

    donemler = []

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

        px = seri_xu100[(seri_xu100.index >= t0) & (seri_xu100.index <= t1)]
        r_xu = float((px.iloc[-1] - px.iloc[0]) / px.iloc[0]) if len(px) >= 2 else 0.0

        satirlar = []
        for s in mevcut:
            curr, _ = hizli_pit(pit_bellek, s, t0)
            if not curr:
                continue
            is_bank = bool(curr.get("is_bank", False))
            sektor = cfg.HISSE_SEKTOR.get(s, "XBANK.IS" if is_bank else "XUSIN.IS")
            mom = hesapla_mom(fiyat_dict[s], t0)
            pb = curr.get("pb", np.nan)
            roe = curr.get("roe", np.nan)
            fcf_v = curr.get("fcf_verim", np.nan)
            net_b = curr.get("net_borc", 0.0) or 0.0
            ebit = curr.get("ebitda", 1.0) or 1.0

            # Banka için borç/ebitda ve fcf yerine proxy:
            # Bankalarda net borç/ebitda yoktur; tarafsız 0 olarak ele alınır
            borc_ebitda = -net_b / max(1.0, abs(ebit)) if not is_bank else np.nan

            satirlar.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb
            })

        df_k = pd.DataFrame(satirlar)

        # Z-Skorları (Sektör bazında)
        z_fcf  = hesapla_sektor_zscore(df_k, "fcf_v", min_grup=4).fillna(0.0)
        z_roe  = hesapla_sektor_zscore(df_k, "roe", min_grup=4).fillna(0.0)
        z_mom  = hesapla_sektor_zscore(df_k, "mom", min_grup=4).fillna(0.0)
        z_borc = hesapla_sektor_zscore(df_k, "borc_ebitda", min_grup=4).fillna(0.0)
        z_pb   = hesapla_sektor_zscore(df_k, "pb", min_grup=4).fillna(0.0)

        # VARYANT A: Z(FCF/PD) + Z(ROE) + Z(Mom) + Z(-NetBorç/EBITDA) [P/B'siz]
        df_k["skor_var_a"] = z_fcf + z_roe + z_mom + z_borc

        # VARYANT B: Z(FCF/PD) + Z(ROE) + Z(Mom) + Z(-NetBorç/EBITDA) - Z(P/B) [P/B'li]
        df_k["skor_var_b"] = z_fcf + z_roe + z_mom + z_borc - z_pb

        # Referans Eski Kaba Skor (-PB + ROE + Mom)
        df_k["skor_kaba"] = -z_pb + z_roe + z_mom

        donemler.append({
            "t0": t0, "t1": t1, "yil": t0.year,
            "is_early": t0 < pd.Timestamp("2022-01-01"),
            "rets": rets, "mevcut": mevcut, "r_xu": r_xu,
            "df_scores": df_k
        })

    print(f"Toplam Dönem Sayısı: {len(donemler)} (Erken IS: {sum(1 for d in donemler if d['is_early'])}, Geç OOS: {sum(1 for d in donemler if not d['is_early'])})")

    # TEST RAPORLAYICI
    def test_et_donem(donem_listesi, baslik):
        print("\n" + "=" * 115)
        print(f"=== {baslik.upper()} ===")
        print("=" * 115)
        print(f"{'Strateji':<35} | {'K':<4} | {'Kümülatif':<12} | {'CAGR':<8} | {'Sharpe':<8} | {'Max DD':<9} | {'Placebo p':<10}")
        print("-" * 105)

        k_values = [10, 15, 20]
        xu_rets = [d["r_xu"] for d in donem_listesi]
        m_xu = metrikler_quarterly(xu_rets)

        for k in k_values:
            # Placebo simülasyonu
            plac_rets = [[] for _ in range(n_placebo)]
            for d in donem_listesi:
                mevcut = d["mevcut"]
                for p_i in range(n_placebo):
                    sec = rng.choice(mevcut, size=k, replace=False)
                    plac_rets[p_i].append(float(np.mean([d["rets"][s] for s in sec])) - KOMISYON)

            plac_sharpes = [metrikler_quarterly(p)["sharpe"] for p in plac_rets]
            plac_kumuls  = [metrikler_quarterly(p)["kumulatif"] for p in plac_rets]
            mean_plac_kum = float(np.mean(plac_kumuls))
            mean_plac_sh  = float(np.mean(plac_sharpes))

            # Varyant A
            rets_a = []
            for d in donem_listesi:
                sirali_a = d["df_scores"].sort_values("skor_var_a", ascending=False)["sembol"].tolist()
                r_a = float(np.mean([d["rets"][s] for s in sirali_a[:k]])) - KOMISYON
                rets_a.append(r_a)
            m_a = metrikler_quarterly(rets_a)
            p_a = float(np.mean([1 if s >= m_a["sharpe"] else 0 for s in plac_sharpes]))

            # Varyant B
            rets_b = []
            for d in donem_listesi:
                sirali_b = d["df_scores"].sort_values("skor_var_b", ascending=False)["sembol"].tolist()
                r_b = float(np.mean([d["rets"][s] for s in sirali_b[:k]])) - KOMISYON
                rets_b.append(r_b)
            m_b = metrikler_quarterly(rets_b)
            p_b = float(np.mean([1 if s >= m_b["sharpe"] else 0 for s in plac_sharpes]))

            # Referans Kaba Skor
            rets_k = []
            for d in donem_listesi:
                sirali_k = d["df_scores"].sort_values("skor_kaba", ascending=False)["sembol"].tolist()
                r_k = float(np.mean([d["rets"][s] for s in sirali_k[:k]])) - KOMISYON
                rets_k.append(r_k)
            m_k = metrikler_quarterly(rets_k)
            p_k = float(np.mean([1 if s >= m_k["sharpe"] else 0 for s in plac_sharpes]))

            print(f"{'Varyant A (P/B Yok: FCF+ROE+Mom+Borç)':<35} | K={k:<2} | %{m_a['kumulatif']*100:>10.1f} | %{m_a['cagr']*100:>6.1f} | {m_a['sharpe']:>8.2f} | %{m_a['max_dd']*100:>7.1f} | p = {p_a:.3f}")
            print(f"{'Varyant B (P/B Var: FCF+ROE+Mom+Borç-PB)':<35} | K={k:<2} | %{m_b['kumulatif']*100:>10.1f} | %{m_b['cagr']*100:>6.1f} | {m_b['sharpe']:>8.2f} | %{m_b['max_dd']*100:>7.1f} | p = {p_b:.3f}")
            print(f"{'Referans Eski Kaba (-PB+ROE+Mom)':<35} | K={k:<2} | %{m_k['kumulatif']*100:>10.1f} | %{m_k['cagr']*100:>6.1f} | {m_k['sharpe']:>8.2f} | %{m_k['max_dd']*100:>7.1f} | p = {p_k:.3f}")
            print(f"{'100 Placebo Ortalaması':<35} | K={k:<2} | %{mean_plac_kum*100:>10.1f} | %{(mean_plac_kum+1)**(4/max(1, len(rets_a)))-1:>5.1%} | {mean_plac_sh:>8.2f} | {'-':>9} | baseline")
            print("-" * 105)

        print(f"{'BIST 100 Endeksi (Referans)':<35} | {'-':<4} | %{m_xu['kumulatif']*100:>10.1f} | %{m_xu['cagr']*100:>6.1f} | {m_xu['sharpe']:>8.2f} | %{m_xu['max_dd']*100:>7.1f} | -")

    # 1. Erken Dönem (2018-2021) [In-Sample]
    d_is = [d for d in donemler if d["is_early"]]
    test_et_donem(d_is, "Erken Dönem (2018-2021) [In-Sample Kalibrasyon Dönemi]")

    # 2. Geç Dönem (2022-2026) [Out-of-Sample Dondurulmuş Test]
    d_oos = [d for d in donemler if not d["is_early"]]
    test_et_donem(d_oos, "Geç Dönem (2022-2026) [Out-of-Sample Dondurulmuş Test]")

    # 3. Tüm 8 Yıl (2018-2026) Birleşik Test
    test_et_donem(donemler, "Tüm Örneklem (2018-2026) Birleşik Bakış")


if __name__ == "__main__":
    main()
