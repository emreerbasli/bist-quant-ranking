"""
features/kap_scraper/isyatirim_pit_builder.py — İş Yatırım PIT Temel Veri Çekici
================================================================================
Mükemmelleştirme Planı Referansı: FAZ A (Tam Tarihsel PIT Temel Veri Altyapısı)

Bu modül:
  1. İş Yatırım MaliTablo API'sinden 88 hissenin 2018-2026 (32 çeyrek) tablolarını çeker.
  2. Sanayi/Holding (XI_29) ve Banka (UFRS) finansal gruplarını otomatik tespit eder.
  3. BIST yasal bildirim takvimine göre kesin PIT açıklanma tarihlerini (gecerlilik_tarihi) atar:
     - Q1 (03-31) -> 15 Mayıs (+45 gün)
     - Q2 (06-30) -> 15 Ağustos (+45 gün)
     - Q3 (09-30) -> 15 Kasım (+45 gün)
     - Q4 (12-31) -> 15 Mart (+75 gün, bağımsız denetim süresi)
  4. HisseTekil API veya raw fiyat parquet dosyalarından PIT tarihindeki Piyasa Değerini (PD)
     alır ve kurumsal rasyoları (EV/EBITDA, P/B, ROE, ROA, FCF Verim, İhracat Oranı) hesaplar.
  5. Çıktı: data/fundamentals/{TICKER_IS}.parquet (fundamental_pit.py MOD 2 ile %100 uyumlu)
"""

import sys
import json
import time
import urllib3
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import concurrent.futures

import pandas as pd
import numpy as np
import requests
from loguru import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Proje kök dizini
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

# Dizinler
DATA_DIR = cfg.BASE_DIR / "data"
FUND_DIR = DATA_DIR / "fundamentals"
CACHE_DIR = DATA_DIR / "raw" / "isyatirim_cache"
FUND_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

BASE_URL_MALI = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/MaliTablo"
BASE_URL_TEKIL = "https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx/HisseTekil"

START_YEAR = 2018
END_YEAR = 2026


# ─── 1. İŞ YATIRIM MALİ TABLO ÇEKİCİ ─────────────────────────────────────────
def _get_mali_tablo_yil(session: requests.Session,
                         company_code: str,
                         group: str,
                         year: int) -> List[Dict[str, Any]]:
    """Bir şirket ve yıl için 4 çeyreğin mali tablosunu çeker."""
    params = {
        "companyCode": company_code,
        "exchange": "TRY",
        "financialGroup": group,
        "year1": year, "period1": 3,
        "year2": year, "period2": 6,
        "year3": year, "period3": 9,
        "year4": year, "period4": 12
    }
    try:
        r = session.get(BASE_URL_MALI, params=params, headers=HEADERS, timeout=12, verify=False)
        if r.status_code == 200:
            data = r.json()
            return data.get("value", [])
    except Exception as e:
        logger.debug(f"{company_code} ({year}, {group}) mali tablo hatası: {e}")
    return []


def _tespit_finansal_grup(session: requests.Session, company_code: str) -> str:
    """Şirketin XI_29 (Sanayi/Holding) mi yoksa UFRS (Banka) mı olduğunu tespit eder."""
    # Test yılı: 2024
    res_xi29 = _get_mali_tablo_yil(session, company_code, "XI_29", 2024)
    if len(res_xi29) > 20:
        return "XI_29"
    res_ufrs = _get_mali_tablo_yil(session, company_code, "UFRS", 2024)
    if len(res_ufrs) > 20:
        return "UFRS"
    # Fallback 2023 dene
    res_xi29_23 = _get_mali_tablo_yil(session, company_code, "XI_29", 2023)
    if len(res_xi29_23) > 20:
        return "XI_29"
    return "XI_29"


def _safe_float(val: Any) -> float:
    if val is None or val == "" or val == "null":
        return np.nan
    try:
        f = float(str(val).replace(",", ".").replace(" ", ""))
        return f if not np.isnan(f) else np.nan
    except Exception:
        return np.nan


# ─── 2. HİSSE TEKİL (PİYASA DEĞERİ VE SERMAYE) ÇEKİCİ ─────────────────────────
def _get_hisse_tekil_serisi(session: requests.Session, company_code: str) -> pd.DataFrame:
    """HisseTekil API'sinden 2018-2026 günlük PD, HAO_PD ve Sermaye verilerini çeker."""
    cache_file = CACHE_DIR / f"{company_code}_tekil.parquet"
    if cache_file.exists():
        try:
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if (datetime.now() - mtime).days < 7:
                return pd.read_parquet(cache_file)
        except Exception:
            pass

    params = {
        "hisse": company_code,
        "startdate": f"01-01-{START_YEAR}",
        "enddate": datetime.now().strftime("%d-%m-%Y")
    }
    try:
        r = session.get(BASE_URL_TEKIL, params=params, headers=HEADERS, timeout=15, verify=False)
        if r.status_code == 200:
            val = r.json().get("value", [])
            if val:
                df = pd.DataFrame(val)
                if "HGDG_TARIH" in df.columns:
                    df["tarih"] = pd.to_datetime(df["HGDG_TARIH"], format="%d-%m-%Y", errors="coerce")
                    df = df.dropna(subset=["tarih"]).sort_values("tarih").set_index("tarih")
                    for col in ["PD", "PD_USD", "HAO_PD", "SERMAYE", "HGDG_KAPANIS"]:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                    df.to_parquet(cache_file)
                    return df
    except Exception as e:
        logger.debug(f"{company_code} hisse tekil çekim hatası: {e}")
    return pd.DataFrame()


# ─── 3. ÇEYREKLİK KALEM PARSE VE BİRLEŞTİRME ─────────────────────────────────
def cek_ve_birlestir_hisse(sembol: str, zorla: bool = False) -> Optional[pd.DataFrame]:
    """
    Tek hisse için 2018-2026 tüm çeyrekleri çeker, kurumsal metrikleri hesaplar
    ve PIT takvimiyle hizalayıp DataFrame döndürür.
    """
    ticker_clean = sembol.replace(".IS", "").replace("^", "").replace("=", "")
    dosya_adi = sembol.replace("^", "IDX_").replace(".", "_").replace("=", "_")
    cikti_parquet = FUND_DIR / f"{dosya_adi}.parquet"

    if cikti_parquet.exists() and not zorla:
        try:
            df_var = pd.read_parquet(cikti_parquet)
            if len(df_var) >= 15:
                return df_var
        except Exception:
            pass

    session = requests.Session()
    group = _tespit_finansal_grup(session, ticker_clean)
    is_bank = (group == "UFRS")

    # Günlük piyasa değeri ve sermaye tablosunu al
    df_tekil = _get_hisse_tekil_serisi(session, ticker_clean)

    # Raw fiyat dosyasından alternatif kapanış fiyatı al
    df_raw_fiyat = None
    raw_dosya = cfg.DATA_RAW / f"{dosya_adi}.parquet"
    if raw_dosya.exists():
        try:
            df_rf = pd.read_parquet(raw_dosya)
            if "close" in df_rf.columns:
                df_raw_fiyat = df_rf["close"].sort_index()
        except Exception:
            pass

    sektor = cfg.HISSE_SEKTOR.get(sembol, "XUSIN.IS")

    # Tüm yılları çek
    raw_years_data = {}
    for year in range(START_YEAR, END_YEAR + 1):
        cache_json = CACHE_DIR / f"{ticker_clean}_{year}_{group}.json"
        if cache_json.exists() and not zorla:
            try:
                with open(cache_json, "r", encoding="utf-8") as f:
                    val = json.load(f)
            except Exception:
                val = _get_mali_tablo_yil(session, ticker_clean, group, year)
                with open(cache_json, "w", encoding="utf-8") as f:
                    json.dump(val, f)
        else:
            val = _get_mali_tablo_yil(session, ticker_clean, group, year)
            if val:
                with open(cache_json, "w", encoding="utf-8") as f:
                    json.dump(val, f)
            time.sleep(0.05)  # Nazik istek gecikmesi

        if val:
            raw_years_data[year] = val

    if not raw_years_data:
        logger.warning(f"{sembol}: Hiç mali tablo verisi bulunamadı!")
        return None

    # Çeyreklik satırları oluştur
    ceyreklik_kayitlar = []

    for year in sorted(raw_years_data.keys()):
        items_list = raw_years_data[year]
        # ItemCode -> {value1, value2, value3, value4} sözlüğü
        kod_deger = {}
        for it in items_list:
            c = it.get("itemCode")
            if c:
                kod_deger[c] = (
                    _safe_float(it.get("value1")),
                    _safe_float(it.get("value2")),
                    _safe_float(it.get("value3")),
                    _safe_float(it.get("value4"))
                )

        period_configs = [
            (1, "03-31", f"{year}-05-15", 0),  # Q1 -> 15 Mayıs (+45g)
            (2, "06-30", f"{year}-08-15", 1),  # Q2 -> 15 Ağustos (+45g)
            (3, "09-30", f"{year}-11-15", 2),  # Q3 -> 15 Kasım (+45g)
            (4, "12-31", f"{year+1}-03-15", 3) # Q4 -> 15 Mart (+75g)
        ]

        for q_num, bitis_gun, pit_gun, p_idx in period_configs:
            ceyrek_str = f"{year}Q{q_num}"
            ceyrek_bitis = f"{year}-{bitis_gun}"
            gecerlilik_tarihi = pd.Timestamp(pit_gun)

            # Gelecekteki çeyrekler için açıklanmadıysa atla
            if gecerlilik_tarihi > pd.Timestamp.now() + pd.Timedelta(days=15):
                continue

            def val_at(kod: str) -> float:
                if kod in kod_deger:
                    return kod_deger[kod][p_idx]
                return np.nan

            # --- Kalem Çıkarımları ---
            if not is_bank:
                # Sanayi / Holding
                satislar = val_at("3C")
                yurtdisi = val_at("4BD")
                yurtici  = val_at("4BC")
                net_faal = val_at("3H")
                amort    = val_at("4B") if not np.isnan(val_at("4B")) else val_at("4CAB")
                net_kar  = val_at("3L") if not np.isnan(val_at("3L")) else val_at("3Z")
                ozkaynak = val_at("2N") if not np.isnan(val_at("2N")) else val_at("2O")
                borc_kisa= val_at("2AA")
                borc_uzun= val_at("2BA")
                nakit    = val_at("1AA")
                aktif    = val_at("2ODB")
                cfo      = val_at("4C")
                fcf      = val_at("4CB")
                net_fx   = val_at("4BE")

                toplam_borc = (0.0 if np.isnan(borc_kisa) else borc_kisa) + (0.0 if np.isnan(borc_uzun) else borc_uzun)
                if np.isnan(borc_kisa) and np.isnan(borc_uzun):
                    toplam_borc = np.nan

                net_borc = toplam_borc - (0.0 if np.isnan(nakit) else nakit) if not np.isnan(toplam_borc) else np.nan

                # EBITDA = Net Faaliyet Kârı + Amortisman
                ebitda = np.nan
                if not np.isnan(net_faal):
                    ebitda = net_faal + (0.0 if np.isnan(amort) else amort)

                # İhracat oranı
                ihracat_orani = np.nan
                if not np.isnan(yurtdisi) and yurtdisi > 0:
                    toplam_satis = (yurtici if not np.isnan(yurtici) else 0.0) + yurtdisi
                    if toplam_satis > 0:
                        ihracat_orani = yurtdisi / toplam_satis
                    elif not np.isnan(satislar) and satislar > 0:
                        ihracat_orani = yurtdisi / satislar

                kayit = {
                    "ticker": sembol,
                    "gecerlilik_tarihi": gecerlilik_tarihi,
                    "ceyrek": ceyrek_str,
                    "ceyrek_bitis": ceyrek_bitis,
                    "sektor": sektor,
                    "is_bank": False,
                    "ebitda": ebitda,
                    "net_kar": net_kar,
                    "satislar": satislar,
                    "op_gelir": net_faal,
                    "ozkaynaklar": ozkaynak,
                    "toplam_borc": toplam_borc,
                    "net_borc": net_borc,
                    "nakit": nakit,
                    "toplam_aktif": aktif,
                    "cfo": cfo,
                    "fcf": fcf,
                    "ihracat_orani": ihracat_orani,
                    "net_fx": net_fx,
                    "tfrs29": (year >= 2024 or (year == 2023 and q_num == 4)),
                    "kaynak": "isyatirim_pit"
                }
            else:
                # Banka (UFRS)
                faiz_gelir = val_at("3AA")
                net_kar    = val_at("3Z")
                ozkaynak   = val_at("2O") if not np.isnan(val_at("2O")) else val_at("2N")
                kredi_karş = val_at("3CF")
                komisyon   = val_at("3CAA")
                krediler   = val_at("1AF")
                takip_kredi= val_at("1AFD")
                aktif      = val_at("2ODB")

                npl_orani = np.nan
                if not np.isnan(takip_kredi) and not np.isnan(krediler) and krediler > 0:
                    npl_orani = takip_kredi / krediler

                kayit = {
                    "ticker": sembol,
                    "gecerlilik_tarihi": gecerlilik_tarihi,
                    "ceyrek": ceyrek_str,
                    "ceyrek_bitis": ceyrek_bitis,
                    "sektor": sektor,
                    "is_bank": True,
                    "ebitda": np.nan,
                    "net_kar": net_kar,
                    "satislar": faiz_gelir,
                    "op_gelir": faiz_gelir,
                    "ozkaynaklar": ozkaynak,
                    "toplam_borc": np.nan,
                    "net_borc": np.nan,
                    "nakit": np.nan,
                    "toplam_aktif": aktif,
                    "cfo": np.nan,
                    "fcf": np.nan,
                    "ihracat_orani": 0.0,
                    "net_fx": np.nan,
                    "kredi_karsiligi": kredi_karş,
                    "komisyon": komisyon,
                    "npl_orani": npl_orani,
                    "tfrs29": False,  # Bankalar enflasyon muhasebesi kapsamı dışındadır
                    "kaynak": "isyatirim_bank_pit"
                }

            # En azından net_kar veya ozkaynaklar varsa ekle
            if not np.isnan(kayit.get("net_kar", np.nan)) or not np.isnan(kayit.get("ozkaynaklar", np.nan)):
                ceyreklik_kayitlar.append(kayit)

    if not ceyreklik_kayitlar:
        logger.warning(f"{sembol}: Uygun bilanço kaydı parse edilemedi!")
        return None

    df_res = pd.DataFrame(ceyreklik_kayitlar).sort_values("gecerlilik_tarihi").reset_index(drop=True)

    # ─── PİYASA DEĞERİ VE ÇARPANLARI HİZALA (PIT-DOĞRU) ──────────────────────
    piyasa_degerleri = []
    pd_usd_degerleri = []
    hao_pd_degerleri = []
    pb_degerleri     = []
    roe_degerleri    = []
    roa_degerleri    = []
    ev_degerleri     = []
    ev_ebitda_deger  = []
    fcf_verim_deger  = []

    for _, row in df_res.iterrows():
        t_pit = row["gecerlilik_tarihi"]
        ozk = row["ozkaynaklar"]
        aktif = row["toplam_aktif"]
        nkar = row["net_kar"]
        ebitda = row["ebitda"]
        net_b = row["net_borc"]
        fcf = row["fcf"]

        # Piyasa değeri bul: df_tekil'den t_pit tarihindeki son geçerli bar
        pd_val = np.nan
        pd_usd = np.nan
        hao_pd = np.nan

        if not df_tekil.empty:
            gecmis_tekil = df_tekil[df_tekil.index <= t_pit]
            if not gecmis_tekil.empty:
                son_row = gecmis_tekil.iloc[-1]
                pd_val = son_row.get("PD", np.nan)
                pd_usd = son_row.get("PD_USD", np.nan)
                hao_pd = son_row.get("HAO_PD", np.nan)

        # df_tekil'de yoksa raw fiyattan sharesOutstanding ile dene
        if (np.isnan(pd_val) or pd_val <= 0) and df_raw_fiyat is not None:
            gecmis_fiyat = df_raw_fiyat[df_raw_fiyat.index <= t_pit]
            if not gecmis_fiyat.empty and not df_tekil.empty and "SERMAYE" in df_tekil.columns:
                sermaye = df_tekil["SERMAYE"].dropna().iloc[-1]
                pd_val = float(gecmis_fiyat.iloc[-1] * sermaye)

        piyasa_degerleri.append(pd_val)
        pd_usd_degerleri.append(pd_usd)
        hao_pd_degerleri.append(hao_pd)

        # P/B = Piyasa Değeri / Özkaynaklar
        pb = np.nan
        if not np.isnan(pd_val) and not np.isnan(ozk) and ozk > 0:
            pb = float(pd_val / ozk)
        pb_degerleri.append(pb)

        # ROE = Net Kâr / Özkaynaklar
        roe = np.nan
        if not np.isnan(nkar) and not np.isnan(ozk) and ozk > 0:
            roe = float(nkar / ozk)
        roe_degerleri.append(roe)

        # ROA = Net Kâr / Toplam Aktif
        roa = np.nan
        if not np.isnan(nkar) and not np.isnan(aktif) and aktif > 0:
            roa = float(nkar / aktif)
        roa_degerleri.append(roa)

        # EV = Piyasa Değeri + Net Borç
        ev = np.nan
        if not np.isnan(pd_val):
            ev = pd_val + (0.0 if np.isnan(net_b) else net_b)
        ev_degerleri.append(ev)

        # EV/EBITDA
        eveb = np.nan
        if not np.isnan(ev) and not np.isnan(ebitda) and ebitda > 0:
            eveb = float(ev / ebitda)
        ev_ebitda_deger.append(eveb)

        # FCF Verimi
        fcf_v = np.nan
        if not np.isnan(fcf) and not np.isnan(pd_val) and pd_val > 0:
            fcf_v = float(fcf / pd_val)
        fcf_verim_deger.append(fcf_v)

    df_res["piyasa_degeri"] = piyasa_degerleri
    df_res["pd_usd"]        = pd_usd_degerleri
    df_res["hao_pd"]        = hao_pd_degerleri
    df_res["pb"]            = pb_degerleri
    df_res["roe"]           = roe_degerleri
    df_res["roa"]           = roa_degerleri
    df_res["ev"]            = ev_degerleri
    df_res["ev_ebitda"]     = ev_ebitda_deger
    df_res["fcf_verim"]     = fcf_verim_deger

    df_res.to_parquet(cikti_parquet, index=False)
    logger.info(f"✓ {sembol:<10} | {len(df_res):>2} çeyrek | Grup: {group:<6} | {df_res['ceyrek'].iloc[0]} -> {df_res['ceyrek'].iloc[-1]}")
    return df_res


# ─── 4. PARALEL ÇALIŞTIRICI ──────────────────────────────────────────────────
def calistir_tam_pit_scrape(hisseler: Optional[List[str]] = None,
                            max_workers: int = 8,
                            zorla: bool = False) -> Dict[str, Any]:
    """Tüm evrendeki hisseler için İş Yatırım PIT tabanlı veri çekimini paralel yürütür."""
    if hisseler is None:
        hisseler = cfg.HISSELER

    logger.info(f"İş Yatırım PIT Scraper Başlatılıyor: {len(hisseler)} hisse, {max_workers} thread...")
    t0 = time.time()

    basarili = 0
    hatali = 0
    toplam_ceyrek = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        gelecekler = {executor.submit(cek_ve_birlestir_hisse, s, zorla): s for s in hisseler}
        for future in concurrent.futures.as_completed(gelecekler):
            sembol = gelecekler[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    basarili += 1
                    toplam_ceyrek += len(df)
                else:
                    hatali += 1
            except Exception as e:
                logger.error(f"{sembol} genel hata: {e}")
                hatali += 1

    gecen = time.time() - t0
    logger.info("=" * 65)
    logger.info(f"Tamamlandı: {basarili}/{len(hisseler)} başarılı (%{basarili/len(hisseler)*100:.1f})")
    logger.info(f"Toplam Çeyrek: {toplam_ceyrek} bilanço | Süre: {gecen:.1f} saniye")
    logger.info("=" * 65)

    return {
        "basarili": basarili,
        "hatali": hatali,
        "toplam_hisse": len(hisseler),
        "toplam_ceyrek": toplam_ceyrek,
        "sure_sn": round(gecen, 1)
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="İş Yatırım PIT Bilanço Scraper")
    parser.add_argument("--test", action="store_true", help="Sadece 3 hisse ile test et")
    parser.add_argument("--zorla", action="store_true", help="Mevcut parquet'leri ez")
    parser.add_argument("--workers", type=int, default=8, help="Paralel thread sayısı")
    args = parser.parse_args()

    if args.test:
        test_syms = ["THYAO.IS", "AKBNK.IS", "SAHOL.IS"]
        print(f"Test modu: {test_syms}")
        calistir_tam_pit_scrape(test_syms, max_workers=3, zorla=args.zorla)
    else:
        calistir_tam_pit_scrape(max_workers=args.workers, zorla=args.zorla)
