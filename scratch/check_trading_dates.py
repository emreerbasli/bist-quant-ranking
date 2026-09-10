"""
scratch/check_trading_dates.py
"""
import sys
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

xu_f = cfg.DATA_RAW / "XU100_IS.parquet"
if not xu_f.exists():
    xu_f = cfg.DATA_RAW / "IDX_XU100_IS.parquet"
seri_xu100 = pd.read_parquet(xu_f)["close"].sort_index()

dates = seri_xu100.index
dates_train = dates[(dates >= "2018-09-01") & (dates <= "2025-05-31")]
print(f"XU100 Dates in [2018-09-01, 2025-05-31]: {len(dates_train)} trading days.")
print(f"First date: {dates_train[0]}, Last date: {dates_train[-1]}")

dates_earlier = dates[(dates >= "2018-01-01") & (dates <= "2025-05-31")]
print(f"XU100 Dates in [2018-01-01, 2025-05-31]: {len(dates_earlier)} trading days.")
print(f"First date: {dates_earlier[0]}")
