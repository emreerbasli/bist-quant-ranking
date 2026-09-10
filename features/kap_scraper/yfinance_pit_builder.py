"""
features/kap_scraper/yfinance_pit_builder.py
============================================
yfinance uzerinden ceyreklik PIT-uyumlu temel veri olusturucu.

Mimari:
  - Her hisse icin quarterly_financials + quarterly_balance_sheet ceker
  - gecerlilik_tarihi = ceyrek_bitis + 45 gun (PIT proxy - KAP'ta ortalama gecikme)
  - data/fundamentals/{TICKER_IS}.parquet olarak kaydeder
  - fundamental_pit.py MOD 2 ile tam uyumlu

Kapsam:
  - yfinance'in sakladigi kadar gecmis (tipik: 6-8 ceyrek, ~2024+)
  - TTM (trailing 12-month) EBITDA / Net Borc / Ozkaynaklar
  - EV/EBITDA, ROE, ROA, P/B hesaplama

Hiz: 88 hisse icin ~8-12 dakika (paralel, 10 thread)
"""

import sys, json, time, traceback
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import yfinance as yf
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config as cfg

PIT_DIR  = cfg.BASE_DIR / "data" / "fundamentals"
CACHE_DIR = cfg.DATA_RAW / "yf_pit_cache"
PIT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PIT_LAG_GUN = 45   # KAP aciklama gecikmesi proxy (gun)
MAX_WORKERS  = 10   # Paralel thread sayisi


def _safe_float(val) -> Optional[float]:
    try:
        f = float(val)
        return f if not (np.isnan(f) or np.isinf(f)) else None
    except Exception:
        return None


def _getir_deger(df: pd.DataFrame, satirlar: List[str], kolon: pd.Timestamp) -> Optional[float]:
    """DataFrame'den ilk eslesen satiri doner."""
    for satir in satirlar:
        if satir in df.index:
            val = df.loc[satir, kolon] if kolon in df.columns else np.nan
            f = _safe_float(val)
            if f is not None:
                return f
    return None


def _hisse_cek(sembol: str) -> List[Dict[str, Any]]:
    """
    Tek hisse icin yfinance ceyreklik veri ceker.
    Her ceyrek icin bir satir doner.
    gecerlilik_tarihi = ceyrek_bitis + PIT_LAG_GUN (proxy)
    """
    # Cache kontrolu
    cache_dosya = CACHE_DIR / f"{sembol.replace('.','_')}.parquet"
    if cache_dosya.exists():
        try:
            df_cache = pd.read_parquet(cache_dosya)
            if len(df_cache) > 0:
                son_guncelleme = pd.Timestamp(df_cache.get('_cekme_tarihi', pd.Series(['2000-01-01'])).iloc[0])
                if (pd.Timestamp.now() - son_guncelleme).days < 7:
                    return df_cache.drop(columns=['_cekme_tarihi'], errors='ignore').to_dict('records')
        except Exception:
            pass

    try:
        tick = yf.Ticker(sembol)

        # Ceyreklik tablolar
        qf = tick.quarterly_financials      # Gelir tablosu
        qb = tick.quarterly_balance_sheet   # Bilanco
        qcf = tick.quarterly_cashflow       # Nakit akis

        if qf is None or qf.empty:
            logger.warning(f"{sembol}: quarterly_financials bos")
            return []

        info = {}
        try:
            info = tick.info or {}
        except Exception:
            pass

        # Piyasa degeri icin fiyat serisi al
        fiyat_dosya = cfg.DATA_RAW / f"{sembol.replace('.','_').replace('^','IDX_').replace('=','_')}.parquet"
        fiyat_seri = None
        if fiyat_dosya.exists():
            try:
                df_fiyat = pd.read_parquet(fiyat_dosya)
                if 'close' in df_fiyat.columns:
                    fiyat_seri = df_fiyat['close'].sort_index()
            except Exception:
                pass

        # Paylasim sayisi
        hisse_adedi = _safe_float(info.get('sharesOutstanding')) or _safe_float(info.get('impliedSharesOutstanding'))

        kayitlar = []

        for ceyrek_tarih in sorted(qf.columns):
            ceyrek_str = ceyrek_tarih.strftime('%YQ') + str((ceyrek_tarih.month - 1) // 3 + 1)
            pit_tarih  = ceyrek_tarih + pd.Timedelta(days=PIT_LAG_GUN)

            # --- Gelir tablosu kalemleri ---
            ebitda     = _getir_deger(qf, ['EBITDA', 'Normalized EBITDA'], ceyrek_tarih)
            net_kar    = _getir_deger(qf, ['Net Income', 'Net Income Common Stockholders'], ceyrek_tarih)
            satislar   = _getir_deger(qf, ['Total Revenue', 'Operating Revenue'], ceyrek_tarih)
            op_gelir   = _getir_deger(qf, ['Operating Income', 'EBIT'], ceyrek_tarih)

            # --- Bilanco kalemleri ---
            ozkaynaklar = None
            toplam_borc = None
            nakit       = None
            toplam_aktif = None

            if qb is not None and not qb.empty and ceyrek_tarih in qb.columns:
                ozkaynaklar  = _getir_deger(qb, [
                    'Stockholders Equity',
                    'Total Equity Gross Minority Interest',
                    'Common Stock Equity'], ceyrek_tarih)
                toplam_borc  = _getir_deger(qb, ['Total Debt', 'Long Term Debt And Capital Lease Obligation'], ceyrek_tarih)
                nakit        = _getir_deger(qb, ['Cash And Cash Equivalents', 'Cash Cash Equivalents And Short Term Investments'], ceyrek_tarih)
                toplam_aktif = _getir_deger(qb, ['Total Assets'], ceyrek_tarih)

            net_borc = None
            if toplam_borc is not None and nakit is not None:
                net_borc = toplam_borc - nakit

            # --- Piyasa degeri ve carpanlar ---
            # PIT tarihi etrafindaki fiyati kullan
            piyasa_degeri = None
            if fiyat_seri is not None and hisse_adedi:
                gecmis = fiyat_seri[fiyat_seri.index <= pit_tarih]
                if len(gecmis) > 0:
                    fiyat = float(gecmis.iloc[-1])
                    piyasa_degeri = fiyat * hisse_adedi

            ev = None
            if piyasa_degeri and net_borc is not None:
                ev = piyasa_degeri + net_borc

            # EV/EBITDA (TTM proxy - bu ceyrek * 4)
            ev_ebitda = None
            if ev and ebitda and ebitda > 0:
                ebitda_ttm = ebitda * 4   # Tek ceyrek * 4 = TTM yaklasimi
                ev_ebitda = ev / ebitda_ttm

            # ROE
            roe = None
            if net_kar is not None and ozkaynaklar and ozkaynaklar > 0:
                roe = (net_kar * 4) / ozkaynaklar   # TTM proxy

            # ROA
            roa = None
            if net_kar is not None and toplam_aktif and toplam_aktif > 0:
                roa = (net_kar * 4) / toplam_aktif

            # P/B
            pb = None
            if piyasa_degeri and ozkaynaklar and ozkaynaklar > 0:
                pb = piyasa_degeri / ozkaynaklar

            # Serbest nakit akisi
            fcf_verim = None
            if qcf is not None and not qcf.empty and ceyrek_tarih in qcf.columns:
                cfo    = _getir_deger(qcf, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities'], ceyrek_tarih)
                capex  = _getir_deger(qcf, ['Capital Expenditure', 'Purchase Of Ppe'], ceyrek_tarih)
                if cfo and capex and piyasa_degeri and piyasa_degeri > 0:
                    fcf = cfo + capex  # capex genellikle negatif gelir
                    fcf_verim = (fcf * 4) / piyasa_degeri

            # TFRS29 bayragi
            tfrs29 = bool(ceyrek_tarih >= pd.Timestamp('2024-01-01'))

            sektor = cfg.HISSE_SEKTOR.get(sembol, 'GENEL')

            kayit = {
                'ticker':              sembol,
                'gecerlilik_tarihi':   pit_tarih.strftime('%Y-%m-%d'),
                'ceyrek':              ceyrek_str,
                'ceyrek_bitis':        ceyrek_tarih.strftime('%Y-%m-%d'),
                'sektor':              sektor,
                'ebitda':              ebitda,
                'net_kar':             net_kar,
                'satislar':            satislar,
                'op_gelir':            op_gelir,
                'ozkaynaklar':         ozkaynaklar,
                'toplam_borc':         toplam_borc,
                'net_borc':            net_borc,
                'nakit':               nakit,
                'toplam_aktif':        toplam_aktif,
                'piyasa_degeri':       piyasa_degeri,
                'ev':                  ev,
                'ev_ebitda':           ev_ebitda,
                'roe':                 roe,
                'roa':                 roa,
                'pb':                  pb,
                'fcf_verim':           fcf_verim,
                'tfrs29':              tfrs29,
                'kaynak':              'yfinance_quarterly',
                '_cekme_tarihi':       datetime.now().strftime('%Y-%m-%d'),
            }
            kayitlar.append(kayit)

        # Cache kaydet
        if kayitlar:
            pd.DataFrame(kayitlar).to_parquet(cache_dosya, index=False)

        return kayitlar

    except Exception as e:
        logger.error(f"{sembol} hata: {type(e).__name__}: {e}")
        return []


def kaydet_pit(sembol: str, kayitlar: List[Dict[str, Any]]) -> bool:
    """Ceyreklik kayitlari data/fundamentals/ altina parquet olarak kaydet."""
    if not kayitlar:
        return False
    try:
        df = pd.DataFrame(kayitlar)
        df['gecerlilik_tarihi'] = pd.to_datetime(df['gecerlilik_tarihi'])
        df = df.sort_values('gecerlilik_tarihi').reset_index(drop=True)
        # _cekme_tarihi kolununu cikart (internal)
        df = df.drop(columns=['_cekme_tarihi'], errors='ignore')

        dosya_adi = sembol.replace('.', '_').replace('^', 'IDX_') + '.parquet'
        hedef = PIT_DIR / dosya_adi
        df.to_parquet(hedef, index=False)
        return True
    except Exception as e:
        logger.error(f"{sembol} kaydetme hatasi: {e}")
        return False


def calistir_tam_scrape(
    hisseler: Optional[List[str]] = None,
    max_workers: int = MAX_WORKERS,
    zorla: bool = False,
) -> Dict[str, Any]:
    """
    Tum hisseler icin paralel yfinance PIT verisi cekimi.

    Args:
        hisseler:    None ise cfg.HISSELER kullanilir
        max_workers: Paralel thread sayisi
        zorla:       True ise cache'i yoksay

    Returns:
        {basarili: int, bos: int, hatali: int, toplam: int}
    """
    if hisseler is None:
        hisseler = cfg.HISSELER

    if zorla:
        # Cache temizle
        for f in CACHE_DIR.glob("*.parquet"):
            f.unlink()
        logger.info("Cache temizlendi.")

    logger.info(f"PIT veri cekimi basladi: {len(hisseler)} hisse, {max_workers} thread")
    basarili = bos = hatali = 0
    sonuclar = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_hisse_cek, s): s for s in hisseler}

        for i, future in enumerate(as_completed(future_map), 1):
            sembol = future_map[future]
            try:
                kayitlar = future.result()
                if kayitlar:
                    basarili_kayit = kaydet_pit(sembol, kayitlar)
                    if basarili_kayit:
                        basarili += 1
                        logger.info(f"[{i}/{len(hisseler)}] {sembol}: {len(kayitlar)} ceyrek kaydedildi")
                    else:
                        hatali += 1
                else:
                    bos += 1
                    logger.warning(f"[{i}/{len(hisseler)}] {sembol}: Veri yok")
                sonuclar[sembol] = len(kayitlar)
            except Exception as e:
                hatali += 1
                logger.error(f"[{i}/{len(hisseler)}] {sembol}: {e}")

    ozet = {
        'basarili': basarili,
        'bos':      bos,
        'hatali':   hatali,
        'toplam':   len(hisseler),
        'kapsam':   f"{basarili/len(hisseler)*100:.0f}%",
    }

    logger.info(f"Tamamlandi: {basarili} basarili / {bos} bos / {hatali} hatali")
    return ozet


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test',   action='store_true', help='Sadece 3 hisse ile test')
    parser.add_argument('--zorla',  action='store_true', help='Cache yoksay, yeniden cek')
    parser.add_argument('--ticker', type=str, default=None)
    args = parser.parse_args()

    if args.ticker:
        kayitlar = _hisse_cek(args.ticker)
        kaydet_pit(args.ticker, kayitlar)
        df = pd.DataFrame(kayitlar)
        print(df[['gecerlilik_tarihi','ceyrek','ebitda','roe','pb','ev_ebitda']].to_string(index=False))
    elif args.test:
        ozet = calistir_tam_scrape(['THYAO.IS','AKBNK.IS','BIMAS.IS'], zorla=args.zorla)
        print('Test ozeti:', ozet)
    else:
        ozet = calistir_tam_scrape(zorla=args.zorla)
        rapor = cfg.BASE_DIR / 'reports' / 'pit_scrape_raporu.json'
        rapor.parent.mkdir(exist_ok=True)
        with open(rapor, 'w', encoding='utf-8') as f:
            json.dump(ozet, f, ensure_ascii=False, indent=2)
        print('Ozet:', ozet)
        print(f'Rapor: {rapor}')
