"""
backtest/risk_kurallari.py — FAZ 5: Portföy Risk Kuralları, Maskeleme & Execution Motoru
========================================================================================
Plan referansı: FAZ 5.0 - 5.3 (bist_sinyal_botu_proje_plani_v2.md)

Uygulanan Kurallar:
  1. Risk Bazlı Pozisyon Boyutlandırma:
     - Kasa riski = %0.5 (stop mesafesine göre lot adedi)
     - Maksimum tek hisse nominal ağırlığı = %20
  2. Sektörel & Portföy Kısıtları:
     - Maksimum eşzamanlı pozisyon = 5
     - Sektör başına maksimum pozisyon = 2
     - Toplam portföy risk heat <= %3.0
  3. Gap Stres Kontrolü:
     - T+1 açılışında %4'ten büyük gap veya > 0.75*ATR sapma varsa işlem iptal edilir.
  4. Limit Emir Simülasyonu:
     - T+1 sabah açılışında Limit Fiyat = T_Kapanış * (1 + 0.005) (+%0.5).
     - Günün en düşüğü (Low) bu seviyeyi görmediyse emir gerçekleşmez (iptal).
  5. Temettü / Split Maskelemesi:
     - Son 5 iş gününde temettü/split gerçekleştiyse sinyal üretilmez (maskeleme aktif).
  6. Maliyetler:
     - Komisyon: %0.1 (0.001)
     - Slippage: %0.2 likit, %0.4 düşük likidite (TERA, FORTE)
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import pandas as pd
import numpy as np

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg


def pozisyon_boyutu_hesapla(
    portfoy_degeri: float,
    stop_mesafesi: float,
    giris_fiyati: float,
    max_risk_yuzde: float = cfg.MAX_RISK_PER_ISLEM,
    max_agirlik: float = cfg.MAX_POZISYON_AGIRLIGI,
) -> Tuple[int, float, float]:
    """
    Risk bazlı pozisyon lot adedi ve nominal tutarını hesaplar.
    
    Returns:
        lot_adedi (int): Alınacak hisse adedi
        nominal_tutar (float): Toplam pozisyon büyüklüğü (TL)
        risk_tutari (float): Stop olursa kaybedilecek tutar (TL)
    """
    if stop_mesafesi <= 0 or giris_fiyati <= 0 or portfoy_degeri <= 0:
        return 0, 0.0, 0.0

    # 1. İşlem başı risk tutarı (örn. 100.000 TL * %0.5 = 500 TL)
    risk_tutari = portfoy_degeri * max_risk_yuzde
    
    # 2. Stop mesafesine göre adet
    adet = int(risk_tutari / stop_mesafesi)
    if adet <= 0:
        return 0, 0.0, 0.0

    nominal_tutar = adet * giris_fiyati
    max_nominal = portfoy_degeri * max_agirlik

    # 3. Maksimum nominal tavan (%20) kontrolü
    if nominal_tutar > max_nominal:
        adet = int(max_nominal / giris_fiyati)
        nominal_tutar = adet * giris_fiyati
        risk_tutari = adet * stop_mesafesi

    return adet, round(nominal_tutar, 2), round(risk_tutari, 2)


def gap_kontrolu(
    sinyal_kapanis: float,
    t1_open: float,
    t_atr: float,
    max_gap_yuzde: float = cfg.GAP_ESIK_MUTLAK,
    max_atr_orani: float = cfg.GAP_ESIK_ATR_ORANI,
) -> Tuple[bool, str]:
    """
    T+1 Açılış gap büyüklüğünü kontrol eder.
    
    Returns:
        gap_gecerli (bool): True ise işlem yapılabilir, False ise gap nedeniyle atla.
        mesaj (str): Açıklama
    """
    if sinyal_kapanis <= 0 or t1_open <= 0 or t_atr <= 0:
        return False, "Geçersiz fiyat veya ATR"

    gap_mutlak = abs(t1_open - sinyal_kapanis) / sinyal_kapanis
    gap_atr_orani = abs(t1_open - sinyal_kapanis) / t_atr

    if gap_mutlak > max_gap_yuzde:
        return False, f"Aşırı mutlak gap (%{gap_mutlak*100:.1f} > %{max_gap_yuzde*100:.1f})"

    if gap_atr_orani > max_atr_orani:
        return False, f"Aşırı ATR gap ({gap_atr_orani:.2f}x ATR > {max_atr_orani:.2f}x)"

    return True, "Gap uygun"


def limit_emir_simulasyonu(
    sinyal_kapanis: float,
    t1_open: float,
    t1_low: float,
    limit_tolerans: float = cfg.LIMIT_EMIR_TOLERANS,
) -> Tuple[bool, float]:
    """
    T+1 Sabah Limit Emir gerçekleşme kontrolü.
    Limit Fiyat = Sinyal Kapanışı * (1 + limit_tolerans) (+%0.5)
    
    Returns:
        gerceklesti (bool): Limit emir doldu mu?
        gerceklesme_fiyati (float): İşleme giriş fiyatı
    """
    limit_fiyat = sinyal_kapanis * (1.0 + limit_tolerans)

    # Eğer günün en düşüğü limit fiyatın üstünde kaldıysa -> emir gerçekleşmedi
    if t1_low > limit_fiyat:
        return False, 0.0

    # Açılış limitin altındaysa veya eşitse -> açılıştan maliyetlenir
    # Açılış limitin üstünde ama gün içi limit fiyata indiyse -> limit fiyattan maliyetlenir
    if t1_open <= limit_fiyat:
        giris_fiyati = t1_open
    else:
        giris_fiyati = limit_fiyat

    return True, round(giris_fiyati, 4)


def kurumsal_aksiyon_maskele(
    df_hisse: pd.DataFrame,
    tarih_idx: int,
    maskeleme_is_gunu: int = cfg.MASKELEME_GUN,
) -> bool:
    """
    Son 'maskeleme_is_gunu' kadar bar içinde split veya temettü var mı kontrol eder.
    
    Returns:
        bool: True ise maskele (sinyal üretme), False ise serbest.
    """
    baslangic_idx = max(0, tarih_idx - maskeleme_is_gunu)
    pencere = df_hisse.iloc[baslangic_idx:tarih_idx + 1]

    has_split = False
    has_div = False

    if "stock_splits" in pencere.columns:
        has_split = (pencere["stock_splits"] > 0).any()

    if "dividends" in pencere.columns:
        has_div = (pencere["dividends"] > 0).any()

    return bool(has_split or has_div)


def hesapla_islem_maliyeti(
    nominal_tutar: float,
    sembol: str,
) -> Tuple[float, float, float]:
    """
    Komisyon ve hisse bazlı slippage (kayma) maliyetini hesaplar.
    
    Returns:
        komisyon_tl (float)
        slippage_tl (float)
        toplam_maliyet_tl (float)
    """
    komisyon_orani = cfg.KOMISYON_ORANI
    
    # Likit vs Düşük Likidite
    if sembol in cfg.DUSUK_LIKIDITE:
        slippage_orani = cfg.SLIPPAGE["dusuk"]
    else:
        slippage_orani = cfg.SLIPPAGE["default"]

    komisyon_tl = nominal_tutar * komisyon_orani
    slippage_tl = nominal_tutar * slippage_orani
    toplam_tl = komisyon_tl + slippage_tl

    return round(komisyon_tl, 2), round(slippage_tl, 2), round(toplam_tl, 2)


# ─── FAZ C3: Portföy Korelasyon Kalkanı ───────────────────────────────────────

def portfoy_korelasyon_kalkani(
    aday_sembol: str,
    acik_pozisyon_sembolleri: list[str],
    esik: float = cfg.KORELASYON_ESIGI,
    pencere: int = 30,
) -> Tuple[bool, float, str, Dict[str, float]]:
    """
    Aday sembolün açık pozisyonlarla son 'pencere' günlük getiri korelasyonunu hesaplar.
    
    Kural:
      - Eğer aday hissenin portföydeki herhangi bir açık pozisyon ile korelasyonu > esik (0.70) ise:
        -> gecerli = False (Korelasyon Kalkanı Devrede - İşlem İptal)
      - Aksi halde:
        -> gecerli = True (Portföy çeşitlendirmesi güvenli)

    Returns:
        gecerli (bool): Sinyal onaylandı mı?
        max_korelasyon (float): En yüksek ikili korelasyon değeri
        en_yuksek_sembol (str): En yüksek korelasyonlu açık hisse
        detaylar (dict): Tüm açık pozisyonlarla ikili korelasyon sözlüğü
    """
    # Açık pozisyon yoksa veya aday zaten açık pozisyonsa
    if not acik_pozisyon_sembolleri:
        return True, 0.0, "", {}

    # Aday verisini yükle
    aday_dosya = cfg.DATA_RAW / f"{aday_sembol.replace('.', '_')}.parquet"
    if not aday_dosya.exists():
        aday_dosya = cfg.DATA_FEAT / f"{aday_sembol.replace('.', '_')}.parquet"

    if not aday_dosya.exists():
        # Veri yoksa güvenli modda geçişe izin ver
        return True, 0.0, "", {}

    try:
        df_aday = pd.read_parquet(aday_dosya)
        ret_aday = df_aday["close"].pct_change().dropna()
    except Exception:
        return True, 0.0, "", {}

    detaylar = {}
    max_corr = -1.0
    en_yuksek_sembol = ""

    for acik_sym in acik_pozisyon_sembolleri:
        if acik_sym == aday_sembol:
            # Aynı hissede zaten pozisyon varsa korelasyon 1.0 (aynı hisseye ikinci pozisyon açılmaz)
            detaylar[acik_sym] = 1.0
            return False, 1.0, acik_sym, detaylar

        acik_dosya = cfg.DATA_RAW / f"{acik_sym.replace('.', '_')}.parquet"
        if not acik_dosya.exists():
            acik_dosya = cfg.DATA_FEAT / f"{acik_sym.replace('.', '_')}.parquet"

        if not acik_dosya.exists():
            detaylar[acik_sym] = 0.0
            continue

        try:
            df_acik = pd.read_parquet(acik_dosya)
            ret_acik = df_acik["close"].pct_change().dropna()

            # Ortak tarih hizalaması ve son 30 gün
            ortak_idx = ret_aday.index.intersection(ret_acik.index)
            if len(ortak_idx) < 10:
                detaylar[acik_sym] = 0.0
                continue

            ret_aday_pencere = ret_aday.loc[ortak_idx].iloc[-pencere:]
            ret_acik_pencere = ret_acik.loc[ortak_idx].iloc[-pencere:]

            corr = float(ret_aday_pencere.corr(ret_acik_pencere))
            if np.isnan(corr):
                corr = 0.0

            corr = round(corr, 3)
            detaylar[acik_sym] = corr

            if corr > max_corr:
                max_corr = corr
                en_yuksek_sembol = acik_sym

        except Exception:
            detaylar[acik_sym] = 0.0

    # Korelasyon kalkanı kontrolü
    if max_corr > esik:
        return False, max_corr, en_yuksek_sembol, detaylar

    return True, max(0.0, max_corr), en_yuksek_sembol, detaylar

