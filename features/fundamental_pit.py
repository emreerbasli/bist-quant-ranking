"""
features/fundamental_pit.py - PIT-Uyumlu Temel Analiz Veri Katmani
====================================================================
Mukemmellestirme Plani Referansi: Faz A + Faz B.5

MIMARI TASARIM (Scraper-Uyumlu):
  Bu modul iki modda calisir:

  MOD 1 - CANLI (yfinance):
    - Guncel ROE, P/B, ev_ebitda yfinance'tan cekilir.
    - Faz B.5 kaba skor testinde bu mod kullanilir.

  MOD 2 - TARIHSEL PIT (KAP XBRL Scraper):
    - data/fundamentals/{ticker}.parquet dosyalari okunur.
    - Her satir: {ticker, gecerlilik_tarihi (KAP aciklama), ebitda,
                 net_borc, ev, ev_ebitda, roe, roa, fcf_verim, pb, tfrs29}
    - gecerlilik_tarihi: ceyrek bitis degil, fiili KAP aciklanma tarihi (PIT).
    - Bu mod Faz A tamamlandiktan sonra otomatik devreye girer.
"""

import sys
import json
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

# Dizin: PIT bilanco verileri buraya gelecek (KAP scraper ciktisi)
PIT_FUND_DIR = cfg.BASE_DIR / "data" / "fundamentals"
PIT_FUND_DIR.mkdir(parents=True, exist_ok=True)

# yfinance cache
_YFIN_CACHE_FILE = cfg.DATA_RAW / "yfin_fundamental_cache.json"
_CACHE_OMRU_SAAT = 24


# ─── YARDIMCI: yfinance cache ────────────────────────────────────────────────
def _cache_yukle() -> Dict[str, Any]:
    if not _YFIN_CACHE_FILE.exists():
        return {}
    try:
        with open(_YFIN_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        kayit = datetime.fromisoformat(data.get("_ts", "2000-01-01T00:00:00"))
        if datetime.now() - kayit < timedelta(hours=_CACHE_OMRU_SAAT):
            return data.get("hisseler", {})
    except Exception:
        pass
    return {}


def _cache_kaydet(hisseler: Dict[str, Any]) -> None:
    try:
        _YFIN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_YFIN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"_ts": datetime.now().isoformat(), "hisseler": hisseler},
                      f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Fundamental cache kaydetme hatasi: {e}")


# ─── MOD 1: CANLI yfinance ───────────────────────────────────────────────────
def _yfin_tek_hisse(sembol: str) -> Dict[str, Any]:
    """Tek hisse icin yfinance'tan guncel temel veriyi ceker."""
    try:
        import yfinance as yf
        tick = yf.Ticker(sembol)
        info = {}
        try:
            info = tick.info or {}
        except Exception:
            pass

        pb     = info.get("priceToBook")
        roe    = info.get("returnOnEquity") or info.get("returnOnEquityTTM")
        roa    = info.get("returnOnAssets") or info.get("returnOnAssetsTTM")
        ev     = info.get("enterpriseValue")
        ebitda = info.get("ebitda")

        ev_ebitda = None
        if ev and ebitda and ebitda > 0:
            ev_ebitda = ev / ebitda

        sektor = cfg.HISSE_SEKTOR.get(sembol, "XU100.IS")

        return {
            "sembol":    sembol,
            "sektor":    sektor,
            "pb":        float(pb)        if pb        and not np.isnan(float(pb))        else np.nan,
            "roe":       float(roe)       if roe       and not np.isnan(float(roe))       else np.nan,
            "roa":       float(roa)       if roa       and not np.isnan(float(roa))       else np.nan,
            "ev_ebitda": float(ev_ebitda) if ev_ebitda else np.nan,
            "kaynak":    "yfinance_canli",
            "tarih":     datetime.now().strftime("%Y-%m-%d"),
        }
    except Exception as e:
        logger.debug(f"{sembol} yfinance temel veri hatasi: {e}")
        sektor = cfg.HISSE_SEKTOR.get(sembol, "XU100.IS")
        return {
            "sembol": sembol, "sektor": sektor,
            "pb": np.nan, "roe": np.nan, "roa": np.nan,
            "ev_ebitda": np.nan,
            "kaynak": "hata", "tarih": datetime.now().strftime("%Y-%m-%d"),
        }


def cek_canli_temel(hisseler: Optional[List[str]] = None,
                    zorla: bool = False,
                    max_workers: int = 12) -> pd.DataFrame:
    """
    MOD 1: yfinance'tan guncel temel verileri paralel ceker.
    Faz B.5 kaba skor icin yeterli.
    """
    if hisseler is None:
        hisseler = cfg.HISSELER

    if not zorla:
        cached = _cache_yukle()
        if cached and all(s in cached for s in hisseler):
            logger.info("Temel veri guncel cache'ten yuklendi.")
            return pd.DataFrame.from_dict(cached, orient="index")

    logger.info(f"yfinance temel veri cekiliyor ({len(hisseler)} hisse, {max_workers} thread)...")
    sonuclar = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_yfin_tek_hisse, s): s for s in hisseler}
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            sonuclar[res["sembol"]] = res

    _cache_kaydet(sonuclar)
    return pd.DataFrame.from_dict(sonuclar, orient="index")


# ─── MOD 2: TARIHSEL PIT (KAP Scraper hazir oldugunda) ──────────────────────
def pit_mevcut_mu(sembol: str) -> bool:
    """data/fundamentals/{sembol}.parquet dosyasi var mi?"""
    dosya = PIT_FUND_DIR / f"{sembol.replace('.', '_')}.parquet"
    return dosya.exists()


def cek_pit_kesit(sembol: str, tarih: pd.Timestamp) -> Optional[Dict[str, Any]]:
    """
    MOD 2: Belirli bir tarihte gecerli olan en son PIT temel veriyi doner.
    gecerlilik_tarihi <= tarih filtresi - sifir geleceğe bakis sızıntısı.
    KAP scraper tamamlandiginda bu fonksiyon otomatik devreye girer.
    """
    dosya = PIT_FUND_DIR / f"{sembol.replace('.', '_')}.parquet"
    if not dosya.exists():
        return None
    try:
        df = pd.read_parquet(dosya)
        df["gecerlilik_tarihi"] = pd.to_datetime(df["gecerlilik_tarihi"])
        gecerli = df[df["gecerlilik_tarihi"] <= tarih]
        if gecerli.empty:
            return None
        return gecerli.sort_values("gecerlilik_tarihi").iloc[-1].to_dict()
    except Exception as e:
        logger.warning(f"{sembol} PIT veri okuma hatasi: {e}")
        return None


# ─── ANA ARABIRIM: Otomatik mod secimi ───────────────────────────────────────
def getir_temel_kesit(sembol: str,
                      tarih: Optional[pd.Timestamp] = None) -> Dict[str, Any]:
    """
    Otomatik mod secimi:
    - PIT dosyasi varsa: MOD 2 (tarihsel, sifir sizinti)
    - Yoksa: MOD 1 (yfinance guncel, canli sinyal icin)
    """
    if tarih is None:
        tarih = pd.Timestamp.now()

    if pit_mevcut_mu(sembol):
        pit = cek_pit_kesit(sembol, tarih)
        if pit:
            return {**pit, "kaynak": "pit_kap"}

    cached = _cache_yukle()
    if sembol in cached:
        return cached[sembol]
    return _yfin_tek_hisse(sembol)


# ─── SEKTOR Z-SCORE (Faz B.5 + Faz C) ───────────────────────────────────────
def hesapla_sektor_zscore(df: pd.DataFrame,
                           kolon: str,
                           min_grup: int = 4) -> pd.Series:
    """
    Kolonu sektor icinde z-score'a donusturur.
    Sektorde < min_grup hisse varsa tum evren uzerinden normalize eder.
    Plan Faz A.4: kucuk sektor emniyeti.
    """
    zscores = pd.Series(np.nan, index=df.index)

    for sektor, grup in df.groupby("sektor"):
        gecerli = grup[kolon].dropna()
        if len(gecerli) >= min_grup:
            mu  = gecerli.mean()
            std = gecerli.std()
        else:
            gecerli = df[kolon].dropna()
            mu  = gecerli.mean()
            std = gecerli.std()
            logger.debug(f"Kucuk sektor ({sektor}, n={len(grup)}) evren z-score kullanildi.")

        if std > 1e-8:
            zscores.loc[grup.index] = (grup[kolon] - mu) / std
        else:
            zscores.loc[grup.index] = 0.0

    return zscores.clip(-3.0, 3.0)


# ─── FAZ B.5 KABA SKOR ───────────────────────────────────────────────────────
def hesapla_kaba_skor(df_temel: pd.DataFrame,
                       mom_12_1_dict: Optional[Dict[str, float]] = None) -> pd.Series:
    """
    Faz B.5 kaba skor formulu (Mukemmellestirme Plani):
        Skor = -Z(P/B) + Z(ROE) + Z(Mom_12-1)

    - Dusuk P/B (iskontolu)       -> pozitif katki
    - Yuksek ROE (karli)          -> pozitif katki
    - Yuksek Mom 12-1 (momentumlu) -> pozitif katki
    """
    df = df_temel.copy().reset_index(drop=True)

    if mom_12_1_dict:
        df["mom_12_1"] = df["sembol"].map(mom_12_1_dict)
    elif "mom_12_1" not in df.columns:
        df["mom_12_1"] = np.nan

    z_pb  = hesapla_sektor_zscore(df, "pb",       min_grup=4)
    z_roe = hesapla_sektor_zscore(df, "roe",      min_grup=4)
    z_mom = hesapla_sektor_zscore(df, "mom_12_1", min_grup=4)

    skor = (
        z_pb.fillna(0.0)  * (-1.0) +
        z_roe.fillna(0.0) *  1.0   +
        z_mom.fillna(0.0) *  1.0
    )

    skor.index = df["sembol"].values
    return skor


# ─── CLI TEST ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 70)
    print("fundamental_pit.py - Sistem Kontrolu")
    print("=" * 70)

    pit_hisseler = [s for s in cfg.HISSELER if pit_mevcut_mu(s)]
    print(f"PIT dosyasi mevcut: {len(pit_hisseler)} hisse "
          f"({'KAP scraper tamamlandi' if pit_hisseler else 'KAP scraper yok, yfinance modu aktif'})")

    test_hisseler = cfg.HISSELER[:5]
    print(f"\nyfinance test ({len(test_hisseler)} hisse)...")
    df = cek_canli_temel(test_hisseler, zorla=True)
    print(df[["sembol", "sektor", "pb", "roe", "ev_ebitda"]].to_string(index=False))

    df_tam = cek_canli_temel(cfg.HISSELER)
    skor = hesapla_kaba_skor(df_tam)
    top10 = skor.nlargest(10)
    print(f"\n--- Kaba Skor Top-10 (bugun) ---")
    print(top10.to_string())
