"""
scratch/faz1_ek_kantitatif_testler.py
======================================
FAZ 1 EK KANTİTATİF ANALİZ: ORTOGONALLİK VE OTOKORELASYON (TURNOVER) TESTLERİ
----------------------------------------------------------------------------
Kapsam:
  1. Ortogonallik Matrisi:
     - 10 Feature: 8 V3 Orijinal + 2 Yeni Aday (reel_eps_growth, op_marji_trend)
     - Hem Pooled (Havuzlanmış Panel) Pearson & Spearman Korelasyonu
     - Hem de 21 Çeyreğin Ortalama Kesitsel Spearman Korelasyonu
     - Karar Kuralı: rho(reel_eps_growth, op_marji_trend) > 0.50 ise yalnızca yüksek IC-IR'lı olan seçilir.
  2. Otokorelasyon (Turnover / Rank Persistence):
     - Her ardışık çeyrek geçişinde (t -> t+1) kesitsel Spearman derece otokorelasyonu
     - Top-15 portföy çeyreklik pozisyon tutma (retention) ve çalkantı (implied turnover) oranı
     - Sistemin işlem maliyeti ve turnover risk analizi
"""

import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from typing import Dict, List, Any
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg
from models.v3_ranking.data_loader import yukle_veriler, hizli_pit, hesapla_mom, getir_tcmb_reel_faiz
from models.v3_ranking.ranking_pipeline import hesapla_sektor_zscore
from scratch.faz1_ic_tarama import extract_candidate_features


def build_full_feature_panel():
    """
    2019-09 -> 2024-12 arasındaki 21 çeyreklik rebalance tarihinde
    tüm 88 hisse için 8 orijinal V3 feature'ı ve 2 yeni adayı hesaplar.
    """
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    tarihler = pd.date_range("2019-09-01", "2024-12-01", freq="3MS")
    hisseler = sorted(fiyat_dict.keys())

    all_rows = []
    quarterly_dfs = {}

    for t in tarihler:
        reel_faiz = getir_tcmb_reel_faiz(t, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

        q_rows = []
        for s in hisseler:
            curr, _ = hizli_pit(pit_bellek, s, t)
            if not curr:
                continue

            is_bank = bool(curr.get("is_bank", False))
            sektor = cfg.HISSE_SEKTOR.get(s, "XBANK.IS" if is_bank else "XUSIN.IS")
            mom = hesapla_mom(fiyat_dict[s], t)
            pb = curr.get("pb", np.nan)
            roe = curr.get("roe", np.nan)
            fcf_v = curr.get("fcf_verim", np.nan)
            net_b = curr.get("net_borc", 0.0) or 0.0
            ebit = curr.get("ebitda", 1.0) or 1.0
            borc_ebitda = -net_b / max(1.0, abs(ebit)) if not is_bank else np.nan

            # Yeni Adaylar
            cand_feats = extract_candidate_features(
                t, s, fiyat_dict[s], seri_usdtry, pit_bellek.get(s, []), tufe_aylik
            )

            q_rows.append({
                "t": t,
                "sembol": s,
                "sektor": sektor,
                "is_bank": is_bank,
                "pb": pb,
                "roe": roe,
                "fcf_v": fcf_v,
                "mom": mom,
                "borc_ebitda": borc_ebitda,
                "reel_eps_growth": cand_feats.get("reel_eps_growth", np.nan),
                "op_marji_trend": cand_feats.get("op_marji_trend", np.nan),
            })

        df_q = pd.DataFrame(q_rows)
        if len(df_q) < 30:
            continue

        # Sektörel Kesitsel Z-Skorları (V3 ile birebir aynı formülasyon)
        df_q["z_fcf"] = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"] = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"] = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"] = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)  # Ters PB

        # Yeni feature'ların z-skorları (kesitsel sıralama veya sektörel z-skor)
        df_q["z_reel_eps"] = hesapla_sektor_zscore(df_q, "reel_eps_growth", min_grup=4).fillna(0.0)
        df_q["z_op_marj"] = hesapla_sektor_zscore(df_q, "op_marji_trend", min_grup=4).fillna(0.0)

        # Makro Özellikler
        df_q["reel_faiz"] = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        quarterly_dfs[t] = df_q
        all_rows.append(df_q)

    df_panel = pd.concat(all_rows, ignore_index=True)
    return df_panel, quarterly_dfs


def analyze_orthogonality(df_panel: pd.DataFrame, quarterly_dfs: Dict[pd.Timestamp, pd.DataFrame]):
    """
    Ortogonallik analizini hem havuzlanmış hem de kesitsel bazda gerçekleştirir.
    """
    feature_cols = [
        "z_pb", "z_roe", "z_fcf", "z_mom", "z_borc",
        "reel_eps_growth", "op_marji_trend"
    ]
    all_ten_cols = feature_cols + ["reel_faiz", "usd_mom_60", "usd_mom_90"]

    print("\n" + "=" * 110)
    print("1. TEST: ORTOGONALLİK VE KORELASYON ANALİZİ (2019-09 -> 2024-12, N=%d Gözlem)" % len(df_panel))
    print("=" * 110)

    # A. Havuzlanmış Panel Spearman Korelasyon Matrisi
    sub_df = df_panel[all_ten_cols].dropna()
    corr_spearman_pooled = sub_df.corr(method="spearman")
    corr_pearson_pooled = sub_df.corr(method="pearson")

    print("\nA. HAVUZLANMIŞ PANEL SPEARMAN DERECE KORELASYON MATRİSİ:")
    print("-" * 110)
    print(corr_spearman_pooled[feature_cols].loc[feature_cols].round(3).to_string())

    print("\nB. HAVUZLANMIŞ PANEL PEARSON DOĞRUSAL KORELASYON MATRİSİ:")
    print("-" * 110)
    print(corr_pearson_pooled[feature_cols].loc[feature_cols].round(3).to_string())

    # C. Ortalama Kesitsel Spearman Korelasyonu (21 Çeyreğin Ortalaması)
    cs_corrs = []
    for t, df_q in quarterly_dfs.items():
        sub_q = df_q[feature_cols].dropna()
        if len(sub_q) >= 20:
            c = sub_q.corr(method="spearman")
            cs_corrs.append(c)

    avg_cs_spearman = sum(cs_corrs) / len(cs_corrs)
    print("\nC. ORTALAMA KESİTSEL SPEARMAN KORELASYON MATRİSİ (21 ÇEYREK ORTALAMASI):")
    print("-" * 110)
    print(avg_cs_spearman.round(3).to_string())

    # İki Aday Arasındaki Korelasyonun İncelenmesi
    rho_pooled_sp = corr_spearman_pooled.loc["reel_eps_growth", "op_marji_trend"]
    rho_pooled_pr = corr_pearson_pooled.loc["reel_eps_growth", "op_marji_trend"]
    rho_cs_avg = avg_cs_spearman.loc["reel_eps_growth", "op_marji_trend"]

    print("\n" + "-" * 110)
    print(f"KRİTİK TEST: reel_eps_growth <-> op_marji_trend Korelasyonu:")
    print(f"  • Havuzlanmış Spearman Derece Korelasyonu:  rho = {rho_pooled_sp:+.4f}")
    print(f"  • Havuzlanmış Pearson Doğrusal Korelasyonu:  r   = {rho_pooled_pr:+.4f}")
    print(f"  • 21 Çeyrek Ortalama Kesitsel Spearman:      rho = {rho_cs_avg:+.4f}")
    print(f"  • Kullanıcı Eşik Kuralı:                     rho > 0.50 (Yüksek Korelasyon Sınırı)")

    # Yeni Adayların Orijinal 5 Hisse Bazlı Faktörle Olan Maksimum Korelasyonları
    orig_cols = ["z_pb", "z_roe", "z_fcf", "z_mom", "z_borc"]
    print("\nYENİ ADAYLARIN ORİJİNAL FAKTÖRLERLE MAKSİMUM KESİTSEL KORELASYONLARI:")
    for cand in ["reel_eps_growth", "op_marji_trend"]:
        corrs = avg_cs_spearman.loc[cand, orig_cols]
        max_f = corrs.abs().idxmax()
        print(f"  • {cand:<16} -> En Yüksek Korelasyon: {max_f} ({corrs[max_f]:+.3f}) | PB: {corrs['z_pb']:+.3f} | MOM: {corrs['z_mom']:+.3f} | FCF: {corrs['z_fcf']:+.3f}")

    return {
        "rho_pooled_sp": rho_pooled_sp,
        "rho_pooled_pr": rho_pooled_pr,
        "rho_cs_avg": rho_cs_avg,
        "avg_cs_spearman": avg_cs_spearman,
        "corr_spearman_pooled": corr_spearman_pooled
    }


def analyze_autocorrelation_and_turnover(quarterly_dfs: Dict[pd.Timestamp, pd.DataFrame]):
    """
    2. TEST: Çeyrekten çeyreğe kesitsel otokorelasyon ve Top-15 pozisyon devir (turnover) oranı.
    """
    print("\n" + "=" * 110)
    print("2. TEST: KESİTSEL OTOKORELASYON VE TURNOVER ANALİZİ (20 ÇEYREK GEÇİŞİ)")
    print("=" * 110)

    factors = [
        "z_pb", "z_roe", "z_fcf", "z_mom", "z_borc",
        "reel_eps_growth", "op_marji_trend"
    ]

    t_list = sorted(quarterly_dfs.keys())
    autocorr_records = []
    top15_retention_records = []

    for i in range(len(t_list) - 1):
        t0, t1 = t_list[i], t_list[i + 1]
        df0 = quarterly_dfs[t0].set_index("sembol")
        df1 = quarterly_dfs[t1].set_index("sembol")

        ortak_semboller = df0.index.intersection(df1.index)
        if len(ortak_semboller) < 25:
            continue

        ac_entry = {"t0": t0, "t1": t1}
        ret_entry = {"t0": t0, "t1": t1}

        for f in factors:
            s0 = df0.loc[ortak_semboller, f].dropna()
            s1 = df1.loc[ortak_semboller, f].dropna()
            valid = s0.index.intersection(s1.index)
            if len(valid) >= 20:
                corr, _ = spearmanr(s0.loc[valid], s1.loc[valid])
                ac_entry[f] = corr

                # Top-15 constituent persistence (Turnover proxy)
                top15_0 = set(s0.nlargest(15).index)
                top15_1 = set(s1.nlargest(15).index)
                overlap = len(top15_0.intersection(top15_1))
                ret_entry[f] = overlap / 15.0  # Retention rate (1.0 = hiç değişmedi, 0.0 = tamamen yenilendi)
            else:
                ac_entry[f] = np.nan
                ret_entry[f] = np.nan

        autocorr_records.append(ac_entry)
        top15_retention_records.append(ret_entry)

    df_ac = pd.DataFrame(autocorr_records)
    df_ret = pd.DataFrame(top15_retention_records)

    print(f"\nDeğerlendirilen Ardışık Çeyrek Geçişi: {len(df_ac)} periyot")
    print("\nFAKTÖR DERECE OTOKORELASYONU VE TOP-15 TUTMA (RETENTION) ORANLARI:")
    print("-" * 110)
    print(f"{'Faktör Adı':<18} | {'Ortalama Otokorelasyon':<24} | {'Std':<8} | {'Top-15 Tutma Oranı':<20} | {'Çeyreklik Turnover Riski':<25}")
    print("-" * 110)

    summary_rows = []
    for f in factors:
        mean_ac = df_ac[f].mean()
        std_ac = df_ac[f].std()
        mean_ret = df_ret[f].mean()
        implied_turnover = (1.0 - mean_ret) * 100.0

        if mean_ac >= 0.70:
            risk = "🟢 ÇOK DÜŞÜK (Yüksek Kararlılık)"
        elif mean_ac >= 0.50:
            risk = "🟡 NORMAL / DENGELİ"
        elif mean_ac >= 0.30:
            risk = "🟠 ORTA-YÜKSEK (Dinamik)"
        else:
            risk = "🔴 YÜKSEK (Aşırı Çalkantı)"

        print(f"{f:<18} | {mean_ac:>+10.3f}                | {std_ac:.3f}  | %{mean_ret*100:>5.1f}              | {risk:<25}")
        summary_rows.append({
            "factor": f,
            "mean_autocorr": mean_ac,
            "std_autocorr": std_ac,
            "top15_retention": mean_ret,
            "implied_turnover_pct": implied_turnover,
            "turnover_risk": risk
        })

    print("=" * 110)
    return pd.DataFrame(summary_rows), df_ac, df_ret


def main():
    print("=" * 110)
    print("FAZ 1 EK TESTLER: ORTOGONALLİK VE OTOKORELASYON HESAPLAMALARI BAŞLATILIYOR...")
    print("=" * 110)

    df_panel, quarterly_dfs = build_full_feature_panel()
    ortho_res = analyze_orthogonality(df_panel, quarterly_dfs)
    turnover_df, df_ac, df_ret = analyze_autocorrelation_and_turnover(quarterly_dfs)

    # Karar ve Yorum Mantığı
    rho_cs = ortho_res["rho_cs_avg"]
    rho_pl = ortho_res["rho_pooled_sp"]

    print("\n" + "=" * 110)
    print("KANTİTATİF KARAR VE V4 FAKTÖR LİSTESİ SONUCU:")
    print("=" * 110)

    if rho_cs > 0.50 or rho_pl > 0.50:
        print(f"🚨 DİKKAT: reel_eps_growth ile op_marji_trend arasındaki korelasyon (Kesitsel: {rho_cs:+.3f}, Pooled: {rho_pl:+.3f}) 0.50 EŞİĞİNİ AŞMIŞTIR!")
        print("  -> Kullanıcı kuralı gereğince yalnızca IC-IR skoru daha yüksek olan seçilecektir:")
        print("     • reel_eps_growth: IC-IR = 0.46 (Dönem B IR = 0.97, p = 0.0471)")
        print("     • op_marji_trend:  IC-IR = 0.43 (Dönem B IR = 0.69, p = 0.0617)")
        print("  -> KAZANAN VE SEÇİLEN: reel_eps_growth (V4'e tek başına alınacak, op_marji_trend elenecektir).")
        v4_features = [
            "z_pb", "z_roe", "z_fcf", "z_mom", "z_borc",
            "reel_faiz", "usd_mom_60", "usd_mom_90",
            "reel_eps_growth"
        ]
    else:
        print(f"✅ ONAY: reel_eps_growth ile op_marji_trend arasındaki korelasyon (Kesitsel: {rho_cs:+.3f}, Pooled: {rho_pl:+.3f}) 0.50 EŞİĞİNİN ALTINDADIR.")
        print("  -> İki faktör yeterince ortogonaldir, çoklu doğrusal bağlantı (multicollinearity) riski düşüktür.")
        print("  -> Her iki faktör de V4 modeline dahil edilebilir.")
        v4_features = [
            "z_pb", "z_roe", "z_fcf", "z_mom", "z_borc",
            "reel_faiz", "usd_mom_60", "usd_mom_90",
            "reel_eps_growth", "op_marji_trend"
        ]

    print(f"\nKESİNLEŞEN V4 FEATURE LİSTESİ ({len(v4_features)} ADET):")
    for i, col in enumerate(v4_features, 1):
        print(f"  {i:>2}. {col}")

    # JSON Olarak Kaydet
    output_path = ROOT_DIR / "reports" / "faz1_ek_kantitatif_test_sonuclari.json"
    turnover_df.to_json(output_path, orient="records", indent=2)
    print(f"\n✅ Ek test sonuçları kaydedildi: {output_path}")


if __name__ == "__main__":
    main()
