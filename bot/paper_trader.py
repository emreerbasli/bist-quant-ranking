"""
bot/paper_trader.py — FAZ 6: Paper Trading Sanal Portföy & Pozisyon Takip Motoru
================================================================================
Plan referansı: FAZ 6 (bist_sinyal_botu_proje_plani_v2.md)

Özellikler:
  1. SQLite veritabanı (data/paper_trading.db) üzerinde sanal pozisyonları yönetir.
  2. Her akşam çalıştırıldığında açık pozisyonların günün High / Low değerlerine göre
     TP, SL veya 5 günlük Zaman Aşımı (Timeout) durumunu değerlendirir ve kapatır.
  3. Gün içi tarama YOKTUR; sistem sadece günlük kapanmış barlara sadık kalır.
  4. Komisyon ve kayma maliyetlerini düşerek net gerçekleşen PnL ve Win-Rate takibi yapar.
"""

import sys
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

import pandas as pd
import yfinance as yf
from loguru import logger

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg
from backtest.risk_kurallari import hesapla_islem_maliyeti

DB_PATH = cfg.BASE_DIR / "data" / "paper_trading.db"


def init_db(db_path: Path = DB_PATH):
    """SQLite veritabanını ve tablolarını oluşturur, eksik kolonları migrate eder."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        # Pozisyonlar tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pozisyonlar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sembol TEXT NOT NULL,
                sektor TEXT,
                durum TEXT NOT NULL, -- 'ACIK', 'KAPANDI_TP', 'KAPANDI_SL', 'KAPANDI_BREAKEVEN', 'KAPANDI_TIMEOUT', 'KAPANDI_MANUEL'
                giris_tarihi TEXT NOT NULL,
                giris_fiyati REAL NOT NULL,
                lot_adedi INTEGER NOT NULL,
                nominal_tutar REAL NOT NULL,
                upper_barrier REAL NOT NULL,
                lower_barrier REAL NOT NULL,
                atr REAL NOT NULL,
                islem_skoru INTEGER,
                kalibre_olasilik REAL,
                elde_tutma_gun INTEGER DEFAULT 1,
                tp1_alindi INTEGER DEFAULT 0,
                kismi_kar_tl REAL DEFAULT 0.0,
                cikis_tarihi TEXT,
                cikis_fiyati REAL,
                cikis_nedeni TEXT,
                net_pnl_tl REAL DEFAULT 0.0,
                net_getiri_pct REAL DEFAULT 0.0,
                toplam_maliyet_tl REAL DEFAULT 0.0
            )
        """)

        # Migration: tp1_alindi ve kismi_kar_tl kolonları yoksa ekle
        cursor.execute("PRAGMA table_info(pozisyonlar)")
        cols = [c[1] for c in cursor.fetchall()]
        if "tp1_alindi" not in cols:
            cursor.execute("ALTER TABLE pozisyonlar ADD COLUMN tp1_alindi INTEGER DEFAULT 0")
        if "kismi_kar_tl" not in cols:
            cursor.execute("ALTER TABLE pozisyonlar ADD COLUMN kismi_kar_tl REAL DEFAULT 0.0")

        # Portföy bakiye geçmişi
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfoy_bakiye (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tarih TEXT NOT NULL,
                nakit REAL NOT NULL,
                toplam_portfoy REAL NOT NULL,
                acik_pozisyon_sayisi INTEGER NOT NULL
            )
        """)
        conn.commit()


def yeni_pozisyon_ac(
    sembol: str,
    giris_fiyati: float,
    lot_adedi: int,
    upper_barrier: float,
    lower_barrier: float,
    atr: float,
    islem_skoru: int,
    kalibre_olasilik: float,
    sektor: str = "BIST",
    tarih_str: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> int:
    """Yeni bir paper trading pozisyonu kaydeder."""
    init_db(db_path)
    if tarih_str is None:
        tarih_str = str(datetime.now().date())

    nominal = lot_adedi * giris_fiyati
    _, _, giris_maliyeti = hesapla_islem_maliyeti(nominal, sembol)

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pozisyonlar (
                sembol, sektor, durum, giris_tarihi, giris_fiyati, lot_adedi,
                nominal_tutar, upper_barrier, lower_barrier, atr, islem_skoru,
                kalibre_olasilik, elde_tutma_gun, tp1_alindi, kismi_kar_tl, toplam_maliyet_tl
            ) VALUES (?, ?, 'ACIK', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 0.0, ?)
        """, (
            sembol, sektor, tarih_str, giris_fiyati, lot_adedi,
            nominal, upper_barrier, lower_barrier, atr, islem_skoru,
            kalibre_olasilik, giris_maliyeti
        ))
        conn.commit()
        poz_id = cursor.lastrowid
        logger.info(f"Paper Trading: #{sembol} pozisyonu açıldı (ID: {poz_id}, Giriş: {giris_fiyati:.2f} TL, Lot: {lot_adedi})")
        return poz_id


def getir_acik_pozisyonlar(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """Tüm açık pozisyonları döner."""
    init_db(db_path)
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pozisyonlar WHERE durum = 'ACIK'")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def getir_tum_islemler(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """Kapanan ve açık tüm işlemleri döner."""
    init_db(db_path)
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pozisyonlar ORDER BY id DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def guncelle_gunluk_paper_trading(
    bugun_str: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Her akşam 18:45'te çağrılır.
    Açık pozisyonların günün son mumuna göre Kademeli TP1, Breakeven Stop, TP2 veya 5 günlük Zaman Aşımı durumunu kontrol eder.
    Gap-down / Taban açılış kayma (slippage) koruması entegredir.
    """
    init_db(db_path)
    if bugun_str is None:
        bugun_str = str(datetime.now().date())

    aciklar = getir_acik_pozisyonlar(db_path)
    if not aciklar:
        logger.debug("Paper Trading: Açık pozisyon bulunmuyor.")
        return []

    kapanan_islemler = []

    for poz in aciklar:
        sembol = poz["sembol"]
        poz_id = poz["id"]
        tp1_alindi = int(poz.get("tp1_alindi", 0))
        kismi_kar = float(poz.get("kismi_kar_tl", 0.0))
        
        # Güncel günlük mumu data/raw üzerinden veya yfinance'ten oku
        dosya = cfg.DATA_RAW / f"{sembol.replace('.', '_')}.parquet"
        if dosya.exists():
            df = pd.read_parquet(dosya)
            son_row = df.iloc[-1]
            open_price = float(son_row["open"]) if "open" in son_row else float(son_row.get("Open", son_row["close"]))
            high = float(son_row["high"])
            low = float(son_row["low"])
            close = float(son_row["close"])
        else:
            ticker = yf.Ticker(sembol)
            df = ticker.history(period="2d")
            if df.empty:
                continue
            son_row = df.iloc[-1]
            open_price = float(son_row["Open"]) if "Open" in son_row else float(son_row["Close"])
            high = float(son_row["High"])
            low = float(son_row["Low"])
            close = float(son_row["Close"])

        upper = poz["upper_barrier"]
        lower = poz["lower_barrier"]
        elde_gun = poz["elde_tutma_gun"]
        giris_fiyati = poz["giris_fiyati"]
        lot_adedi = poz["lot_adedi"]

        cikis_fiyati = None
        cikis_nedeni = None
        yeni_durum = None

        hit_upper = high >= upper
        hit_lower = low <= lower

        # ─── KADEMELİ TP1 / BREAKEVEN STOP / TP2 & GAP-SLIPPAGE MOTORU ────────
        if hit_lower:
            # KRİTİK CRO DÜZELTME: Eğer açılış stopun altındaysa (GAP DOWN / TABAN),
            # piyasa fiyatı 'open_price'tır; hayali 'lower' fiyattan çıkılamaz!
            cikis_fiyati = min(open_price, lower)
            if tp1_alindi == 1:
                cikis_nedeni = "BREAKEVEN_STOP"
                yeni_durum = "KAPANDI_BREAKEVEN"
            else:
                cikis_nedeni = "SL_GAP" if open_price < lower else "SL"
                yeni_durum = "KAPANDI_SL"

        elif hit_upper and tp1_alindi == 0:
            # 1. Aşama: TP1 Vuruldu -> %50 Sat, Stop'u Giriş Maliyetine Çek (Sıfır Risk Modu)
            gercek_tp_fiyat = max(open_price, upper)
            satilan_lot = max(1, lot_adedi // 2) if lot_adedi > 1 else lot_adedi
            kalan_lot   = lot_adedi - satilan_lot

            satilan_nominal = satilan_lot * gercek_tp_fiyat
            _, _, kismi_maliyet = hesapla_islem_maliyeti(satilan_nominal, sembol)
            bu_kismi_kar = satilan_nominal - (satilan_lot * giris_fiyati) - kismi_maliyet

            # Başa baş (Breakeven) stop: giriş fiyatı + komisyon payı
            yeni_lower = giris_fiyati * (1.0 + getattr(cfg, "BREAKEVEN_TOLERANS", 0.001))
            # Genişletilmiş TP2 Hedefi
            yeni_upper = giris_fiyati + (2.5 * poz["atr"])

            with sqlite3.connect(db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                if kalan_lot > 0:
                    cursor.execute("""
                        UPDATE pozisyonlar SET
                            lot_adedi = ?,
                            nominal_tutar = ?,
                            lower_barrier = ?,
                            upper_barrier = ?,
                            tp1_alindi = 1,
                            kismi_kar_tl = ?,
                            toplam_maliyet_tl = toplam_maliyet_tl + ?
                        WHERE id = ?
                    """, (
                        kalan_lot, kalan_lot * giris_fiyati, round(yeni_lower, 4),
                        round(yeni_upper, 4), round(kismi_kar + bu_kismi_kar, 2),
                        round(kismi_maliyet, 2), poz_id
                    ))
                    conn.commit()
                    logger.info(
                        f"🎯 Paper Trading: #{sembol} TP1 (%50 Kâr: {bu_kismi_kar:+.2f} TL, Fiyat: {gercek_tp_fiyat:.2f} TL) ALINDI! "
                        f"Kalan {kalan_lot} lot için Stop seviyesi GİRİŞ MALİYETİNE ({yeni_lower:.2f} TL) çekildi (Sıfır Risk Modu)."
                    )
                    continue
                else:
                    cikis_fiyati = gercek_tp_fiyat
                    cikis_nedeni = "TP1_TAM"
                    yeni_durum = "KAPANDI_TP"

        elif hit_upper and tp1_alindi == 1:
            # 2. Aşama: TP2 Genişletilmiş Hedef Vuruldu
            cikis_fiyati = max(open_price, upper)
            cikis_nedeni = "TP2_GENISLETILMIS"
            yeni_durum = "KAPANDI_TP"

        elif elde_gun >= cfg.ZAMAN_BARIYERI:
            cikis_fiyati = close
            cikis_nedeni = "TIMEOUT"
            yeni_durum = "KAPANDI_TIMEOUT"

        with sqlite3.connect(db_path, timeout=30.0) as conn:
            cursor = conn.cursor()
            if cikis_fiyati is not None:
                # Pozisyonu Tamamen Kapat
                cikis_nominal = lot_adedi * cikis_fiyati
                _, _, cikis_maliyeti = hesapla_islem_maliyeti(cikis_nominal, sembol)
                toplam_maliyet = poz["toplam_maliyet_tl"] + cikis_maliyeti

                net_kar_zarar = cikis_nominal - (lot_adedi * giris_fiyati) - toplam_maliyet + kismi_kar
                net_getiri_pct = (net_kar_zarar / poz["nominal_tutar"]) * 100.0

                cursor.execute("""
                    UPDATE pozisyonlar SET
                        durum = ?,
                        cikis_tarihi = ?,
                        cikis_fiyati = ?,
                        cikis_nedeni = ?,
                        net_pnl_tl = ?,
                        net_getiri_pct = ?,
                        toplam_maliyet_tl = ?
                    WHERE id = ?
                """, (
                    yeni_durum, bugun_str, round(cikis_fiyati, 4), cikis_nedeni,
                    round(net_kar_zarar, 2), round(net_getiri_pct, 2),
                    round(toplam_maliyet, 2), poz_id
                ))
                conn.commit()

                poz_ozet = dict(poz)
                poz_ozet.update({
                    "cikis_tarihi": bugun_str,
                    "cikis_fiyati": cikis_fiyati,
                    "cikis_nedeni": cikis_nedeni,
                    "net_kar_zarar_tl": net_kar_zarar,
                    "net_getiri_%": net_getiri_pct,
                })
                kapanan_islemler.append(poz_ozet)
                logger.info(f"Paper Trading: #{sembol} kapandı ({cikis_nedeni} -> Toplam Net PnL: {net_kar_zarar:+.2f} TL)")
            else:
                # Gün sayısını artır
                cursor.execute("UPDATE pozisyonlar SET elde_tutma_gun = elde_tutma_gun + 1 WHERE id = ?", (poz_id,))
                conn.commit()

    return kapanan_islemler


import concurrent.futures

def _tek_pozisyon_canli_fiyat_hesapla(poz: Dict[str, Any]) -> Dict[str, Any]:
    """Tek bir açık pozisyonun canlı fiyatını ve PnL metriklerini hesaplar."""
    sembol = poz["sembol"]
    try:
        ticker = yf.Ticker(sembol)
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info and hasattr(fast_info, "last_price") and fast_info.last_price:
            anlik_fiyat = float(fast_info.last_price)
        else:
            hist = ticker.history(period="1d")
            anlik_fiyat = float(hist["Close"].iloc[-1]) if not hist.empty else poz["giris_fiyati"]
    except Exception:
        anlik_fiyat = poz["giris_fiyati"]

    giris = poz["giris_fiyati"]
    pnl_pct = ((anlik_fiyat - giris) / giris) * 100.0
    pnl_tl = (anlik_fiyat - giris) * poz["lot_adedi"]

    # Hedefe ve Stop'a mesafe (%)
    tp_mesafe_pct = ((poz["upper_barrier"] - anlik_fiyat) / anlik_fiyat) * 100.0
    sl_mesafe_pct = ((anlik_fiyat - poz["lower_barrier"]) / anlik_fiyat) * 100.0

    return {
        "id": poz["id"],
        "sembol": sembol.replace(".IS", ""),
        "full_sembol": sembol,
        "giris_tarihi": poz["giris_tarihi"],
        "giris_fiyati": giris,
        "anlik_fiyat": round(anlik_fiyat, 2),
        "lot_adedi": poz["lot_adedi"],
        "elde_tutma_gun": poz["elde_tutma_gun"],
        "anlik_pnl_%": round(pnl_pct, 2),
        "anlik_pnl_tl": round(pnl_tl, 2),
        "tp_hedef": round(poz["upper_barrier"], 2),
        "sl_stop": round(poz["lower_barrier"], 2),
        "tp_mesafe_%": round(tp_mesafe_pct, 1),
        "sl_mesafe_%": round(sl_mesafe_pct, 1),
        "islem_skoru": poz["islem_skoru"],
    }


def anlik_pnl_durumu_cek(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """
    /durum komutu için yfinance üzerinden canlı fiyatları paralel çeker ve açık pozisyon tablosu üretir.
    """
    aciklar = getir_acik_pozisyonlar(db_path)
    if not aciklar:
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(aciklar))) as executor:
        canli_rapor = list(executor.map(_tek_pozisyon_canli_fiyat_hesapla, aciklar))

    return canli_rapor


def pozisyon_sil(poz_id: int, db_path: Path = DB_PATH) -> bool:
    """Veritabanından belirtilen pozisyonu siler."""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pozisyonlar WHERE id = ?", (poz_id,))
        conn.commit()
        return cursor.rowcount > 0


def pozisyon_manuel_kapat(
    poz_id: int,
    cikis_fiyati: float,
    cikis_nedeni: str = "MANUEL_SATIS",
    db_path: Path = DB_PATH,
) -> bool:
    """Açık pozisyonu kullanıcının girdiği veya canlı satış fiyatından kapatır."""
    init_db(db_path)
    bugun_str = str(datetime.now().date())
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pozisyonlar WHERE id = ?", (poz_id,))
        row = cursor.fetchone()
        if not row:
            return False

        poz = dict(row)
        cikis_nominal = poz["lot_adedi"] * cikis_fiyati
        _, _, cikis_maliyeti = hesapla_islem_maliyeti(cikis_nominal, poz["sembol"])
        toplam_maliyet = poz["toplam_maliyet_tl"] + cikis_maliyeti

        net_pnl = cikis_nominal - poz["nominal_tutar"] - toplam_maliyet
        net_pct = (net_pnl / poz["nominal_tutar"]) * 100.0

        cursor.execute("""
            UPDATE pozisyonlar SET
                durum = 'KAPANDI_MANUEL',
                cikis_tarihi = ?,
                cikis_fiyati = ?,
                cikis_nedeni = ?,
                net_pnl_tl = ?,
                net_getiri_pct = ?,
                toplam_maliyet_tl = ?
            WHERE id = ?
        """, (
            bugun_str, round(cikis_fiyati, 4), cikis_nedeni,
            round(net_pnl, 2), round(net_pct, 2),
            round(toplam_maliyet, 2), poz_id
        ))
        conn.commit()
        return True


def bakiye_guncelle(yeni_bakiye: float, db_path: Path = DB_PATH):
    """Kullanıcının toplam portföy kasasını günceller."""
    init_db(db_path)
    bugun_str = str(datetime.now().date())
    aciklar = getir_acik_pozisyonlar(db_path)
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO portfoy_bakiye (tarih, nakit, toplam_portfoy, acik_pozisyon_sayisi)
            VALUES (?, ?, ?, ?)
        """, (bugun_str, yeni_bakiye, yeni_bakiye, len(aciklar)))
        conn.commit()


def bakiye_getir(varsayilan: float = 100_000.0, db_path: Path = DB_PATH) -> float:
    """Kaydedilmiş en güncel portföy bakiyesini döner."""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT toplam_portfoy FROM portfoy_bakiye ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return float(row[0]) if row else varsayilan

