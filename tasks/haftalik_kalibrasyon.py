"""
tasks/haftalik_kalibrasyon.py — FAZ B3: Otomatik Haftalık Kalibrasyon Görevi
=============================================================================
Plan referansı: FAZ B3

Her Cumartesi sabah 10:00'da (Türkiye saati) çalışır:
  - PSI < 0.25:  Sadece Isotonic kalibrasyon yenile (5 dk, modelsiz)
  - PSI 0.25-0.50: Telegram uyarısı at: "Yeniden eğitim önerilir"
  - PSI >= 0.50: Tam yeniden eğitim otomatik tetiklenir + bildirim

Kullanım:
  python tasks/haftalik_kalibrasyon.py  (manuel çalıştırma)
  telegram_bot.py içinde JobQueue.run_daily(day=(6,)) ile Cumartesi otomatik tetiklenir.
"""

import sys
from pathlib import Path
from datetime import datetime
import asyncio

import numpy as np
import pandas as pd
import joblib
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg
from bot.health_check import health_check_verisi
from models.calibration_ensemble import SniperEnsemblePipeline
from models.dataset_loader import yukle_tum_etiketli_veri, olustur_purged_walk_forward_splits
from models.optimization import optimize_lightgbm, optimize_random_forest, optimize_logistic_regression


# ─── Log ayarı ───────────────────────────────────────────────────────────────
logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add(cfg.LOGS_DIR / "kalibrasyon_{time:YYYY-MM-DD}.log",
           rotation="1 week", retention="8 weeks", level="DEBUG", encoding="utf-8")


def _psi_ortalama() -> float:
    """Health check'ten ortalama PSI değerini hesaplar."""
    hc = health_check_verisi()
    # Drift uyarı sayısına bakıyoruz; sayıyı normalize ediyoruz
    n_kritik = hc.get("kritik_uyari_sayisi", 0)
    n_drift  = hc.get("drift_uyari_sayisi", 0)
    n_hisse  = max(1, hc.get("kontrol_edilen_hisse", 20))
    # Kaba PSI proxy: (kritik * 0.6 + drift * 0.25) / hisse_sayisi
    psi_proxy = (n_kritik * 0.6 + n_drift * 0.25) / n_hisse
    return min(psi_proxy, 1.0)


def sadece_kalibre_et() -> None:
    """
    Modeli yeniden eğitmeden sadece Isotonic kalibrasyonu tazeler.
    Son %15'lik veriyi kalibrasyon seti olarak kullanır.
    Hızlıdır (~3-5 dakika).
    """
    logger.info("Haftalık Hızlı Kalibrasyon (Isotonic) başlatıldı...")
    model_yolu = cfg.MODELS_DIR / "aktif" / "ensemble_sniper.joblib"

    if not model_yolu.exists():
        logger.error("Aktif model dosyası bulunamadı! Önce tam eğitim yapılmalı.")
        return

    pipeline = SniperEnsemblePipeline.load(model_yolu)
    X, y, _ = yukle_tum_etiketli_veri()

    # Son %15 kalibrasyon verisi
    split_idx = int(len(X) * 0.85)
    X_calib   = X.iloc[split_idx:]
    y_calib   = y.iloc[split_idx:]

    # Sadece kalibrasyonu yenile (fit çağrısı olmadan)
    # Mevcut ham tahminler üzerinde yeniden kalibratör fit et
    for cal in [pipeline.cal_lgbm, pipeline.cal_rf, pipeline.cal_logreg]:
        raw_probs_all = cal.base_estimator.predict_proba(X_calib)
        if pipeline.multiclass and y_calib.nunique() > 2:
            raw_pos = raw_probs_all[:, 1:].sum(axis=1)
            y_bin = (y_calib.values >= 1).astype(int)
        else:
            raw_pos = raw_probs_all[:, 1]
            y_bin = y_calib.values

        from sklearn.isotonic import IsotonicRegression
        from sklearn.linear_model import LogisticRegression
        if len(X_calib) >= 500:
            cal.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            cal.calibrator.fit(raw_pos, y_bin)
        else:
            cal.calibrator = LogisticRegression(C=1.0, max_iter=500, random_state=42)
            cal.calibrator.fit(raw_pos.reshape(-1, 1), y_bin)

    pipeline.save(model_yolu)
    logger.info("✅ Hızlı Kalibrasyon tamamlandı. Model güncellendi.")


def tam_yeniden_egitim() -> None:
    """
    PSI > 0.50 durumunda tam yeniden eğitim çalıştırır.
    Tüm labeling → feature → model döngüsünü yeniler.
    """
    logger.info("=" * 60)
    logger.info("🔁 TAM YENİDEN EĞİTİM BAŞLATILDI (PSI >= 0.50)")
    logger.info("=" * 60)

    from features.veri_cek import veri_guncelle
    from features.feature_engine import hesapla_tumunu
    from features.labeling import etiketle_tumunu

    logger.info("Adım 1: Veri güncelleniyor...")
    veri_guncelle()

    logger.info("Adım 2: Feature engineering...")
    hesapla_tumunu()

    logger.info("Adım 3: Etiketleme...")
    etiketle_tumunu()

    logger.info("Adım 4: Model eğitimi (Walk-Forward)...")
    from models.train import calistir_walk_forward_egitimi
    calistir_walk_forward_egitimi(n_optuna_trials=15)

    logger.info("✅ Tam yeniden eğitim tamamlandı!")


def haftalik_kalibrasyon_calistir() -> dict:
    """
    Ana kalibrasyon döngüsü. Telegram bot tarafından Cumartesi çağrılır.

    Returns:
        dict: eylem, psi_proxy, mesaj
    """
    bugun = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"{'─'*50}")
    logger.info(f"Haftalık Kalibrasyon Çalışıyor — {bugun}")
    logger.info(f"{'─'*50}")

    psi = _psi_ortalama()
    logger.info(f"PSI Proxy Değeri: {psi:.3f}")

    if psi >= 0.50:
        logger.warning(f"PSI >= 0.50 → TAM YENİDEN EĞİTİM tetikleniyor!")
        tam_yeniden_egitim()
        eylem  = "TAM_YENIDEN_EGITIM"
        mesaj  = (
            f"🔁 <b>HAFTALIK KALİBRASYON RAPORU — {bugun}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ PSI Drift yüksek tespit edildi ({psi:.2f}).\n"
            f"✅ Tam yeniden eğitim başarıyla tamamlandı.\n"
            f"Yeni model aktif: <code>models/aktif/ensemble_sniper.joblib</code>"
        )
    elif psi >= 0.25:
        logger.info(f"PSI >= 0.25 → Hızlı kalibrasyon uygulanıyor + Uyarı gönderiliyor.")
        sadece_kalibre_et()
        eylem  = "UYARI_KALIBRASYON"
        mesaj  = (
            f"⚠️ <b>HAFTALIK KALİBRASYON RAPORU — {bugun}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 Orta düzey piyasa değişimi tespit edildi (PSI: {psi:.2f}).\n"
            f"✅ Hızlı Isotonic kalibrasyon uygulandı.\n"
            f"💡 PSI 0.50'yi geçerse otomatik tam eğitim tetiklenecek."
        )
    else:
        logger.info(f"PSI < 0.25 → Hızlı kalibrasyon uygulanıyor. Sistem stabil.")
        sadece_kalibre_et()
        eylem  = "RUTIN_KALIBRASYON"
        mesaj  = (
            f"✅ <b>HAFTALIK KALİBRASYON RAPORU — {bugun}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Sistem tamamen stabil (PSI: {psi:.2f})\n"
            f"• Rutin Isotonic kalibrasyon tamamlandı\n"
            f"• Herhangi bir müdahale gerekmez"
        )

    logger.info(f"Kalibrasyon tamamlandı. Eylem: {eylem}")
    return {"eylem": eylem, "psi": psi, "mesaj": mesaj, "tarih": bugun}


if __name__ == "__main__":
    sonuc = haftalik_kalibrasyon_calistir()
    print(f"\nSonuç: {sonuc['eylem']} | PSI: {sonuc['psi']:.3f}")
    print(sonuc["mesaj"])
