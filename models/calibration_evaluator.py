"""
models/calibration_evaluator.py — C1: Kalibrasyon Eğrisi, ECE & Brier Score Analiz Motoru
========================================================================================
Plan referansı: Aşama 3 (C1) — Analiz Kalitesi & Sinyal Doğruluk Raporu

Özellikler:
  1. Expected Calibration Error (ECE) ve Maximum Calibration Error (MCE) hesaplar.
  2. Brier Score (olasılık tahmin doğruluğu karesel hatası) hesaplar.
  3. Güvenilirlik Çizelgesi (Reliability Diagram / Calibration Curve) verisi üretir.
  4. Sinyal günlüğü (data/signals_log.db) üzerinden gerçek işlemlerin kalibrasyon sapmasını izler.
  5. Aşırı Güven (Overconfidence) veya Düşük Güven (Underconfidence) durumlarını tespit edip raporlar.
"""

import sys
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

import pandas as pd
import numpy as np
from loguru import logger

# Proje kökünü ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg


def hesapla_ece_ve_brier(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> Dict[str, Any]:
    """
    Model olasılıklarının gerçek başarı oranları ile ne kadar uyumlu olduğunu ölçer.

    Args:
        y_true: Gerçek ikili sonuçlar (0 veya 1)
        y_prob: Modelin tahmin ettiği olasılıklar [0.0, 1.0]
        n_bins: Dilim (bin) sayısı (varsayılan: 10)

    Returns:
        dict: {
            brier_score: float,
            ece: float (Expected Calibration Error, 0.0 - 1.0),
            mce: float (Maximum Calibration Error),
            dilimler: list of dicts,
            kalibrasyon_durumu: str,
            tavsiye: str
        }
    """
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)

    if len(y_true) == 0 or len(y_true) != len(y_prob):
        return {
            "brier_score": 0.0,
            "ece": 0.0,
            "mce": 0.0,
            "dilimler": [],
            "ornek_sayisi": 0,
            "kalibrasyon_durumu": "YETERRSIZ_VERI",
            "tavsiye": "Yeterli örnek bulunamadı.",
        }

    # 1. Brier Score: 1/N * sum((p - y)^2)
    brier = float(np.mean((y_prob - y_true) ** 2))

    # 2. ECE ve MCE Hesaplama
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    mce = 0.0
    dilimler = []
    n_total = len(y_true)

    for i in range(n_bins):
        alt = bin_edges[i]
        ust = bin_edges[i + 1]
        
        # Son dilim için üst sınırı dahil et
        if i == n_bins - 1:
            mask = (y_prob >= alt) & (y_prob <= ust)
        else:
            mask = (y_prob >= alt) & (y_prob < ust)

        n_bin = int(np.sum(mask))
        if n_bin > 0:
            avg_prob = float(np.mean(y_prob[mask]))
            avg_true = float(np.mean(y_true[mask]))
            fark = abs(avg_prob - avg_true)

            ece += (n_bin / n_total) * fark
            if fark > mce:
                mce = fark

            dilimler.append({
                "dilim_araligi": f"{alt:.1f}-{ust:.1f}",
                "ornek_sayisi": n_bin,
                "ortalama_tahmin": round(avg_prob, 3),
                "gercek_basari": round(avg_true, 3),
                "kalibrasyon_farki": round(fark, 3),
            })

    # 3. Durum Değerlendirmesi
    if ece < 0.05:
        durum = "MUKEMMEL_KALIBRE"
        tavsiye = "🟢 Model olasılıkları gerçek başarı oranları ile mükemmel uyumlu."
    elif ece < 0.10:
        durum = "IYI_KALIBRE"
        tavsiye = "🟢 Model olasılıkları güvenilir seviyede, ek düzeltmeye gerek yok."
    elif ece < 0.18:
        durum = "ORTA_SAPMA"
        tavsiye = "⚠️ Model olasılıklarında hafif sapma var, Platt/Isotonic kalibrasyon tazelenmeli."
    else:
        durum = "YUKSEK_SAPMA"
        tavsiye = "🔴 Model olasılıkları yanıltıcı (aşırı/düşük güven). Yeniden eğitim ve kalibrasyon şart."

    return {
        "brier_score": round(brier, 4),
        "ece": round(ece, 4),
        "mce": round(mce, 4),
        "ornek_sayisi": n_total,
        "dilimler": dilimler,
        "kalibrasyon_durumu": durum,
        "tavsiye": tavsiye,
    }


def degerlendir_sinyal_gunlugu_kalibrasyonu(
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    data/signals_log.db tablosundaki gerçekleşmiş sinyallerin kalibrasyonunu test eder.
    """
    if db_path is None:
        db_path = getattr(cfg, "SIGNAL_LOG_DB_PATH", cfg.BASE_DIR / "data" / "signals_log.db")

    if not db_path.exists():
        return {
            "durum": "VERITABANI_YOK",
            "mesaj": f"Sinyal veritabanı henüz oluşmadı: {db_path}",
            "ornek_sayisi": 0,
        }

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        query = """
            SELECT model_olasiligi, sinyal_dogru_mu
            FROM sinyal_gunlugu
            WHERE sinyal_dogru_mu IS NOT NULL
        """
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        return {"durum": "HATA", "mesaj": str(e), "ornek_sayisi": 0}
    finally:
        if conn:
            conn.close()

    if len(df) < 10:
        return {
            "durum": "YETERSIZ_ORNEK",
            "mesaj": f"Kalibrasyon testi için en az 10 tamamlanmış sinyal gerekir (Mevcut: {len(df)}).",
            "ornek_sayisi": len(df),
            "tamamlanan_sinyaller": len(df),
        }

    y_prob = df["model_olasiligi"].values
    y_true = df["sinyal_dogru_mu"].values

    return hesapla_ece_ve_brier(y_true, y_prob, n_bins=5)
