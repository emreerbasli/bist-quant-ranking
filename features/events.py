"""
features/events.py — FAZ 2.3: Bilanço / KAP Etkinlik Takvimi & Feature Üretimi
=============================================================================
Plan referansı: FAZ 2.3 (bist_sinyal_botu_proje_plani_v2.md)

Özellikler:
  - gun_fark_bilanco: Tarihin en yakın bilanço/etkinlik tarihine olan gün farkı
                      (negatif = bilanço öncesi, pozitif = bilanço sonrası)
  - bilanco_penceresi: Bilanço tarihinden +-5 iş günü içinde mi? (binary 1/0)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg


def olustur_varsayilan_etkinlik_takvimi(dosya_yolu: Path = cfg.BASE_DIR / "data" / "events.csv") -> pd.DataFrame:
    """
    2018-2026 BIST genel bilanço dönemleri ve önemli etkinlik takvimini oluşturur.
    Tarihler: Q4 (Mart başı), Q1 (Mayıs ortası), Q2 (Ağustos ortası), Q3 (Kasım başı)
    """
    yillar = range(2018, 2027)
    etkinlikler = []

    for yil in yillar:
        # Q4 / Yıllık Bilanço
        etkinlikler.append({"tarih": f"{yil}-03-01", "tip": "BILANCO_Q4", "aciklama": f"{yil-1} Yıllık Bilanço"})
        # Q1 / 3 Aylık
        etkinlikler.append({"tarih": f"{yil}-05-10", "tip": "BILANCO_Q1", "aciklama": f"{yil} 1. Çeyrek Bilanço"})
        # Q2 / 6 Aylık
        etkinlikler.append({"tarih": f"{yil}-08-20", "tip": "BILANCO_Q2", "aciklama": f"{yil} 2. Çeyrek Bilanço"})
        # Q3 / 9 Aylık
        etkinlikler.append({"tarih": f"{yil}-11-10", "tip": "BILANCO_Q3", "aciklama": f"{yil} 3. Çeyrek Bilanço"})

    df_events = pd.DataFrame(etkinlikler)
    df_events["tarih"] = pd.to_datetime(df_events["tarih"])
    df_events = df_events.sort_values("tarih").reset_index(drop=True)

    dosya_yolu.parent.mkdir(parents=True, exist_ok=True)
    df_events.to_csv(dosya_yolu, index=False, encoding="utf-8")
    return df_events


def yukle_etkinlik_tarihleri(dosya_yolu: Path = cfg.BASE_DIR / "data" / "events.csv") -> pd.DatetimeIndex:
    """Etkinlik tarihlerini yükler, dosya yoksa varsayılan takvimi oluşturur."""
    if not dosya_yolu.exists():
        df_events = olustur_varsayilan_etkinlik_takvimi(dosya_yolu)
    else:
        df_events = pd.read_csv(dosya_yolu)
        df_events["tarih"] = pd.to_datetime(df_events["tarih"])
    return pd.DatetimeIndex(df_events["tarih"].sort_values().unique())


def hesapla_etkinlik_featurelari(
    tarih_index: pd.DatetimeIndex,
    etkinlik_tarihleri: pd.DatetimeIndex = None,
    pencere_is_gunu: int = 5,
) -> pd.DataFrame:
    """
    Her bir tarih için:
      - gun_fark_bilanco: En yakın bilanço tarihine takvim günü farkı
      - bilanco_penceresi: En yakın bilanço tarihine +-5 gün içinde mi? (1/0)
    """
    if etkinlik_tarihleri is None:
        etkinlik_tarihleri = yukle_etkinlik_tarihleri()

    dates = pd.to_datetime(tarih_index)
    gun_farklari = []
    pencereler = []

    # Her tarih için en yakın etkinlik tarihini bul
    for d in dates:
        # Farklar (gün cinsinden: d - event_date)
        # Eğer d etkinlikten önceyse d - event_date < 0
        diffs = (d - etkinlik_tarihleri).days
        abs_diffs = np.abs(diffs)
        min_idx = np.argmin(abs_diffs)
        signed_diff = (d - etkinlik_tarihleri[min_idx]).days
        min_abs_diff = abs_diffs[min_idx]

        gun_farklari.append(int(signed_diff))
        # Yaklaşık 5 iş günü = ~7 takvim günü
        pencereler.append(1 if min_abs_diff <= (pencere_is_gunu * 7 // 5 + 1) else 0)

    result_df = pd.DataFrame(
        {
            "gun_fark_bilanco": gun_farklari,
            "bilanco_penceresi": pencereler,
        },
        index=tarih_index,
    )
    return result_df
