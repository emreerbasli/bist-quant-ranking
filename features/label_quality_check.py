"""
features/label_quality_check.py — FAZ 3.5: Etiket Kalite Denetimi
================================================================
Plan referansı: FAZ 3.5 (bist_sinyal_botu_proje_plani_v2.md)

Denetim Adımları:
  1. Birleşik ve hisse bazında 0/1 dağılımı (Hedef: %35-%55 arası label 1)
  2. Çıkış Nedenleri Dağılımı: TP, SL, SL_SAME_BAR, TIMEOUT
  3. Zaman bazlı etiket dağılımı (2018-2020 vs 2021-2023 vs 2024-2026)
  4. Ortalama ATR bariyer büyüklükleri (% cinsinden)
  5. İşlem süreleri (holding days) ortalamaları
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg


def calistir_etiket_kalite_denetimi() -> pd.DataFrame:
    """
    data/labeled/ altındaki tüm etiketli verileri okuyup detaylı kalite raporu üretir.
    """
    labeled_dir = cfg.DATA_LABEL
    files = list(labeled_dir.glob("*.parquet"))
    
    if not files:
        print("Etiketli dosya bulunamadı! Önce features/labeling.py çalıştırın.")
        return pd.DataFrame()

    tum_df_list = []
    hisse_raporlari = []

    for f in sorted(files):
        df = pd.read_parquet(f)
        df["sembol"] = f.stem
        tum_df_list.append(df)
        
        n = len(df)
        n_pos = int((df["label"] == 1).sum())
        pos_ratio = (n_pos / n) * 100.0 if n > 0 else 0
        
        tp_cnt = int((df["exit_reason"] == "TP").sum())
        sl_cnt = int((df["exit_reason"] == "SL").sum())
        sl_sb_cnt = int((df["exit_reason"] == "SL_SAME_BAR").sum())
        to_cnt = int((df["exit_reason"] == "TIMEOUT").sum())
        
        avg_holding = df["holding_days"].mean()
        avg_atr_pct = (df["atr_14"] / df["close"]).mean() * 100.0
        avg_ret = df["trade_return"].mean() * 100.0
        
        durum = "MÜKEMMEL" if 35 <= pos_ratio <= 55 else ("KABUL EDİLEBİLİR" if 25 <= pos_ratio <= 60 else "DİKKAT")
        
        hisse_raporlari.append({
            "Hisse": f.stem.replace("_IS", ""),
            "Toplam_Bar": n,
            "Label_1_%": round(pos_ratio, 1),
            "TP_Adet": tp_cnt,
            "SL_Adet": sl_cnt,
            "SameBar_SL": sl_sb_cnt,
            "Timeout_Adet": to_cnt,
            "Ort_Gün": round(avg_holding, 1),
            "Ort_ATR_%": round(avg_atr_pct, 1),
            "Ort_Getiri_%": round(avg_ret, 2),
            "Denge_Durumu": durum,
        })

    df_summary = pd.DataFrame(hisse_raporlari)
    df_all = pd.concat(tum_df_list, axis=0)

    # 1. Genel Özet
    toplam_ornek = len(df_all)
    toplam_pos = int((df_all["label"] == 1).sum())
    genel_pos_orani = (toplam_pos / toplam_ornek) * 100.0

    print("=" * 80)
    print("FAZ 3.5: ETİKET KALİTE DENETİM RAPORU (TRIPLE BARRIER)")
    print("=" * 80)
    print(f"Toplam İncelenen Hisse : {len(files)}")
    print(f"Toplam İşlem Örneği    : {toplam_ornek:,}")
    print(f"Toplam Label 1 (TP)    : {toplam_pos:,} (%{genel_pos_orani:.1f})")
    print(f"Toplam Label 0 (Kayıp) : {toplam_ornek - toplam_pos:,} (%{100 - genel_pos_orani:.1f})")
    print("-" * 80)
    
    # 2. Çıkış Nedenleri Dağılımı
    print("\nGENEL ÇIKIŞ NEDENLERİ DAĞILIMI:")
    cikis_tablosu = df_all["exit_reason"].value_counts()
    for reason, cnt in cikis_tablosu.items():
        pct = (cnt / toplam_ornek) * 100.0
        print(f"  - {reason:12s} : {cnt:6,d} adet (%{pct:.1f})")

    # 3. Hisse Bazlı Detay Tablosu
    print("\nHİSSE BAZINDA ETİKET VE İŞLEM DAĞILIMI:")
    print(df_summary.to_string(index=False))

    # 4. Dönem Bazlı Kararlılık Denetimi
    print("\nDÖNEMSEL ETİKET DAĞILIMI (REJİM KARARLILIĞI):")
    df_all["yil_grubu"] = pd.cut(
        df_all.index.year,
        bins=[2017, 2020, 2023, 2027],
        labels=["2018-2020 (Pandemi Öncesi/Sırası)", "2021-2023 (Enflasyon Rallisi)", "2024-2026 (Son Dönem)"]
    )
    donem_ozet = df_all.groupby("yil_grubu", observed=False)["label"].agg(
        Toplam="count",
        Label_1="sum",
        Label_1_Orani=lambda x: round((x.sum() / len(x)) * 100, 1) if len(x) > 0 else 0
    )
    print(donem_ozet.to_string())
    print("=" * 80)
    
    return df_summary


if __name__ == "__main__":
    calistir_etiket_kalite_denetimi()
