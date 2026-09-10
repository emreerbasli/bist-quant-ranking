"""
bot/telegram_bot.py
===================
PRODUCTION-CANDIDATE: TELEGRAM BİLDİRİM ENTEGRASYON MODÜLÜ (ADIM 4)
-------------------------------------------------------------------
KRİTİK KURUMSAL SINIR (İHLAL EDİLEMEZ):
Bu sistem SADECE bildirim gönderir — hiçbir şekilde otomatik emir veya
al-sat kararı VERMEZ. Tüm kararlar yatırımcının kendi takdirindedir.

Bu modül, config.py veya .env dosyasından okunan Telegram kimlik bilgileriyle
yalnızca bilgilendirme mesajı iletiminden sorumludur.
Hassas token ve chat_id bilgileri KESİNLİKLE koda yazılmaz.
"""

import sys
import logging
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg

logger = logging.getLogger("TelegramBot")

# Token ve Chat ID okuma (config.py veya .env üzerinden)
TELEGRAM_TOKEN = getattr(cfg, "TELEGRAM_TOKEN", "")
ADMIN_CHAT_ID = getattr(cfg, "ADMIN_CHAT_ID", "")


def mesaj_gonder(metin: str, parse_mode: str = "HTML") -> bool:
    """
    Telegram botu üzerinden yöneticiye (ADMIN_CHAT_ID) metin mesajı gönderir.
    
    Parametreler:
        metin (str): Gönderilecek bildirim metni.
        parse_mode (str): 'HTML' veya None.
        
    Dönüş:
        bool: Mesaj başarıyla iletildiyse True, aksi halde False.
    """
    token = TELEGRAM_TOKEN or getattr(cfg, "TELEGRAM_TOKEN", "")
    chat_id = ADMIN_CHAT_ID or getattr(cfg, "ADMIN_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("Telegram gönderimi iptal: TELEGRAM_TOKEN veya ADMIN_CHAT_ID konfigürasyonda tanımlı değil.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": metin,
        "parse_mode": parse_mode
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram bildirimi başarıyla iletildi.")
            return True
        else:
            # HTML parse hatası durumunda düz metin olarak tekrar dene
            if "can't parse entities" in response.text.lower() and parse_mode:
                logger.warning("Telegram HTML parse hatası, düz metin olarak tekrar deneniyor...")
                payload.pop("parse_mode", None)
                retry_res = requests.post(url, data=payload, timeout=10)
                if retry_res.status_code == 200:
                    logger.info("Telegram bildirimi düz metin olarak iletildi.")
                    return True

            logger.error(f"Telegram API hatası (HTTP {response.status_code}): {response.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram mesajı gönderilirken istisna oluştu: {e}")
        return False


if __name__ == "__main__":
    # Test çalıştırması
    test_msg = "🔔 <b>BIST Kantitatif Model</b>: Telegram bildirim servisi aktif."
    basarili = mesaj_gonder(test_msg)
    print(f"Telegram Mesaj Gönderim Sonucu: {'BAŞARILI' if basarili else 'BAŞARISIZ'}")
