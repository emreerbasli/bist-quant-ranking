"""
bot/signal_logger.py — E3: Sinyal Loglama Şeması & Bileşen Başarı Takip Motoru
=============================================================================
Plan referansı: Aşama 2 (E3) — Analiz Kalitesi & Sinyal Doğruluk Raporu

Özellikler:
  1. HER sinyal için giriş anındaki TÜM girdi feature'larını (RSI, MACD, Hacim Oranı,
     Model Olasılığı, Momentum Tükenmesi, Değerleme İskontosu, Piyasa Rejimi vb.)
     SQLite (data/signals_log.db) ve CSV (data/signals_log.csv) formatında kaydeder.
  2. Pozisyon/sinyal kapandığında (TP, SL, TIMEOUT) gerçekleşen getiri ve her bileşenin
     (temel, teknik, hacim, makro) sinyal başarısına katkısını hesaplar.
  3. Walk-Forward / Brier / Kalibrasyon analizleri için temiz analitik veri tabanı sunar.
"""

import sys
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

import pandas as pd
import numpy as np
from loguru import logger

# Proje kökünü ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

DB_PATH  = getattr(cfg, "SIGNAL_LOG_DB_PATH", cfg.BASE_DIR / "data" / "signals_log.db")
CSV_PATH = getattr(cfg, "SIGNAL_LOG_CSV_PATH", cfg.BASE_DIR / "data" / "signals_log.csv")


def init_signal_log_db(db_path: Path = DB_PATH):
    """Sinyal günlüğü tablosunu SQLite üzerinde oluşturur."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sinyal_gunlugu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tarih TEXT NOT NULL,
                zaman TEXT NOT NULL,
                sembol TEXT NOT NULL,
                sektor TEXT,
                
                -- Fiyat & Seviyeler
                kapanis_fiyati REAL NOT NULL,
                planlanan_giris REAL NOT NULL,
                hedef_fiyat REAL NOT NULL,
                stop_fiyat REAL NOT NULL,
                atr_14 REAL NOT NULL,
                gercek_rr REAL NOT NULL,
                
                -- Model & Karar Katmanı
                model_olasiligi REAL NOT NULL,
                fikir_birligi_std REAL DEFAULT 0.0,
                islem_skoru INTEGER NOT NULL,
                karar_aksiyonu TEXT NOT NULL,
                karar_aciklama TEXT,
                
                -- Makro & Rejim
                piyasa_rejimi TEXT NOT NULL,
                vix_durum TEXT NOT NULL,
                kap_riski TEXT DEFAULT 'DUSUK',
                
                -- Teknik İndikatörler (Giriş Anı)
                rsi_14 REAL,
                macd_hist REAL,
                stoch_k REAL,
                vol_ratio_20 REAL,
                hacim_soku INTEGER DEFAULT 0,
                fiyat_ma20_sapma REAL,
                ret_5d REAL,
                ret_10d REAL,
                momentum_tukenmesi_skoru INTEGER DEFAULT 0,
                momentum_karar TEXT,
                
                -- Temel Analiz (Giriş Anı)
                fk_orani REAL,
                fk_sektor_orani REAL,
                pd_dd REAL,
                roe REAL,
                roa REAL,
                h1_deger_skoru REAL,
                h1_deger_etiketi TEXT,
                eps_surpriz_yonu INTEGER DEFAULT 0,
                eps_aciklama TEXT,
                eps_guvenilirlik TEXT,
                deger_momentum_celiski INTEGER DEFAULT 0,
                deger_momentum_aciklama TEXT,
                
                -- Göreceli Güç, Emsal & Kur
                fx_beta_60d REAL,
                vol_rejim_orani REAL,
                rel_str_xu100_5d REAL,
                rel_str_sektor_5d REAL,
                emsal_grubu TEXT,
                rel_str_emsal_5d REAL,
                emsal_lideri INTEGER DEFAULT 0,
                
                -- Sonuç & Değerlendirme Takibi (Çıkışta güncellenir)
                durum TEXT DEFAULT 'BEKLEMEDE', -- 'BEKLEMEDE', 'KAPANDI_TP', 'KAPANDI_SL', 'KAPANDI_TIMEOUT', 'IPTAL'
                gercek_giris_tarihi TEXT,
                gercek_giris_fiyati REAL,
                cikis_tarihi TEXT,
                cikis_fiyati REAL,
                cikis_nedeni TEXT,
                elde_tutma_gun INTEGER DEFAULT 0,
                gerceklesen_getiri_pct REAL,
                sinyal_dogru_mu INTEGER, -- 1: TP (Kazanç), 0: SL veya Timeout (Kayıp)
                
                -- Bileşen Doğruluk Katkıları (Post-mortem)
                temel_katki_dogru INTEGER,
                teknik_katki_dogru INTEGER,
                hacim_katki_dogru INTEGER,
                makro_katki_dogru INTEGER
            )
        """)
        conn.commit()
    finally:
        conn.close()


def kaydet_sinyal_girisi(sinyal_dict: Dict[str, Any], db_path: Path = DB_PATH) -> int:
    """
    Üretilen her yeni sinyali ve tüm girdi feature'larını eksiksiz loglar.
    """
    init_signal_log_db(db_path)
    simdi = datetime.now()
    tarih_str = sinyal_dict.get("tarih", str(simdi.date()))
    zaman_str = simdi.isoformat()

    sembol = sinyal_dict.get("sembol", "")
    kapanis = float(sinyal_dict.get("kapanis_fiyati", 0.0))
    atr = float(sinyal_dict.get("atr_14", sinyal_dict.get("atr", 0.0)))
    
    # Giriş, hedef ve stop seviyeleri
    planlanan_giris = float(sinyal_dict.get("planlanan_giris", kapanis * (1.0 - getattr(cfg, "LIMIT_GIRIS_ISKONTO", 0.003))))
    k1 = getattr(cfg, "K1", 1.5)
    k2 = getattr(cfg, "K2", 1.0)
    hedef = float(sinyal_dict.get("hedef_fiyat", planlanan_giris + (k1 * atr)))
    stop  = float(sinyal_dict.get("stop_fiyat", planlanan_giris - (k2 * atr)))

    risk = planlanan_giris - stop
    kazanc = hedef - planlanan_giris
    rr = round(kazanc / (risk + 1e-8), 2) if risk > 0 else 0.0

    payload = (
        tarih_str,
        zaman_str,
        sembol,
        sinyal_dict.get("sektor", cfg.HISSE_SEKTOR.get(sembol, "BIST")),
        kapanis,
        planlanan_giris,
        hedef,
        stop,
        atr,
        rr,
        float(sinyal_dict.get("kalibre_olasilik", sinyal_dict.get("model_olasiligi", 0.0))),
        float(sinyal_dict.get("fikir_birligi_std", 0.0)),
        int(sinyal_dict.get("islem_skoru", 0)),
        str(sinyal_dict.get("karar_aksiyonu", "AL")),
        str(sinyal_dict.get("karar_aciklama", "")),
        str(sinyal_dict.get("piyasa_rejimi", "YATAY")),
        str(sinyal_dict.get("vix_durum", "NORMAL")),
        str(sinyal_dict.get("kap_riski", "DUSUK")),
        # Teknik
        float(sinyal_dict.get("rsi_14", 50.0)),
        float(sinyal_dict.get("macd_hist", 0.0)),
        float(sinyal_dict.get("stoch_k", 50.0)),
        float(sinyal_dict.get("vol_ratio_20", 1.0)),
        int(sinyal_dict.get("hacim_soku", 0)),
        float(sinyal_dict.get("fiyat_ma20_sapma", 0.0)),
        float(sinyal_dict.get("ret_5d", 0.0)),
        float(sinyal_dict.get("ret_10d", 0.0)),
        int(sinyal_dict.get("momentum_tukenmesi_skoru", sinyal_dict.get("momentum_tukenmesi", 0))),
        str(sinyal_dict.get("momentum_karar", "NORMAL")),
        # Temel (H1 dahil)
        float(sinyal_dict.get("fk_orani", 8.5)),
        float(sinyal_dict.get("fk_sektor_orani", 0.0)),
        float(sinyal_dict.get("pd_dd", 1.0)),
        float(sinyal_dict.get("roe", 0.14)),
        float(sinyal_dict.get("roa", 0.06)),
        float(sinyal_dict.get("h1_deger_skoru", 0.0)),
        str(sinyal_dict.get("h1_deger_etiketi", "ADIL")),
        int(sinyal_dict.get("eps_surpriz_yonu", 0)),
        str(sinyal_dict.get("eps_aciklama", "")),
        str(sinyal_dict.get("eps_guvenilirlik", "ORTA")),
        int(sinyal_dict.get("deger_momentum_celiski", 0)),
        str(sinyal_dict.get("deger_momentum_aciklama", "")),
        # Göreceli & Emsal (G1 dahil)
        float(sinyal_dict.get("fx_beta_60d", 0.0)),
        float(sinyal_dict.get("vol_rejim_orani", 1.0)),
        float(sinyal_dict.get("rel_str_xu100_5d", 0.0)),
        float(sinyal_dict.get("rel_str_sektor_5d", 0.0)),
        str(sinyal_dict.get("emsal_grubu", "GENEL_BIST")),
        float(sinyal_dict.get("rel_str_emsal_5d", 0.0)),
        1 if sinyal_dict.get("emsal_lideri", False) else 0,
    )

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sinyal_gunlugu (
                tarih, zaman, sembol, sektor, kapanis_fiyati, planlanan_giris, hedef_fiyat, stop_fiyat,
                atr_14, gercek_rr, model_olasiligi, fikir_birligi_std, islem_skoru, karar_aksiyonu,
                karar_aciklama, piyasa_rejimi, vix_durum, kap_riski, rsi_14, macd_hist, stoch_k,
                vol_ratio_20, hacim_soku, fiyat_ma20_sapma, ret_5d, ret_10d, momentum_tukenmesi_skoru,
                momentum_karar, fk_orani, fk_sektor_orani, pd_dd, roe, roa, h1_deger_skoru,
                h1_deger_etiketi, eps_surpriz_yonu, eps_aciklama, eps_guvenilirlik,
                deger_momentum_celiski, deger_momentum_aciklama, fx_beta_60d, vol_rejim_orani,
                rel_str_xu100_5d, rel_str_sektor_5d, emsal_grubu, rel_str_emsal_5d, emsal_lideri
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, payload)
        conn.commit()
        sinyal_id = cursor.lastrowid
    finally:
        conn.close()

    logger.info(f"📊 Sinyal Günlüğe Kaydedildi: ID={sinyal_id} | {sembol} | Skor={sinyal_dict.get('islem_skoru')} | Karar={sinyal_dict.get('karar_aksiyonu')}")
    _csv_aynayi_guncelle(db_path)
    return sinyal_id


def guncelle_sinyal_sonucu(
    sinyal_id: int,
    cikis_tarihi: str,
    cikis_fiyati: float,
    cikis_nedeni: str,
    elde_tutma_gun: int,
    db_path: Path = DB_PATH,
) -> None:
    """
    Sinyalin nihai sonucunu (TP/SL/Timeout) ve getirisini kaydeder.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT planlanan_giris, eps_surpriz_yonu, rsi_14, vol_ratio_20, piyasa_rejimi FROM sinyal_gunlugu WHERE id = ?", (sinyal_id,))
        row = cursor.fetchone()
        if not row:
            logger.warning(f"Sinyal ID {sinyal_id} bulunamadı!")
            return

        giris_fiyati, eps_yon, rsi, vol_rat, rejim = row
        net_ret = (cikis_fiyati - giris_fiyati) / (giris_fiyati + 1e-8)
        sinyal_dogru = 1 if "TP" in cikis_nedeni or net_ret > 0.015 else 0

        # Bileşen Katkı Değerlendirmeleri (Post-Mortem)
        temel_dogru  = 1 if (eps_yon > 0 and net_ret > 0) or (eps_yon <= 0 and net_ret <= 0) else 0
        teknik_dogru = 1 if (rsi < 65 and net_ret > 0) or (rsi >= 70 and net_ret <= 0) else 0
        hacim_dogru  = 1 if (vol_rat > 1.2 and net_ret > 0) else 0
        makro_dogru  = 1 if ("YUKSELIS" in rejim and net_ret > 0) or ("DUSUS" in rejim and net_ret <= 0) else 0

        durum_str = f"KAPANDI_{cikis_nedeni}"

        cursor.execute("""
            UPDATE sinyal_gunlugu SET
                durum = ?,
                cikis_tarihi = ?,
                cikis_fiyati = ?,
                cikis_nedeni = ?,
                elde_tutma_gun = ?,
                gerceklesen_getiri_pct = ?,
                sinyal_dogru_mu = ?,
                temel_katki_dogru = ?,
                teknik_katki_dogru = ?,
                hacim_katki_dogru = ?,
                makro_katki_dogru = ?
            WHERE id = ?
        """, (
            durum_str, cikis_tarihi, cikis_fiyati, cikis_nedeni, elde_tutma_gun,
            round(net_ret * 100.0, 2), sinyal_dogru, temel_dogru, teknik_dogru,
            hacim_dogru, makro_dogru, sinyal_id
        ))
        conn.commit()
    finally:
        conn.close()


    logger.info(f"🏁 Sinyal Sonucu Güncellendi: ID={sinyal_id} | Durum={durum_str} | Getiri=%{net_ret*100:.2f} | Doğru={sinyal_dogru}")
    _csv_aynayi_guncelle(db_path)


def _csv_aynayi_guncelle(db_path: Path = DB_PATH, csv_path: Path = CSV_PATH) -> None:
    """Veritabanındaki günlüğü kolay analiz için CSV dosyasına da yansıtır."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM sinyal_gunlugu ORDER BY id DESC", conn)
        if not df.empty:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    except Exception as e:
        logger.debug(f"CSV aynalama hatası: {e}")
    finally:
        if conn:
            conn.close()


def getir_sinyal_gecmisi_df(db_path: Path = DB_PATH) -> pd.DataFrame:
    """Tüm sinyal günlüğünü DataFrame olarak çeker."""
    init_signal_log_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query("SELECT * FROM sinyal_gunlugu ORDER BY id DESC", conn)
        return df
    finally:
        conn.close()


def hesapla_bilesen_performans_raporu(db_path: Path = DB_PATH) -> Dict[str, Any]:
    """
    E3: Her bir analiz bileşeninin (temel, teknik, hacim, makro) sinyal doğruluk
    oranına olan katkısını ve hata kaynaklarını raporlar.
    """
    df = getir_sinyal_gecmisi_df(db_path)
    if df.empty:
        return {"toplam_sinyal": 0, "tamamlanan_sinyal": 0, "genel_win_rate": 0.0}

    tamamlanan = df.dropna(subset=["sinyal_dogru_mu"]).copy()
    if tamamlanan.empty:
        return {
            "toplam_sinyal": len(df),
            "tamamlanan_sinyal": 0,
            "bekleyen_sinyal": len(df),
            "genel_win_rate": 0.0,
        }

    n = len(tamamlanan)
    win_rate = float(tamamlanan["sinyal_dogru_mu"].mean() * 100.0)
    avg_return = float(tamamlanan["gerceklesen_getiri_pct"].mean())

    # Bileşen Bazlı Başarı Oranları
    temel_basari  = float(tamamlanan["temel_katki_dogru"].mean() * 100.0) if "temel_katki_dogru" in tamamlanan else 0.0
    teknik_basari = float(tamamlanan["teknik_katki_dogru"].mean() * 100.0) if "teknik_katki_dogru" in tamamlanan else 0.0
    hacim_basari  = float(tamamlanan["hacim_katki_dogru"].mean() * 100.0) if "hacim_katki_dogru" in tamamlanan else 0.0
    makro_basari  = float(tamamlanan["makro_katki_dogru"].mean() * 100.0) if "makro_katki_dogru" in tamamlanan else 0.0

    return {
        "toplam_sinyal": len(df),
        "tamamlanan_sinyal": n,
        "bekleyen_sinyal": len(df) - n,
        "genel_win_rate": round(win_rate, 1),
        "ortalama_getiri_pct": round(avg_return, 2),
        "bilesen_basari_oranlari": {
            "temel_analiz_dogruluk_%": round(temel_basari, 1),
            "teknik_analiz_dogruluk_%": round(teknik_basari, 1),
            "hacim_onayi_dogruluk_%": round(hacim_basari, 1),
            "makro_rejim_dogruluk_%": round(makro_basari, 1),
        }
    }
