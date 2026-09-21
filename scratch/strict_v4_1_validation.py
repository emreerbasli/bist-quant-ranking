"""
scratch/strict_v4_1_validation.py
==================================
V4.1 ŞAMPİYON MODELİ İÇİN KATI KİLİT KUTU (LOCKBOX) DENETİM PROTOKOLÜ
Dönem: 2025-06-01 -> 2026-09-07 (5 Çeyrek / 15 Ay)

4 Kural ve Başarısızlık Taahhüdü:
  1. İstatistiksel anlamlılık: K=15 için 100 tohumlu Monte Carlo placebo testinde p < 0.10
  2. Ekonomik Sharpe primi: Model Sharpe > Placebo ortalaması + 0.20
  3. Piyasa üstünlüğü: Model kümülatif getirisi > BIST100 getirisi
  4. Portföy tutarlılığı: K=10 ve K=20'de de model placebo ortalamasının üzerinde kalmalı

Hüküm:
  - 4/4 geçerse: 'V4.1 TESCİLLENDİ VE ONAYLANDI'
  - 1 kural bile kalırsa: 'V4.1 REDDEDİLDİ. V3 AKTİF KALACAK'
"""

import sys
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

KOMISYON = 0.003  # Çeyreklik rotasyon için %0.3 kurumsal işlem maliyeti ve kayma


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


def main():
    print("=" * 90)
    print("V4.1 ŞAMPİYON MODELİ KATI KİLİT KUTU (LOCKBOX) DENETİM PROTOKOLÜ")
    print("Kilit Kutu Dönemi: 2025-06-01 -> 2026-09-07 (5 Çeyrek / 15 Ay)")
    print("=" * 90)

    # 1. Modeli Yükle
    model_path = ROOT_DIR / "models" / "v4_ranking" / "winning_lgbm_ranker_v4_1.joblib"
    if not model_path.exists():
        model_path = ROOT_DIR / "models" / "v4_ranking" / "winning_lgbm_ranker_v4.joblib"
    
    print(f"📦 Model Yükleniyor: {model_path.name}")
    v4_obj = joblib.load(model_path)
    model_v4_1 = v4_obj["model"]
    feats_v4_1 = v4_obj["feature_cols"]
    print(f"  Model Tanımı: {v4_obj.get('model_name', 'V4.1 LGBMRanker')} ({len(feats_v4_1)} Özellik)")
    print(f"  Özellik Listesi: {feats_v4_1}")

    # 2. Verileri Yükle
    print("\n📂 Piyasa Verileri ve PIT Bilanço Belleği Yükleniyor...")
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    hisseler = sorted(fiyat_dict.keys())
    print(f"  Evren: {len(hisseler)} hisse | PIT: {len(pit_bellek)} kayıt")

    # 3. Kilit Kutu Çeyrekleri
    lockbox_dates = [
        (pd.Timestamp("2025-06-01"), pd.Timestamp("2025-09-01"), "2025Q2"),
        (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-12-01"), "2025Q3"),
        (pd.Timestamp("2025-12-01"), pd.Timestamp("2026-03-01"), "2025Q4"),
        (pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-01"), "2026Q1"),
        (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-09-07"), "2026Q2 (Son Çeyrek)"),
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

        # 9 Faktör Hesabı
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)

        # V4.1 Resmi 9. Faktörü: z_reel_eps (Sektörel Z-Skoru + [-1.5, 1.5] Winsorize)
        df_q["z_reel_eps"] = hesapla_sektor_zscore(df_q, "reel_eps_raw", min_grup=4).fillna(0.0).clip(-1.5, 1.5)

        df_q["reel_faiz"]  = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        # Tahmin üret
        df_q["pred_v4_1"] = model_v4_1.predict(df_q[feats_v4_1])

        lockbox_data.append({
            "label": label, "t0": t0, "t1": t1,
            "rets_tl": rets_tl,
            "mevcut": mevcut,
            "r_xu_tl": r_xu_tl,
            "df": df_q
        })

    # BIST 100 Kümülatif Getirisi
    xu_rets = [d["r_xu_tl"] for d in lockbox_data]
    m_xu = metrikler_quarterly(xu_rets, rf_annual=0.18)
    xu_kumulatif = m_xu["kumulatif"]

    print(f"\n📊 BIST 100 Kilit Kutu Kümülatif Getirisi: %{xu_kumulatif*100:.2f} (Sharpe: {m_xu['sharpe']:.2f})")

    # 4. Monte Carlo Placebo ve 4 Kuralın Hesaplanması
    n_placebo = 100
    rng = np.random.default_rng(42)

    # -------------------------------------------------------------
    # KURAL 1 & 2: K=15 İncelemesi
    # -------------------------------------------------------------
    plac_rets_k15 = [[] for _ in range(n_placebo)]
    for d in lockbox_data:
        mevcut = d["mevcut"]
        for p_i in range(n_placebo):
            sec = rng.choice(mevcut, size=15, replace=False)
            r_p = float(np.mean([d["rets_tl"][s] for s in sec])) - KOMISYON
            plac_rets_k15[p_i].append(r_p)

    plac_sharpes_k15 = [metrikler_quarterly(p, 0.18)["sharpe"] for p in plac_rets_k15]
    plac_kumuls_k15  = [metrikler_quarterly(p, 0.18)["kumulatif"] for p in plac_rets_k15]
    mean_plac_sharpe_k15 = float(np.mean(plac_sharpes_k15))
    mean_plac_kumul_k15  = float(np.mean(plac_kumuls_k15))

    v4_1_rets_k15 = []
    for d in lockbox_data:
        sirali = d["df"].sort_values("pred_v4_1", ascending=False)["sembol"].tolist()
        r = float(np.mean([d["rets_tl"][s] for s in sirali[:15]])) - KOMISYON
        v4_1_rets_k15.append(r)

    m_v4_1_k15 = metrikler_quarterly(v4_1_rets_k15, 0.18)
    v4_1_sharpe_k15 = m_v4_1_k15["sharpe"]
    v4_1_kumul_k15  = m_v4_1_k15["kumulatif"]

    p_value_k15 = float(np.mean([1 if s >= v4_1_sharpe_k15 else 0 for s in plac_sharpes_k15]))
    sharpe_primi_k15 = v4_1_sharpe_k15 - mean_plac_sharpe_k15

    # -------------------------------------------------------------
    # KURAL 4: K=10 ve K=20 Portföy Tutarlılığı
    # -------------------------------------------------------------
    # K=10
    plac_rets_k10 = [[] for _ in range(n_placebo)]
    for d in lockbox_data:
        mevcut = d["mevcut"]
        for p_i in range(n_placebo):
            sec = rng.choice(mevcut, size=10, replace=False)
            r_p = float(np.mean([d["rets_tl"][s] for s in sec])) - KOMISYON
            plac_rets_k10[p_i].append(r_p)
    plac_kumuls_k10 = [metrikler_quarterly(p, 0.18)["kumulatif"] for p in plac_rets_k10]
    mean_plac_kumul_k10 = float(np.mean(plac_kumuls_k10))

    v4_1_rets_k10 = []
    for d in lockbox_data:
        sirali = d["df"].sort_values("pred_v4_1", ascending=False)["sembol"].tolist()
        r = float(np.mean([d["rets_tl"][s] for s in sirali[:10]])) - KOMISYON
        v4_1_rets_k10.append(r)
    v4_1_kumul_k10 = metrikler_quarterly(v4_1_rets_k10, 0.18)["kumulatif"]

    # K=20
    plac_rets_k20 = [[] for _ in range(n_placebo)]
    for d in lockbox_data:
        mevcut = d["mevcut"]
        for p_i in range(n_placebo):
            sec = rng.choice(mevcut, size=20, replace=False)
            r_p = float(np.mean([d["rets_tl"][s] for s in sec])) - KOMISYON
            plac_rets_k20[p_i].append(r_p)
    plac_kumuls_k20 = [metrikler_quarterly(p, 0.18)["kumulatif"] for p in plac_rets_k20]
    mean_plac_kumul_k20 = float(np.mean(plac_kumuls_k20))

    v4_1_rets_k20 = []
    for d in lockbox_data:
        sirali = d["df"].sort_values("pred_v4_1", ascending=False)["sembol"].tolist()
        r = float(np.mean([d["rets_tl"][s] for s in sirali[:20]])) - KOMISYON
        v4_1_rets_k20.append(r)
    v4_1_kumul_k20 = metrikler_quarterly(v4_1_rets_k20, 0.18)["kumulatif"]

    # -------------------------------------------------------------
    # 4 KURAL DEĞERLENDİRMESİ
    # -------------------------------------------------------------
    kural1_gecti = p_value_k15 < 0.10
    kural2_gecti = sharpe_primi_k15 > 0.20
    kural3_gecti = v4_1_kumul_k15 > xu_kumulatif
    kural4_gecti = (v4_1_kumul_k10 > mean_plac_kumul_k10) and (v4_1_kumul_k20 > mean_plac_kumul_k20)

    print("\n" + "=" * 90)
    print("KİLİT KUTU (2025-06-01 -> 2026-09-07) KATI DEĞERLENDİRME TABLOSU")
    print("=" * 90)
    print(f"{'Kural':<8} | {'Tanım':<25} | {'Eşik Değeri':<20} | {'Model Değeri':<18} | {'Sonuç':<10}")
    print("-" * 90)
    print(f"{'Kural 1':<8} | {'İstatistiksel Anlamlılık':<25} | {'p < 0.10':<20} | {f'p = {p_value_k15:.3f}':<18} | {'[GEÇTİ]' if kural1_gecti else '[KALDI]':<10}")
    print(f"{'Kural 2':<8} | {'Ekonomik Sharpe Primi':<25} | {'> Placebo + 0.20':<20} | {f'Sharpe: {v4_1_sharpe_k15:.2f} (+{sharpe_primi_k15:.2f})':<18} | {'[GEÇTİ]' if kural2_gecti else '[KALDI]':<10}")
    print(f"{'Kural 3':<8} | {'Piyasa Üstünlüğü':<25} | {'> BIST100 (%'+f'{xu_kumulatif*100:.1f})':<20} | {f'%{v4_1_kumul_k15*100:.1f}':<18} | {'[GEÇTİ]' if kural3_gecti else '[KALDI]':<10}")
    k10_txt = f"K10: %{v4_1_kumul_k10*100:.1f}>%{mean_plac_kumul_k10*100:.1f}"
    k20_txt = f"K20: %{v4_1_kumul_k20*100:.1f}>%{mean_plac_kumul_k20*100:.1f}"
    print(f"{'Kural 4':<8} | {'Portföy Tutarlılığı':<25} | {'K=10 ve K=20 > Plac.':<20} | {k10_txt:<18} | {'[GEÇTİ]' if kural4_gecti else '[KALDI]':<10}")
    print(f"{'':<8} | {'':<25} | {'':<20} | {k20_txt:<18} | {'':<10}")
    print("=" * 90)

    tum_kurallar_gecti = kural1_gecti and kural2_gecti and kural3_gecti and kural4_gecti

    print("\n" + "#" * 90)
    if tum_kurallar_gecti:
        print("🏆 SONUÇ: V4.1 TESCİLLENDİ VE ONAYLANDI")
        print("   4 Kuralın 4'ü de [GEÇTİ]. Model kilit kutuda istatistiksel ve ekonomik üstünlüğünü kanıtladı.")
    else:
        print("🛑 SONUÇ: V4.1 REDDEDİLDİ. V3 AKTİF KALACAK")
        print("   Başarısızlık taahhüdü devreye girdi. En az bir kural [KALDI] verdi.")
    print("#" * 90 + "\n")

    return 0 if tum_kurallar_gecti else 1


if __name__ == "__main__":
    sys.exit(main())
