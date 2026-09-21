"""
scratch/v5_holy_grail_test.py
=============================
V5 HOLY GRAIL (KUTSAL KÂSE) MİMARİSİ FİZİBİLİTE VE SİMÜLASYON TESTİ
-------------------------------------------------------------------
Kapsam:
  1. Ensemble (Kolektif Zeka):
     - V3 (8 Özellik) + V4.1 (9 Özellik: z_reel_eps)
     - Min-Max ölçekleme ile 50/50 hibrit Meta-Skor ve Top-10 (K=10) seçimi
  2. Risk Paritesi (Ters Volatilite):
     - T0 öncesi son 30 işlem gününün günlük getiri standart sapması (Lookahead-free)
     - W_i = (1 / sigma_i) / sum(1 / sigma_j)
  3. Dinamik Nakit ve Rejim (Regime-Aware Cash):
     - XU100 < SMA100(XU100) -> Ayı Rejimi: %50 Hisse / %50 Nakit (Yıllık %40 risksiz faiz)
     - XU100 >= SMA100 -> Boğa Rejimi: %100 Hisse
  4. Kilit Kutu Dönemi: 2025-06-01 -> 2026-09-07 (5 Çeyrek)
  5. Karşılaştırmalı Bloomberg Stili Kurumsal Performans Tablosu
-------------------------------------------------------------------
GÜVENLİK GARANTİSİ: Tamamen SALT-OKUNUR (read-only). Hiçbir üretim dosyasına yazmaz.
"""

import sys
import warnings
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Set

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
from models.v4_ranking.ranking_pipeline_v4 import LGBMRankingPipelineV4

KOMISYON = 0.003
RF_ANNUAL = 0.18
NAKIT_MEVDUAT_ANNUAL = 0.40  # Riskli rejimde mevduat park faizi (%40 yıllık)


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


def min_max_scale(arr: np.ndarray) -> np.ndarray:
    """Dizi değerlerini [0, 1] aralığına normalize eder."""
    arr = np.array(arr, dtype=float)
    a_min = np.min(arr)
    a_max = np.max(arr)
    if (a_max - a_min) < 1e-8:
        return np.zeros_like(arr)
    return (arr - a_min) / (a_max - a_min)


def select_top_k_scored(df_scored: pd.DataFrame,
                        score_col: str,
                        k: int = 10,
                        fiyat_dict: Optional[Dict[str, pd.Series]] = None,
                        excluded_semboller: Optional[Set[str]] = None) -> List[str]:
    """
    Belirli bir skor kolonuna (score_v3, score_v4, meta_score) göre
    Faz 0 Taban, Likidite ve Sektör kısıtlarını işleterek Top-K hisseyi seçer.
    """
    all_excluded = set(excluded_semboller or set())
    if fiyat_dict:
        try:
            from bot.kap_filter import ardisik_taban_tespit
            for s, p_seri in fiyat_dict.items():
                tetik, cnt = ardisik_taban_tespit(p_seri, lookback_gun=10, min_taban=5, taban_esik=-0.095)
                if tetik:
                    all_excluded.add(s)
        except Exception:
            pass

    df_ranked = df_scored.sort_values(score_col, ascending=False).reset_index(drop=True).copy()
    df_ranked["sektor_v2"] = df_ranked["sembol"].map(lambda s: cfg.HISSE_SEKTOR_V2.get(s, "DIGER"))

    likidite_esik_m = cfg.LIKIDITE_MIN_TL_HACIM_V2 / 1e6
    vip = set(cfg.VIP_HISSELER)

    sektor_sayac: Dict[str, int] = {}
    secilen: List[str] = []

    for _, row in df_ranked.iterrows():
        if len(secilen) >= k:
            break
        s = row["sembol"]
        if s in all_excluded:
            continue

        # Likidite kontrolü
        if s not in vip:
            try:
                clean = s.replace(".", "_")
                p_file = cfg.DATA_RAW / f"{clean}.parquet"
                if p_file.exists():
                    sub = pd.read_parquet(p_file).tail(60)
                    hacim_m = float((sub["volume"] * sub["close"]).mean()) / 1e6
                    if hacim_m < likidite_esik_m:
                        continue
            except Exception:
                pass

        sektor = row["sektor_v2"]
        max_pos = cfg.MAX_SEKTOR_POZISYON_V2.get(sektor, cfg.MAX_SEKTOR_VARSAYILAN_V2)
        mevcut = sektor_sayac.get(sektor, 0)

        if mevcut < max_pos:
            secilen.append(s)
            sektor_sayac[sektor] = mevcut + 1

    return secilen


def main():
    print("=" * 115)
    print("🏛️ V5 HOLY GRAIL MİMARİSİ FİZİBİLİTE & STRES TESTİ (LOCKBOX 2025-06 -> 2026-09)")
    print("=" * 115)

    print("Veri tabanı ve modeller yükleniyor...")
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    pipeline_v4 = LGBMRankingPipelineV4()

    # V3 ve V4.1 Modellerini Yükle
    v3_joblib = ROOT_DIR / "models" / "v3_ranking" / "winning_lgbm_ranker.joblib"
    v4_joblib = ROOT_DIR / "models" / "v4_ranking" / "winning_lgbm_ranker_v4_1.joblib"
    if not v4_joblib.exists():
        v4_joblib = ROOT_DIR / "models" / "v4_ranking" / "winning_lgbm_ranker_v4.joblib"

    v3_obj = joblib.load(v3_joblib)
    v4_obj = joblib.load(v4_joblib)

    m_v3 = v3_obj["model"]
    f_v3 = v3_obj["feature_cols"]

    m_v4 = v4_obj["model"]
    f_v4 = v4_obj["feature_cols"]

    print(f"✅ V3 Modeli: {len(f_v3)} Özellik ({f_v3})")
    print(f"✅ V4.1 Modeli: {len(f_v4)} Özellik ({f_v4})")

    lockbox_quarters = [
        (pd.Timestamp("2025-06-01"), pd.Timestamp("2025-09-01"), "2025Q2"),
        (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-12-01"), "2025Q3"),
        (pd.Timestamp("2025-12-01"), pd.Timestamp("2026-03-01"), "2025Q4"),
        (pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-01"), "2026Q1"),
        (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-09-07"), "2026Q2"),
    ]

    hisseler = sorted(fiyat_dict.keys())

    # Sonuç Taşıyıcıları
    ret_v3 = []
    ret_v4 = []
    ret_ens_eq = []       # V5-A: Ensemble + Eşit Ağırlık
    ret_ens_rp = []       # V5-B: Ensemble + Ters Volatilite
    ret_ens_cash50 = []   # V5-C: Ensemble + Eşit Ağırlık + Dinamik Nakit %50
    ret_holy_grail50 = [] # V5-D: Ensemble + Ters Volatilite + Dinamik Nakit %50 (Full Holy Grail)
    ret_holy_grail40 = [] # V5-E: Ensemble + Ters Volatilite + Dinamik Nakit %40 Hisse / %60 Nakit
    ret_bist100 = []

    quarterly_details = []

    q_cash_ret = (1.0 + NAKIT_MEVDUAT_ANNUAL) ** 0.25 - 1.0  # Çeyreklik mevduat faizi (~%8.78)

    for idx, (t0, t1, label) in enumerate(lockbox_quarters):
        # 1. BIST 100 Getirisi ve SMA100 Rejim Tespiti
        sub_xu = seri_xu100[seri_xu100.index <= t0]
        px_xu0 = float(sub_xu.iloc[-1])
        sma100_xu = float(sub_xu.tail(100).mean())
        is_bear = (px_xu0 < sma100_xu)
        regime_label = "🐻 AYI / RİSKLİ" if is_bear else "🐂 BOĞA"

        # BIST 100 Çeyrek Getirisi
        px_all = seri_xu100[(seri_xu100.index >= t0) & (seri_xu100.index <= t1)]
        r_xu = float((px_all.iloc[-1] - px_all.iloc[0]) / px_all.iloc[0]) if len(px_all) >= 2 else 0.0
        ret_bist100.append(r_xu)

        # 2. Hisselerin Gerçekleşen Çeyrek Getirileri
        rets_tl = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets_tl[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        # 3. t0 Anındaki Kesin Point-in-Time Özellikler
        df_feat = pipeline_v4.compute_features(t0, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
        df_valid = df_feat[df_feat["sembol"].isin(rets_tl.keys())].copy().reset_index(drop=True)

        # 4. Ayrı Tahmin Skorları Üretimi
        s_v3_raw = m_v3.predict(df_valid[f_v3])
        s_v4_raw = m_v4.predict(df_valid[f_v4])

        df_valid["score_v3"] = s_v3_raw
        df_valid["score_v4"] = s_v4_raw

        # Min-Max Normalizasyonu
        df_valid["norm_v3"] = min_max_scale(s_v3_raw)
        df_valid["norm_v4"] = min_max_scale(s_v4_raw)

        # 5. Kolektif Zeka (Meta-Skor)
        df_valid["meta_score"] = 0.50 * df_valid["norm_v3"] + 0.50 * df_valid["norm_v4"]

        # 6. Doğru Skor Kolonuyla Seçimler (K=10):
        sel_v3 = select_top_k_scored(df_valid, "score_v3", k=10, fiyat_dict=fiyat_dict)
        sel_v4 = select_top_k_scored(df_valid, "score_v4", k=10, fiyat_dict=fiyat_dict)
        sel_meta = select_top_k_scored(df_valid, "meta_score", k=10, fiyat_dict=fiyat_dict)

        # 7. Risk Paritesi (Ters Volatilite) Ağırlıklarının Hesaplanması (Lookahead-Free)
        inv_vols = []
        for s in sel_meta:
            # t0 öncesindeki son 30 işlem günü
            p_hist = fiyat_dict[s][fiyat_dict[s].index <= t0].tail(30)
            if len(p_hist) >= 5:
                daily_rets = p_hist.pct_change().dropna()
                vol = float(daily_rets.std()) if len(daily_rets) > 1 else 0.02
            else:
                vol = 0.02
            vol = max(1e-6, vol)
            inv_vols.append(1.0 / vol)

        inv_vol_sum = sum(inv_vols)
        rp_weights = [iv / inv_vol_sum for iv in inv_vols]

        # 8. Portföy Getirilerinin Hesaplanması
        # Saf V3 (Eşit Ağırlık)
        r_v3_q = float(np.mean([rets_tl[s] for s in sel_v3])) - KOMISYON
        # Saf V4.1 (Eşit Ağırlık)
        r_v4_q = float(np.mean([rets_tl[s] for s in sel_v4])) - KOMISYON

        # V5-A: Ensemble + Eşit Ağırlık (100% Hisse)
        r_ens_eq_q = float(np.mean([rets_tl[s] for s in sel_meta])) - KOMISYON

        # V5-B: Ensemble + Ters Volatilite (100% Hisse)
        r_ens_rp_q = float(sum(w * rets_tl[s] for w, s in zip(rp_weights, sel_meta))) - KOMISYON

        # V5-C: Ensemble + Eşit Ağırlık + Dinamik Nakit (%50 Hisse / %50 Nakit Ayıda)
        if is_bear:
            r_ens_cash50_q = 0.50 * r_ens_eq_q + 0.50 * q_cash_ret
            r_holy50_q = 0.50 * r_ens_rp_q + 0.50 * q_cash_ret
            r_holy40_q = 0.40 * r_ens_rp_q + 0.60 * q_cash_ret
        else:
            r_ens_cash50_q = r_ens_eq_q
            r_holy50_q = r_ens_rp_q
            r_holy40_q = r_ens_rp_q

        ret_v3.append(r_v3_q)
        ret_v4.append(r_v4_q)
        ret_ens_eq.append(r_ens_eq_q)
        ret_ens_rp.append(r_ens_rp_q)
        ret_ens_cash50.append(r_ens_cash50_q)
        ret_holy_grail50.append(r_holy50_q)
        ret_holy_grail40.append(r_holy40_q)

        quarterly_details.append({
            "label": label, "t0": t0, "is_bear": is_bear, "regime": regime_label,
            "px_xu": px_xu0, "sma100": sma100_xu,
            "r_xu": r_xu, "r_v3": r_v3_q, "r_v4": r_v4_q,
            "r_ens_eq": r_ens_eq_q, "r_ens_rp": r_ens_rp_q,
            "r_holy50": r_holy50_q,
            "meta_top10": sel_meta,
            "v3_top10": sel_v3,
            "v4_top10": sel_v4,
            "min_weight": min(rp_weights), "max_weight": max(rp_weights)
        })

    # Metrik Hesaplamaları
    m_v3 = metrikler_quarterly(ret_v3, RF_ANNUAL)
    m_v4 = metrikler_quarterly(ret_v4, RF_ANNUAL)
    m_ens_eq = metrikler_quarterly(ret_ens_eq, RF_ANNUAL)
    m_ens_rp = metrikler_quarterly(ret_ens_rp, RF_ANNUAL)
    m_ens_c50 = metrikler_quarterly(ret_ens_cash50, RF_ANNUAL)
    m_holy50 = metrikler_quarterly(ret_holy_grail50, RF_ANNUAL)
    m_holy40 = metrikler_quarterly(ret_holy_grail40, RF_ANNUAL)
    m_xu = metrikler_quarterly(ret_bist100, RF_ANNUAL)

    # 1. ÇEYREKLİK PERFORMANS VE REJİM DÖKÜMÜ
    print("\n" + "─" * 125)
    print("1. ÇEYREKLİK REJİM VE GETİRİ DÖKÜMÜ (2025Q2 -> 2026Q2)")
    print("─" * 125)
    print(f"{'Çeyrek':<10} | {'Makro Rejim (SMA100)':<22} | {'Saf V3 (K=10)':<15} | {'Saf V4.1 (K=10)':<15} | {'V5-Ensemble':<15} | {'V5-Holy Grail':<15} | {'BIST 100'}")
    print("─" * 125)
    for q in quarterly_details:
        lbl = q["label"]
        reg = f"{q['regime']} (Px:{q['px_xu']:.0f}/SMA:{q['sma100']:.0f})"
        print(f"{lbl:<10} | {reg:<22} | %{q['r_v3']*100:>13.2f} | %{q['r_v4']*100:>13.2f} | %{q['r_ens_eq']*100:>13.2f} | %{q['r_holy50']*100:>13.2f} | %{q['r_xu']*100:>8.2f}")
    print("─" * 125)

    # 2. BÜYÜK KARŞILAŞTIRMA TABLOSU (BLOOMBERG TERMINAL STYLE)
    print("\n" + "█" * 125)
    print("2. BÜYÜK KURUMSAL MUKAYESE TABLOSU: SAF V3 vs SAF V4.1 vs V5 VARYASYONLARI vs HOLY GRAIL")
    print("█" * 125)
    print(f"{'Strateji Mimarisi':<46} | {'Kümülatif':<12} | {'CAGR':<10} | {'Sharpe':<8} | {'Max DD':<9} | {'Son Çeyrek':<12} | {'Değerlendirme'}")
    print("─" * 125)

    rows_summary = [
        ("Saf V3 (Referans: K=10, Eşit Ağırlık)", m_v3, ret_v3[-1], "Mevcut Canlı Standart"),
        ("Saf V4.1 Şampiyon (K=10, Eşit Ağırlık)", m_v4, ret_v4[-1], "Kilit Kutu Fatihi"),
        ("V5-A: Kolektif Zeka (V3+V4.1 Meta-Skor)", m_ens_eq, ret_ens_eq[-1], "Yalnızca Ensemble"),
        ("V5-B: Ensemble + Ters Volatilite (Risk Paritesi)", m_ens_rp, ret_ens_rp[-1], "Risk Parity Etkisi"),
        ("V5-C: Ensemble + Dinamik Nakit (%50 Ayıda)", m_ens_c50, ret_ens_cash50[-1], "SMA100 Nakit Kalkanı"),
        ("V5-Holy Grail (Ensemble + Ters Vol + %50 Nakit)", m_holy50, ret_holy_grail50[-1], "★ Kutsal Kâse Modeli"),
        ("V5-Holy Grail (Ensemble + Ters Vol + %60 Nakit)", m_holy40, ret_holy_grail40[-1], "Defansif Nakit Ağırlıklı"),
        ("BIST 100 Endeksi (Kıstas)", m_xu, ret_bist100[-1], "Piyasa Benchmark"),
    ]

    for name, m, q5, desc in rows_summary:
        kum_str = f"%{m['kumulatif']*100:>10.1f}"
        cagr_str = f"%{m['cagr']*100:>8.1f}"
        sh_str = f"{m['sharpe']:>7.2f}"
        dd_str = f"%{m['max_dd']*100:>7.1f}"
        q5_str = f"%{q5*100:>10.2f}"
        highlight = " 🚀" if m['sharpe'] >= 4.0 else (" ⭐" if m['sharpe'] >= 3.0 else "")
        print(f"{name:<46} | {kum_str} | {cagr_str} | {sh_str}{highlight} | {dd_str} | {q5_str} | {desc}")

    print("█" * 125)

    # 3. HİPOTEZ VE KANTİTATİF ANALİZ ÇIKARIMLARI
    print("\n" + "=" * 105)
    print("🎯 BİLGİSEL OTOPSİ & HİPOTEZ DOĞRULAMA (QUANTITATIVE FINDINGS):")
    print("=" * 105)

    # A. Ensemble Katkısı:
    delta_ens_sh = m_ens_eq["sharpe"] - max(m_v3["sharpe"], m_v4["sharpe"])
    delta_ens_kum = (m_ens_eq["kumulatif"] - max(m_v3["kumulatif"], m_v4["kumulatif"])) * 100.0
    print(f"1. ENSEMBLE (KOLEKTİF ZEKA) ETKİSİ:")
    print(f"   • V3 Sharpe: {m_v3['sharpe']:.2f} (%{m_v3['kumulatif']*100:.1f})")
    print(f"   • V4.1 Sharpe: {m_v4['sharpe']:.2f} (%{m_v4['kumulatif']*100:.1f})")
    print(f"   • Ensemble Sharpe: {m_ens_eq['sharpe']:.2f} (%{m_ens_eq['kumulatif']*100:.1f})")
    print(f"   • Delta: {delta_ens_sh:+.2f} Sharpe | {delta_ens_kum:+.1f} puan kümülatif getiri")

    # B. Risk Paritesi (Ters Volatilite) Katkısı:
    delta_rp_sh = m_ens_rp["sharpe"] - m_ens_eq["sharpe"]
    delta_rp_ret = (m_ens_rp["kumulatif"] - m_ens_eq["kumulatif"]) * 100.0
    print(f"\n2. RİSK PARİTESİ (TERS VOLATİLİTE) ETKİSİ:")
    print(f"   • Eşit Ağırlık Getiri: %{m_ens_eq['kumulatif']*100:.1f} (Sharpe: {m_ens_eq['sharpe']:.2f})")
    print(f"   • Ters Volatilite Getiri: %{m_ens_rp['kumulatif']*100:.1f} (Sharpe: {m_ens_rp['sharpe']:.2f})")
    print(f"   • Fark: {delta_rp_ret:+.1f} puan kümülatif getiri | {delta_rp_sh:+.2f} Sharpe primi")
    if delta_rp_sh < 0:
        print("   • ⚠️ KURUMSAL DERS: PROJECT_MEMORY.md'deki 'Ters Volatilite Getiriyi Düşürür' bulgusu burada da doğrulandı!")
        print("     BIST'te volatilite sadece risk değil, büyüme primidir; düşük volatiliteye sermaye yığmak kazanan hisselerin kârını budamaktadır.")

    # C. Dinamik Nakit ve SMA100 Rejim Kalkanı Katkısı:
    delta_cash_sh = m_ens_c50["sharpe"] - m_ens_eq["sharpe"]
    print(f"\n3. DİNAMİK NAKİT & REJİM KALKANI ETKİSİ (SMA100):")
    print(f"   • 5 Çeyreğin {sum(q['is_bear'] for q in quarterly_details)} çeyreği 'Ayı Rejimi' olarak işaretlendi.")
    print(f"   • Nakitsiz Sharpe: {m_ens_eq['sharpe']:.2f} -> %50 Nakitli Sharpe: {m_ens_c50['sharpe']:.2f} ({delta_cash_sh:+.2f} Delta)")

    # D. 4.00+ Sharpe Hedefi Değerlendirmesi:
    print(f"\n4. 4.00+ SHARPE HEDEFİ FİZİBİLİTE RAPORU:")
    best_strategy = sorted(rows_summary[:-1], key=lambda x: x[1]["sharpe"], reverse=True)[0]
    print(f"   • Kilit Kutuda En Yüksek Sharpe Üreten Model: '{best_strategy[0]}'")
    print(f"   • Ulaşılan Tepe Sharpe Oranı: {best_strategy[1]['sharpe']:.2f}")
    if best_strategy[1]['sharpe'] >= 4.0:
        print("   • SONUÇ: 4.00+ Sharpe BARAJINI AŞTI! İlgili strateji kurumsal ligde parlamaktadır.")
    else:
        print(f"   • SONUÇ: 4.00 barajına {4.00 - best_strategy[1]['sharpe']:.2f} kaldı.")

    print("=" * 105)


if __name__ == "__main__":
    main()
