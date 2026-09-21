"""
scratch/run_comprehensive_v3_v4_study.py
========================================
V3 vs V4 Kapsamlı ve Çok Boyutlu Kantitatif Karşılaştırma Motoru
5 Bağımsız Test Protokolü:
  1. Bootstrap Performans Karşılaştırması (500 Tohumlu Block Bootstrap)
  2. Rejim Bazında Ayrıştırılmış Analiz (Dönem A, B, C, D)
  3. Kilit Kutu Dönemi Temiz Karşılaştırması (K=10 ve K=15 Eşitlemeli)
  4. Turnover ve İşlem Maliyeti / Sürtünme Analizi
  5. 2022 Stres Testi, Taban Riski ve Recovery Süresi
"""

import sys
import os
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
from scipy.stats import mannwhitneyu

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
from bot.kap_filter import ardisik_taban_tespit

KOMISYON = 0.003  # Çeyreklik %0.3 baz komisyon + slippage
RF_ANNUAL = 0.18  # %18 yıllık risksiz faiz


def metrikler_quarterly(arr, rf_annual=0.18):
    if not len(arr):
        return {"kumulatif": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0, "vol": 0.0}
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
    vol = float(std * np.sqrt(4))
    return {"kumulatif": kum, "cagr": cagr, "sharpe": sharpe, "max_dd": mdd, "vol": vol}


def build_all_quarterly_data():
    """2018-09'dan 2026-09'a kadar tüm çeyrekleri ve kesitleri Point-in-Time olarak üretir."""
    print(">> Piyasa ve PIT bilanço verileri yükleniyor...")
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    hisseler = sorted(fiyat_dict.keys())

    # 1. Tüm çeyrek pencereleri: 2018-09 -> 2025-06 (eğitim) ve 2025-06 -> 2026-09 (kilit kutu)
    # 2018-09-01'den 2025-06-01'e
    tarihler_all = [
        (pd.Timestamp("2018-09-01"), pd.Timestamp("2018-12-01"), "2018Q3"),
        (pd.Timestamp("2018-12-01"), pd.Timestamp("2019-03-01"), "2018Q4"),
        (pd.Timestamp("2019-03-01"), pd.Timestamp("2019-06-01"), "2019Q1"),
        (pd.Timestamp("2019-06-01"), pd.Timestamp("2019-09-01"), "2019Q2"),
        (pd.Timestamp("2019-09-01"), pd.Timestamp("2019-12-01"), "2019Q3"),
        (pd.Timestamp("2019-12-01"), pd.Timestamp("2020-03-01"), "2019Q4"),
        (pd.Timestamp("2020-03-01"), pd.Timestamp("2020-06-01"), "2020Q1"),
        (pd.Timestamp("2020-06-01"), pd.Timestamp("2020-09-01"), "2020Q2"),
        (pd.Timestamp("2020-09-01"), pd.Timestamp("2020-12-01"), "2020Q3"),
        (pd.Timestamp("2020-12-01"), pd.Timestamp("2021-03-01"), "2020Q4"),
        (pd.Timestamp("2021-03-01"), pd.Timestamp("2021-06-01"), "2021Q1"),
        (pd.Timestamp("2021-06-01"), pd.Timestamp("2021-09-01"), "2021Q2"),
        (pd.Timestamp("2021-09-01"), pd.Timestamp("2021-12-01"), "2021Q3"),
        (pd.Timestamp("2021-12-01"), pd.Timestamp("2022-03-01"), "2021Q4"),
        (pd.Timestamp("2022-03-01"), pd.Timestamp("2022-06-01"), "2022Q1"),
        (pd.Timestamp("2022-06-01"), pd.Timestamp("2022-09-01"), "2022Q2"),
        (pd.Timestamp("2022-09-01"), pd.Timestamp("2022-12-01"), "2022Q3"),
        (pd.Timestamp("2022-12-01"), pd.Timestamp("2023-03-01"), "2022Q4"),
        (pd.Timestamp("2023-03-01"), pd.Timestamp("2023-06-01"), "2023Q1"),
        (pd.Timestamp("2023-06-01"), pd.Timestamp("2023-09-01"), "2023Q2"),
        (pd.Timestamp("2023-09-01"), pd.Timestamp("2023-12-01"), "2023Q3"),
        (pd.Timestamp("2023-12-01"), pd.Timestamp("2024-03-01"), "2023Q4"),
        (pd.Timestamp("2024-03-01"), pd.Timestamp("2024-06-01"), "2024Q1"),
        (pd.Timestamp("2024-06-01"), pd.Timestamp("2024-09-01"), "2024Q2"),
        (pd.Timestamp("2024-09-01"), pd.Timestamp("2024-12-01"), "2024Q3"),
        (pd.Timestamp("2024-12-01"), pd.Timestamp("2025-03-01"), "2024Q4"),
        (pd.Timestamp("2025-03-01"), pd.Timestamp("2025-06-01"), "2025Q1"),
        # Kilit Kutu
        (pd.Timestamp("2025-06-01"), pd.Timestamp("2025-09-01"), "2025Q2_LOCK"),
        (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-12-01"), "2025Q3_LOCK"),
        (pd.Timestamp("2025-12-01"), pd.Timestamp("2026-03-01"), "2025Q4_LOCK"),
        (pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-01"), "2026Q1_LOCK"),
        (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-09-07"), "2026Q2_LOCK"),
    ]

    quarters = []

    for t0, t1, label in tarihler_all:
        rets_tl = {}
        rets_usd = {}

        # USD kuru değişimi
        sub_usd = seri_usdtry[(seri_usdtry.index >= t0) & (seri_usdtry.index <= t1)]
        r_usd_try = float((sub_usd.iloc[-1] - sub_usd.iloc[0]) / sub_usd.iloc[0]) if len(sub_usd) >= 2 else 0.0

        # XU100 değişimi
        sub_xu = seri_xu100[(seri_xu100.index >= t0) & (seri_xu100.index <= t1)]
        r_xu_tl = float((sub_xu.iloc[-1] - sub_xu.iloc[0]) / sub_xu.iloc[0]) if len(sub_xu) >= 2 else 0.0
        r_xu_usd = (1.0 + r_xu_tl) / (1.0 + r_usd_try) - 1.0

        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                r_tl = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))
                rets_tl[s] = r_tl
                rets_usd[s] = (1.0 + r_tl) / (1.0 + r_usd_try) - 1.0

        mevcut = [s for s in hisseler if s in rets_tl]
        if len(mevcut) < 25:
            continue

        reel_faiz = getir_tcmb_reel_faiz(t0, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t0]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

        rows = []
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

            cand_feats = extract_candidate_features(
                t0, s, fiyat_dict[s], seri_usdtry, pit_bellek.get(s, []), tufe_aylik
            )
            reel_eps_raw = cand_feats.get("reel_eps_growth", np.nan)

            rows.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb,
                "reel_eps_raw": reel_eps_raw,
                "fwd_ret_tl": rets_tl[s],
                "fwd_ret_usd": rets_usd[s]
            })

        df_q = pd.DataFrame(rows)
        # Sektörel z-skorları
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)

        # 9. Faktör varyantları
        df_q["reel_eps_growth"] = df_q["reel_eps_raw"].fillna(0.0).clip(-2.0, 2.0)
        df_q["z_reel_eps"]      = hesapla_sektor_zscore(df_q, "reel_eps_raw", min_grup=4).fillna(0.0).clip(-1.5, 1.5)

        df_q["reel_faiz"]  = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        quarters.append({
            "t0": t0, "t1": t1, "label": label, "df": df_q,
            "rets_tl": rets_tl, "rets_usd": rets_usd,
            "r_xu_tl": r_xu_tl, "r_xu_usd": r_xu_usd,
            "mevcut": mevcut
        })

    return quarters, fiyat_dict, seri_xu100, seri_usdtry


def evaluate_quarters_for_models(quarters, model_v3, feats_v3, model_v4, feats_v4):
    """Her çeyrek için V3 (K=10, 15) ve V4 (K=10, 15) Top-K seçimlerini ve getirilerini üretir."""
    results = []
    for q in quarters:
        df = q["df"].copy()
        t0, t1, label = q["t0"], q["t1"], q["label"]

        # V3 skorları
        df["pred_v3"] = model_v3.predict(df[feats_v3])
        # V4 skorları
        df["pred_v4"] = model_v4.predict(df[feats_v4])

        sirali_v3 = df.sort_values("pred_v3", ascending=False)["sembol"].tolist()
        sirali_v4 = df.sort_values("pred_v4", ascending=False)["sembol"].tolist()

        # Getiriler (TL ve USD)
        def get_portfolio_rets(symbols):
            r_tl = float(np.mean([q["rets_tl"][s] for s in symbols])) - KOMISYON
            r_usd = float(np.mean([q["rets_usd"][s] for s in symbols])) - KOMISYON
            return r_tl, r_usd

        v3_10_tl, v3_10_usd = get_portfolio_rets(sirali_v3[:10])
        v3_15_tl, v3_15_usd = get_portfolio_rets(sirali_v3[:15])
        v4_10_tl, v4_10_usd = get_portfolio_rets(sirali_v4[:10])
        v4_15_tl, v4_15_usd = get_portfolio_rets(sirali_v4[:15])

        results.append({
            "t0": t0, "t1": t1, "label": label,
            "v3_top10": sirali_v3[:10],
            "v3_top15": sirali_v3[:15],
            "v4_top10": sirali_v4[:10],
            "v4_top15": sirali_v4[:15],
            "mevcut": q["mevcut"],
            "rets_tl": q["rets_tl"],
            "rets_usd": q["rets_usd"],
            "r_xu_tl": q["r_xu_tl"],
            "r_xu_usd": q["r_xu_usd"],
            "v3_10_tl": v3_10_tl, "v3_10_usd": v3_10_usd,
            "v3_15_tl": v3_15_tl, "v3_15_usd": v3_15_usd,
            "v4_10_tl": v4_10_tl, "v4_10_usd": v4_10_usd,
            "v4_15_tl": v4_15_tl, "v4_15_usd": v4_15_usd,
        })
    return results


def run_test1_bootstrap(quarter_evals):
    """
    TEST 1 — BOOTSTRAP PERFORMANS KARŞILAŞTIRMASI
    2018-09 -> 2025-05 eğitim penceresinde 500 tohumlu block bootstrap (blok = 1 çeyrek).
    """
    print("\n" + "="*80)
    print(">> TEST 1 — BOOTSTRAP PERFORMANS KARŞILAŞTIRMASI (500 Tohum)")
    print("="*80)

    # 2018-09 -> 2025-05 (LOCK olmayan çeyrekler)
    train_evals = [e for e in quarter_evals if not e["label"].endswith("_LOCK")]
    print(f"Toplam Eğitim Çeyrek Sayısı: {len(train_evals)} ({train_evals[0]['label']} -> {train_evals[-1]['label']})")

    r_v3_10 = [e["v3_10_tl"] for e in train_evals]
    r_v4_15 = [e["v4_15_tl"] for e in train_evals]
    r_v4_10 = [e["v4_10_tl"] for e in train_evals]

    n_q = len(train_evals)
    n_boot = 500

    sh_v3_10 = []
    sh_v4_15 = []
    sh_v4_10 = []

    for seed in range(n_boot):
        rng = np.random.RandomState(seed + 1000)
        idx = rng.choice(n_q, size=n_q, replace=True)

        sh_v3_10.append(metrikler_quarterly([r_v3_10[i] for i in idx])["sharpe"])
        sh_v4_15.append(metrikler_quarterly([r_v4_15[i] for i in idx])["sharpe"])
        sh_v4_10.append(metrikler_quarterly([r_v4_10[i] for i in idx])["sharpe"])

    def get_stats(arr):
        return {
            "median": float(np.median(arr)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "p5": float(np.percentile(arr, 5)),
            "p95": float(np.percentile(arr, 95)),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
        }

    stats_v3_10 = get_stats(sh_v3_10)
    stats_v4_15 = get_stats(sh_v4_15)
    stats_v4_10 = get_stats(sh_v4_10)

    # Mann-Whitney U Testi (V4_15 vs V3_10)
    u_stat_15, p_val_mwu_15 = mannwhitneyu(sh_v4_15, sh_v3_10, alternative="greater")
    # Mann-Whitney U Testi (V4_10 vs V3_10)
    u_stat_10, p_val_mwu_10 = mannwhitneyu(sh_v4_10, sh_v3_10, alternative="greater")

    res = {
        "n_quarters": n_q,
        "n_boot": n_boot,
        "v3_10": stats_v3_10,
        "v4_15": stats_v4_15,
        "v4_10": stats_v4_10,
        "mwu_v4_15_vs_v3_10": {"u_stat": float(u_stat_15), "p_val": float(p_val_mwu_15), "is_sig": bool(p_val_mwu_15 < 0.05)},
        "mwu_v4_10_vs_v3_10": {"u_stat": float(u_stat_10), "p_val": float(p_val_mwu_10), "is_sig": bool(p_val_mwu_10 < 0.05)},
    }
    return res


def run_test2_regimes(quarter_evals):
    """
    TEST 2 — REJİM BAZINDA AYRI AYRI KARŞILAŞTIRMA
    - Dönem A: 2019-09 -> 2021-12 (Negatif reel faiz, boğa)
    - Dönem B: 2022-01 -> 2022-12 (Kur şoku, volatil)
    - Dönem C: 2023-01 -> 2024-06 (Pozitif reel faiz, sıkılaşma)
    - Dönem D: 2024-07 -> 2025-05 (Dezenflasyon, normalleşme)
    """
    print("\n" + "="*80)
    print(">> TEST 2 — REJİM BAZINDA AYRI AYRI KARŞILAŞTIRMA")
    print("="*80)

    regimes = {
        "Dönem A (2019-09 -> 2021-12)": (pd.Timestamp("2019-09-01"), pd.Timestamp("2021-12-01")),
        "Dönem B (2022-01 -> 2022-12)": (pd.Timestamp("2021-12-01"), pd.Timestamp("2022-12-01")),
        "Dönem C (2023-01 -> 2024-06)": (pd.Timestamp("2022-12-01"), pd.Timestamp("2024-06-01")),
        "Dönem D (2024-07 -> 2025-05)": (pd.Timestamp("2024-06-01"), pd.Timestamp("2025-06-01")),
    }

    results = {}

    for name, (d_start, d_end) in regimes.items():
        q_sub = [e for e in quarter_evals if e["t0"] >= d_start and e["t0"] < d_end]
        n_q = len(q_sub)
        print(f"\nRejim: {name} (Çeyrek Sayısı: {n_q})")

        r_v3_10 = [e["v3_10_tl"] for e in q_sub]
        r_v4_15 = [e["v4_15_tl"] for e in q_sub]
        r_v4_10 = [e["v4_10_tl"] for e in q_sub]
        r_xu = [e["r_xu_tl"] for e in q_sub]

        m_v3_10 = metrikler_quarterly(r_v3_10)
        m_v4_15 = metrikler_quarterly(r_v4_15)
        m_v4_10 = metrikler_quarterly(r_v4_10)
        m_xu = metrikler_quarterly(r_xu)

        # Placebo testleri (100 tohum)
        def run_placebo(k, target_sharpe):
            plac_sh = []
            for seed in range(100):
                rng = np.random.RandomState(seed + 200)
                p_rets = []
                for e in q_sub:
                    sec = rng.choice(e["mevcut"], size=k, replace=False)
                    r = float(np.mean([e["rets_tl"][s] for s in sec])) - KOMISYON
                    p_rets.append(r)
                plac_sh.append(metrikler_quarterly(p_rets)["sharpe"])
            p_val = float(np.mean([1 if s >= target_sharpe else 0 for s in plac_sh]))
            return p_val

        p_v3_10 = run_placebo(10, m_v3_10["sharpe"])
        p_v4_15 = run_placebo(15, m_v4_15["sharpe"])
        p_v4_10 = run_placebo(10, m_v4_10["sharpe"])

        results[name] = {
            "n_quarters": n_q,
            "v3_10": {**m_v3_10, "p_val": p_v3_10},
            "v4_15": {**m_v4_15, "p_val": p_v4_15},
            "v4_10": {**m_v4_10, "p_val": p_v4_10},
            "xu100": m_xu,
        }

    return results


def run_test3_lockbox(quarter_evals):
    """
    TEST 3 — KİLİT KUTU DÖNEMİ TEMİZ KARŞILAŞTIRMA (2025-06-01 -> 2026-09-07, 5 Çeyrek)
    """
    print("\n" + "="*80)
    print(">> TEST 3 — KİLİT KUTU DÖNEMİ TEMİZ KARŞILAŞTIRMA (5 Çeyrek)")
    print("="*80)

    lock_evals = [e for e in quarter_evals if e["label"].endswith("_LOCK")]
    print(f"Kilit Kutu Çeyrek Sayısı: {len(lock_evals)}")

    # TL ve USD
    r_v3_10_tl = [e["v3_10_tl"] for e in lock_evals]
    r_v3_10_usd = [e["v3_10_usd"] for e in lock_evals]

    r_v4_15_tl = [e["v4_15_tl"] for e in lock_evals]
    r_v4_15_usd = [e["v4_15_usd"] for e in lock_evals]

    r_v4_10_tl = [e["v4_10_tl"] for e in lock_evals]
    r_v4_10_usd = [e["v4_10_usd"] for e in lock_evals]

    r_v3_15_tl = [e["v3_15_tl"] for e in lock_evals]
    r_v3_15_usd = [e["v3_15_usd"] for e in lock_evals]

    r_xu_tl = [e["r_xu_tl"] for e in lock_evals]
    r_xu_usd = [e["r_xu_usd"] for e in lock_evals]

    m_v3_10_tl = metrikler_quarterly(r_v3_10_tl)
    m_v3_10_usd = metrikler_quarterly(r_v3_10_usd, rf_annual=0.045)

    m_v4_15_tl = metrikler_quarterly(r_v4_15_tl)
    m_v4_15_usd = metrikler_quarterly(r_v4_15_usd, rf_annual=0.045)

    m_v4_10_tl = metrikler_quarterly(r_v4_10_tl)
    m_v4_10_usd = metrikler_quarterly(r_v4_10_usd, rf_annual=0.045)

    m_v3_15_tl = metrikler_quarterly(r_v3_15_tl)
    m_v3_15_usd = metrikler_quarterly(r_v3_15_usd, rf_annual=0.045)

    m_xu_tl = metrikler_quarterly(r_xu_tl)
    m_xu_usd = metrikler_quarterly(r_xu_usd, rf_annual=0.045)

    res = {
        "v3_10": {
            "sharpe_tl": m_v3_10_tl["sharpe"], "cagr_tl": m_v3_10_tl["cagr"],
            "max_dd_tl": m_v3_10_tl["max_dd"], "kumulatif_tl": m_v3_10_tl["kumulatif"],
            "usd_kumulatif": m_v3_10_usd["kumulatif"], "usd_sharpe": m_v3_10_usd["sharpe"],
            "bist100_farki_tl": m_v3_10_tl["kumulatif"] - m_xu_tl["kumulatif"]
        },
        "v4_15": {
            "sharpe_tl": m_v4_15_tl["sharpe"], "cagr_tl": m_v4_15_tl["cagr"],
            "max_dd_tl": m_v4_15_tl["max_dd"], "kumulatif_tl": m_v4_15_tl["kumulatif"],
            "usd_kumulatif": m_v4_15_usd["kumulatif"], "usd_sharpe": m_v4_15_usd["sharpe"],
            "bist100_farki_tl": m_v4_15_tl["kumulatif"] - m_xu_tl["kumulatif"]
        },
        "v4_10": {
            "sharpe_tl": m_v4_10_tl["sharpe"], "cagr_tl": m_v4_10_tl["cagr"],
            "max_dd_tl": m_v4_10_tl["max_dd"], "kumulatif_tl": m_v4_10_tl["kumulatif"],
            "usd_kumulatif": m_v4_10_usd["kumulatif"], "usd_sharpe": m_v4_10_usd["sharpe"],
            "bist100_farki_tl": m_v4_10_tl["kumulatif"] - m_xu_tl["kumulatif"]
        },
        "v3_15": {
            "sharpe_tl": m_v3_15_tl["sharpe"], "cagr_tl": m_v3_15_tl["cagr"],
            "max_dd_tl": m_v3_15_tl["max_dd"], "kumulatif_tl": m_v3_15_tl["kumulatif"],
            "usd_kumulatif": m_v3_15_usd["kumulatif"], "usd_sharpe": m_v3_15_usd["sharpe"],
            "bist100_farki_tl": m_v3_15_tl["kumulatif"] - m_xu_tl["kumulatif"]
        },
        "xu100": {
            "sharpe_tl": m_xu_tl["sharpe"], "cagr_tl": m_xu_tl["cagr"],
            "max_dd_tl": m_xu_tl["max_dd"], "kumulatif_tl": m_xu_tl["kumulatif"],
            "usd_kumulatif": m_xu_usd["kumulatif"], "usd_sharpe": m_xu_usd["sharpe"]
        }
    }
    return res


def run_test4_turnover_and_cost(quarter_evals, fiyat_dict):
    """
    TEST 4 — TURNOVER VE MALİYET ETKİSİ (Aynı K=10 üzerinden)
    """
    print("\n" + "="*80)
    print(">> TEST 4 — TURNOVER VE MALİYET ETKİSİ (Aynı K=10 Karşılaştırması)")
    print("="*80)

    # 2019-09 -> 2025-05 arasındaki çeyrekler
    evals_train = [e for e in quarter_evals if e["t0"] >= pd.Timestamp("2019-09-01") and not e["label"].endswith("_LOCK")]

    v3_turnovers = []
    v4_turnovers = []
    v3_changed_counts = []
    v4_changed_counts = []

    for i in range(len(evals_train) - 1):
        # V3 Top 10
        s_v3_curr = set(evals_train[i]["v3_top10"])
        s_v3_next = set(evals_train[i+1]["v3_top10"])
        changed_v3 = len(s_v3_next - s_v3_curr)
        v3_changed_counts.append(changed_v3)
        v3_turnovers.append(changed_v3 / 10.0)

        # V4 Top 10
        s_v4_curr = set(evals_train[i]["v4_top10"])
        s_v4_next = set(evals_train[i+1]["v4_top10"])
        changed_v4 = len(s_v4_next - s_v4_curr)
        v4_changed_counts.append(changed_v4)
        v4_turnovers.append(changed_v4 / 10.0)

    avg_annual_turnover_v3 = float(np.mean(v3_turnovers) * 4.0 * 100.0)
    avg_annual_turnover_v4 = float(np.mean(v4_turnovers) * 4.0 * 100.0)

    avg_changed_v3 = float(np.mean(v3_changed_counts))
    avg_changed_v4 = float(np.mean(v4_changed_counts))

    # Brüt vs Net Getiriler
    # Brüt getiri (komisyonsuz)
    r_v3_gross = [e["v3_10_tl"] + KOMISYON for e in evals_train]
    r_v4_gross = [e["v4_10_tl"] + KOMISYON for e in evals_train]

    # Net getiri (30 bps baz)
    r_v3_net_30 = [e["v3_10_tl"] for e in evals_train]
    r_v4_net_30 = [e["v4_10_tl"] for e in evals_train]

    # Net getiri (50 bps yüksek sürtünme)
    r_v3_net_50 = [e["v3_10_tl"] - 0.002 for e in evals_train]
    r_v4_net_50 = [e["v4_10_tl"] - 0.002 for e in evals_train]

    m_v3_gross = metrikler_quarterly(r_v3_gross)
    m_v3_net_30 = metrikler_quarterly(r_v3_net_30)
    m_v3_net_50 = metrikler_quarterly(r_v3_net_50)

    m_v4_gross = metrikler_quarterly(r_v4_gross)
    m_v4_net_30 = metrikler_quarterly(r_v4_net_30)
    m_v4_net_50 = metrikler_quarterly(r_v4_net_50)

    # Düşük hacimli hisseler analizi (TERA, FORTE vb. volatil/sığ hisseler)
    # Hangi hisseler kaç kez portföye girdi?
    from collections import Counter
    v3_stock_counts = Counter([s for e in evals_train for s in e["v3_top10"]])
    v4_stock_counts = Counter([s for e in evals_train for s in e["v4_top10"]])

    volatile_suspects = ["TERA.IS", "FORTE.IS", "PASEU.IS", "ONCSM.IS", "SELEC.IS", "GUBRF.IS"]
    suspects_in_v3 = {s: v3_stock_counts.get(s, 0) for s in volatile_suspects}
    suspects_in_v4 = {s: v4_stock_counts.get(s, 0) for s in volatile_suspects}

    res = {
        "v3_10": {
            "avg_annual_turnover_pct": avg_annual_turnover_v3,
            "avg_stocks_changed_per_q": avg_changed_v3,
            "cagr_gross": m_v3_gross["cagr"],
            "cagr_net_30bps": m_v3_net_30["cagr"],
            "cagr_net_50bps": m_v3_net_50["cagr"],
            "drag_30bps": m_v3_gross["cagr"] - m_v3_net_30["cagr"],
            "drag_50bps": m_v3_gross["cagr"] - m_v3_net_50["cagr"],
            "sharpe_gross": m_v3_gross["sharpe"],
            "sharpe_net_30bps": m_v3_net_30["sharpe"],
            "sharpe_net_50bps": m_v3_net_50["sharpe"],
            "suspects_counts": suspects_in_v3
        },
        "v4_10": {
            "avg_annual_turnover_pct": avg_annual_turnover_v4,
            "avg_stocks_changed_per_q": avg_changed_v4,
            "cagr_gross": m_v4_gross["cagr"],
            "cagr_net_30bps": m_v4_net_30["cagr"],
            "cagr_net_50bps": m_v4_net_50["cagr"],
            "drag_30bps": m_v4_gross["cagr"] - m_v4_net_30["cagr"],
            "drag_50bps": m_v4_gross["cagr"] - m_v4_net_50["cagr"],
            "sharpe_gross": m_v4_gross["sharpe"],
            "sharpe_net_30bps": m_v4_net_30["sharpe"],
            "sharpe_net_50bps": m_v4_net_50["sharpe"],
            "suspects_counts": suspects_in_v4
        }
    }
    return res


def run_test5_stress_and_recovery(quarter_evals, fiyat_dict, seri_xu100):
    """
    TEST 5 — STRES TESTİ (PASEU TİPİ SENARYO & 2022 EN SERT DÖNEMİ)
    """
    print("\n" + "="*80)
    print(">> TEST 5 — STRES TESTİ (2022 En Sert Drawdown Dönemi ve Recovery)")
    print("="*80)

    # 2022 yılındaki 4 çeyrek
    evals_2022 = [e for e in quarter_evals if e["t0"] >= pd.Timestamp("2021-12-01") and e["t0"] < pd.Timestamp("2022-12-01")]

    # En kötü 3 aylık dönem: 2022 çeyrekleri arasında en düşük getirili çeyrek
    q_rets_v3 = {e["label"]: e["v3_10_tl"] for e in evals_2022}
    q_rets_v4_15 = {e["label"]: e["v4_15_tl"] for e in evals_2022}
    q_rets_v4_10 = {e["label"]: e["v4_10_tl"] for e in evals_2022}

    min_q_v3 = min(q_rets_v3.items(), key=lambda x: x[1])
    min_q_v4_15 = min(q_rets_v4_15.items(), key=lambda x: x[1])
    min_q_v4_10 = min(q_rets_v4_10.items(), key=lambda x: x[1])

    # 2022 çeyreklerinde portföydeki hisselerden kaç tanesi ardışık taban (Faz 0) kuralına takıldı?
    # Son 10 işlem gününde >=5 kez <= -0.095 kapanış
    taban_v3_counts = []
    taban_v4_15_counts = []
    taban_v4_10_counts = []

    for e in evals_2022:
        t0 = e["t0"]
        # V3 Top 10
        v3_hits = 0
        for s in e["v3_top10"]:
            p = fiyat_dict[s][fiyat_dict[s].index <= t0]
            tetik, _ = ardisik_taban_tespit(p, lookback_gun=10, min_taban=5, taban_esik=-0.095)
            if tetik: v3_hits += 1
        taban_v3_counts.append(v3_hits)

        # V4 Top 15
        v4_15_hits = 0
        for s in e["v4_top15"]:
            p = fiyat_dict[s][fiyat_dict[s].index <= t0]
            tetik, _ = ardisik_taban_tespit(p, lookback_gun=10, min_taban=5, taban_esik=-0.095)
            if tetik: v4_15_hits += 1
        taban_v4_15_counts.append(v4_15_hits)

        # V4 Top 10
        v4_10_hits = 0
        for s in e["v4_top10"]:
            p = fiyat_dict[s][fiyat_dict[s].index <= t0]
            tetik, _ = ardisik_taban_tespit(p, lookback_gun=10, min_taban=5, taban_esik=-0.095)
            if tetik: v4_10_hits += 1
        taban_v4_10_counts.append(v4_10_hits)

    # 2022 Drawdown ve Recovery Analizi
    # Tüm 2019-2025 serisinde 2022 krizinden sonra recovery kaç çeyrek sürdü?
    evals_post = [e for e in quarter_evals if e["t0"] >= pd.Timestamp("2019-09-01") and not e["label"].endswith("_LOCK")]

    def compute_recovery_quarters(returns):
        equity = np.cumprod(1.0 + np.array(returns))
        peaks = np.maximum.accumulate(equity)
        drawdowns = (equity - peaks) / peaks

        # En derin drawdown noktası
        worst_idx = np.argmin(drawdowns)
        worst_dd = float(drawdowns[worst_idx])

        # O tarihten itibaren zirveyi tekrar ne zaman geçti?
        peak_at_worst = peaks[worst_idx]
        rec_quarters = -1
        for i in range(worst_idx + 1, len(equity)):
            if equity[i] >= peak_at_worst:
                rec_quarters = i - worst_idx
                break
        return worst_dd, rec_quarters

    r_v3 = [e["v3_10_tl"] for e in evals_post]
    r_v4_15 = [e["v4_15_tl"] for e in evals_post]
    r_v4_10 = [e["v4_10_tl"] for e in evals_post]

    mdd_v3, rec_v3 = compute_recovery_quarters(r_v3)
    mdd_v4_15, rec_v4_15 = compute_recovery_quarters(r_v4_15)
    mdd_v4_10, rec_v4_10 = compute_recovery_quarters(r_v4_10)

    # 2022 içi en kötü çeyreğin max dd'si
    mdd_2022_v3 = metrikler_quarterly([e["v3_10_tl"] for e in evals_2022])["max_dd"]
    mdd_2022_v4_15 = metrikler_quarterly([e["v4_15_tl"] for e in evals_2022])["max_dd"]
    mdd_2022_v4_10 = metrikler_quarterly([e["v4_10_tl"] for e in evals_2022])["max_dd"]

    res = {
        "worst_quarter_2022": {
            "v3_10": {"quarter": min_q_v3[0], "return": min_q_v3[1]},
            "v4_15": {"quarter": min_q_v4_15[0], "return": min_q_v4_15[1]},
            "v4_10": {"quarter": min_q_v4_10[0], "return": min_q_v4_10[1]},
        },
        "max_dd_in_2022": {
            "v3_10": mdd_2022_v3,
            "v4_15": mdd_2022_v4_15,
            "v4_10": mdd_2022_v4_10,
        },
        "avg_taban_hits_per_q": {
            "v3_10": float(np.mean(taban_v3_counts)),
            "v4_15": float(np.mean(taban_v4_15_counts)),
            "v4_10": float(np.mean(taban_v4_10_counts)),
        },
        "all_time_mdd_and_recovery": {
            "v3_10": {"max_dd": mdd_v3, "recovery_quarters": rec_v3},
            "v4_15": {"max_dd": mdd_v4_15, "recovery_quarters": rec_v4_15},
            "v4_10": {"max_dd": mdd_v4_10, "recovery_quarters": rec_v4_10},
        }
    }
    return res


def main():
    print("="*90)
    print("V3 vs V4 ÇOK BOYUTLU VE KAPSAMLI KANTİTATİF MUKAYESE PROTOKOLÜ")
    print("="*90)

    # Dondurulmuş Modelleri Yükle
    v3_path = ROOT_DIR / "models" / "v3_ranking" / "winning_lgbm_ranker.joblib"
    v4_path = ROOT_DIR / "models" / "v4_ranking" / "winning_lgbm_ranker_v4.joblib"

    print(f"📦 V3 Modeli: {v3_path.name}")
    v3_obj = joblib.load(v3_path)
    model_v3 = v3_obj["model"]
    feats_v3 = v3_obj["feature_cols"]
    print(f"   Özellikler ({len(feats_v3)}): {feats_v3}")

    print(f"📦 V4 Modeli: {v4_path.name}")
    v4_obj = joblib.load(v4_path)
    model_v4 = v4_obj["model"]
    feats_v4 = v4_obj["feature_cols"]
    print(f"   Özellikler ({len(feats_v4)}): {feats_v4}")

    # Veri kümelerini oluştur
    quarters, fiyat_dict, seri_xu100, seri_usdtry = build_all_quarterly_data()
    print(f"Toplam Üretilen Çeyrek Sayısı: {len(quarters)}")

    # Her çeyrek için model tahminlerini ve getirilerini üret
    quarter_evals = evaluate_quarters_for_models(quarters, model_v3, feats_v3, model_v4, feats_v4)

    # TEST 1: Bootstrap
    res_t1 = run_test1_bootstrap(quarter_evals)

    # TEST 2: Rejimler
    res_t2 = run_test2_regimes(quarter_evals)

    # TEST 3: Kilit Kutu
    res_t3 = run_test3_lockbox(quarter_evals)

    # TEST 4: Turnover & Maliyet
    res_t4 = run_test4_turnover_and_cost(quarter_evals, fiyat_dict)

    # TEST 5: Stres & Recovery
    res_t5 = run_test5_stress_and_recovery(quarter_evals, fiyat_dict, seri_xu100)

    master_results = {
        "test1_bootstrap": res_t1,
        "test2_regimes": res_t2,
        "test3_lockbox": res_t3,
        "test4_turnover": res_t4,
        "test5_stress": res_t5,
    }

    def np_encoder(o):
        if isinstance(o, (np.integer, int)):
            return int(o)
        if isinstance(o, (np.floating, float)):
            return float(o)
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        if isinstance(o, pd.Timestamp):
            return str(o)
        return str(o)

    out_json = ROOT_DIR / "reports" / "v3_v4_kapsamli_karsilastirma.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(master_results, f, indent=2, ensure_ascii=False, default=np_encoder)
    print(f"\n[OK] Tüm ham test sonuçları JSON olarak kaydedildi: {out_json}")


if __name__ == "__main__":
    main()
