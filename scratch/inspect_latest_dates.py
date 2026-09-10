"""
scratch/inspect_latest_dates.py
"""
import sys
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scratch.run_faz_c_walk_forward_test import yukle_veriler

fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()

last_xu_date = seri_xu100.index[-1]
last_try_date = seri_usdtry.index[-1]
print(f"XU100 Son Tarih: {last_xu_date}")
print(f"USD/TRY Son Tarih: {last_try_date}")

sample_stock = list(fiyat_dict.keys())[0]
print(f"Örnek Hisse ({sample_stock}) Son Fiyat Tarihi: {fiyat_dict[sample_stock].index[-1]}")

# Son bilanço PIT çeyrekleri
recs = pit_bellek.get(sample_stock, [])
if recs:
    print(f"Örnek Hisse Son PIT Kaydı: Dönem={recs[-1].get('donem')}, Geçerlilik={recs[-1].get('gecerlilik_tarihi')}")
