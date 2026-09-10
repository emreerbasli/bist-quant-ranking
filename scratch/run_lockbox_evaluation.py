"""
scratch/run_lockbox_evaluation.py
=================================
ADIM 4: KİLİT KUTU (LOCKBOX) RESMİ TESTİ (2025-06-01 -> 2026-09-07)
-------------------------------------------------------------------
Dondurulmuş Model: scratch/winning_lgbm_ranker.joblib (Aday 1: Aşırı Muhafazakâr)

Test İçeriği:
  1. 5 Kilit Kutu Çeyreği:
     - Q1: 2025-06-01 -> 2025-09-01
     - Q2: 2025-09-01 -> 2025-12-01
     - Q3: 2025-12-01 -> 2026-03-01
     - Q4: 2026-03-01 -> 2026-06-01
     - Q5: 2026-06-01 -> 2026-09-07
  2. K in [10, 15, 20]
  3. 100 Tohumlu Monte Carlo Placebo Testi
  4. Bağlamsal Referans Kaba Formül (-PB + ROE + Mom)
  5. BIST 100 Endeks Kıyaslaması
  6. 4 Resmi Sözleşme Kriterinin Değerlendirilmesi
"""

import sys
import joblib
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

from scratch.run_faz_c_walk_forward_test import yukle_veriler, hizli_pit, hesapla_mom, getir_tcmb_reel_faiz

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


def run_lockbox():
    print("=" * 115)
    print("ADIM 4: KİLİT KUTU (LOCKBOX) KASASI AÇILIŞI VE RESMİ TEST")
    print("Dönem: 2025-06-01 -> 2026-09-07 (Son 5 Çeyrek)")
    print("=" * 115)

    # 1. Dondurulmuş Modeli Yükle
    saved_obj = joblib.load(ROOT_DIR / "scratch" / "winning_lgbm_ranker.joblib")
    model = saved_obj["model"]
    feature_cols = saved_obj["feature_cols"]
    candidate_name = saved_obj["candidate_name"]
    print(f"Yüklenen Dondurulmuş Model: {candidate_name}")
    print(f"Kullanılan Özellikler: {feature_cols}")

    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    hisseler = sorted(fiyat_dict.keys())

    # 2. Kilit Kutu 5 Çeyrek Tanımı
    lockbox_dates = [
        (pd.Timestamp("2025-06-01"), pd.Timestamp("2025-09-01"), "2025Q2"),
        (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-12-01"), "2025Q3"),
        (pd.Timestamp("2025-12-01"), pd.Timestamp("2026-03-01"), "2025Q4"),
        (pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-01"), "2026Q1"),
        (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-09-07"), "2026Q2 (Güncel)"),
    ]

    lockbox_data = []

    for t0, t1, label in lockbox_dates:
        rets = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        mevcut = [s for s in hisseler if s in rets]
        px = seri_xu100[(seri_xu100.index >= t0) & (seri_xu100.index <= t1)]
        r_xu = float((px.iloc[-1] - px.iloc[0]) / px.iloc[0]) if len(px) >= 2 else 0.0

        reel_faiz = getir_tcmb_reel_faiz(t0, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t0]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

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
            borc_ebitda = -net_b / max(1.0, abs(ebit)) if not is_bank else np.nan

            satirlar.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb
            })

        df_q = pd.DataFrame(satirlar)

        # Feature Z-Score'ları
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)

        df_q["reel_faiz"]  = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        # 1. Dondurulmuş LGBMRanker Tahmini
        X_lock = df_q[feature_cols]
        df_q["ml_pred"] = model.predict(X_lock)

        # 2. Bağlamsal Referans Kaba Skor Formülü (-PB + ROE + Mom)
        z_pb_raw = hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)
        df_q["skor_kaba"] = -z_pb_raw + df_q["z_roe"] + df_q["z_mom"]

        lockbox_data.append({
            "label": label, "t0": t0, "t1": t1,
            "rets": rets, "mevcut": mevcut, "r_xu": r_xu,
            "df": df_q
        })

    print(f"\nKilit Kutu 5 Çeyreği başarıyla hazırlandı. Toplam hisse evreni periyot başına ortalama {np.mean([len(d['mevcut']) for d in lockbox_data]):.0f} hisse.")

    # 3. Kilit Kutu Performans Hesaplamaları
    n_placebo = 100
    rng = np.random.default_rng(42)

    k_values = [10, 15, 20]

    sonuclar = {}

    print("\n" + "=" * 115)
    print("KİLİT KUTU (LOCKBOX) 5 ÇEYREKLİK PERFORMANS TABLOSU (2025-06-01 -> 2026-09-07)")
    print("=" * 115)
    print(f"{'Strateji':<35} | {'K':<4} | {'Kümülatif':<12} | {'CAGR':<8} | {'Sharpe':<8} | {'Max DD':<9} | {'Placebo p':<10}")
    print("-" * 105)

    xu_rets = [d["r_xu"] for d in lockbox_data]
    m_xu = metrikler_quarterly(xu_rets)

    for k in k_values:
        # Placebo
        plac_rets = [[] for _ in range(n_placebo)]
        for d in lockbox_data:
            mevcut = d["mevcut"]
            for p_i in range(n_placebo):
                sec = rng.choice(mevcut, size=k, replace=False)
                plac_rets[p_i].append(float(np.mean([d["rets"][s] for s in sec])) - KOMISYON)

        plac_sharpes = [metrikler_quarterly(p)["sharpe"] for p in plac_rets]
        plac_kumuls  = [metrikler_quarterly(p)["kumulatif"] for p in plac_rets]
        mean_plac_kum = float(np.mean(plac_kumuls))
        mean_plac_sh  = float(np.mean(plac_sharpes))

        # Dondurulmuş LGBMRanker
        ml_rets = []
        for d in lockbox_data:
            sirali_ml = d["df"].sort_values("ml_pred", ascending=False)["sembol"].tolist()
            r_ml = float(np.mean([d["rets"][s] for s in sirali_ml[:k]])) - KOMISYON
            ml_rets.append(r_ml)
        m_ml = metrikler_quarterly(ml_rets)
        p_ml = float(np.mean([1 if s >= m_ml["sharpe"] else 0 for s in plac_sharpes]))

        # Bağlamsal Referans Kaba Formül (-PB + ROE + Mom)
        kaba_rets = []
        for d in lockbox_data:
            sirali_kaba = d["df"].sort_values("skor_kaba", ascending=False)["sembol"].tolist()
            r_kaba = float(np.mean([d["rets"][s] for s in sirali_kaba[:k]])) - KOMISYON
            kaba_rets.append(r_kaba)
        m_kaba = metrikler_quarterly(kaba_rets)
        p_kaba = float(np.mean([1 if s >= m_kaba["sharpe"] else 0 for s in plac_sharpes]))

        sonuclar[k] = {
            "m_ml": m_ml, "p_ml": p_ml,
            "m_kaba": m_kaba, "p_kaba": p_kaba,
            "mean_plac_kum": mean_plac_kum, "mean_plac_sh": mean_plac_sh,
            "m_xu": m_xu
        }

        print(f"{'Dondurulmuş LGBMRanker (Aday 1)':<35} | K={k:<2} | %{m_ml['kumulatif']*100:>10.1f} | %{m_ml['cagr']*100:>6.1f} | {m_ml['sharpe']:>8.2f} | %{m_ml['max_dd']*100:>7.1f} | p = {p_ml:.3f}")
        print(f"{'Bağlamsal Kaba Skor (-PB+ROE+Mom)':<35} | K={k:<2} | %{m_kaba['kumulatif']*100:>10.1f} | %{m_kaba['cagr']*100:>6.1f} | {m_kaba['sharpe']:>8.2f} | %{m_kaba['max_dd']*100:>7.1f} | p = {p_kaba:.3f}")
        print(f"{'100 Tohum Placebo Ortalaması':<35} | K={k:<2} | %{mean_plac_kum*100:>10.1f} | %{(mean_plac_kum+1)**(4/len(ml_rets))-1:>5.1%} | {mean_plac_sh:>8.2f} | {'-':>9} | baseline")
        print("-" * 105)

    print(f"{'BIST 100 Endeksi (Referans)':<35} | {'-':<4} | %{m_xu['kumulatif']*100:>10.1f} | %{m_xu['cagr']*100:>6.1f} | {m_xu['sharpe']:>8.2f} | %{m_xu['max_dd']*100:>7.1f} | -")

    # Çeyrek Çeyrek Kilit Kutu Dökümü (K=15 için)
    print("\n" + "=" * 105)
    print("KİLİT KUTU ÇEYREK BAZINDA PERFORMANS AYRIŞMASI (K=15)")
    print("=" * 105)
    print(f"{'Çeyrek':<20} | {'Dondurulmuş LGBM':<18} | {'Bağlamsal Kaba':<16} | {'Placebo Ort':<14} | {'BIST 100':<10}")
    print("-" * 88)

    for idx, d in enumerate(lockbox_data):
        sirali_ml = d["df"].sort_values("ml_pred", ascending=False)["sembol"].tolist()
        r_ml_q = float(np.mean([d["rets"][s] for s in sirali_ml[:15]])) - KOMISYON

        sirali_kaba = d["df"].sort_values("skor_kaba", ascending=False)["sembol"].tolist()
        r_kaba_q = float(np.mean([d["rets"][s] for s in sirali_kaba[:15]])) - KOMISYON

        sec_plac = [float(np.mean([d["rets"][s] for s in rng.choice(d["mevcut"], size=15, replace=False)])) - KOMISYON for _ in range(100)]
        r_plac_q = float(np.mean(sec_plac))

        print(f"{d['label']:<20} | %{r_ml_q*100:>16.2f} | %{r_kaba_q*100:>14.2f} | %{r_plac_q*100:>12.2f} | %{d['r_xu']*100:>8.2f}")

    # 4. Resmi 4 Kriterin Karar Tutanağı (K=15 bazında)
    res_15 = sonuclar[15]
    m_ml_15 = res_15["m_ml"]
    p_ml_15 = res_15["p_ml"]
    sh_plac = res_15["mean_plac_sh"]
    sh_diff = m_ml_15["sharpe"] - sh_plac
    r_ml_total = m_ml_15["kumulatif"]
    r_xu_total = m_xu["kumulatif"]

    kriter_1_ok = p_ml_15 < 0.10
    kriter_2_ok = sh_diff >= 0.20
    kriter_3_ok = r_ml_total > r_xu_total
    kriter_4_ok = (sonuclar[10]["m_ml"]["sharpe"] >= sonuclar[10]["mean_plac_sh"]) and \
                  (sonuclar[20]["m_ml"]["sharpe"] >= sonuclar[20]["mean_plac_sh"])

    print("\n" + "=" * 85)
    print("KİLİT KUTU RESMİ SÖZLEŞME KARAR TUTANAĞI")
    print("=" * 85)
    print(f"Kriter 1 (İstatistiksel Alfa: p < 0.10):        {'GEÇTİ' if kriter_1_ok else 'KALDI'} (p = {p_ml_15:.3f})")
    print(f"Kriter 2 (Ekonomik Sharpe Primi: ΔSh >= +0.20): {'GEÇTİ' if kriter_2_ok else 'KALDI'} (ΔSharpe = {sh_diff:+.2f})")
    print(f"Kriter 3 (Piyasa Üstünlüğü: R_mod > R_XU100):   {'GEÇTİ' if kriter_3_ok else 'KALDI'} (%{r_ml_total*100:.1f} vs %{r_xu_total*100:.1f})")
    print(f"Kriter 4 (K=10/15/20 Tutarlılığı):              {'GEÇTİ' if kriter_4_ok else 'KALDI'}")
    print("-" * 85)

    all_passed = kriter_1_ok and kriter_2_ok and kriter_3_ok and kriter_4_ok
    print(f"\nNİHAİ SÖZLEŞME HÜKMÜ: {'🏆 PROTOKOL ONAYLANDI (BAŞARILI)' if all_passed else '❌ PROTOKOL BAŞARISIZ OLDU (KILL-SWITCH DEVREDE)'}")
    print("=" * 85)


if __name__ == "__main__":
    run_lockbox()
