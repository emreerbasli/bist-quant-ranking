"""
features/temel_analiz.py — FAZ C2 & H1: Temel Analiz Katmanı
=============================================================
Plan referansı: FAZ C2 + Aşama 3 H1

Özellikler:
  1. yfinance üzerinden F/K (P/E), PD/DD, ROE, ROA ve Net Kâr Büyümesini çeker.
  2. 24 saatlik yerel önbellek (data/raw/fundamental_cache.json) ile rate limitleri önlenir.
  3. HATA VE ÇÖKME ÖNLEME KALKANI (Imputation):
     - Eksik veriler sektör medyanı ile doldurulur; yoksa genel piyasa fallback.
     - Uç F/K değerleri [1.0, 80.0] aralığında sınırlandırılır.
  4. H1 — SEKTÖRE ÖZEL DEĞERLEME (Aşama 3):
     - Bankacılık sektörü (XBANK.IS): F/K yerine PD/DD + ROE + ROA bileşik iskonto skoru.
     - Diğer sektörler: F/K primary, PD/DD secondary çarpan.
  5. Çıktı Metrikleri:
     - fk_orani         : Hissenin normalize F/K oranı
     - fk_sektor_orani  : F/K bazlı sektör iskonto oranı
     - pd_dd            : Fiyat / Defter Değeri
     - roe              : Özkaynak Kârlılığı (Return on Equity)
     - roa              : Aktif Kârlılığı (Return on Assets)
     - h1_deger_skoru   : Sektöre özel bileşik değerleme skoru (-2.0 ile +2.0)
     - h1_deger_etiketi : 'COK_UCUZ' | 'UCUZ' | 'ADIL' | 'PAHALI' | 'COK_PAHALI'
     - eps_surpriz_yonu : +1 (Güçlü büyüme), 0 (Nötr), -1 (Daralma)
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import yfinance as yf
from loguru import logger

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

CACHE_DOSYASI = cfg.DATA_RAW / "fundamental_cache.json"
CACHE_OMRU_SAAT = 24

# Varsayılan Sektör Medyan F/K Fallback Değerleri (BIST Tarihsel Ortalamaları)
VARSAYILAN_SEKTOR_FK = {
    "XBANK.IS": 4.8,         # Bankacılık düşük F/K ile işlem görür
    "MINI_PERAKENDE": 14.5,  # Perakende gıda yüksek çarpanlı
    "XUSIN.IS": 9.2,         # Sanayi ortalaması
    "XU100.IS": 8.5,         # BIST 100 genel medyanı
}

# H1: Sektöre Özel ROE ve ROA Fallback Değerleri (Banka için kritik)
VARSAYILAN_SEKTOR_ROE = {
    "XBANK.IS":       0.16,  # Türk bankacılığı tarihsel ROE ~%16
    "MINI_PERAKENDE": 0.20,  # Perakende yüksek ROE
    "XUSIN.IS":       0.14,  # Sanayi genel
    "XU100.IS":       0.14,
}
VARSAYILAN_SEKTOR_ROA = {
    "XBANK.IS":       0.014, # Türk bankacılığı tarihsel ROA ~%1.4
    "MINI_PERAKENDE": 0.07,
    "XUSIN.IS":       0.06,
    "XU100.IS":       0.06,
}


# ─── H1: SEKTÖRE ÖZEL BİLEŞİK DEĞERLEME SKORU ───────────────────────────────
def hesapla_h1_deger_skoru(
    sembol: str,
    pd_dd: float,
    roe: float,
    roa: float,
    fk_orani: float,
    fk_sektor_orani: float,
) -> Dict[str, Any]:
    """
    H1: Sektöre göre farklı değerleme mantığı uygular.

    - Bankacılık (XBANK.IS): PD/DD + ROE + ROA ağırlıklı bileşik iskonto skoru.
      F/K banka için güvenilmez (kredi karşılıkları değişkenliği).
    - Diğer sektörler: F/K tabanlı sektör iskontosu birincil, PD/DD ikincil.

    Returns:
        dict: {
            h1_deger_skoru  : float (-2.0 ile +2.0 arası),
            h1_deger_etiketi: str ('COK_UCUZ' | 'UCUZ' | 'ADIL' | 'PAHALI' | 'COK_PAHALI'),
            h1_metodoloji   : str,
            h1_aciklama     : str
        }
    """
    sektor = cfg.HISSE_SEKTOR.get(sembol, "XU100.IS")
    banka_sektoru = getattr(cfg, "BANKA_SEKTORU", "XBANK.IS")

    skor = 0.0
    metodoloji = ""
    parcalar = []

    if sektor == banka_sektoru:
        # ── BANKA MODI: PD/DD (0.55) + ROE (0.30) + ROA (0.15) ──────────────
        metodoloji = "BANKA (PD/DD + ROE + ROA)"

        # Sektör medyanlarını config'den al
        sektor_pddd = getattr(cfg, "VARSAYILAN_SEKTOR_PDDD", {}).get(sektor, 1.20)
        sektor_roe  = getattr(cfg, "ROE_KABUL", 0.12)

        pddd_cokucuz = getattr(cfg, "PDDD_COKUCUZ", 0.80)
        pddd_ucuz    = getattr(cfg, "PDDD_UCUZ", 1.10)
        pddd_pahali  = getattr(cfg, "PDDD_PAHALI", 2.00)
        pddd_cokpah  = getattr(cfg, "PDDD_COKPAHALI", 3.00)
        roe_guclu    = getattr(cfg, "ROE_GUCLU", 0.18)
        roe_kabul    = getattr(cfg, "ROE_KABUL", 0.12)
        roe_zayif    = getattr(cfg, "ROE_ZAYIF", 0.08)
        roa_saglikli = getattr(cfg, "ROA_SAGLIKLI", 0.015)
        roa_zayif    = getattr(cfg, "ROA_ZAYIF", 0.008)

        w_pddd = getattr(cfg, "H1_PDDD_AGIRLIK", 0.55)
        w_roe  = getattr(cfg, "H1_ROE_AGIRLIK", 0.30)
        w_roa  = getattr(cfg, "H1_ROA_AGIRLIK", 0.15)

        # PD/DD bileşeni
        if pd_dd <= pddd_cokucuz:
            pddd_puan = 2.0
            parcalar.append(f"PD/DD={pd_dd:.2f} < {pddd_cokucuz} (tarihi ucuz, +2)")
        elif pd_dd <= pddd_ucuz:
            pddd_puan = 1.0
            parcalar.append(f"PD/DD={pd_dd:.2f} < {pddd_ucuz} (iskontolu, +1)")
        elif pd_dd <= sektor_pddd:
            pddd_puan = 0.0
            parcalar.append(f"PD/DD={pd_dd:.2f} sektör medyanına yakın (0)")
        elif pd_dd <= pddd_pahali:
            pddd_puan = -0.5
            parcalar.append(f"PD/DD={pd_dd:.2f} sektör üstü (-0.5)")
        elif pd_dd <= pddd_cokpah:
            pddd_puan = -1.0
            parcalar.append(f"PD/DD={pd_dd:.2f} pahalı (-1)")
        else:
            pddd_puan = -2.0
            parcalar.append(f"PD/DD={pd_dd:.2f} aşırı değerli (-2)")

        # ROE bileşeni
        if roe >= roe_guclu:
            roe_puan = 1.0
            parcalar.append(f"ROE={roe*100:.1f}% güçlü (+1)")
        elif roe >= roe_kabul:
            roe_puan = 0.0
            parcalar.append(f"ROE={roe*100:.1f}% kabul edilebilir (0)")
        elif roe >= roe_zayif:
            roe_puan = -0.5
            parcalar.append(f"ROE={roe*100:.1f}% zayıf (-0.5)")
        else:
            roe_puan = -1.0
            parcalar.append(f"ROE={roe*100:.1f}% çok zayıf (-1)")

        # ROA bileşeni
        if roa >= roa_saglikli:
            roa_puan = 1.0
            parcalar.append(f"ROA={roa*100:.2f}% sağlıklı (+1)")
        elif roa >= roa_zayif:
            roa_puan = 0.0
            parcalar.append(f"ROA={roa*100:.2f}% orta (0)")
        else:
            roa_puan = -1.0
            parcalar.append(f"ROA={roa*100:.2f}% zayıf (-1)")

        skor = (pddd_puan * w_pddd) + (roe_puan * w_roe) + (roa_puan * w_roa)

    else:
        # ── DİĞER SEKTÖRLER: F/K tabanlı, PD/DD ikincil ─────────────────────
        metodoloji = "STANDART (F/K + PD/DD)"

        # F/K sektör iskontosu (-1.0 ile +1.0 arası, ters çevir: iskonto → pozitif)
        fk_puan = max(-1.0, min(1.0, -fk_sektor_orani))  # negatif iskonto → pozitif puan
        parcalar.append(f"F/K sektör farkı={fk_sektor_orani*100:.1f}% (F/K puanı={fk_puan:.2f})")

        # PD/DD ikincil katkı
        sektor_pddd = getattr(cfg, "VARSAYILAN_SEKTOR_PDDD", {}).get(sektor, 2.0)
        pddd_nispi  = (pd_dd / (sektor_pddd + 1e-6)) - 1.0 if pd_dd > 0 else 0.0
        pddd_puan_2 = max(-0.5, min(0.5, -pddd_nispi))  # Sektör altında → pozitif
        parcalar.append(f"PD/DD={pd_dd:.2f} sektör medyan={sektor_pddd:.2f} (PD/DD katkı={pddd_puan_2:.2f})")

        skor = (fk_puan * 0.70) + (pddd_puan_2 * 0.30)

    # Etiket
    if skor >= 1.2:
        etiket = "COK_UCUZ"
    elif skor >= 0.4:
        etiket = "UCUZ"
    elif skor >= -0.4:
        etiket = "ADIL"
    elif skor >= -1.0:
        etiket = "PAHALI"
    else:
        etiket = "COK_PAHALI"

    aciklama = f"{metodoloji} | {' | '.join(parcalar)} → Skor: {skor:.3f} ({etiket})"

    return {
        "h1_deger_skoru":   round(skor, 3),
        "h1_deger_etiketi": etiket,
        "h1_metodoloji":    metodoloji,
        "h1_aciklama":      aciklama,
    }


# ─── A2: ÜÇ BOYUTLU KÂR BÜYÜMESİ KARAR FONKSİYONU ───────────────────────────────────
def kar_buyumesi_etiketi(
    yoy_yillik: Optional[float],
    yoy_quarterly: Optional[float],
    kaynaklar_ayni_mi: bool = True,
) -> tuple:
    """
    A2 düzeltmesi: earningsGrowth ve earningsQuarterlyGrowth ayrı ayrı değerlendirilir,
    OR fallback yapılmaz. Birbiriyle çelişen sinyaller 'Karışık/Belirsiz' verir.

    Args:
        yoy_yillik:     info.get('earningsGrowth')         — YoY yıllık konsolide
        yoy_quarterly:  info.get('earningsQuarterlyGrowth') — QoQ çeyreksel
        kaynaklar_ayni_mi: Her iki alan da aynı değeri taşıyorsa True (yfinance sınırlaması)

    Returns:
        (eps_surpriz_yonu: int, aciklama: str, guvenilirlik: str)
        eps_surpriz_yonu: +1 Güçlü Artış | 0 Nötr/Belirsiz | -1 Daralma
        guvenilirlik: 'YUKSEK' | 'ORTA' | 'DUSUK'
    """
    GUCLU     = cfg.KAR_BUYUME_GUCLU_ARTIS_ESIK    # 0.10
    DARALMA   = cfg.KAR_BUYUME_ZAYIF_DARALMA_ESIK  # -0.05
    QOQ_POS   = cfg.KAR_BUYUME_QOQ_ESIK            # 0.15
    QOQ_NEG   = cfg.KAR_BUYUME_QOQ_NEGATIF_ESIK    # -0.10
    ESIK_GUCLU   = cfg.KAR_BUYUME_GUCLU_ESIK       # 1.5
    ESIK_DARALMA = cfg.KAR_BUYUME_DARALMA_ESIK     # -1.0

    agirlikli_skor = 0.0
    aktif_boyut = 0

    # Boyut 1: YoY Yıllık (en kritik, 1.0 ağırlık)
    if yoy_yillik is not None and not (isinstance(yoy_yillik, float) and yoy_yillik != yoy_yillik):
        aktif_boyut += 1
        if yoy_yillik > GUCLU:
            agirlikli_skor += 1.0
        elif yoy_yillik < DARALMA:
            agirlikli_skor -= 1.0

    # Boyut 2: QoQ / Quarterly (farklı bir veri ise kullan, 0.5 ağırlık)
    # Eğer yfinance ikisini aynı değerle döndürmüşse (kaynaklar_ayni_mi=True), hafif ağırlık ver
    if yoy_quarterly is not None and not (isinstance(yoy_quarterly, float) and yoy_quarterly != yoy_quarterly):
        aktif_boyut += 1
        qoq_agirlik = 0.25 if kaynaklar_ayni_mi else 0.5  # Aynı kaynaktan geliyorsa yarı ağırlık
        if yoy_quarterly > QOQ_POS:
            agirlikli_skor += qoq_agirlik
        elif yoy_quarterly < QOQ_NEG:
            agirlikli_skor -= qoq_agirlik

    # Kritik kontrol: YoY negatifken QoQ pozitif → zorunlu Belirsiz
    if (yoy_yillik is not None and yoy_yillik < DARALMA and
            yoy_quarterly is not None and yoy_quarterly > QOQ_POS):
        return 0, "Karışık: YoY negatif, QoQ pozitif — sinyal üretme", "DUSUK"

    # Veri hiç yoksa
    if aktif_boyut == 0:
        return 0, "Veri yok", "DUSUK"

    # Karar
    if agirlikli_skor >= ESIK_GUCLU:
        return 1, f"Güçlü Artış (skor={agirlikli_skor:.2f})", "YUKSEK"
    elif agirlikli_skor <= ESIK_DARALMA:
        return -1, f"Ciddi Daralma (skor={agirlikli_skor:.2f})", "YUKSEK"
    else:
        return 0, f"Nötr/Belirsiz (skor={agirlikli_skor:.2f})", "ORTA"



def _onbellegi_yukle() -> Dict[str, Any]:
    """Önbellek dosyasını okur; süresi geçmişse boş sözlük döner."""
    if not CACHE_DOSYASI.exists():
        return {}
    try:
        with open(CACHE_DOSYASI, "r", encoding="utf-8") as f:
            data = json.load(f)
        kayit_tarihi = datetime.fromisoformat(data.get("_guncelleme_tarihi", "2000-01-01T00:00:00"))
        if datetime.now() - kayit_tarihi < timedelta(hours=CACHE_OMRU_SAAT):
            return data.get("hisseler", {})
    except Exception as e:
        logger.warning(f"Temel analiz önbellek okuma hatası: {e}")
    return {}


def _onbellegi_kaydet(hisseler_dict: Dict[str, Any]) -> None:
    """Temel analiz verilerini önbellek dosyasına kaydeder."""
    CACHE_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_guncelleme_tarihi": datetime.now().isoformat(),
        "hisseler": hisseler_dict,
    }
    try:
        with open(CACHE_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Temel analiz önbellek kaydetme hatası: {e}")


import concurrent.futures

def _tek_hisse_temel_cek(sembol: str) -> tuple:
    """Tek bir hisse için yfinance temel verilerini çeker (Thread-safe worker)."""
    try:
        ticker = yf.Ticker(sembol)
        fast = getattr(ticker, "fast_info", None)
        info = {}
        try:
            info = ticker.info or {}
        except Exception:
            pass

        pe = info.get("trailingPE") or info.get("forwardPE")
        if pe is None and fast:
            mcap = getattr(fast, "market_cap", None)
            pe = info.get("priceToBook", 1.5) * 5.0 if mcap else None

        pb = info.get("priceToBook")
        roe = info.get("returnOnEquity") or info.get("returnOnEquityTTM")
        roa = info.get("returnOnAssets") or info.get("returnOnAssetsTTM")

        eg_yoy = info.get("earningsGrowth")
        eg_qoq = info.get("earningsQuarterlyGrowth")

        kaynaklar_ayni = (
            eg_yoy is not None and eg_qoq is not None and
            abs(float(eg_yoy) - float(eg_qoq)) < 0.005
        )

        eps_yon, eps_aciklama, eps_guvenilirlik = kar_buyumesi_etiketi(
            yoy_yillik=eg_yoy,
            yoy_quarterly=eg_qoq,
            kaynaklar_ayni_mi=kaynaklar_ayni,
        )

        eg_kullanilan = eg_yoy if eg_yoy is not None else (eg_qoq if eg_qoq is not None else None)

        sektor_kodu = cfg.HISSE_SEKTOR.get(sembol, "XU100.IS")
        med_roe = VARSAYILAN_SEKTOR_ROE.get(sektor_kodu, 0.14)
        med_roa = VARSAYILAN_SEKTOR_ROA.get(sektor_kodu, 0.06)
        roe_val = float(roe) if roe is not None and not (isinstance(roe, float) and np.isnan(roe)) else med_roe
        roa_val = float(roa) if roa is not None and not (isinstance(roa, float) and np.isnan(roa)) else med_roa

        pb_gecici  = float(pb) if pb and not np.isnan(pb) and pb > 0 else 1.0

        res = {
            "sembol": sembol,
            "fk_ham": float(pe) if pe and not np.isnan(pe) and pe > 0 else np.nan,
            "pd_dd":  pb_gecici,
            "roe":    round(roe_val, 4),
            "roa":    round(roa_val, 4),
            "net_kar_buyume_yoy": float(eg_yoy) if eg_yoy is not None else 0.0,
            "net_kar_buyume_qoq": float(eg_qoq) if eg_qoq is not None else 0.0,
            "net_kar_buyume":     float(eg_kullanilan) if eg_kullanilan is not None else 0.0,
            "kaynaklar_ayni":     bool(kaynaklar_ayni),
            "eps_surpriz_yonu": int(eps_yon),
            "eps_aciklama":     str(eps_aciklama),
            "eps_guvenilirlik": str(eps_guvenilirlik),
        }
        return sembol, res
    except Exception as e:
        sektor_kodu = cfg.HISSE_SEKTOR.get(sembol, "XU100.IS")
        res = {
            "sembol": sembol,
            "fk_ham": np.nan,
            "pd_dd":  np.nan,
            "roe":    VARSAYILAN_SEKTOR_ROE.get(sektor_kodu, 0.14),
            "roa":    VARSAYILAN_SEKTOR_ROA.get(sektor_kodu, 0.06),
            "net_kar_buyume": 0.0,
            "net_kar_buyume_yoy": 0.0,
            "net_kar_buyume_qoq": 0.0,
            "kaynaklar_ayni": False,
            "eps_surpriz_yonu": 0,
            "eps_aciklama": "Veri hatası",
            "eps_guvenilirlik": "DUSUK",
        }
        return sembol, res


def cek_temel_veriler_yfinance(hisseler: Optional[list[str]] = None, zorla_guncelle: bool = False, max_workers: int = 10) -> Dict[str, Dict[str, Any]]:
    """
    Tüm hisseler için F/K, PD/DD ve kâr büyümesi verilerini ThreadPoolExecutor ile paralel çeker ve önbellekler.
    """
    if hisseler is None:
        hisseler = cfg.HISSELER

    if not zorla_guncelle:
        cached = _onbellegi_yukle()
        if cached and all(h in cached for h in hisseler):
            logger.info("Temel analiz verileri güncel önbellekten yüklendi.")
            return cached

    logger.info(f"Temel analiz verileri paralel çekiliyor ({len(hisseler)} hisse, {max_workers} thread)...")
    sonuclar = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_tek_hisse_temel_cek, s): s for s in hisseler}
        for future in concurrent.futures.as_completed(futures):
            sembol, res = future.result()
            sonuclar[sembol] = res

    _onbellegi_kaydet(sonuclar)
    return sonuclar


def impute_temel_analiz_tablosu(ham_temel_dict: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    """
    Eksik/NaN F/K ve büyüme değerlerini Sektör Medyanı ile doldurur ve göreceli çarpanları üretir.
    """
    df = pd.DataFrame.from_dict(ham_temel_dict, orient="index")
    if df.empty:
        return df

    # Sektör kodunu ekle
    df["sektor"] = df["sembol"].map(lambda s: cfg.HISSE_SEKTOR.get(s, "XU100.IS"))

    # 1. Sektör Medyan F/K Hesaplama (Geçerli F/K'lar üzerinden)
    sektor_medyanlari = {}
    for sektor, grup in df.groupby("sektor"):
        gecerli_fk = grup["fk_ham"].dropna()
        gecerli_fk = gecerli_fk[(gecerli_fk > 1.0) & (gecerli_fk < 70.0)]
        if len(gecerli_fk) >= 2:
            sektor_medyanlari[sektor] = float(gecerli_fk.median())
        else:
            sektor_medyanlari[sektor] = VARSAYILAN_SEKTOR_FK.get(sektor, 8.5)

    # 2. Sektör Medyan PD/DD Hesaplama (H1 için)
    sektor_pddd_medyanlari = {}
    for sektor, grup in df.groupby("sektor"):
        gecerli_pb = grup["pd_dd"].dropna() if "pd_dd" in grup.columns else pd.Series([], dtype=float)
        gecerli_pb = gecerli_pb[(gecerli_pb > 0.1) & (gecerli_pb < 20.0)]
        if len(gecerli_pb) >= 2:
            sektor_pddd_medyanlari[sektor] = float(gecerli_pb.median())
        else:
            sektor_pddd_medyanlari[sektor] = VARSAYILAN_SEKTOR_PDDD.get(sektor, 2.0)

    # 3. İmpütasyon (Eksik veya zarardaki hisseleri doldur)
    imputed_fk = []
    fk_sektor_farki = []
    h1_skorlar = []
    h1_etiketler = []
    h1_aciklamalar = []

    for _, row in df.iterrows():
        sembol = row["sembol"]
        sektor = row["sektor"]
        sektor_med = sektor_medyanlari.get(sektor, 8.5)
        ham_fk = row.get("fk_ham")

        if pd.isna(ham_fk) or ham_fk <= 0:
            # Eksik F/K -> Sektör Medyanı ile güvenli ikame
            nihai_fk = sektor_med
        else:
            # Uç değerleri sınırla [1.0, 80.0]
            nihai_fk = max(1.0, min(80.0, float(ham_fk)))

        # Sektöre göre fark oranı: (hisse_fk / sektor_med) - 1.0
        # Negatifse -> Hissesi sektörüne göre %X daha iskontolu (ucuz)
        sektor_fark = (nihai_fk / (sektor_med + 1e-6)) - 1.0
        sektor_fark = max(-0.80, min(2.0, sektor_fark))

        imputed_fk.append(round(nihai_fk, 2))
        fk_sektor_farki.append(round(sektor_fark, 3))

        # H1: Sektöre özel bileşik değerleme skoru
        pd_dd_val = float(row.get("pd_dd", 0.0)) if not pd.isna(row.get("pd_dd")) else sektor_pddd_medyanlari.get(sektor, 2.0)
        roe_val   = float(row.get("roe", 0.0)) if not pd.isna(row.get("roe", np.nan)) else VARSAYILAN_SEKTOR_ROE.get(sektor, 0.14)
        roa_val   = float(row.get("roa", 0.0)) if not pd.isna(row.get("roa", np.nan)) else VARSAYILAN_SEKTOR_ROA.get(sektor, 0.06)

        h1_res = hesapla_h1_deger_skoru(
            sembol=sembol,
            pd_dd=pd_dd_val,
            roe=roe_val,
            roa=roa_val,
            fk_orani=nihai_fk,
            fk_sektor_orani=sektor_fark,
        )
        h1_skorlar.append(h1_res["h1_deger_skoru"])
        h1_etiketler.append(h1_res["h1_deger_etiketi"])
        h1_aciklamalar.append(h1_res["h1_aciklama"])

    df["fk_orani"]        = imputed_fk
    df["fk_sektor_orani"] = fk_sektor_farki
    df["h1_deger_skoru"]  = h1_skorlar
    df["h1_deger_etiketi"]= h1_etiketler
    df["h1_aciklama"]     = h1_aciklamalar
    df["eps_surpriz_yonu"]= df["eps_surpriz_yonu"].fillna(0).astype(int)
    df["net_kar_buyume"]  = df["net_kar_buyume"].fillna(0.0).clip(-1.0, 5.0)

    # ROE / ROA sütunlarının varlığını garantile
    if "roe" not in df.columns:
        df["roe"] = 0.14
    if "roa" not in df.columns:
        df["roa"] = 0.06
    df["roe"] = df["roe"].fillna(0.0)
    df["roa"] = df["roa"].fillna(0.0)

    return df


def getir_hisse_temel_featurelari(sembol: str) -> Dict[str, Any]:
    """
    Belirli bir hisse için temizlenmiş, impüte edilmiş temel analiz göstergelerini döner.
    A2 güncellemesiyle eps_aciklama ve eps_guvenilirlik de eklendi.
    """
    ham = cek_temel_veriler_yfinance()
    df_imputed = impute_temel_analiz_tablosu(ham)

    if sembol in df_imputed.index:
        row = df_imputed.loc[sembol]
        return {
            # Temel F/K ve Sektör İskontosu
            "fk_orani":           float(row.get("fk_orani", 8.5)),
            "fk_sektor_orani":    float(row.get("fk_sektor_orani", 0.0)),
            # H1: PD/DD, ROE, ROA ve Bileşik Değerleme Skoru
            "pd_dd":              float(row.get("pd_dd", 1.0)),
            "roe":                float(row.get("roe", 0.14)),
            "roa":                float(row.get("roa", 0.06)),
            "h1_deger_skoru":     float(row.get("h1_deger_skoru", 0.0)),
            "h1_deger_etiketi":   str(row.get("h1_deger_etiketi", "ADIL")),
            "h1_aciklama":        str(row.get("h1_aciklama", "")),
            # EPS Büyümesi (A2)
            "eps_surpriz_yonu":   int(row.get("eps_surpriz_yonu", 0)),
            "net_kar_buyume":     float(row.get("net_kar_buyume", 0.0)),
            "net_kar_buyume_yoy": float(row.get("net_kar_buyume_yoy", 0.0)),
            "net_kar_buyume_qoq": float(row.get("net_kar_buyume_qoq", 0.0)),
            "eps_aciklama":       str(row.get("eps_aciklama", "")),
            "eps_guvenilirlik":   str(row.get("eps_guvenilirlik", "DUSUK")),
        }

    # Tam fallback
    sektor = cfg.HISSE_SEKTOR.get(sembol, "XU100.IS")
    med_fk   = VARSAYILAN_SEKTOR_FK.get(sektor, 8.5)
    med_roe  = VARSAYILAN_SEKTOR_ROE.get(sektor, 0.14)
    med_roa  = VARSAYILAN_SEKTOR_ROA.get(sektor, 0.06)
    med_pddd = VARSAYILAN_SEKTOR_PDDD.get(sektor, 2.0)
    return {
        "fk_orani":           med_fk,
        "fk_sektor_orani":    0.0,
        "pd_dd":              med_pddd,
        "roe":                med_roe,
        "roa":                med_roa,
        "h1_deger_skoru":     0.0,
        "h1_deger_etiketi":   "ADIL",
        "h1_aciklama":        "Veri yok (tam fallback)",
        "eps_surpriz_yonu":   0,
        "net_kar_buyume":     0.0,
        "net_kar_buyume_yoy": 0.0,
        "net_kar_buyume_qoq": 0.0,
        "eps_aciklama":       "Veri yok (fallback)",
        "eps_guvenilirlik":   "DUSUK",
    }


if __name__ == "__main__":
    ham = cek_temel_veriler_yfinance(zorla_guncelle=True)
    df_res = impute_temel_analiz_tablosu(ham)
    print("\n" + "=" * 80)
    print("FAZ C2: TEMEL ANALİZ GÖSTERGELERİ & SEKTÖR İMPÜTASYON RAPORU")
    print("=" * 80)
    print(df_res[["sembol", "sektor", "fk_orani", "fk_sektor_orani", "eps_surpriz_yonu"]].head(25).to_string(index=False))
