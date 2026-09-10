"""
scratch/check_pit_availability.py
"""
import sys
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
from scratch.run_faz_c_walk_forward_test import yukle_veriler, hizli_pit

fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()

for check_date in ["2018-01-02", "2018-06-01", "2018-09-03", "2019-01-02"]:
    t = pd.Timestamp(check_date)
    count = 0
    for s in fiyat_dict.keys():
        curr, _ = hizli_pit(pit_bellek, s, t)
        if curr:
            count += 1
    print(f"Date: {check_date} -> {count} stocks have PIT fundamentals available.")
