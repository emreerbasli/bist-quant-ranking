"""
scratch/v4_lockbox_test.py
==========================
V4 MODELİ KİLİT KUTU (LOCKBOX) RESMİ TEST PROTOKOLÜ (2025-06-01 -> 2026-09-07)
-------------------------------------------------------------------------------
Kapsam:
  - Dönem: 2025-06-01 -> 2026-09-07 (5 Çeyrek)
  - V3 Modeli: models/v3_ranking/winning_lgbm_ranker.joblib (8 Feature)
  - V4 Modeli: models/v4_ranking/winning_lgbm_ranker_v4.joblib (9 Feature)
  - Portföyler: K=10, K=15, K=20
  - Monte Carlo: Her K ve model için 100 Tohumlu Placebo Testi
  - Para Birimleri: Hem TL (TRY) hem Dolar (USD) bazında analiz
"""

import sys
import json
import warnings
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import joblib

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg
from scratch.run_faz_c_walk_forward_test import (
    yukle_veriler,
    hizli_pit,
    hesapla_mom,
    getir_tcmb_reel_faiz,
)
from scratch.run_lockbox_evaluation import hesapla_sektor_zscore
from scratch.faz1_ic_tarama import extract_candidate_features

KOMISYON = 0.003  # Çeyreklik rotasyon için %0.3 işlem maliyeti ve kayma


def metrikler_quarterly(arr, rf_annual=0.18):
    if not len(arr):
        return {"kumulatif": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0}
    a = np.array(arr, dtype=float)
    kum = float(np.prod(1.0 + a) - 1.0)
    n = len(a)
    cagr = float((1.0 + kum) ** (4.0 / max(1, n)) - 1.0) if kum > -0.99 else -0.99
    rf_q = (1.0 + rf_annual) ** 0.25 - 1.0
    diff = a - rf_q
    std = float(np.std(a, ddof=1)) if len(a) > 1 else 1e-6
    sharpe = float(np.mean(diff) / (std + 1e-8) * np.sqrt(4))

    zs = np.cumprod(1.0 + a)
    pk = np.maximum.accumulate(zs)
    dd = (zs - pk) / pk
    mdd = float(np.min(dd))
    return {"kumulatif": kum, "cagr": cagr, "sharpe": sharpe, "max_dd": mdd}


def run_lockbox_comparison():
    print("=" * 115)
    print("V4 & V3 RESMİ KİLİT KUTU (LOCKBOX) DEĞERLENDİRME PROTOKOLÜ")
    print("Dönem: 2025-06-01 -> 2026-09-07 (5 Çeyrek / 15 Ay)")
    print("=" * 115)

    # 1. Modelleri Yükle
    v3_path = ROOT_DIR / "models" / "v3_ranking" / "winning_lgbm_ranker.joblib"
    v4_path = ROOT_DIR / "models" / "v4_ranking" / "winning_lgbm_ranker_v4.joblib"

    v3_obj = joblib.load(v3_path)
    v4_obj = joblib.load(v4_path)

    model_v3 = v3_obj["model"]
    feats_v3 = v3_obj["feature_cols"]

    model_v4 = v4_obj["model"]
    feats_v4 = v4_obj["feature_cols"]

    print(f"V3 Modeli Yüklendi: {v3_obj.get('candidate_name', 'V3 LGBMRanker')} ({len(feats_v3)} Feature)")
    print(f"  Özellikler: {feats_v3}")
    print(f"V4 Modeli Yüklendi: {v4_obj.get('model_name', 'V4 LGBMRanker')} ({len(feats_v4)} Feature)")
    print(f"  Özellikler: {feats_v4}")

    # 2. Verileri Yükle
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    hisseler = sorted(fiyat_dict.keys())

    # 3. 5 Kilit Kutu Çeyreği
    lockbox_dates = [
        (pd.Timestamp("2025-06-01"), pd.Timestamp("2025-09-01"), "2025Q2"),
        (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-12-01"), "2025Q3"),
        (pd.Timestamp("2025-12-01"), pd.Timestamp("2026-03-01"), "2025Q4"),
        (pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-01"), "2026Q1"),
        (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-09-07"), "2026Q2 (Güncel)"),
    ]

    lockbox_data = []

    for t0, t1, label in lockbox_dates:
        rets_tl = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets_tl[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        mevcut = [s for s in hisseler if s in rets_tl]

        # BIST 100 Getirisi
        px = seri_xu100[(seri_xu100.index >= t0) & (seri_xu100.index <= t1)]
        r_xu_tl = float((px.iloc[-1] - px.iloc[0]) / px.iloc[0]) if len(px) >= 2 else 0.0

        # USD/TRY Değişimi
        u0_sub = seri_usdtry[seri_usdtry.index <= t0]
        u1_sub = seri_usdtry[seri_usdtry.index <= t1]
        u0 = float(u0_sub.iloc[-1])
        u1 = float(u1_sub.iloc[-1])
        r_usd_try = float((u1 - u0) / u0)

        # USD Bazında Getiriler
        rets_usd = {s: (1.0 + r) / (1.0 + r_usd_try) - 1.0 for s, r in rets_tl.items()}
        r_xu_usd = (1.0 + r_xu_tl) / (1.0 + r_usd_try) - 1.0

        # Makro
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

            # V4 9. Faktörü (reel_eps_growth)
            cand_feats = extract_candidate_features(
                t0, s, fiyat_dict[s], seri_usdtry, pit_bellek.get(s, []), tufe_aylik
            )
            reel_eps_raw = cand_feats.get("reel_eps_growth", np.nan)

            satirlar.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb,
                "reel_eps_raw": reel_eps_raw
            })

        df_q = pd.DataFrame(satirlar)

        # Z-Skorları (Sektörel Standartlaştırma)
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)

        # V4 9. Özelliği (Eğitim ortamında kullanılan formül: fillna(0.0).clip(-2.0, 2.0))
        df_q["reel_eps_growth"] = df_q["reel_eps_raw"].fillna(0.0).clip(-2.0, 2.0)

        df_q["reel_faiz"]  = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        # V3 ve V4 Tahminleri
        df_q["pred_v3"] = model_v3.predict(df_q[feats_v3])
        df_q["pred_v4"] = model_v4.predict(df_q[feats_v4])

        lockbox_data.append({
            "label": label, "t0": t0, "t1": t1,
            "rets_tl": rets_tl, "rets_usd": rets_usd,
            "mevcut": mevcut,
            "r_xu_tl": r_xu_tl, "r_xu_usd": r_xu_usd,
            "r_usd_try": r_usd_try,
            "df": df_q
        })

    print(f"\nKilit Kutu 5 Çeyreği Hazırlandı. Çeyrek başına ortalama {np.mean([len(d['mevcut']) for d in lockbox_data]):.0f} hisse.")

    # 4. Monte Carlo Placebo ve Performans Hesaplamaları
    n_placebo = 100
    rng = np.random.default_rng(42)
    k_values = [10, 15, 20]

    # BIST 100 Metrikleri
    xu_tl_rets = [d["r_xu_tl"] for d in lockbox_data]
    xu_usd_rets = [d["r_xu_usd"] for d in lockbox_data]
    m_xu_tl = metrikler_quarterly(xu_tl_rets, rf_annual=0.18)
    m_xu_usd = metrikler_quarterly(xu_usd_rets, rf_annual=0.045)

    results = {"tl": {}, "usd": {}}

    for k in k_values:
        # Placebo Simülasyonu (100 Tohum)
        plac_tl_rets = [[] for _ in range(n_placebo)]
        plac_usd_rets = [[] for _ in range(n_placebo)]

        for d in lockbox_data:
            mevcut = d["mevcut"]
            r_usd_try = d["r_usd_try"]
            for p_i in range(n_placebo):
                sec = rng.choice(mevcut, size=k, replace=False)
                r_tl_p = float(np.mean([d["rets_tl"][s] for s in sec])) - KOMISYON
                r_usd_p = (1.0 + r_tl_p) / (1.0 + r_usd_try) - 1.0
                plac_tl_rets[p_i].append(r_tl_p)
                plac_usd_rets[p_i].append(r_usd_p)

        plac_tl_sharpes = [metrikler_quarterly(p, 0.18)["sharpe"] for p in plac_tl_rets]
        plac_tl_kumuls  = [metrikler_quarterly(p, 0.18)["kumulatif"] for p in plac_tl_rets]
        plac_tl_cagrs   = [metrikler_quarterly(p, 0.18)["cagr"] for p in plac_tl_rets]
        plac_tl_mdds    = [metrikler_quarterly(p, 0.18)["max_dd"] for p in plac_tl_rets]

        plac_usd_sharpes = [metrikler_quarterly(p, 0.045)["sharpe"] for p in plac_usd_rets]
        plac_usd_kumuls  = [metrikler_quarterly(p, 0.045)["kumulatif"] for p in plac_usd_rets]
        plac_usd_cagrs   = [metrikler_quarterly(p, 0.045)["cagr"] for p in plac_usd_rets]
        plac_usd_mdds    = [metrikler_quarterly(p, 0.045)["max_dd"] for p in plac_usd_rets]

        # Model V3 Getirileri
        v3_tl_rets = []
        v3_usd_rets = []
        for d in lockbox_data:
            sirali_v3 = d["df"].sort_values("pred_v3", ascending=False)["sembol"].tolist()
            r_tl = float(np.mean([d["rets_tl"][s] for s in sirali_v3[:k]])) - KOMISYON
            r_usd = (1.0 + r_tl) / (1.0 + d["r_usd_try"]) - 1.0
            v3_tl_rets.append(r_tl)
            v3_usd_rets.append(r_usd)

        m_v3_tl = metrikler_quarterly(v3_tl_rets, 0.18)
        m_v3_usd = metrikler_quarterly(v3_usd_rets, 0.045)
        p_v3_tl = float(np.mean([1 if s >= m_v3_tl["sharpe"] else 0 for s in plac_tl_sharpes]))
        p_v3_usd = float(np.mean([1 if s >= m_v3_usd["sharpe"] else 0 for s in plac_usd_sharpes]))

        # Model V4 Getirileri
        v4_tl_rets = []
        v4_usd_rets = []
        for d in lockbox_data:
            sirali_v4 = d["df"].sort_values("pred_v4", ascending=False)["sembol"].tolist()
            r_tl = float(np.mean([d["rets_tl"][s] for s in sirali_v4[:k]])) - KOMISYON
            r_usd = (1.0 + r_tl) / (1.0 + d["r_usd_try"]) - 1.0
            v4_tl_rets.append(r_tl)
            v4_usd_rets.append(r_usd)

        m_v4_tl = metrikler_quarterly(v4_tl_rets, 0.18)
        m_v4_usd = metrikler_quarterly(v4_usd_rets, 0.045)
        p_v4_tl = float(np.mean([1 if s >= m_v4_tl["sharpe"] else 0 for s in plac_tl_sharpes]))
        p_v4_usd = float(np.mean([1 if s >= m_v4_usd["sharpe"] else 0 for s in plac_usd_sharpes]))

        results["tl"][k] = {
            "v3": m_v3_tl, "p_v3": p_v3_tl, "v3_q_rets": v3_tl_rets,
            "v4": m_v4_tl, "p_v4": p_v4_tl, "v4_q_rets": v4_tl_rets,
            "plac_mean_kum": float(np.mean(plac_tl_kumuls)),
            "plac_mean_cagr": float(np.mean(plac_tl_cagrs)),
            "plac_mean_sh": float(np.mean(plac_tl_sharpes)),
            "plac_mean_mdd": float(np.mean(plac_tl_mdds)),
            "xu": m_xu_tl
        }

        results["usd"][k] = {
            "v3": m_v3_usd, "p_v3": p_v3_usd, "v3_q_rets": v3_usd_rets,
            "v4": m_v4_usd, "p_v4": p_v4_usd, "v4_q_rets": v4_usd_rets,
            "plac_mean_kum": float(np.mean(plac_usd_kumuls)),
            "plac_mean_cagr": float(np.mean(plac_usd_cagrs)),
            "plac_mean_sh": float(np.mean(plac_usd_sharpes)),
            "plac_mean_mdd": float(np.mean(plac_usd_mdds)),
            "xu": m_xu_usd
        }

    # 5. TABLO YAZDIRMA (TL BAZINDA)
    print("\n" + "=" * 115)
    print("TABLO 1: TÜRK LİRASI (TL) BAZINDA KİLİT KUTU PERFORMANSI (2025-06-01 -> 2026-09-07)")
    print("=" * 115)
    print(f"{'Strateji':<32} | {'K':<4} | {'Kümülatif':<12} | {'CAGR':<8} | {'Sharpe':<8} | {'Max DD':<9} | {'Placebo p':<10}")
    print("-" * 105)

    for k in k_values:
        res = results["tl"][k]
        # V3
        print(f"{'V3 LGBMRanker (8 Feature)':<32} | K={k:<2} | %{res['v3']['kumulatif']*100:>10.1f} | %{res['v3']['cagr']*100:>6.1f} | {res['v3']['sharpe']:>8.2f} | %{res['v3']['max_dd']*100:>7.1f} | p = {res['p_v3']:.3f}")
        # V4
        print(f"{'V4 LGBMRanker (9 Feature)':<32} | K={k:<2} | %{res['v4']['kumulatif']*100:>10.1f} | %{res['v4']['cagr']*100:>6.1f} | {res['v4']['sharpe']:>8.2f} | %{res['v4']['max_dd']*100:>7.1f} | p = {res['p_v4']:.3f}")
        # Placebo
        print(f"{'100 Tohum Placebo Ortalaması':<32} | K={k:<2} | %{res['plac_mean_kum']*100:>10.1f} | %{res['plac_mean_cagr']*100:>6.1f} | {res['plac_mean_sh']:>8.2f} | %{res['plac_mean_mdd']*100:>7.1f} | baseline")
        print("-" * 105)

    print(f"{'BIST 100 Endeksi (Referans)':<32} | {'-':<4} | %{m_xu_tl['kumulatif']*100:>10.1f} | %{m_xu_tl['cagr']*100:>6.1f} | {m_xu_tl['sharpe']:>8.2f} | %{m_xu_tl['max_dd']*100:>7.1f} | -")

    # 6. TABLO YAZDIRMA (USD BAZINDA)
    print("\n" + "=" * 115)
    print("TABLO 2: AMERİKAN DOLARI (USD) BAZINDA KİLİT KUTU PERFORMANSI (2025-06-01 -> 2026-09-07)")
    print("=" * 115)
    print(f"{'Strateji':<32} | {'K':<4} | {'Kümülatif':<12} | {'CAGR':<8} | {'Sharpe':<8} | {'Max DD':<9} | {'Placebo p':<10}")
    print("-" * 105)

    for k in k_values:
        res = results["usd"][k]
        # V3
        print(f"{'V3 LGBMRanker (8 Feature)':<32} | K={k:<2} | %{res['v3']['kumulatif']*100:>10.1f} | %{res['v3']['cagr']*100:>6.1f} | {res['v3']['sharpe']:>8.2f} | %{res['v3']['max_dd']*100:>7.1f} | p = {res['p_v3']:.3f}")
        # V4
        print(f"{'V4 LGBMRanker (9 Feature)':<32} | K={k:<2} | %{res['v4']['kumulatif']*100:>10.1f} | %{res['v4']['cagr']*100:>6.1f} | {res['v4']['sharpe']:>8.2f} | %{res['v4']['max_dd']*100:>7.1f} | p = {res['p_v4']:.3f}")
        # Placebo
        print(f"{'100 Tohum Placebo Ortalaması':<32} | K={k:<2} | %{res['plac_mean_kum']*100:>10.1f} | %{res['plac_mean_cagr']*100:>6.1f} | {res['plac_mean_sh']:>8.2f} | %{res['plac_mean_mdd']*100:>7.1f} | baseline")
        print("-" * 105)

    print(f"{'BIST 100 Endeksi (Referans)':<32} | {'-':<4} | %{m_xu_usd['kumulatif']*100:>10.1f} | %{m_xu_usd['cagr']*100:>6.1f} | {m_xu_usd['sharpe']:>8.2f} | %{m_xu_usd['max_dd']*100:>7.1f} | -")

    # 7. ÇEYREK BAZINDA GETİRİLER (V3 vs V4 vs BIST100, K=15)
    print("\n" + "=" * 105)
    print("ÇEYREKLİK PERFORMANS AYRIŞMASI (K=15, TL Bazında)")
    print("=" * 105)
    print(f"{'Çeyrek':<20} | {'V3 LGBM (K=15)':<16} | {'V4 LGBM (K=15)':<16} | {'Placebo Ort':<14} | {'BIST 100':<10}")
    print("-" * 88)

    for idx, d in enumerate(lockbox_data):
        r_v3_q = results["tl"][15]["v3_q_rets"][idx]
        r_v4_q = results["tl"][15]["v4_q_rets"][idx]
        sec_plac = [float(np.mean([d["rets_tl"][s] for s in rng.choice(d["mevcut"], size=15, replace=False)])) - KOMISYON for _ in range(100)]
        r_plac_q = float(np.mean(sec_plac))
        print(f"{d['label']:<20} | %{r_v3_q*100:>14.2f} | %{r_v4_q*100:>14.2f} | %{r_plac_q*100:>12.2f} | %{d['r_xu_tl']*100:>8.2f}")

    # 8. ADIM 0 RESMİ 4 KRİTERİN HESAPLANMASI (V4 Hedef: K=15)
    res_15_tl = results["tl"][15]
    res_10_tl = results["tl"][10]
    res_20_tl = results["tl"][20]

    v4_sh_15 = res_15_tl["v4"]["sharpe"]
    plac_sh_15 = res_15_tl["plac_mean_sh"]
    delta_sh_15 = v4_sh_15 - plac_sh_15
    p_val_15 = res_15_tl["p_v4"]
    r_v4_15 = res_15_tl["v4"]["kumulatif"]
    r_xu = m_xu_tl["kumulatif"]

    k1_pass = p_val_15 < 0.10
    k2_pass = delta_sh_15 >= 0.20
    k3_pass = r_v4_15 > r_xu
    k4_pass = (res_10_tl["v4"]["kumulatif"] > res_10_tl["plac_mean_kum"]) and \
              (res_20_tl["v4"]["kumulatif"] > res_20_tl["plac_mean_kum"])

    print("\n" + "=" * 95)
    print("V4 KİLİT KUTU RESMİ KRİTER KONTROL RAPORU (ADIM 0 SÖZLEŞMESİNE GÖRE)")
    print("=" * 95)
    print(f"Kriter 1 (Monte Carlo Placebo p < 0.10, K=15):")
    print(f"  -> Gerçekleşen: p = {p_val_15:.3f}  ==> {'[GEÇTİ]' if k1_pass else '[KALDI]'}")
    print(f"Kriter 2 (Ekonomik Sharpe Primi: Model Sh > Placebo + 0.20):")
    print(f"  -> V4 Sharpe: {v4_sh_15:.2f} | Placebo Sharpe: {plac_sh_15:.2f} | ΔSharpe: {delta_sh_15:+.2f} (Hedef >= +0.20) ==> {'[GEÇTİ]' if k2_pass else '[KALDI]'}")
    print(f"Kriter 3 (Piyasa Üstünlüğü: Model Getirisi > BIST 100):")
    print(f"  -> V4 Kümülatif: %{r_v4_15*100:.1f} | BIST 100: %{r_xu*100:.1f} | Fark: %{(r_v4_15 - r_xu)*100:+.1f} ==> {'[GEÇTİ]' if k3_pass else '[KALDI]'}")
    print(f"Kriter 4 (Portföy Tutarlılığı: K=10 ve K=20'de Model > Placebo):")
    print(f"  -> K=10: V4 %{res_10_tl['v4']['kumulatif']*100:.1f} vs Placebo %{res_10_tl['plac_mean_kum']*100:.1f} ({'Üstünde' if res_10_tl['v4']['kumulatif'] > res_10_tl['plac_mean_kum'] else 'Altında'})")
    print(f"  -> K=20: V4 %{res_20_tl['v4']['kumulatif']*100:.1f} vs Placebo %{res_20_tl['plac_mean_kum']*100:.1f} ({'Üstünde' if res_20_tl['v4']['kumulatif'] > res_20_tl['plac_mean_kum'] else 'Altında'})")
    print(f"  ==> {'[GEÇTİ]' if k4_pass else '[KALDI]'}")
    print("-" * 95)

    all_pass = k1_pass and k2_pass and k3_pass and k4_pass
    print(f"4 KRİTER SONUCU: {'4/4 KARŞILANDI' if all_pass else 'KARŞILANMADI (KILL-SWITCH)'}")
    print("=" * 95)

    # Sonuçları JSON olarak kaydet
    summary_out = {
        "dates": [f"{t0.strftime('%Y-%m-%d')} -> {t1.strftime('%Y-%m-%d')}" for t0, t1, _ in lockbox_dates],
        "k_values": k_values,
        "results_tl": {k: {
            "v3": results["tl"][k]["v3"], "p_v3": results["tl"][k]["p_v3"],
            "v4": results["tl"][k]["v4"], "p_v4": results["tl"][k]["p_v4"],
            "plac_mean_kum": results["tl"][k]["plac_mean_kum"],
            "plac_mean_sh": results["tl"][k]["plac_mean_sh"],
            "plac_mean_cagr": results["tl"][k]["plac_mean_cagr"],
            "plac_mean_mdd": results["tl"][k]["plac_mean_mdd"],
        } for k in k_values},
        "results_usd": {k: {
            "v3": results["usd"][k]["v3"], "p_v3": results["usd"][k]["p_v3"],
            "v4": results["usd"][k]["v4"], "p_v4": results["usd"][k]["p_v4"],
            "plac_mean_kum": results["usd"][k]["plac_mean_kum"],
            "plac_mean_sh": results["usd"][k]["plac_mean_sh"],
            "plac_mean_cagr": results["usd"][k]["plac_mean_cagr"],
            "plac_mean_mdd": results["usd"][k]["plac_mean_mdd"],
        } for k in k_values},
        "xu100_tl": m_xu_tl,
        "xu100_usd": m_xu_usd,
        "criteria": {
            "k1_p_val": {"pass": bool(k1_pass), "val": float(p_val_15), "threshold": 0.10},
            "k2_sharpe_diff": {"pass": bool(k2_pass), "val": float(delta_sh_15), "threshold": 0.20},
            "k3_market_outperform": {"pass": bool(k3_pass), "v4_ret": float(r_v4_15), "xu_ret": float(r_xu)},
            "k4_consistency": {"pass": bool(k4_pass),
                               "k10_v4": float(res_10_tl["v4"]["kumulatif"]), "k10_plac": float(res_10_tl["plac_mean_kum"]),
                               "k20_v4": float(res_20_tl["v4"]["kumulatif"]), "k20_plac": float(res_20_tl["plac_mean_kum"])}
        },
        "all_passed": bool(all_pass)
    }

    out_file = ROOT_DIR / "reports" / "v4_lockbox_test_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_out, f, indent=2, ensure_ascii=False)
    print(f"\nResmi sonuçlar kaydedildi: {out_file}")


if __name__ == "__main__":
    run_lockbox_comparison()
