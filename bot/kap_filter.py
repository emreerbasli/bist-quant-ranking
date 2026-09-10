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
import requests
from bs4 import BeautifulSoup
from loguru import logger

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

