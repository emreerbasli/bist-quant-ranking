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

from typing import List

import config as cfg

logger = logging.getLogger("TelegramBot")

# Token ve Chat ID okuma (config.py veya .env üzerinden)
TELEGRAM_TOKEN = getattr(cfg, "TELEGRAM_TOKEN", "")
ADMIN_CHAT_ID = getattr(cfg, "ADMIN_CHAT_ID", "")


def _parcala_mesaj(metin: str, max_uzunluk: int = 4000) -> List[str]:
    """
    Uzun metinleri Telegram'ın 4096 karakter üst sınırını aşmayacak şekilde
    doğal satır sonlarından parçalar (chunking).
    """
    if len(metin) <= max_uzunluk:
        return [metin]

    parcalar: List[str] = []
    satirlar = metin.splitlines(keepends=True)
    mevcut_parca = ""

    for s in satirlar:
        if len(mevcut_parca) + len(s) <= max_uzunluk:
            mevcut_parca += s
        else:
            if mevcut_parca:
                parcalar.append(mevcut_parca)
                mevcut_parca = ""
            while len(s) > max_uzunluk:
                parcalar.append(s[:max_uzunluk])
                s = s[max_uzunluk:]
            mevcut_parca = s

    if mevcut_parca:
        parcalar.append(mevcut_parca)

    return parcalar


def mesaj_gonder(metin: str, parse_mode: str = "HTML") -> bool:
    """
    Telegram botu üzerinden yöneticiye (ADMIN_CHAT_ID) metin mesajı gönderir.
    4000 karakterden uzun mesajları otomatik olarak parçalara (chunking) ayırır.
    
    Parametreler:
        metin (str): Gönderilecek bildirim metni.
        parse_mode (str): 'HTML' veya None.
        
    Dönüş:
        bool: Mesaj(lar) başarıyla iletildiyse True, aksi halde False.
    """
    token = TELEGRAM_TOKEN or getattr(cfg, "TELEGRAM_TOKEN", "")
    chat_id = ADMIN_CHAT_ID or getattr(cfg, "ADMIN_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("Telegram gönderimi iptal: TELEGRAM_TOKEN veya ADMIN_CHAT_ID konfigürasyonda tanımlı değil.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parcalar = _parcala_mesaj(metin, max_uzunluk=4000)
    hepsi_basarili = True

    for parca in parcalar:
        payload = {
            "chat_id": chat_id,
            "text": parca,
            "parse_mode": parse_mode
        }

        try:
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram bildirimi başarıyla iletildi.")
            else:
                # HTML parse hatası durumunda düz metin olarak tekrar dene
                if "can't parse entities" in response.text.lower() and parse_mode:
                    logger.warning("Telegram HTML parse hatası, düz metin olarak tekrar deneniyor...")
                    payload.pop("parse_mode", None)
                    retry_res = requests.post(url, data=payload, timeout=10)
                    if retry_res.status_code == 200:
                        logger.info("Telegram bildirimi düz metin olarak iletildi.")
                        continue

                logger.error(f"Telegram API hatası (HTTP {response.status_code}): {response.text}")
                hepsi_basarili = False
        except requests.exceptions.Timeout:
            logger.error("Telegram API isteği zaman aşımına (timeout) uğradı.")
            hepsi_basarili = False
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram ağ bağlantı hatası: {e}")
            hepsi_basarili = False
        except Exception as e:
            logger.error(f"Telegram mesajı gönderilirken istisna oluştu: {e}")
            hepsi_basarili = False

    return hepsi_basarili


if __name__ == "__main__":
    # Test çalıştırması
    test_msg = "🔔 <b>BIST Kantitatif Model</b>: Telegram bildirim servisi aktif."
    basarili = mesaj_gonder(test_msg)
    print(f"Telegram Mesaj Gönderim Sonucu: {'BAŞARILI' if basarili else 'BAŞARISIZ'}")
