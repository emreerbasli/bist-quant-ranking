import sys, os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from models.v4_ranking.data_loader_v4 import yukle_veriler
from models.v4_ranking.drift_monitor_v4 import DriftMonitorV4
import config as cfg

fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
t_now = pd.Timestamp("2026-09-17")

monitor = DriftMonitorV4()
health_res = monitor.check_data_health(fiyat_dict, pit_bellek, tufe_aylik, t_now)

print("=== KATMAN 5: VERİ SAĞLIK DENETİMİ SONUCU ===")
print(f"Durum: {health_res.status}")
print(f"Hisse Sayısı: {health_res.tickers_count}")
print(f"Toplam Bar: {health_res.total_bars}")
print(f"NaN Oranı: %{health_res.nan_ratio_pct}")
print(f"PIT Bilanço Hisse Sayısı: {health_res.pit_tickers_count}")
print(f"100g+ Eski Bilanço Sayısı: {health_res.stale_financials_count}")
print(f"Makro USD: {health_res.macro_usd_status}")
print(f"Makro TÜFE: {health_res.macro_cpi_status}")
print(f"Detay: {health_res.details}")

# Ek Analizler:
# 1) Kaç hissede NaN var, tek tek döküm
nan_stocks = {}
for s, s_ser in fiyat_dict.items():
    n_nan = int(s_ser.isnull().sum())
    if n_nan > 0:
        nan_stocks[s] = n_nan

print(f"\n1) NaN Bar İçeren Hisse Sayısı: {len(nan_stocks)}")
if len(nan_stocks) > 0:
    for s, count in nan_stocks.items():
        print(f"   - {s}: {count} NaN bar")
else:
    print("   -> Hiçbir hissede NaN veri noktası YOKTUR (%0.00).")

# 2) En eski veri noktası hangi hissede?
earliest_dates = {}
latest_dates = {}
bar_lengths = {}
for s, s_ser in fiyat_dict.items():
    if not s_ser.empty:
        earliest_dates[s] = s_ser.index.min()
        latest_dates[s] = s_ser.index.max()
        bar_lengths[s] = len(s_ser)

earliest_stock = min(earliest_dates, key=earliest_dates.get)
print(f"\n2) En Eski Veri Noktası:")
print(f"   - Hisse: {earliest_stock}")
print(f"   - Başlangıç Tarihi: {earliest_dates[earliest_stock]}")
print(f"   - En Geç Başlayan Hisse: {max(earliest_dates, key=earliest_dates.get)} ({earliest_dates[max(earliest_dates, key=earliest_dates.get)]})")

# 3) Momentum hesaplaması için gereken 12 aylık geçmiş (min 250 iş günü / bar) tüm hisselerde mevcut mu?
insufficient_mom = {}
for s, s_ser in fiyat_dict.items():
    bars_as_of_t = len(s_ser[s_ser.index <= t_now])
    if bars_as_of_t < 250:
        insufficient_mom[s] = bars_as_of_t

print(f"\n3) 12 Aylık Geçmiş (250+ bar) Eksik Olan Hisse Sayısı: {len(insufficient_mom)}")
if len(insufficient_mom) > 0:
    for s, b_count in insufficient_mom.items():
        print(f"   - {s}: sadece {b_count} bar var (< 250 bar)")
else:
    min_bars_sym = min(bar_lengths, key=bar_lengths.get)
    print(f"   -> 88 hissenin TAMAMINDA 12 aylık geçmiş (>= 250 bar) MEVCUTTUR!")
    print(f"   -> En az bara sahip hisse: {min_bars_sym} ({bar_lengths[min_bars_sym]} bar)")
