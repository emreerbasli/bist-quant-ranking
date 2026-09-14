"""
tasks/data_sync_service.py
==========================
FAZ -1.2 & FAZ -1.4: GÜNLÜK VERİ GÜNCELLEME VE VBTS ARŞİVLEME OTOMASYON SERVİSİ
-------------------------------------------------------------------------------
İşlevler:
  1. BIST Seans Kapanış Zamanlayıcısı:
     - Normal günlerde seans kapanışı ve takas mutabakatı sonrası saat 18:15'te çalışır.
     - Arife / yarım günlerde saat 13:15'te çalışır.
     - Hafta sonu ve resmi/dini tatillerde piyasa kapalı olduğu için atlar.
  2. Veri İndirme:
     - 88 Hisse + XU100 + XUSIN + XBANK + USDTRY + VIX parquet dosyalarını yfinance üzerinden günceller.
     - Split ve temettü düzeltmelerini (auto_adjust=True) otomatik işler.
  3. Güvenlik & Doğrulama Kapısı:
     - Tarih hizalamasını denetler (check_market_date_alignment).
     - Başarısızlık durumunda (API hatası, eksik/boş veri) sessizce geçmez;
       hata günlüğüne yazar ve Telegram'a 🚨 acil uyarı bildirimi gönderir.
  4. Canlı VBTS / İdari Tedbir Arşivleme (Faz -1.4):
     - Güncellenen verilerle birlikte son 7 günün KAP haberlerini tarar,
       VBTS / kredili işlem yasaklarını 'data/kap_vbts_arsiv.csv' dosyasına zaman damgasıyla kaydeder.
"""

import sys
import os
import time
import argparse
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg
from features.veri_cek import veri_guncelle
from models.v3_ranking.data_loader import yukle_veriler, check_market_date_alignment
from bot.kap_filter import tara_ve_arsivle_vbts

# Loglama Ayarları (RotatingFileHandler: 5MB sınır, 5 yedek dosya koruması)
LOGS_DIR = cfg.LOGS_DIR
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SERVICE_LOG_FILE = LOGS_DIR / "data_sync_service.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler(
            SERVICE_LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DataSyncService")


def icra_et_veri_guncelleme(force: bool = False) -> Dict[str, Any]:
    """
    Günlük veri indirme, kalite denetimi ve VBTS arşivleme döngüsünü icra eder.
    
    Returns:
        Dict[str, Any]: İşlem sonuç raporu
    """
    simdi = datetime.now()
    logger.info("=" * 70)
    logger.info(f"BIST Günlük Veri Güncelleme Başladı: {simdi.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    # 1. BIST Seans Kontrolü
    if not force:
        if not cfg.bist_is_gunu_mu(simdi):
            logger.info("BIST piyasası bugün kapalı (Hafta sonu veya tam tatil). Güncelleme atlandı.")
            return {"success": True, "skipped": True, "reason": "Piyasa kapalı"}

    rapor = {
        "success": False,
        "timestamp": simdi.isoformat(),
        "market_date": None,
        "hisseler_count": 0,
        "alignment_status": None,
        "vbts_count": 0,
        "errors": []
    }

    try:
        # 2. Fiyat ve Makro Verileri İndir (features/veri_cek.py)
        logger.info("Adım 1/3: 88 hisse + endeksler ve makro kurlar güncelleniyor...")
        tum_raporlar = veri_guncelle(hisseler=cfg.HISSELER)
        rapor["hisseler_count"] = len(tum_raporlar)

        # 3. Tarih Hizalama ve Sağlık Kontrolü
        logger.info("Adım 2/3: Tarih hizalama ve veri bütünlüğü denetleniyor...")
        fiyat_dict, seri_xu100, seri_usdtry, _, _, _ = yukle_veriler()
        alignment = check_market_date_alignment(fiyat_dict, seri_xu100)
        rapor["alignment_status"] = alignment
        rapor["market_date"] = alignment.get("market_date")

        if not alignment["aligned"]:
            err_msg = f"HİZALAMA KAPISI UYARISI: {alignment['reason']}"
            logger.warning(f"⚠️ {err_msg}")
            rapor["errors"].append(err_msg)
            # Telegram uyarısı gönder
            _telegram_uyari_gonder(f"⚠️ BIST Veri Güncelleme Uyarısı:\n{err_msg}")
        else:
            logger.info(f"✅ Tarih Hizalaması Başarılı: Tüm hisseler {rapor['market_date']} kapanışında eşitlendi.")

        # 4. Canlı VBTS / İdari Tedbir Arşivleme (Faz -1.4)
        logger.info("Adım 3/3: KAP haberleri taranıyor ve VBTS tedbirleri arşivleniyor...")
        try:
            vbts_kayitlar = tara_ve_arsivle_vbts(hisseler=cfg.HISSELER)
            rapor["vbts_count"] = len(vbts_kayitlar)
            if vbts_kayitlar:
                logger.info(f"📁 {len(vbts_kayitlar)} adet güncel VBTS tedbir kaydı arşive işlendi.")
            else:
                logger.info("Aktif yeni VBTS tedbiri bulunamadı.")
        except Exception as e:
            err_v = f"VBTS arşivleme hatası: {e}"
            logger.warning(err_v)
            rapor["errors"].append(err_v)

        rapor["success"] = True
        logger.info("✅ sistem çalıştı — Günlük veri güncelleme ve arşivleme başarıyla tamamlandı.")

    except Exception as e:
        err_msg = f"Veri güncelleme sırasında kritik hata: {e}"
        logger.error(f"❌ {err_msg}", exc_info=True)
        rapor["errors"].append(err_msg)
        _telegram_uyari_gonder(f"🚨 BIST KRİTİK VERİ GÜNCELLEME HATASI!\n{err_msg}")

    return rapor


def _telegram_uyari_gonder(mesaj: str):
    """Hata durumunda Telegram üzerinden admin bildirimi iletir."""
    try:
        from bot.telegram_bot import mesaj_gonder
        mesaj_gonder(mesaj, parse_mode=None)
    except Exception as e:
        logger.debug(f"Telegram bildirim hatası: {e}")


def seans_1315_guncelle(force: bool = False) -> Dict[str, Any]:
    """
    Arife / Yarım Gün Veri Güncelleme Tetikleyicisi (13:15).
    KRİTİK GÜVENLİK KAPISI:
    Normal günlerde BIST 18:00'e kadar açık olduğundan ASLA veri çekmez.
    Sadece ve sadece BIST arife / yarım gün ise saat 13:15'te çalışır.
    """
    simdi = datetime.now()
    if not force:
        if not cfg.bist_is_gunu_mu(simdi):
            logger.info("BIST piyasası bugün kapalı (Hafta sonu veya tatil). Saat 13:15 güncellemesi atlandı.")
            return {"success": True, "skipped": True, "reason": "Piyasa kapalı"}
        if not cfg.bist_yarim_gun_mu(simdi):
            logger.info("Bugün BIST normal tam gün seansı (Arife/Yarım gün DEĞİL). Saat 13:15 güncellemesi güvenlik kapısıyla engellendi. (18:15'te çalışacak)")
            return {"success": True, "skipped": True, "reason": "Normal gün 13:15 koşusu engellendi"}
    return icra_et_veri_guncelleme(force=force)


def seans_1815_guncelle(force: bool = False) -> Dict[str, Any]:
    """
    Normal Gün Seans Kapanışı Veri Güncelleme Tetikleyicisi (18:15).
    Eğer bugün yarım gün idiyse (13:15'te zaten veri çekildiyse) mükerrer çalışmayı engeller.
    """
    simdi = datetime.now()
    if not force:
        if not cfg.bist_is_gunu_mu(simdi):
            logger.info("BIST piyasası bugün kapalı (Hafta sonu veya tatil). Saat 18:15 güncellemesi atlandı.")
            return {"success": True, "skipped": True, "reason": "Piyasa kapalı"}
        if cfg.bist_yarim_gun_mu(simdi):
            logger.info("Bugün BIST yarım seans günüydü ve veri güncellemesi 13:15'te tamamlandı. Saat 18:15 mükerrer koşusu atlandı.")
            return {"success": True, "skipped": True, "reason": "Yarım gün 18:15 mükerrer koşusu atlandı"}
    return icra_et_veri_guncelleme(force=force)


def zamanlayici_dongusu():
    """
    Seans kapanış zamanlayıcısı:
    - Normal günlerde seans 18:00'de kapanır -> 18:15'te veri güncellenir.
    - Yarım günlerde (Arife) seans 12:40'ta kapanır -> 13:15'te veri güncellenir.
    """
    try:
        import schedule
    except ImportError:
        logger.error("Schedule kütüphanesi bulunamadı! 'pip install schedule' gereklidir.")
        return

    logger.info("Zamanlayıcı Servisi Kuruldu:")
    logger.info("  • Normal Seans: Her gün saat 18:15'te çalışacak (Yarım günlerde atlar).")
    logger.info("  • Yarım Seans:  Arife günlerinde saat 13:15'te çalışacak (Normal günlerde atlar).")

    # 18:15 ve 13:15 kontrolü (Güvenlik kapılarıyla korumalı)
    schedule.every().day.at("13:15").do(seans_1315_guncelle, force=False)
    schedule.every().day.at("18:15").do(seans_1815_guncelle, force=False)

    logger.info("Veri Senkronizasyon Servisi Arka Planda Başlatıldı (Durdurmak için Ctrl+C)...")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"Zamanlayıcı döngü hatası: {e}")
        time.sleep(30)


def main():
    parser = argparse.ArgumentParser(description="BIST Günlük Veri Güncelleme ve VBTS Arşiv Servisi")
    parser.add_argument("--now", "--run-once", action="store_true", help="Hemen tek seferlik çalıştır ve çık")
    parser.add_argument("--force", action="store_true", help="Hafta sonu/tatil kontrolünü yoksayarak zorla çalıştır")
    args = parser.parse_args()

    if args.now:
        icra_et_veri_guncelleme(force=args.force)
    else:
        zamanlayici_dongusu()


if __name__ == "__main__":
    main()
