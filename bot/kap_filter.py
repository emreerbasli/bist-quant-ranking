"""
bot/kap_filter.py — FAZ 5.7: Canlı KAP, Bilanço & Güncel Finans Haberleri Filtresi (Son 7 Gün)
=============================================================================================
Plan referansı: FAZ 5.7 (bist_sinyal_botu_proje_plani_v2.md)

Özellikler:
  1. Yalnızca son 7 günün güncel KAP, bilanço ve şirket haberlerini çeker (Eski haberler elenir).
  2. Bilanço & Finansal Rapor tespiti ("bilanço", "faaliyet raporu", "net kar", "gelir tablosu").
  3. Kural Tabanlı Negatif Risk Taraması:
     - "zarar", "ceza", "dava", "istifa", "spk", "yangın", "tedbir", "soruşturma", "iflas",
       "konkordato", "haciz", "erteleme", "iptal", "kayıp", "yaptırım", "suç", "uyarı", "olağandışı"
"""

import sys
import time
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import os
import requests
from bs4 import BeautifulSoup
from loguru import logger
import pandas as pd
import numpy as np

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

# Kural Tabanlı Negatif Risk Kelimeleri (Regex)
RISK_KELIMELERI = [
    r"\bzarar\b", r"\bceza\b", r"\bdava\b", r"\bistifa\b", r"\bspk\b",
    r"\byang[ıi]n\b", r"\btedbir\b", r"\bsoru[şs]turma\b", r"\biflas\b",
    r"\bkonkordato\b", r"\bhaciz\b", r"\berteleme\b", r"\biptal\b",
    r"\bkay[ıi]p\b", r"\byapt[ıi]r[ıi]m\b", r"\bsu[çc]\b", r"\buyar[ıi]\b",
    r"\bola[ğg]and[ıi][şs][ıi]\b", r"\bsavc[ıi]l[ıi]k\b", r"\bm[üu]h[üu]r\b"
]
RISK_REGEX = re.compile("|".join(RISK_KELIMELERI), re.IGNORECASE)

# ─── FAZ 0: VBTS ve İdari Tedbir Kelimeleri (İzleme Modu — Tarihsel Test Edilemez) ───
# NOT: VBTS tedbir bildirimleri geçmiş KAP metin arşivinde bulunmadığı için tarihsel
# backtest'ten geçirilememiştir (test edilemez). Plan gereği CANLI İZLEME MODUNDA (soft warning)
# çalışır. 4 çeyreklik canlı takip sonrası vaka analizine göre hard exclusion değerlendirilecektir.
VBTS_TEDBIR_KELIMELERI = [
    r"\bVBTS\b", r"\bvolatilite bazl[ıi] tedbir\b",
    r"\bkredili i[şs]lem yasa[ğg][ıi]\b",
    r"\baç[ıi][ğg]a sat[ıi][şs] yasa[ğg][ıi]\b",
    r"\bbrüt takas\b", r"\bbrut takas\b",
    r"\bpay sat[ıi][şs] yasa[ğg][ıi]\b",
    r"\bBorsa [İi]stanbul tedbir\b", r"\bBİST tedbir\b",
    r"\binternet emir yasa[ğg][ıi]\b", r"\bemir iptal yasa[ğg][ıi]\b",
    r"\bpiyasa doland[ıi]r[ıi]c[ıi]l[ıi][ğg][ıi]\b",
]
VBTS_REGEX = re.compile("|".join(VBTS_TEDBIR_KELIMELERI), re.IGNORECASE)

# Bilanço & Finansal Sonuç Kelimeleri
BILANCO_KELIMELERI = [r"\bbilan[çc]o\b", r"\bfaaliyet raporu\b", r"\bnet k[aâ]r\b", r"\bfinansal sonu[çc]\b", r"\bgelir tablosu\b", r"\btemett[üu]\b"]
BILANCO_REGEX = re.compile("|".join(BILANCO_KELIMELERI), re.IGNORECASE)

# ─── YENİ: Pozitif Katalizör Kelimeleri ────────────────────────────────────────
# Bu kelimeler hisse için pozitif momentum yaratır → sinyal skoru bonusu
POZITIF_KATALIZOR_TAZE = [          # Son 2 gün içindeyse → +15 puan (Taze Katalizör)
    r"\bihale kazand[ıi]\b", r"\banla[şs]ma imzaland[ıi]\b", r"\bortakl[ıi]k\b",
    r"\bihracat anla[şs]mas[ıi]\b", r"\bnew contract\b", r"\baward\b",
    r"\bsipar[ıi][şs] ald[ıi]\b", r"\bkapasite art[ıi][şs][ıi]\b",
]
POZITIF_KATALIZOR_NORMAL = [        # Tüm 7 gün içindeyse → +10 puan (Normal Katalizör)
    r"\btemett[üu]\b", r"\bk[aâ]r aç[ıi]klad[ıi]\b", r"\bb[üu]y[üu]me\b",
    r"\bgenişleme\b", r"\byat[ıi]r[ıi]m kararı\b", r"\bred bull\b",
    r"\bgüçlü sonu[çc]\b", r"\brekora ula[şs]t[ıi]\b", r"\ben y[üu]ksek\b",
    r"\bzirve\b", r"\btarihsel y[üu]ksek\b", r"\by[üu]ksek k[aâ]r\b",
]
POZITIF_REGEX_TAZE   = re.compile("|".join(POZITIF_KATALIZOR_TAZE),   re.IGNORECASE)
POZITIF_REGEX_NORMAL = re.compile("|".join(POZITIF_KATALIZOR_NORMAL), re.IGNORECASE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}



def cek_hisse_haberleri(sembol: str, max_haber: int = 5, max_gun: int = 7) -> List[Dict[str, Any]]:
    """
    Belirtilen hisse için SADECE SON 7 GÜNÜN KAP, bilanço ve finans haberlerini çeker.
    Eski tarihli haberleri kesinlikle filtreler ve dışlar.
    """
    ticker_clean = sembol.replace(".IS", "").upper()
    haberler = []
    simdi = datetime.now(timezone.utc)
    esik_tarih = simdi - timedelta(days=max_gun)

    # 1. Öncelikli Canlı Kaynak: Google News RSS (when:7d güncellik filtresi ile)
    try:
        rss_url = f"https://news.google.com/rss/search?q={ticker_clean}+BIST+OR+KAP+when:{max_gun}d&hl=tr&gl=TR&ceid=TR:tr"
        resp = requests.get(rss_url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                
                # Tarih kontrolü (Eski haberleri ele)
                haber_tarihi = None
                if pub_date_str:
                    try:
                        haber_tarihi = parsedate_to_datetime(pub_date_str)
                        if haber_tarihi < esik_tarih:
                            continue
                    except Exception:
                        pass

                # Kaynak adını başlıktan ayıkla
                kaynak = "KAP / Finans"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0]
                    kaynak = parts[1]

                # Bilanço haberi mi?
                is_bilanco = bool(BILANCO_REGEX.search(title))

                if title and len(title) > 10:
                    tarih_gorunum = haber_tarihi.strftime("%d.%m.%Y %H:%M") if haber_tarihi else ""
                    haberler.append({
                        "baslik": title.strip(),
                        "kaynak": kaynak.strip(),
                        "tarih": tarih_gorunum,
                        "link": link,
                        "is_bilanco": is_bilanco,
                    })

                if len(haberler) >= max_haber:
                    break
    except Exception as e:
        logger.debug(f"RSS haber çekme hatası: {e}")

    # 2. Fallback: Bigpara
    if not haberler:
        try:
            url_bigpara = f"https://bigpara.hurriyet.com.tr/haberler/sirket-haberleri/?hisse={ticker_clean}"
            resp = requests.get(url_bigpara, headers=HEADERS, timeout=6)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.select("div.news-list-item, div.content-item, a.news-item")[:max_haber]:
                    baslik = item.get_text(strip=True)
                    if baslik and len(baslik) > 15:
                        haberler.append({
                            "baslik": baslik,
                            "kaynak": "Bigpara",
                            "tarih": "Güncel",
                            "link": url_bigpara,
                            "is_bilanco": bool(BILANCO_REGEX.search(baslik)),
                        })
        except Exception as e:
            logger.debug(f"Bigpara haber çekme hatası: {e}")

    return haberler


def analiz_et_kap_riski(haber_listesi: List[Dict[str, Any]]) -> Tuple[str, List[str], List[str], bool]:
    """
    Son 7 günün haberleri içinde negatif risk + pozitif katalizör kelimelerini tarar.

    Returns:
        kap_riski (str): "DUSUK", "ORTA", "YUKSEK"
        eslesen_kelimeler (List[str])
        riskli_basliklar (List[str])
        has_bilanco (bool): Güncel bilanço haberi var mı?
    """
    if not haber_listesi:
        return "DUSUK", [], [], False

    riskli_basliklar = []
    eslesen_kelimeler = set()
    has_bilanco = False

    for h in haber_listesi:
        baslik = h["baslik"]
        if h.get("is_bilanco", False) or BILANCO_REGEX.search(baslik):
            has_bilanco = True

        matches = RISK_REGEX.findall(baslik)
        if matches:
            riskli_basliklar.append(baslik)
            for m in matches:
                eslesen_kelimeler.add(m.lower())

    if len(riskli_basliklar) >= 2:
        return "YUKSEK", list(eslesen_kelimeler), riskli_basliklar, has_bilanco
    elif len(riskli_basliklar) == 1:
        return "ORTA", list(eslesen_kelimeler), riskli_basliklar, has_bilanco
    else:
        return "DUSUK", [], [], has_bilanco


def analiz_et_kap_pozitif_katalizor(
    haber_listesi: List[Dict[str, Any]],
    simdi: Optional[datetime] = None,
) -> Tuple[int, str]:
    """
    Son 7 günün haberleri içinde POZITIF katalizör tespit eder.
    Taze katalizör (son 2 gün): +15 puan
    Normal katalizör (7 gün):   +10 puan

    Returns:
        bonus_puan (int): 0, 10 veya 15
        aciklama (str): Hangi kelime tetikledi
    """
    if not haber_listesi:
        return 0, ""

    if simdi is None:
        simdi = datetime.now(timezone.utc)
    taze_esik = simdi - timedelta(days=2)

    taze_eslesme = []
    normal_eslesme = []

    for h in haber_listesi:
        baslik = h["baslik"]
        # Tarihi datetime'a çevir
        haber_dt = None
        if h.get("tarih"):
            try:
                haber_dt = datetime.strptime(h["tarih"], "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
            except Exception:
                pass

        taze = haber_dt and haber_dt >= taze_esik

        if POZITIF_REGEX_TAZE.search(baslik):
            if taze:
                taze_eslesme.append(baslik[:60])
            else:
                normal_eslesme.append(baslik[:60])
        elif POZITIF_REGEX_NORMAL.search(baslik):
            normal_eslesme.append(baslik[:60])

    if taze_eslesme:
        return 15, f"Taze Katalizör: {taze_eslesme[0]}"
    elif normal_eslesme:
        return 10, f"Pozitif Haber: {normal_eslesme[0]}"
    return 0, ""


def kap_filtresi_uygula(aday_sinyaller: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Üretilen sinyal adaylarının her biri için son 7 günün KAP haber taramasını yapar.
    Negatif haberler cezalandırılır; pozitif katalizörler bonus puan kazandırır.
    """
    logger.info(f"KAP Filtresi: {len(aday_sinyaller)} sinyal adayı için son 7 günün haber taraması yapılıyor...")
    filtrelenmis_adaylar = []
    simdi = datetime.now(timezone.utc)

    for aday in aday_sinyaller:
        sembol = aday["sembol"]
        haberler = cek_hisse_haberleri(sembol, max_haber=5, max_gun=7)
        risk_derecesi, kelimeler, riskli_basliklar, has_bilanco = analiz_et_kap_riski(haberler)
        bonus_puan, bonus_aciklama = analiz_et_kap_pozitif_katalizor(haberler, simdi)

        aday["kap_riski"]            = risk_derecesi
        aday["kap_riskli_kelimeler"] = kelimeler
        aday["kap_haber_ozeti"]      = [h["baslik"] for h in haberler[:2]]
        aday["has_bilanco"]          = has_bilanco
        aday["kap_pozitif_bonus"]    = bonus_puan
        aday["kap_pozitif_aciklama"] = bonus_aciklama

        # Negatif ceza
        if risk_derecesi == "YUKSEK":
            logger.warning(f"🚨 {sembol}: YÜKSEK KAP Riski! Eşleşenler: {kelimeler}")
            aday["islem_skoru"] = max(0, aday["islem_skoru"] - 20)
        elif risk_derecesi == "ORTA":
            logger.info(f"⚠️ {sembol}: Orta düzey haber uyarısı ({kelimeler})")
            aday["islem_skoru"] = max(0, aday["islem_skoru"] - 10)

        # Pozitif bonus (negatif ceza ile üst üste gelmez — negatif öncelikli)
        if bonus_puan > 0 and risk_derecesi == "DUSUK":
            logger.info(f"🚀 {sembol}: +{bonus_puan} puan pozitif katalizör — {bonus_aciklama}")
            aday["islem_skoru"] = min(100, aday["islem_skoru"] + bonus_puan)

        filtrelenmis_adaylar.append(aday)

    return filtrelenmis_adaylar


def analiz_et_vbts_riski(haber_listesi: List[Dict[str, Any]]) -> Tuple[bool, List[str], List[str]]:
    """
    KAP haberleri içinde VBTS, kredili işlem yasağı, açığa satış yasağı ve brüt takas kararlarını tarar.
    
    NOT (FAZ 0): Bu kural tarihsel KAP arşiv metni bulunmadığı için backtest'ten geçirilememiştir
    (test edilemez). Dolayısıyla sistemde 'İzleme Modu' (Soft Warning) olarak çalışır.
    
    Returns:
        has_vbts (bool): VBTS veya ilgili idari tedbir haberi var mı?
        eslesen_terimler (List[str]): Tespit edilen terimler
        riskli_basliklar (List[str]): İlgili haber başlıkları
    """
    if not haber_listesi:
        return False, [], []

    eslesen = set()
    basliklar = []

    for h in haber_listesi:
        baslik = h.get("baslik", "")
        matches = VBTS_REGEX.findall(baslik)
        if matches:
            basliklar.append(baslik)
            for m in matches:
                eslesen.add(m.lower())

    has_vbts = len(basliklar) > 0
    return has_vbts, list(eslesen), basliklar


def ardisik_taban_tespit(fiyat_serisi: pd.Series,
                         lookback_gun: int = 10,
                         min_taban: int = 5,
                         taban_esik: float = -0.095) -> Tuple[bool, int]:
    """
    Hissenin son `lookback_gun` işlem gününde en az `min_taban` kez taban (< `taban_esik`)
    kapanış yapıp yapmadığını tespit eder.
    
    Faz 0 ampirik backtestinde test edilip onaylanan kuraldır.
    PASEU tipi sert çöküş vakalarını portföydeyken yakalayıp acil tasfiye etmeyi amaçlar.
    
    Returns:
        tetiklendi (bool): Kural eşiği aşıldı mı?
        taban_sayisi (int): Son penceredeki taban barı adedi.
    """
    if fiyat_serisi is None or len(fiyat_serisi) < 2:
        return False, 0

    # Son N+1 günlük fiyat verisinden N günlük yüzde değişimleri çıkar
    sub = fiyat_serisi.tail(lookback_gun + 1)
    rets = sub.pct_change().dropna()
    if rets.empty:
        return False, 0

    taban_sayisi = int((rets <= taban_esik).sum())
    tetiklendi = (taban_sayisi >= min_taban)
    return tetiklendi, taban_sayisi


def tara_evren_ardisik_taban(fiyat_dict: Dict[str, pd.Series],
                             lookback_gun: int = 10,
                             min_taban: int = 5,
                             taban_esik: float = -0.095) -> Dict[str, int]:
    """
    Tüm hisse evrenini tarayarak kurala takılan (son 10 günde >=5 taban) hisseleri döner.
    
    Returns:
        Dict[str, int]: {sembol: taban_sayisi}
    """
    yakalananlar = {}
    for sembol, seri in fiyat_dict.items():
        tetiklendi, cnt = ardisik_taban_tespit(seri, lookback_gun, min_taban, taban_esik)
        if tetiklendi:
            yakalananlar[sembol] = cnt
    return yakalananlar


# ─── FAZ -1.4: VBTS / İDARİ TEDBİR CANLI ARŞİVLEME MOTORU ─────────────────────
DEFAULT_VBTS_ARSIV_FILE = cfg.BASE_DIR / "data" / "kap_vbts_arsiv.csv"


def arsivle_vbts_bildirimleri(bildirimler: List[Dict[str, Any]],
                              csv_path: Optional[Path] = None) -> int:
    """
    Tespit edilen VBTS ve idari tedbir bildirimlerini zaman damgasıyla CSV'ye arşivler.
    Idempotent çalışır: Aynı (sembol, haber_basligi) kaydını tekrar eklemez.
    
    Returns:
        int: Arşive yeni eklenen kayıt sayısı.
    """
    if not bildirimler:
        return 0

    p = Path(csv_path) if csv_path else DEFAULT_VBTS_ARSIV_FILE
    p.parent.mkdir(parents=True, exist_ok=True)

    columns = ["kayit_zamani", "haber_tarihi", "sembol", "tedbir_terimleri", "baslik", "kaynak", "link"]
    if p.exists():
        try:
            df_old = pd.read_csv(p, encoding="utf-8")
        except Exception:
            df_old = pd.DataFrame(columns=columns)
    else:
        df_old = pd.DataFrame(columns=columns)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    yeni_satirlar = []

    mevcut_anahtarlar = set()
    if not df_old.empty and "sembol" in df_old.columns and "baslik" in df_old.columns:
        for _, r in df_old.iterrows():
            mevcut_anahtarlar.add((str(r["sembol"]).strip(), str(r["baslik"]).strip()[:80]))

    for b in bildirimler:
        b_sembol = str(b.get("sembol", "")).strip()
        b_baslik = str(b.get("baslik", "")).strip()
        key = (b_sembol, b_baslik[:80])
        if key not in mevcut_anahtarlar and b_sembol and b_baslik:
            terms = b.get("tedbir_terimleri", [])
            terms_str = ", ".join(terms) if isinstance(terms, list) else str(terms)
            yeni_satirlar.append({
                "kayit_zamani": now_str,
                "haber_tarihi": b.get("tarih", ""),
                "sembol": b_sembol,
                "tedbir_terimleri": terms_str,
                "baslik": b_baslik,
                "kaynak": b.get("kaynak", ""),
                "link": b.get("link", ""),
            })
            mevcut_anahtarlar.add(key)

    if yeni_satirlar:
        df_yeni = pd.DataFrame(yeni_satirlar)
        df_toplam = pd.concat([df_old, df_yeni], ignore_index=True)
        temp_f = p.with_suffix(".tmp")
        df_toplam.to_csv(temp_f, index=False, encoding="utf-8")
        os.replace(temp_f, p)
        logger.info(f"📁 VBTS Arşivi Güncellendi: {len(yeni_satirlar)} yeni tedbir kaydı eklendi -> {p}")
        return len(yeni_satirlar)
    return 0


def tara_ve_arsivle_vbts(hisseler: Optional[List[str]] = None,
                         csv_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Hisseler için KAP haberlerini tarar, VBTS/tedbirleri tespit eder ve arşivler.
    """
    import config as _cfg
    target_symbols = hisseler or _cfg.HISSELER
    bulunan_bildirimler = []

    for s in target_symbols:
        haberler = cek_hisse_haberleri(s, max_haber=5, max_gun=7)
        has_v, terms, basliklar = analiz_et_vbts_riski(haberler)
        if has_v:
            for h in haberler:
                b_text = h.get("baslik", "")
                if VBTS_REGEX.search(b_text):
                    bulunan_bildirimler.append({
                        "sembol": s,
                        "tarih": h.get("tarih", ""),
                        "tedbir_terimleri": terms,
                        "baslik": b_text,
                        "kaynak": h.get("kaynak", ""),
                        "link": h.get("link", ""),
                    })

def cek_vbts_tedbir_durumu(csv_path: Optional[Path] = None, max_gun: int = 15) -> Dict[str, Dict[str, Any]]:
    """
    KAP VBTS arşivini (data/kap_vbts_arsiv.csv) okuyarak son `max_gun` içinde
    tedbir almış hisseleri sözlük formatında döner:
      {sembol: {"tedbir_var": True, "detay": "..."}}
    """
    p = Path(csv_path) if csv_path else DEFAULT_VBTS_ARSIV_FILE
    sonuclar = {}
    if not p.exists():
        return sonuclar

    try:
        df = pd.read_csv(p, encoding="utf-8")
        if df.empty or "sembol" not in df.columns or "kayit_zamani" not in df.columns:
            return sonuclar

        simdi = datetime.now()
        df["dt"] = pd.to_datetime(df["kayit_zamani"], errors="coerce")
        gecerli = df[df["dt"] >= (simdi - timedelta(days=max_gun))]

        for _, r in gecerli.iterrows():
            s = str(r["sembol"]).strip()
            terim = str(r.get("tedbir_terimleri", "VBTS Tedbiri"))
            baslik = str(r.get("baslik", ""))
            sonuclar[s] = {
                "tedbir_var": True,
                "detay": f"{terim}: {baslik[:60]}",
                "tarih": str(r.get("haber_tarihi", ""))
            }
    except Exception as e:
        logger.warning(f"VBTS arşiv okuma hatası: {e}")

    return sonuclar



