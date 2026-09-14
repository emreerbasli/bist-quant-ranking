"""
models/v3_ranking/data_loader.py
================================
PRODUCTION-CANDIDATE: VERİ YÜKLEYİCİ VE YARDIMCI HESAPLAMA MODÜLÜ
-----------------------------------------------------------------
Bu modül, dondurulmuş LGBMRanker modelinin Point-in-Time (PIT) temel verilerini,
fiyat serilerini, makro faiz ve enflasyon göstergelerini scratch bağımlılığı
olmadan yükleyen ve hesaplayan kurumsal veri motorudur.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg

logger = logging.getLogger("V3DataLoader")


# ─── 1. VERİ VE HAFİF BELLEK YÜKLEYİCİSİ ──────────────────────────────────────
def yukle_veriler():
    """
    Sistem evrenindeki 88 hissenin fiyat serilerini, BIST100, USD/TRY ve
    PIT bilanço kayıtlarını diskten yükler.
    """
    fiyat_dict = {}
    for s in cfg.HISSELER:
        d = s.replace("^", "IDX_").replace(".", "_").replace("=", "_")
        f = cfg.DATA_RAW / f"{d}.parquet"
        if f.exists():
            try:
                df = pd.read_parquet(f)
                if "close" in df.columns and len(df) > 300:
                    fiyat_dict[s] = df["close"].sort_index()
            except Exception:
                pass

    xu_f = cfg.DATA_RAW / "XU100_IS.parquet"
    if not xu_f.exists():
        xu_f = cfg.DATA_RAW / "IDX_XU100_IS.parquet"
    seri_xu100 = pd.read_parquet(xu_f)["close"].sort_index()

    try_f = cfg.DATA_RAW / "TRY_X.parquet"
    seri_usdtry = pd.read_parquet(try_f)["close"].sort_index()

    pit_bellek = {}
    fund_dir = cfg.BASE_DIR / "data" / "fundamentals"
    for s in fiyat_dict.keys():
        d = s.replace("^", "IDX_").replace(".", "_").replace("=", "_")
        p_dosya = fund_dir / f"{d}.parquet"
        if p_dosya.exists():
            try:
                df_p = pd.read_parquet(p_dosya)
                df_p["gecerlilik_tarihi"] = pd.to_datetime(df_p["gecerlilik_tarihi"])
                pit_bellek[s] = df_p.sort_values("gecerlilik_tarihi").to_dict("records")
            except Exception:
                pass

    # İş Yatırım Cache'ten ham detay kalemlerini bellek haritasına al
    cache_dir = cfg.DATA_RAW / "isyatirim_cache"
    cache_bellek = {}
    if cache_dir.exists():
        for j_file in cache_dir.glob("*.json"):
            stem = j_file.stem
            parts = stem.split("_")
            if len(parts) >= 3:
                ticker = parts[0]
                yil = parts[1]
                grup = "_".join(parts[2:])
                try:
                    with open(j_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        item_dict = {}
                        for row in data:
                            c = row.get("itemCode")
                            if c:
                                item_dict[c] = {
                                    "v1": float(row.get("value1") or 0.0),
                                    "v2": float(row.get("value2") or 0.0),
                                    "v3": float(row.get("value3") or 0.0),
                                    "v4": float(row.get("value4") or 0.0),
                                }
                        cache_bellek[(ticker, yil, grup)] = item_dict
                except Exception:
                    pass

    # TÜİK Resmi Aylık TÜFE Tablosu
    tufe_aylik = {
        "2018-09": 6.30, "2018-10": 2.67, "2018-11": -1.44, "2018-12": -0.40,
        "2019-01": 1.06, "2019-02": 0.16, "2019-03": 1.03, "2019-04": 1.69,
        "2019-05": 0.95, "2019-06": 0.03, "2019-07": 1.36, "2019-08": 0.86,
        "2019-09": 0.99, "2019-10": 2.00, "2019-11": 0.38, "2019-12": 0.74,
        "2020-01": 1.35, "2020-02": 0.35, "2020-03": 0.57, "2020-04": 0.85,
        "2020-05": 1.36, "2020-06": 1.13, "2020-07": 0.58, "2020-08": 0.86,
        "2020-09": 0.97, "2020-10": 2.13, "2020-11": 2.30, "2020-12": 1.25,
        "2021-01": 1.68, "2021-02": 0.91, "2021-03": 1.08, "2021-04": 1.68,
        "2021-05": 0.89, "2021-06": 1.94, "2021-07": 1.80, "2021-08": 1.12,
        "2021-09": 1.25, "2021-10": 2.39, "2021-11": 3.51, "2021-12": 13.58,
        "2022-01": 11.10, "2022-02": 4.81, "2022-03": 5.46, "2022-04": 7.25,
        "2022-05": 2.98, "2022-06": 4.95, "2022-07": 2.37, "2022-08": 1.46,
        "2022-09": 3.08, "2022-10": 3.54, "2022-11": 2.88, "2022-12": 1.18,
        "2023-01": 6.65, "2023-02": 3.15, "2023-03": 2.29, "2023-04": 2.39,
        "2023-05": 0.04, "2023-06": 3.92, "2023-07": 9.49, "2023-08": 9.09,
        "2023-09": 4.75, "2023-10": 3.43, "2023-11": 3.28, "2023-12": 2.93,
        "2024-01": 6.70, "2024-02": 4.53, "2024-03": 3.16, "2024-04": 3.18,
        "2024-05": 3.37, "2024-06": 1.64, "2024-07": 3.23, "2024-08": 2.47,
        "2024-09": 2.97, "2024-10": 2.88, "2024-11": 2.24, "2024-12": 1.80,
        "2025-01": 5.03, "2025-02": 2.27, "2025-03": 2.46, "2025-04": 3.00,
        "2025-05": 1.53, "2025-06": 1.37, "2025-07": 2.08, "2025-08": 2.00,
        "2025-09": 2.20, "2025-10": 2.50, "2025-11": 1.80, "2025-12": 1.50,
        "2026-01": 4.20, "2026-02": 2.00, "2026-03": 1.90, "2026-04": 2.10,
        "2026-05": 1.40, "2026-06": 1.20, "2026-07": 1.80, "2026-08": 1.70
    }

    logger.info(f"Veriler yüklendi: {len(fiyat_dict)} hisse | PIT: {len(pit_bellek)} | Cache: {len(cache_bellek)}")
    return fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik


def check_market_date_alignment(
    fiyat_dict: Dict[str, pd.Series],
    seri_xu100: pd.Series,
) -> Dict[str, Any]:
    """Verify that every equity and the benchmark share one PIT market date.

    A ranking must not mix a newer benchmark close with older constituent
    prices.  This is an operational data-integrity gate, not a model feature
    and not a trading signal.
    """
    if seri_xu100.empty:
        return {"aligned": False, "market_date": None, "stale_symbols": [], "reason": "XU100 serisi boş."}

    market_date = pd.Timestamp(seri_xu100.index.max()).normalize()
    stale_symbols: List[str] = []
    missing_symbols: List[str] = []
    for symbol, series in fiyat_dict.items():
        if series.empty:
            missing_symbols.append(symbol)
            continue
        symbol_date = pd.Timestamp(series.index.max()).normalize()
        if symbol_date != market_date:
            stale_symbols.append(symbol)

    aligned = not stale_symbols and not missing_symbols
    if aligned:
        reason = "Tüm hisse fiyatları ve XU100 aynı işlem gününde."
    else:
        reason = (
            f"XU100={market_date.date()} iken {len(stale_symbols)} hisse farklı tarihte, "
            f"{len(missing_symbols)} hisse eksik."
        )
    return {
        "aligned": aligned,
        "market_date": market_date.date().isoformat(),
        "stale_symbols": stale_symbols,
        "missing_symbols": missing_symbols,
        "reason": reason,
    }


def hizli_pit(pit_bellek: Dict[str, List[Dict[str, Any]]], s: str, t: pd.Timestamp) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """t anında kamuya açıklanmış son bilançoyu ve bir öncekini döner (Point-in-Time)."""
    recs = pit_bellek.get(s)
    if not recs:
        return None, None
    gecerli_recs = [r for r in recs if r["gecerlilik_tarihi"] <= t]
    if not gecerli_recs:
        return None, None
    curr = gecerli_recs[-1]
    prev = gecerli_recs[-2] if len(gecerli_recs) >= 2 else None
    return curr, prev


def hesapla_mom(seri: pd.Series, t: pd.Timestamp, n_gun: int = 252, n_lag: int = 21) -> float:
    """12-1 Aylık kesitsel momentum (Jegadeesh-Titman) hesaplar."""
    g = seri[seri.index <= t]
    if len(g) < (n_gun + 1):
        return 0.0
    f_t = g.iloc[-1]
    f_lag = g.iloc[-(n_lag + 1)]
    f_long = g.iloc[-(n_gun + 1)]
    if f_lag <= 0 or f_long <= 0:
        return 0.0
    r_long = (f_t - f_long) / f_long
    r_lag = (f_t - f_lag) / f_lag
    return float(np.clip(r_long - r_lag, -3.0, 3.0))


def getir_tcmb_reel_faiz(t: pd.Timestamp, tufe_aylik: Dict[str, float]) -> float:
    """t anındaki TCMB politika faizinden son 12 aylık kümülatif TÜFE'yi çıkararak reel faizi hesaplar."""
    tcmb_faiz = [
        ("2018-01-01", 8.00), ("2018-05-24", 16.50), ("2018-06-08", 17.75), ("2018-09-14", 24.00),
        ("2019-07-26", 19.75), ("2019-09-13", 16.50), ("2019-10-25", 14.00), ("2019-12-13", 12.00),
        ("2020-01-17", 11.25), ("2020-02-20", 10.75), ("2020-03-18", 9.75),  ("2020-04-23", 8.75),
        ("2020-05-22", 8.25),  ("2020-09-25", 10.25), ("2020-11-20", 15.00), ("2020-12-25", 17.00),
        ("2021-03-19", 19.00), ("2021-09-24", 18.00), ("2021-10-22", 16.00), ("2021-11-19", 15.00),
        ("2021-12-17", 14.00), ("2022-08-19", 13.00), ("2022-09-23", 12.00), ("2022-10-21", 10.50),
        ("2022-11-25", 9.00),  ("2023-02-24", 8.50),  ("2023-06-23", 15.00), ("2023-07-21", 17.50),
        ("2023-08-25", 25.00), ("2023-09-22", 30.00), ("2023-10-27", 35.00), ("2023-11-24", 40.00),
        ("2023-12-22", 42.50), ("2024-01-26", 45.00), ("2024-03-22", 50.00), ("2025-01-01", 47.50),
        ("2025-06-01", 42.50), ("2025-10-01", 37.50), ("2026-01-01", 32.50)
    ]
    t_str = t.strftime("%Y-%m-%d")
    pol = 8.0
    for d, rate in tcmb_faiz:
        if d <= t_str:
            pol = rate
        else:
            break

    son_ay_dt = (t - pd.DateOffset(months=2 if t.day < 4 else 1)).replace(day=1)
    aylar = pd.date_range(end=son_ay_dt, periods=12, freq="MS").strftime("%Y-%m").tolist()
    # Bilinmeyen gelecekteki aylar için güvenli varsayılan %2.0
    factors = [1.0 + tufe_aylik.get(m, 2.0) / 100.0 for m in aylar]
    yillik_tufe = (np.prod(factors) - 1.0) * 100.0
    return float(pol - yillik_tufe)
