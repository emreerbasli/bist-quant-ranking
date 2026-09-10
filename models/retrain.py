"""
models/retrain.py — FAZ 8: Otomatik Model Yeniden Eğitimi (Retraining Pipeline)
================================================================================
Plan referansı: FAZ 8 (bist_sinyal_botu_proje_plani_v2.md)

Özellikler:
  - PSI drift eşiği aşıldığında veya periyodik olarak çalıştırılır.
  - Güncel verileri çeker, feature'ları hesaplar, Triple Barrier etiketlerini günceller.
  - Modeli sıfırdan eğitir ve performansı eski modelden iyiyse models/aktif altına kaydeder.
"""

import sys
from pathlib import Path
from loguru import logger
import shutil

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg
from features.veri_cek import veri_guncelle
from features.feature_engine import hesapla_tumunu
from features.labeling import etiketle_tumunu
from models.train import master_train_pipeline


def modeli_yeniden_egit(veri_guncelle_dahil: bool = True) -> bool:
    """
    Uçtan uca veri güncelleme ve model yeniden eğitim pipeline'ı.
    """
    logger.info("=" * 70)
    logger.info("FAZ 8: Otomatik Model Yeniden Eğitimi (Retraining Pipeline) Başlatıldı")
    logger.info("=" * 70)

    try:
        if veri_guncelle_dahil:
            logger.info("1. Güncel veriler çekiliyor...")
            veri_guncelle()

        logger.info("2. Feature'lar güncelleniyor...")
        hesapla_tumunu()

        logger.info("3. Triple Barrier etiketleri üretiliyor...")
        etiketle_tumunu()

        logger.info("4. Sniper Ensemble Modeli eğitiliyor ve kalibre ediliyor...")
        master_train_pipeline()

        logger.info("✅ FAZ 8: Model yeniden eğitimi başarıyla tamamlandı ve 'models/aktif' güncellendi!")
        return True

    except Exception as e:
        logger.error(f"Retraining hatası: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    modeli_yeniden_egit()
