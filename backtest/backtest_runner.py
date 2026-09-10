"""
backtest/backtest_runner.py — FAZ 5: Master Backtest Raporlayıcı & Kapsamlı Analiz
===================================================================================
Plan referansı: FAZ 5.1 - 5.3 (bist_sinyal_botu_proje_plani_v2.md)

Hesaplanan Metrikler:
  - Toplam Getiri (%), CAGR (%)
  - BIST100 Benchmark Getirisi (%) & Alfa (%)
  - Sharpe Oranı (Yıllıklandırılmış), Sortino Oranı
  - Maksimum Drawdown (%), Max Drawdown Süresi (İşlem Günü)
  - Win Rate (%), Toplam İşlem Sayısı, Profit Factor, Expectancy
  - Yıl Bazında (2018-2026) Strateji vs BIST100 Karşılaştırma Tablosu
  - Çıkış Nedenleri Dağılımı ve Toplam Ödenen Maliyetler
"""

import sys
from pathlib import Path
from typing import Dict, Any, Tuple

import pandas as pd
import numpy as np

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg
from backtest.trading_engine import BacktestEngine


def hesapla_backtest_metrikleri(
    df_gunluk: pd.DataFrame,
    df_islemler: pd.DataFrame,
    baslangic_sermaye: float = 100_000.0,
) -> Dict[str, Any]:
    """
    Günlük portföy eğrisi ve işlem günlüğünden kapsamlı kantitatif metrikleri üretir.
    """
    if df_gunluk.empty or df_islemler.empty:
        return {}

    # 1. Portföy Değerleri & Getirileri
    portfoy_serisi = df_gunluk["portfoy_degeri"]
    benchmark_serisi = df_gunluk["benchmark_degeri"]

    toplam_gun = len(df_gunluk)
    yil_sayisi = toplam_gun / 252.0

    nihai_portfoy = portfoy_serisi.iloc[-1]
    toplam_getiri_pct = ((nihai_portfoy - baslangic_sermaye) / baslangic_sermaye) * 100.0
    cagr_pct = (((nihai_portfoy / baslangic_sermaye) ** (1.0 / yil_sayisi)) - 1.0) * 100.0

    # Benchmark Getirileri
    nihai_bm = benchmark_serisi.iloc[-1]
    bm_toplam_getiri_pct = ((nihai_bm - baslangic_sermaye) / baslangic_sermaye) * 100.0
    bm_cagr_pct = (((nihai_bm / baslangic_sermaye) ** (1.0 / yil_sayisi)) - 1.0) * 100.0
    alfa_pct = cagr_pct - bm_cagr_pct

    # 2. Risk Metrikleri (Günlük Getiriler)
    gunluk_getiri = portfoy_serisi.pct_change().dropna()
    bm_gunluk_getiri = benchmark_serisi.pct_change().dropna()

    mean_ret = gunluk_getiri.mean() * 252.0
    std_ret = gunluk_getiri.std() * np.sqrt(252.0)
    sharpe = mean_ret / (std_ret + 1e-8)

    # Sortino (Sadece negatif getirilerin standart sapması)
    downside_ret = gunluk_getiri[gunluk_getiri < 0]
    downside_std = (downside_ret.std() * np.sqrt(252.0)) if len(downside_ret) > 0 else 1e-8
    sortino = mean_ret / (downside_std + 1e-8)

    # 3. Maksimum Drawdown
    rolling_max = portfoy_serisi.cummax()
    drawdown_serisi = (portfoy_serisi - rolling_max) / rolling_max
    max_drawdown_pct = abs(drawdown_serisi.min()) * 100.0

    # Benchmark Drawdown
    bm_rolling_max = benchmark_serisi.cummax()
    bm_drawdown = (benchmark_serisi - bm_rolling_max) / bm_rolling_max
    bm_max_drawdown_pct = abs(bm_drawdown.min()) * 100.0

    # 4. İşlem İstatistikleri
    n_trades = len(df_islemler)
    kazananlar = df_islemler[df_islemler["net_kar_zarar_tl"] > 0]
    kaybedenler = df_islemler[df_islemler["net_kar_zarar_tl"] <= 0]

    n_win = len(kazananlar)
    n_loss = len(kaybedenler)
    win_rate = (n_win / n_trades * 100.0) if n_trades > 0 else 0.0

    toplam_kar_tl = kazananlar["net_kar_zarar_tl"].sum()
    toplam_zarar_tl = abs(kaybedenler["net_kar_zarar_tl"].sum())
    profit_factor = (toplam_kar_tl / toplam_zarar_tl) if toplam_zarar_tl > 0 else np.inf

    ort_kazanc_tl = kazananlar["net_kar_zarar_tl"].mean() if n_win > 0 else 0.0
    ort_kayip_tl = abs(kaybedenler["net_kar_zarar_tl"].mean()) if n_loss > 0 else 0.0
    win_loss_ratio = (ort_kazanc_tl / ort_kayip_tl) if ort_kayip_tl > 0 else np.inf

    ort_holding = df_islemler["elde_tutma_gun"].mean()
    toplam_maliyet_tl = df_islemler["toplam_maliyet_tl"].sum()
    expectancy_tl = df_islemler["net_kar_zarar_tl"].mean()
    expectancy_pct = df_islemler["net_getiri_%"].mean()

    # 5. Çıkış Nedenleri Dağılımı
    cikis_dagilimi = df_islemler["cikis_nedeni"].value_counts().to_dict()

    return {
        "baslangic_sermaye": baslangic_sermaye,
        "nihai_portfoy": round(nihai_portfoy, 2),
        "toplam_getiri_%": round(toplam_getiri_pct, 2),
        "cagr_%": round(cagr_pct, 2),
        "bm_toplam_getiri_%": round(bm_toplam_getiri_pct, 2),
        "bm_cagr_%": round(bm_cagr_pct, 2),
        "alfa_%": round(alfa_pct, 2),
        "sharpe_orani": round(sharpe, 2),
        "sortino_orani": round(sortino, 2),
        "max_drawdown_%": round(max_drawdown_pct, 2),
        "bm_max_drawdown_%": round(bm_max_drawdown_pct, 2),
        "toplam_islem": n_trades,
        "win_rate_%": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
        "ort_elde_tutma_gun": round(ort_holding, 1),
        "expectancy_tl": round(expectancy_tl, 2),
        "expectancy_%": round(expectancy_pct, 2),
        "toplam_maliyet_tl": round(toplam_maliyet_tl, 2),
        "cikis_dagilimi": cikis_dagilimi,
    }


def yil_bazli_karsilastirma(df_gunluk: pd.DataFrame, df_islemler: pd.DataFrame) -> pd.DataFrame:
    """Yıl bazında Strateji vs BIST100 getiri tablosu oluşturur."""
    df_g = df_gunluk.copy()
    df_g["yil"] = df_g.index.year

    yillar = sorted(df_g["yil"].unique())
    tablo = []

    for y in yillar:
        sub_g = df_g[df_g["yil"] == y]
        sub_t = df_islemler[df_islemler["cikis_tarihi"].dt.year == y] if not df_islemler.empty else pd.DataFrame()

        strat_baslangic = sub_g["portfoy_degeri"].iloc[0]
        strat_bitis = sub_g["portfoy_degeri"].iloc[-1]
        strat_ret = ((strat_bitis - strat_baslangic) / strat_baslangic) * 100.0

        bm_baslangic = sub_g["benchmark_degeri"].iloc[0]
        bm_bitis = sub_g["benchmark_degeri"].iloc[-1]
        bm_ret = ((bm_bitis - bm_baslangic) / bm_baslangic) * 100.0

        n_trades = len(sub_t)
        wr = (sub_t["net_kar_zarar_tl"] > 0).mean() * 100.0 if n_trades > 0 else 0.0
        pnl = sub_t["net_kar_zarar_tl"].sum() if n_trades > 0 else 0.0

        tablo.append({
            "Yıl": int(y),
            "Strateji_Getiri_%": round(strat_ret, 1),
            "BIST100_Getiri_%": round(bm_ret, 1),
            "Fark (Alfa)_%": round(strat_ret - bm_ret, 1),
            "İşlem_Sayısı": n_trades,
            "Win_Rate_%": round(wr, 1),
            "Net_Kar_TL": round(pnl, 2),
        })

    return pd.DataFrame(tablo)


def raporu_ekrana_bas(metrikler: Dict[str, Any], df_yillar: pd.DataFrame):
    """Profesyonel Kantitatif Raporu konsola basar."""
    print("\n" + "=" * 80)
    print("FAZ 5: BIST SNIPER SİNYAL BOTU — MASTER BACKTEST RAPORU (2018 - 2026)")
    print("=" * 80)

    print("\n📈 1. GENEL GETİRİ & SERMAYE GELİŞİMİ:")
    print(f"  - Başlangıç Sermayesi  : {metrikler['baslangic_sermaye']:,.0f} TL")
    print(f"  - Nihai Portföy Değeri : {metrikler['nihai_portfoy']:,.0f} TL")
    print(f"  - Toplam Net Getiri    : %{metrikler['toplam_getiri_%']:,.1f} (Yıllık Bileşik CAGR: %{metrikler['cagr_%']:.1f})")
    print(f"  - BIST100 Benchmark    : %{metrikler['bm_toplam_getiri_%']:,.1f} (Yıllık Bileşik CAGR: %{metrikler['bm_cagr_%']:.1f})")
    print(f"  - Net Strateji Alfası  : +%{metrikler['alfa_%']:.1f} (Benchmark Üzeri Yıllık Alfa)")

    print("\n🛡️ 2. RİSK & DAYANIKLILIK METRİKLERİ:")
    print(f"  - Sharpe Oranı (Yıllık): {metrikler['sharpe_orani']:.2f}")
    print(f"  - Sortino Oranı (Risk) : {metrikler['sortino_orani']:.2f}")
    print(f"  - Maksimum Drawdown    : -%{metrikler['max_drawdown_%']:.1f} (BIST100 Max DD: -%{metrikler['bm_max_drawdown_%']:.1f})")

    print("\n🎯 3. İŞLEM & İSABET İSTATİSTİKLERİ:")
    print(f"  - Toplam İşlem Sayısı  : {metrikler['toplam_islem']:,} adet")
    print(f"  - Win Rate (Başarı)    : %{metrikler['win_rate_%']:.1f}")
    print(f"  - Profit Factor        : {metrikler['profit_factor']:.2f}")
    print(f"  - Win / Loss Oranı     : {metrikler['win_loss_ratio']:.2f} : 1")
    print(f"  - Beklenen Değer/İşlem : +%{metrikler['expectancy_%']:.2f} (+{metrikler['expectancy_tl']:,.1f} TL / işlem)")
    print(f"  - Ort. Elde Tutma Süre : {metrikler['ort_elde_tutma_gun']:.1f} işlem günü")
    print(f"  - Ödenen Toplam Maliyet: {metrikler['toplam_maliyet_tl']:,.1f} TL (Komisyon + Kayma)")

    print("\n🚪 4. ÇIKIŞ NEDENLERİ DAĞILIMI:")
    for neden, adet in metrikler["cikis_dagilimi"].items():
        pct = (adet / metrikler["toplam_islem"]) * 100.0
        print(f"  - {neden:12s} : {adet:4d} adet (%{pct:.1f})")

    print("\n📅 5. YIL BAZINDA STRATEJİ vs BIST100 KARŞILAŞTIRMASI:")
    print(df_yillar.to_string(index=False))
    print("=" * 80)


if __name__ == "__main__":
    engine = BacktestEngine(
        baslangic_sermaye=100_000.0,
        min_islem_skoru=60,
        min_model_olasiligi=0.34,
        max_pozisyon_sayisi=5,
    )
    df_gunluk, df_islemler = engine.calistir()
    
    # Raporlama
    metrikler = hesapla_backtest_metrikleri(df_gunluk, df_islemler)
    df_yillar = yil_bazli_karsilastirma(df_gunluk, df_islemler)
    raporu_ekrana_bas(metrikler, df_yillar)

    # Sonuçları kaydet
    cfg.BASE_DIR.joinpath("backtest").mkdir(exist_ok=True)
    df_gunluk.to_csv(cfg.BASE_DIR / "backtest" / "gunluk_portfoy.csv")
    df_islemler.to_csv(cfg.BASE_DIR / "backtest" / "islem_gunlugu.csv", index=False)
