"""
features/emsal_analizi.py — G1: Emsal Grubu (Peer Group) Güç & Değerleme Analizi
================================================================================
Plan referansı: Aşama 3 (G1) — Analiz Kalitesi & Sinyal Doğruluk Raporu

Özellikler:
  1. Hisseleri geniş sektör yerine mikro "Emsal Grupları" (Peer Groups) altında kümeler:
     - BANKACILIK     : ISCTR, AKBNK, GARAN, YKBNK, VAKBN, HALKB, TSKB, SAHOL
     - PERAKENDE_GIDA : BIMAS, MGROS, SOKM, CCOLA, AEFES, ULKER, TABGD
     - AGIR_SANAYI_OTO: THYAO, PGSUS, TUPRS, FROTO, TOASO, DOAS, OTKAR, EREGL, KRDMD, BRSAN, ARCLK, VESTL, SISE, ASELS, KCHOL, ENKAI
     - YENI_ENERJI_TEK: ASTOR, EUPWR, GESAN, KONTR, FORTE, TERA, TUREX
     - GYO_ILETISIM   : EKGYO, ISGYO, TCELL, TTKOM, ALARK, PETKM, SASA, HEKTS, GUBRF, CIMSA, OYAKC, MAVI
  2. Her hissenin kendi emsal grubuna göre 5 günlük ve 20 günlük Göreceli Gücünü (Peer Relative Strength) hesaplar.
  3. Emsal grubu içindeki değerleme (F/K veya PD/DD) iskonto sıralamasını ve genel grup yüzdeliğini belirler.
  4. Hissenin "Emsal Grubu Lideri" (üst %30 dilimde) olup olmadığını bayraklar.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from loguru import logger

# Proje kökünü ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

# Mikro Emsal Grubu Tanımları (91 Hisse Kapsamı)
EMSAL_GRUPLARI: Dict[str, List[str]] = {
    "BANKACILIK": [
        "ISCTR.IS", "AKBNK.IS", "GARAN.IS", "YKBNK.IS",
        "VAKBN.IS", "HALKB.IS", "TSKB.IS", "SKBNK.IS", "SAHOL.IS"
    ],
    "PERAKENDE_GIDA": [
        "BIMAS.IS", "MGROS.IS", "SOKM.IS", "BIZIM.IS",
        "CCOLA.IS", "AEFES.IS", "ULKER.IS", "TABGD.IS", "GOKNR.IS"
    ],
    "AGIR_SANAYI_OTO_HAVACILIK": [
        "THYAO.IS", "PGSUS.IS", "TAVHL.IS", "CLEBI.IS", "TUPRS.IS",
        "FROTO.IS", "TOASO.IS", "DOAS.IS", "OTKAR.IS", "TTRAK.IS",
        "EREGL.IS", "KRDMD.IS", "BRSAN.IS", "KCAER.IS", "ARCLK.IS",
        "VESTL.IS", "SISE.IS", "ASELS.IS", "SDTTR.IS", "KCHOL.IS",
        "AGHOL.IS", "DOHOL.IS", "TKFEN.IS", "ENKAI.IS", "KORDS.IS",
        "GENTS.IS", "CIMSA.IS", "OYAKC.IS", "BSOKE.IS"
    ],
    "YENI_ENERJI_TEKNOLOJI_LOJISTIK": [
        "ASTOR.IS", "EUPWR.IS", "GESAN.IS", "KONTR.IS", "CWENE.IS",
        "ALFAS.IS", "CANTE.IS", "ODAS.IS", "MOGAN.IS", "FORTE.IS",
        "TERA.IS", "TUREX.IS", "AGROT.IS", "BINHO.IS", "REEDR.IS",
        "MIATK.IS", "MTRKS.IS", "LOGO.IS", "PASEU.IS", "PLTUR.IS", "INVES.IS"
    ],
    "GYO_ILETISIM_KIMYA_SAGLIK_MADEN": [
        "EKGYO.IS", "ISGYO.IS", "TRGYO.IS", "SURGY.IS", "TCELL.IS",
        "TTKOM.IS", "ALARK.IS", "PETKM.IS", "SASA.IS", "HEKTS.IS",
        "GUBRF.IS", "MAVI.IS", "KBORU.IS", "ALVES.IS", "CVKMD.IS",
        "SELEC.IS", "ECILC.IS", "ONCSM.IS", "TURSG.IS", "ANSGR.IS"
    ]
}


def bul_hisse_emsal_grubu(sembol: str) -> str:
    """Hissenin dahil olduğu mikro emsal grubunun adını döner."""
    for grup_adi, uyeler in EMSAL_GRUPLARI.items():
        if sembol in uyeler:
            return grup_adi
    # Tanımlı grupta yoksa sektör koduna fallback yap
    return cfg.HISSE_SEKTOR.get(sembol, "GENEL_BIST")


def getir_emsal_grubu_hisseleri(grup_adi: str) -> List[str]:
    """Belirtilen emsal grubundaki tüm hisseleri döner."""
    if grup_adi in EMSAL_GRUPLARI:
        return EMSAL_GRUPLARI[grup_adi]
    # Sektör koduna göre filtrele
    return [s for s, sek in cfg.HISSE_SEKTOR.items() if sek == grup_adi] or cfg.HISSELER


def hesapla_emsal_grubu_metrikleri(
    tum_hisseler_df_dict: Dict[str, pd.DataFrame],
    temel_df_dict: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Tüm hisseler için emsal grubu ortalamalarını ve hisse bazlı göreceli güç metriklerini hesaplar.

    Args:
        tum_hisseler_df_dict: {sembol: feature_veya_fiyat_dataframe}
        temel_df_dict: {sembol: temel_analiz_sozlugu}

    Returns:
        {sembol: {
            'emsal_grubu': str,
            'rel_str_emsal_5d': float,
            'rel_str_emsal_20d': float,
            'emsal_grup_sirasi': float (0.0 - 1.0),
            'emsal_lideri': bool,
            'emsal_sayisi': int,
            'emsal_aciklama': str
        }}
    """
    sonuclar = {}

    # 1. Her hissenin son 5g ve 20g getirilerini topla
    getiriler_5d: Dict[str, float] = {}
    getiriler_20d: Dict[str, float] = {}

    for sembol, df in tum_hisseler_df_dict.items():
        if df is None or df.empty:
            continue
        son = df.iloc[-1]
        r5 = float(son.get("ret_5d", 0.0))
        r20 = float(son.get("ret_20d", 0.0))
        getiriler_5d[sembol] = r5
        getiriler_20d[sembol] = r20

    # 2. Emsal Grupları bazında analiz
    for grup_adi, uyeler in EMSAL_GRUPLARI.items():
        mevcut_uyeler = [u for u in uyeler if u in getiriler_5d]
        if not mevcut_uyeler:
            continue

        # Grup ortalama getirileri
        grup_r5_ort = float(np.mean([getiriler_5d[u] for u in mevcut_uyeler]))
        grup_r20_ort = float(np.mean([getiriler_20d[u] for u in mevcut_uyeler]))

        # Grup içi getiri sıralaması (5g + 20g ağırlıklı skor)
        grup_skorlari = {}
        for u in mevcut_uyeler:
            # %60 5 günlük ivme + %40 20 günlük trend
            skor = (getiriler_5d[u] * 0.60) + (getiriler_20d[u] * 0.40)
            grup_skorlari[u] = skor

        sirali_uyeler = sorted(grup_skorlari.keys(), key=lambda x: grup_skorlari[x])
        n = len(sirali_uyeler)

        for u in mevcut_uyeler:
            r5 = getiriler_5d[u]
            r20 = getiriler_20d[u]
            rel_5d = r5 - grup_r5_ort
            rel_20d = r20 - grup_r20_ort

            # Yüzdelik sıra: 0.0 (en zayıf) ile 1.0 (en güçlü lider)
            rank_idx = sirali_uyeler.index(u)
            yuzdelik = round((rank_idx + 1) / n, 2)
            lider_mi = bool(yuzdelik >= getattr(cfg, "G1_GUCLU_USTU_ESIK", 0.70))

            if lider_mi:
                aciklama = f"🏆 Emsal Lideri ({grup_adi} grubu üst %{int((1-yuzdelik)*100+10)}, 5g fark: %{rel_5d*100:+.1f})"
            elif yuzdelik <= 0.30:
                aciklama = f"⚠️ Emsal Gerisinde ({grup_adi} alt %30, 5g fark: %{rel_5d*100:+.1f})"
            else:
                aciklama = f"⚪ Emsal Dengeli ({grup_adi} grubu, 5g fark: %{rel_5d*100:+.1f})"

            sonuclar[u] = {
                "emsal_grubu": grup_adi,
                "rel_str_emsal_5d": round(rel_5d, 4),
                "rel_str_emsal_20d": round(rel_20d, 4),
                "emsal_grup_sirasi": yuzdelik,
                "emsal_lideri": lider_mi,
                "emsal_sayisi": n,
                "emsal_aciklama": aciklama,
            }

    return sonuclar


def tek_hisse_emsal_analizi(
    sembol: str,
    hisse_df: pd.DataFrame,
    tum_hisseler_df_dict: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, Any]:
    """
    Tek bir hisse için hızlı emsal analizi döner.
    Eğer diğer hisselerin verisi yoksa güvenli varsayılanlar üretir.
    """
    grup_adi = bul_hisse_emsal_grubu(sembol)
    if hisse_df is None or hisse_df.empty or len(hisse_df) < 5:
        return {
            "emsal_grubu": grup_adi,
            "rel_str_emsal_5d": 0.0,
            "rel_str_emsal_20d": 0.0,
            "emsal_grup_sirasi": 0.50,
            "emsal_lideri": False,
            "emsal_sayisi": len(getir_emsal_grubu_hisseleri(grup_adi)),
            "emsal_aciklama": "Yetersiz veri",
        }

    if tum_hisseler_df_dict:
        toplu = hesapla_emsal_grubu_metrikleri(tum_hisseler_df_dict)
        if sembol in toplu:
            return toplu[sembol]

    # Fallback: Sadece kendi getirisi
    son = hisse_df.iloc[-1]
    r5 = float(son.get("ret_5d", 0.0))
    r20 = float(son.get("ret_20d", 0.0))

    return {
        "emsal_grubu": grup_adi,
        "rel_str_emsal_5d": round(r5, 4),
        "rel_str_emsal_20d": round(r20, 4),
        "emsal_grup_sirasi": 0.50,
        "emsal_lideri": False,
        "emsal_sayisi": len(getir_emsal_grubu_hisseleri(grup_adi)),
        "emsal_aciklama": f"{grup_adi} grubu (tekil hesaplama)",
    }
