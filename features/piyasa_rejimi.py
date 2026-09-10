"""
features/piyasa_rejimi.py — FAZ 2.4: XU100 Piyasa Rejimi & VIX Makro Risk Filtresi
================================================================================
Plan referansı: FAZ 2.4 & 2.4.1 (bist_sinyal_botu_proje_plani_v2.md)

1. XU100 Piyasa Rejimi:
   - GUCLU_YUKSELIS: XU100, 50 günlük ortalamanın %2+ üstünde
   - YATAY: MA50 etrafında dar bantta (-%2 <= fark <= +%2)
   - GUCLU_DUSUS: XU100, 50 günlük ortalamanın %2+ altında
   - PANIK: XU100 ATR z-score > 2 (kriz / ani oynaklık şoku)

2. VIX Makro Risk Filtresi:
   - KURESEL_PANIK: VIX son 3 günde %20'den fazla arttı
   - ARTIS_UYARISI: VIX son 3 günde %10'dan fazla arttı
   - NORMAL: Stabil veya sakin piyasa
"""

import sys
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import numpy as np
import pandas_ta as ta

# Proje kökünü ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg


def hesapla_xu100_rejim_serisi(xu100_df: pd.DataFrame) -> pd.DataFrame:
    """
    XU100 tarihsel serisi için 4 bileşenden güçlendirilmiş piyasa rejimini hesaplar:
      1. Trend: Fiyat / MA50 Farkı
      2. Momentum & Crossover: MA50 vs MA200 (Golden / Death Cross)
      3. Volatilite: ATR(14) Z-Score (100 barlık pencere)
      4. Kısa Vadeli Momentum: 20 Günlük Fiyat Getirisi (ret_20d)

    Zero-leakage: Sadece geçmiş kapanmış barlardan hesaplanır.
    """
    df = xu100_df.copy()

    # 1. 50 ve 200 günlük hareketli ortalamalar
    df["ma50"] = df["close"].rolling(window=50, min_periods=50).mean()
    df["ma200"] = df["close"].rolling(window=200, min_periods=50).mean()
    df["fiyat_ma_farki"] = (df["close"] - df["ma50"]) / (df["ma50"] + 1e-8)
    df["golden_cross"] = (df["ma50"] > df["ma200"]).astype(bool)

    # 2. 20 Günlük Kısa Vadeli Momentum
    df["ret_20d"] = df["close"].pct_change(20).fillna(0.0)

    # 3. ATR(14) ve ATR Z-Score (100 günlük pencere)
    atr = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["atr"] = atr
    atr_mean = df["atr"].rolling(window=100, min_periods=30).mean()
    atr_std = df["atr"].rolling(window=100, min_periods=30).std()
    df["atr_zscore"] = (df["atr"] - atr_mean) / (atr_std + 1e-8)

    # Eşikleri config'den oku (yoksa güvenli varsayılan)
    panik_esik   = getattr(cfg, "REJIM_PANIK_ATR_ZSCORE", 2.0)
    guclu_yuk_ma = getattr(cfg, "REJIM_GUCLU_YUKSELIS_MA_ESIK", 0.03)
    guclu_yuk_r  = getattr(cfg, "REJIM_GUCLU_YUKSELIS_RET20_ESIK", 0.03)
    yuk_ma       = getattr(cfg, "REJIM_YUKSELIS_MA_ESIK", 0.01)
    guclu_dus_ma = getattr(cfg, "REJIM_GUCLU_DUSUS_MA_ESIK", -0.03)
    dus_ma       = getattr(cfg, "REJIM_DUSUS_MA_ESIK", -0.01)

    # 4 Bileşenli Karar Kuralı
    rejimler = []
    for _, row in df.iterrows():
        ma_fark = row["fiyat_ma_farki"]
        zscore  = row["atr_zscore"]
        gc      = row["golden_cross"]
        r20     = row["ret_20d"]

        if pd.isna(ma_fark) or pd.isna(zscore):
            rejimler.append("BELIRSIZ")
        elif zscore > panik_esik:
            rejimler.append("PANIK")
        elif ma_fark > guclu_yuk_ma and gc and r20 > guclu_yuk_r:
            # 3 teyit birlikte: MA50 üstünde + Golden Cross + 20g getiri pozitif
            rejimler.append("GUCLU_YUKSELIS")
        elif ma_fark > yuk_ma or (gc and r20 > 0):
            rejimler.append("YUKSELIS")
        elif ma_fark < guclu_dus_ma and not gc:
            rejimler.append("GUCLU_DUSUS")
        elif ma_fark < dus_ma:
            rejimler.append("DUSUS")
        else:
            rejimler.append("YATAY")

    df["rejim"] = rejimler
    return df


def detayli_piyasa_rejimi(xu100_df: pd.DataFrame) -> Dict[str, Any]:
    """
    En son güncel bar için 4 bileşenin tüm değerlerini ve açıklamasını içeren rejim analizini döner.
    """
    df = hesapla_xu100_rejim_serisi(xu100_df)
    son = df.iloc[-1]
    rejim = str(son["rejim"])
    fark = float(son["fiyat_ma_farki"])
    gc = bool(son["golden_cross"])
    zscore = float(son["atr_zscore"])
    r20 = float(son["ret_20d"])

    aciklama_map = {
        "PANIK": "⚠️ Aşırı oynaklık ve volatilite şoku (ATR Z-Score > 2.0)",
        "GUCLU_YUKSELIS": "🟢 Çok boyutlu güçlü boğa (Fiyat>MA50, Golden Cross ve 20g Pozitif İvme)",
        "YUKSELIS": "🟢 Pozitif trend / yükseliş eğilimi",
        "GUCLU_DUSUS": "🔴 Çok boyutlu güçlü ayı (Fiyat<MA50 ve Death Cross baskısı)",
        "DUSUS": "🔴 Negatif eğilim / düzeltme baskısı",
        "YATAY": "⚪ Dar bantta yatay / kararsız piyasa",
        "BELIRSIZ": "⚪ Yetersiz veri",
    }

    return {
        "rejim": rejim,
        "fiyat_ma50_farki": round(fark, 4),
        "golden_cross": gc,
        "atr_zscore": round(zscore, 2),
        "ret_20d": round(r20, 4),
        "aciklama": aciklama_map.get(rejim, rejim),
    }


def piyasa_rejimi(xu100_df: pd.DataFrame) -> str:
    """
    En son güncel mum için XU100 piyasa rejimini döndürür.
    """
    detay = detayli_piyasa_rejimi(xu100_df)
    return detay["rejim"]


def hesapla_vix_filtre_serisi(vix_df: pd.DataFrame) -> pd.DataFrame:
    """
    VIX tarihsel serisi için her günün makro risk durumunu hesaplar.
    Zero-leakage: 3 günlük geriye dönük getiri.
    """
    df = vix_df.copy()
    df["vix_ret_3d"] = df["close"].pct_change(3)
    
    durumlar = []
    for _, row in df.iterrows():
        val = row["vix_ret_3d"]
        if pd.isna(val):
            durumlar.append("NORMAL")
        elif val > 0.20:
            durumlar.append("KURESEL_PANIK")
        elif val > 0.10:
            durumlar.append("ARTIS_UYARISI")
        else:
            durumlar.append("NORMAL")
            
    df["vix_durum"] = durumlar
    return df


def vix_makro_filtresi(vix_df: pd.DataFrame) -> str:
    """
    En son güncel mum için VIX makro risk durumunu döndürür.
    """
    df = hesapla_vix_filtre_serisi(vix_df)
    return str(df["vix_durum"].iloc[-1])
