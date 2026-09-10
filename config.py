"""
config.py — BIST Sinyal Botu Ana Konfigürasyon Dosyası
=======================================================
Hassas bilgileri (token, API key) buraya YAZMA.
Bunlar .env dosyasından yüklenir.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# --- Ortam değişkenlerini yükle ---
load_dotenv()

# ============================================================
# TELEGRAM
# ============================================================
TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
ADMIN_CHAT_ID: str  = os.getenv("ADMIN_CHAT_ID", "")

# ============================================================
# PROJE YOLLARI
# ============================================================
BASE_DIR    = Path(__file__).parent
DATA_RAW    = BASE_DIR / "data" / "raw"
DATA_FEAT   = BASE_DIR / "data" / "features"
DATA_LABEL  = BASE_DIR / "data" / "labeled"
MODELS_DIR  = BASE_DIR / "models"
LOGS_DIR    = BASE_DIR / "logs"

# Dizinleri otomatik oluştur
for _d in [DATA_RAW, DATA_FEAT, DATA_LABEL, MODELS_DIR, LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ============================================================
# FOCUS UNIVERSE / STRATEGIC OVERLAY (FAZ C1)
# ============================================================
# Strategic priority tickers tracked by the systematic overlay.
# Maintained in active coverage across all regimes.
VIP_HISSELER: list[str] = [
    "TUPRS.IS",   # Tüpraş (Focus)
    "MGROS.IS",   # Migros (Focus)
    "SAHOL.IS",   # Sabancı Holding (Focus)
    "TERA.IS",    # Tera Yatırım (Focus)
    "FORTE.IS",   # Forte Bilgi (Focus)
    "TUREX.IS",   # Turex Turizm & Taşımacılık (Focus)
]


# ============================================================
# HİSSE EVRENİ (85+ HİSSE: BIST 100 + BIST TÜM / YAN TAHTA & BÜYÜME)
# ============================================================
HISSELER: list[str] = [
    # ── VIP Özel Portföy (6 Hisse) ──
    "TUPRS.IS",   # Tüpraş [VIP]
    "MGROS.IS",   # Migros [VIP]
    "SAHOL.IS",   # Sabancı Holding [VIP]
    "TERA.IS",    # Tera Yatırım [VIP]
    "FORTE.IS",   # Forte Bilgi [VIP]
    "TUREX.IS",   # Turex Taşımacılık [VIP]

    # ── BIST 30 / 50 / 100 Lokomotifler (58 Hisse) ──
    "THYAO.IS",   # Türk Hava Yolları
    "ASELS.IS",   # Aselsan
    "KCHOL.IS",   # Koç Holding
    "BIMAS.IS",   # BİM Mağazalar
    "EREGL.IS",   # Ereğli Demir Çelik
    "ISCTR.IS",   # İş Bankası C
    "AKBNK.IS",   # Akbank
    "GARAN.IS",   # Garanti BBVA
    "YKBNK.IS",   # Yapı Kredi Bankası
    "VAKBN.IS",   # Vakıfbank
    "HALKB.IS",   # Halkbank
    "TSKB.IS",    # TSKB Bankası
    "SKBNK.IS",   # Şekerbank
    "SISE.IS",    # Şişecam
    "FROTO.IS",   # Ford Otosan
    "TOASO.IS",   # Tofaş
    "DOAS.IS",    # Doğuş Otomotiv
    "OTKAR.IS",   # Otokar
    "TTRAK.IS",   # Türk Traktör
    "PGSUS.IS",   # Pegasus
    "TAVHL.IS",   # TAV Havalimanları
    "CLEBI.IS",   # Çelebi Hava Servisi
    "TCELL.IS",   # Turkcell
    "TTKOM.IS",   # Türk Telekom
    "ENKAI.IS",   # Enka İnşaat
    "ALARK.IS",   # Alarko Holding
    "PETKM.IS",   # Petkim
    "SASA.IS",    # Sasa Polyester
    "HEKTS.IS",   # Hektaş
    "GUBRF.IS",   # Gübre Fabrikaları
    "ASTOR.IS",   # Astor Enerji
    "EUPWR.IS",   # Europower Enerji
    "GESAN.IS",   # Girişim Elektrik
    "KONTR.IS",   # Kontrolmatik
    "CWENE.IS",   # CW Enerji
    "ALFAS.IS",   # Alfa Solar Enerji
    "ARCLK.IS",   # Arçelik
    "VESTL.IS",   # Vestel Elektronik
    "KRDMD.IS",   # Kardemir D
    "BRSAN.IS",   # Borusan Boru
    "KCAER.IS",   # Kocaer Çelik
    "CIMSA.IS",   # Çimsa
    "OYAKC.IS",   # Oyak Çimento
    "BSOKE.IS",   # Batısöke Çimento
    "SOKM.IS",    # Şok Marketler
    "MAVI.IS",    # Mavi Giyim
    "CCOLA.IS",   # Coca-Cola İçecek
    "AEFES.IS",   # Anadolu Efes
    "ULKER.IS",   # Ülker Bisküvi
    "TABGD.IS",   # TAB Gıda
    "BIZIM.IS",   # Bizim Toptan
    "EKGYO.IS",   # Emlak Konut GYO
    "ISGYO.IS",   # İş GYO
    "TRGYO.IS",   # Torunlar GYO
    "AGHOL.IS",   # AG Anadolu Grubu Holding
    "DOHOL.IS",   # Doğan Holding
    "TKFEN.IS",   # Tekfen Holding
    "KORDS.IS",   # Kordsa
    "SELEC.IS",   # Selçuk Ecza Deposu
    "ECILC.IS",   # Eczacıbaşı İlaç
    "TURSG.IS",   # Türkiye Sigorta
    "ANSGR.IS",   # Anadolu Sigorta
    "MTRKS.IS",   # Matriks Bilgi Dağıtım
    "LOGO.IS",    # Logo Yazılım

    # ── BIST 100 Dışı / Yan Tahta & Yüksek Büyüme (23 Hisse) ──
    "AGROT.IS",   # Agrotech Yüksek Teknoloji
    "BINHO.IS",   # 1000 Yatırımlar Holding
    "REEDR.IS",   # Reeder Teknoloji
    "SDTTR.IS",   # SDT Uzay ve Savunma
    "MIATK.IS",   # Mia Teknoloji
    "KBORU.IS",   # Kuzey Boru
    "CVKMD.IS",   # CVK Madencilik
    "GOKNR.IS",   # Göknur Gıda
    "SURGY.IS",   # Sur Tatil Evleri GYO
    "MOGAN.IS",   # Mogan Enerji
    "ALVES.IS",   # Alves Kablo
    "PASEU.IS",   # Pasifik Eurasia Lojistik
    "INVES.IS",   # Investco Holding
    "PLTUR.IS",   # Platform Turizm
    "ONCSM.IS",   # Oncosem Onkolojik Sistemler
    "CANTE.IS",   # Çan2 Termik
    "ODAS.IS",    # Odaş Elektrik
    "GENTS.IS",   # Gentaş
]

# Düşük likidite / yüksek slippage uyarısı olan yan tahta hisseleri
DUSUK_LIKIDITE: list[str] = [
    "TERA.IS", "FORTE.IS", "TUREX.IS", "AGROT.IS", "BINHO.IS",
    "REEDR.IS", "SDTTR.IS", "KBORU.IS", "SURGY.IS", "ALVES.IS", "PLTUR.IS", "ONCSM.IS"
]

# ============================================================
# HİSSE — SEKTÖR EŞLEMESİ (85+ Hisse Kapsamı)
# ============================================================
HISSE_SEKTOR: dict[str, str] = {
    # ── Bankacılık — XBANK.IS ──
    "ISCTR.IS": "XBANK.IS",
    "AKBNK.IS": "XBANK.IS",
    "GARAN.IS": "XBANK.IS",
    "YKBNK.IS": "XBANK.IS",
    "VAKBN.IS": "XBANK.IS",
    "HALKB.IS": "XBANK.IS",
    "TSKB.IS":  "XBANK.IS",
    "SKBNK.IS": "XBANK.IS",
    "SAHOL.IS": "XBANK.IS",

    # ── Perakende & Gıda — MINI_PERAKENDE / XUSIN.IS ──
    "BIMAS.IS": "MINI_PERAKENDE",
    "MGROS.IS": "MINI_PERAKENDE",
    "SOKM.IS":  "MINI_PERAKENDE",
    "BIZIM.IS": "MINI_PERAKENDE",
    "CCOLA.IS": "XUSIN.IS",
    "AEFES.IS": "XUSIN.IS",
    "ULKER.IS": "XUSIN.IS",
    "TABGD.IS": "XUSIN.IS",
    "GOKNR.IS": "XUSIN.IS",

    # ── Sanayi, Savunma, Havacılık, Enerji, Otomotiv, Maden — XUSIN.IS ──
    "THYAO.IS": "XUSIN.IS",
    "PGSUS.IS": "XUSIN.IS",
    "TAVHL.IS": "XUSIN.IS",
    "CLEBI.IS": "XUSIN.IS",
    "TUPRS.IS": "XUSIN.IS",
    "DOAS.IS":  "XUSIN.IS",
    "TOASO.IS": "XUSIN.IS",
    "FROTO.IS": "XUSIN.IS",
    "OTKAR.IS": "XUSIN.IS",
    "TTRAK.IS": "XUSIN.IS",
    "EREGL.IS": "XUSIN.IS",
    "KRDMD.IS": "XUSIN.IS",
    "BRSAN.IS": "XUSIN.IS",
    "KCAER.IS": "XUSIN.IS",
    "ARCLK.IS": "XUSIN.IS",
    "VESTL.IS": "XUSIN.IS",
    "SISE.IS":  "XUSIN.IS",
    "ASELS.IS": "XUSIN.IS",
    "SDTTR.IS": "XUSIN.IS",
    "KCHOL.IS": "XUSIN.IS",
    "AGHOL.IS": "XUSIN.IS",
    "DOHOL.IS": "XUSIN.IS",
    "TKFEN.IS": "XUSIN.IS",
    "ALARK.IS": "XUSIN.IS",
    "ENKAI.IS": "XUSIN.IS",
    "PETKM.IS": "XUSIN.IS",
    "SASA.IS":  "XUSIN.IS",
    "HEKTS.IS": "XUSIN.IS",
    "GUBRF.IS": "XUSIN.IS",
    "ASTOR.IS": "XUSIN.IS",
    "EUPWR.IS": "XUSIN.IS",
    "GESAN.IS": "XUSIN.IS",
    "KONTR.IS": "XUSIN.IS",
    "CWENE.IS": "XUSIN.IS",
    "ALFAS.IS": "XUSIN.IS",
    "CANTE.IS": "XUSIN.IS",
    "ODAS.IS":  "XUSIN.IS",
    "MOGAN.IS": "XUSIN.IS",
    "CIMSA.IS": "XUSIN.IS",
    "OYAKC.IS": "XUSIN.IS",
    "BSOKE.IS": "XUSIN.IS",
    "MAVI.IS":  "XUSIN.IS",
    "KORDS.IS": "XUSIN.IS",
    "GENTS.IS": "XUSIN.IS",
    "KBORU.IS": "XUSIN.IS",
    "ALVES.IS": "XUSIN.IS",
    "KOZAL.IS": "XUSIN.IS",
    "KOZAA.IS": "XUSIN.IS",
    "IPEKE.IS": "XUSIN.IS",
    "CVKMD.IS": "XUSIN.IS",
    "SELEC.IS": "XUSIN.IS",
    "ECILC.IS": "XUSIN.IS",
    "ONCSM.IS": "XUSIN.IS",

    # ── Teknoloji, Hizmet & Lojistik — XU100.IS ──
    "TERA.IS":  "XU100.IS",
    "FORTE.IS": "XU100.IS",
    "TUREX.IS": "XU100.IS",
    "AGROT.IS": "XU100.IS",
    "BINHO.IS": "XU100.IS",
    "REEDR.IS": "XU100.IS",
    "MIATK.IS": "XU100.IS",
    "MTRKS.IS": "XU100.IS",
    "LOGO.IS":  "XU100.IS",
    "PASEU.IS": "XU100.IS",
    "PLTUR.IS": "XU100.IS",
    "INVES.IS": "XU100.IS",

    # ── GYO & Sigorta & İletişim — XU100.IS ──
    "EKGYO.IS": "XU100.IS",
    "ISGYO.IS": "XU100.IS",
    "TRGYO.IS": "XU100.IS",
    "SURGY.IS": "XU100.IS",
    "TCELL.IS": "XU100.IS",
    "TTKOM.IS": "XU100.IS",
    "TURSG.IS": "XU100.IS",
    "ANSGR.IS": "XU100.IS",
}

# ============================================================
# HİSSE — GRANÜLER SEKTÖR EŞLEMESİ V2 (V3.1 İyileştirmesi)
# ============================================================
# Mevcut HISSE_SEKTOR (4 kaba kategori) yerine 11 gerçekçi sektör grubu.
# Post-model sektör kısıt filtresi bu eşlemeyi kullanır.
# Mevcut HISSE_SEKTOR sözlüğü geriye dönük uyum için korunmuştur.
#
# Sektör kısıt kuralı:
#   - BANKA → K=10 portföyde maksimum 2 hisse
#   - SİGORTA → maksimum 2 hisse
#   - GYO → maksimum 2 hisse
#   - Diğer tüm sektörler → maksimum 3 hisse
# ============================================================
HISSE_SEKTOR_V2: dict[str, str] = {
    # ── BANKA (Mevduat Bankası) ──
    "ISCTR.IS": "BANKA",
    "AKBNK.IS": "BANKA",
    "GARAN.IS": "BANKA",
    "YKBNK.IS": "BANKA",
    "VAKBN.IS": "BANKA",
    "HALKB.IS": "BANKA",
    "TSKB.IS":  "BANKA",
    "SKBNK.IS": "BANKA",

    # ── HOLDİNG (Finansal Holding) ──
    "SAHOL.IS": "HOLDING",
    "KCHOL.IS": "HOLDING",
    "AGHOL.IS": "HOLDING",
    "DOHOL.IS": "HOLDING",
    "ALARK.IS": "HOLDING",
    "TKFEN.IS": "HOLDING",
    "ENKAI.IS": "HOLDING",
    "INVES.IS": "HOLDING",
    "BINHO.IS": "HOLDING",

    # ── ENERJİ (Elektrik Üretim ve Dağıtım) ──
    "EUPWR.IS": "ENERJI",
    "CWENE.IS": "ENERJI",
    "ALFAS.IS": "ENERJI",
    "ASTOR.IS": "ENERJI",
    "GESAN.IS": "ENERJI",
    "KONTR.IS": "ENERJI",
    "CANTE.IS": "ENERJI",
    "ODAS.IS":  "ENERJI",
    "MOGAN.IS": "ENERJI",

    # ── OTOMOTİV & TAŞIMACI ──
    "FROTO.IS": "OTOMOTIV",
    "TOASO.IS": "OTOMOTIV",
    "DOAS.IS":  "OTOMOTIV",
    "OTKAR.IS": "OTOMOTIV",
    "TTRAK.IS": "OTOMOTIV",
    "KORDS.IS": "OTOMOTIV",

    # ── HAVAYOLU & LOJİSTİK ──
    "THYAO.IS": "HAVAYOLU_LOJISTIK",
    "PGSUS.IS": "HAVAYOLU_LOJISTIK",
    "TAVHL.IS": "HAVAYOLU_LOJISTIK",
    "CLEBI.IS": "HAVAYOLU_LOJISTIK",
    "PASEU.IS": "HAVAYOLU_LOJISTIK",
    "PLTUR.IS": "HAVAYOLU_LOJISTIK",
    "TUREX.IS": "HAVAYOLU_LOJISTIK",

    # ── PETROKİMYA & RAFINERI ──
    "TUPRS.IS": "PETROKIMYA",
    "PETKM.IS": "PETROKIMYA",
    "SASA.IS":  "PETROKIMYA",
    "HEKTS.IS": "PETROKIMYA",
    "GUBRF.IS": "PETROKIMYA",
    "KBORU.IS": "PETROKIMYA",
    "ALVES.IS": "PETROKIMYA",

    # ── METAL & MADENCİLİK ──
    "EREGL.IS": "METAL_MADEN",
    "KRDMD.IS": "METAL_MADEN",
    "BRSAN.IS": "METAL_MADEN",
    "KCAER.IS": "METAL_MADEN",
    "CVKMD.IS": "METAL_MADEN",

    # ── TEKNOLOJİ & YAZILIM ──
    "LOGO.IS":  "TEKNOLOJI",
    "MTRKS.IS": "TEKNOLOJI",
    "MIATK.IS": "TEKNOLOJI",
    "FORTE.IS": "TEKNOLOJI",
    "TERA.IS":  "TEKNOLOJI",
    "AGROT.IS": "TEKNOLOJI",
    "REEDR.IS": "TEKNOLOJI",
    "SDTTR.IS": "TEKNOLOJI",

    # ── PERAKENDEÇELİK & TÜKETİM ──
    "BIMAS.IS": "PERAKENDE_TUKETIM",
    "MGROS.IS": "PERAKENDE_TUKETIM",
    "SOKM.IS":  "PERAKENDE_TUKETIM",
    "BIZIM.IS": "PERAKENDE_TUKETIM",
    "MAVI.IS":  "PERAKENDE_TUKETIM",
    "CCOLA.IS": "PERAKENDE_TUKETIM",
    "AEFES.IS": "PERAKENDE_TUKETIM",
    "ULKER.IS": "PERAKENDE_TUKETIM",
    "TABGD.IS": "PERAKENDE_TUKETIM",
    "GOKNR.IS": "PERAKENDE_TUKETIM",

    # ── SAĞLIK & İLAÇ ──
    "SELEC.IS": "SAGLIK_ILAC",
    "ECILC.IS": "SAGLIK_ILAC",
    "ONCSM.IS": "SAGLIK_ILAC",

    # ── GAYRİMENKUL (GYO) ──
    "EKGYO.IS": "GYO",
    "ISGYO.IS": "GYO",
    "TRGYO.IS": "GYO",
    "SURGY.IS": "GYO",

    # ── SİGORTA & TELEKOMÜNİKASYON ──
    "TURSG.IS": "SIGORTA_TELEKOM",
    "ANSGR.IS": "SIGORTA_TELEKOM",
    "TCELL.IS": "SIGORTA_TELEKOM",
    "TTKOM.IS": "SIGORTA_TELEKOM",

    # ── CAM & ÇİMENTO & İNŞAAT ──
    "SISE.IS":  "CAM_CIMENTO",
    "CIMSA.IS": "CAM_CIMENTO",
    "OYAKC.IS": "CAM_CIMENTO",
    "BSOKE.IS": "CAM_CIMENTO",
    "GENTS.IS": "CAM_CIMENTO",

    # ── SAVUNMA & UZAY ──
    "ASELS.IS": "SAVUNMA",

    # ── KARMA / DİĞER ──
    "ARCLK.IS": "DIGER",
    "VESTL.IS": "DIGER",
}

# V3.1: Sektör başına maksimum portföy pozisyonu (post-model filtre kuralı)
# Bu değer config değil — ranking_pipeline.py select_top_k_v2() tarafından kullanılır
MAX_SEKTOR_POZISYON_V2: dict[str, int] = {
    "BANKA":              2,   # Sistemik risk → en sıkı kısıt
    "SIGORTA_TELEKOM":    2,   # Finansal sistemle yüksek korelasyon
    "GYO":                2,   # Faiz duyarlılığı yüksek
    "HOLDING":            3,
    "ENERJI":             3,
    "OTOMOTIV":           3,
    "HAVAYOLU_LOJISTIK":  3,
    "PETROKIMYA":         3,
    "METAL_MADEN":        3,
    "TEKNOLOJI":          3,
    "PERAKENDE_TUKETIM":  3,
    "SAGLIK_ILAC":        3,
    "CAM_CIMENTO":        3,
    "SAVUNMA":            3,
    "DIGER":              2,
}
MAX_SEKTOR_VARSAYILAN_V2: int = 3  # Eşleme bulunamazsa varsayılan

# V3.1: Likidite filtresi eşiği (60 günlük ortalama günlük TL hacim)
LIKIDITE_MIN_TL_HACIM_V2: float = 20_000_000.0  # 20M TL minimum

# ============================================================
# V3.2: KÂR GERİ VERME VE BİLANÇO TAZELİK İZLEME PARAMETRELERİ
# ============================================================
PEAK_DRAWDOWN_UYARI_ESIGI: float = 0.20  # Bireysel hisse zirvesinden %20+ düşüşte dikkat uyarısı
BILANCO_ESKILIK_ESIGI_GUN: int = 100     # 100 günden eski finansal veri için tazelik uyarısı (⚠️)


# ============================================================
# ENDEKS VERİLERİ
# ============================================================
ENDEKS_SEMBOLLERI: list[str] = [
    "XU100.IS",   # BIST 100 — piyasa rejimi filtresi için
    "XBANK.IS",   # Bankacılık — tarihsel veri mevcut
    "XUSIN.IS",   # Sanayi — tarihsel veri mevcut
]

MAKRO_SEMBOLLERI: list[str] = [
    "TRY=X",      # USD/TRY
    "^VIX",       # CBOE Volatility Index — küresel risk göstergesi
]

# ============================================================
# VERİ ARALIKLARI
# ============================================================
VERI_BASLANGIC = "2018-01-01"   # Eğitim veri başlangıcı
VERI_BITIS     = None            # None = bugüne kadar

# ============================================================
# MODEL PARAMETRELERİ (FAZ B1: Multiclass Etiketleme)
# ============================================================
ATR_PERIYOT    = 14      # ATR hesaplama periyodu
K1             = 1.5     # Üst bariyer: +k1 × ATR (kâr hedefi)
K2             = 1.0     # Alt bariyer: -k2 × ATR (zarar durdurma)
ZAMAN_BARIYERI = 5       # Gün olarak maksimum elde tutma süresi

MULTICLASS_LABEL = True  # True: 3 sınıf (0: SL/Timeout, 1: Yavaş TP, 2: Hızlı TP)
TP_HIZLI_HORIZON = 3     # İlk 3 günde TP olursa 'Hızlı TP' sayılır
TIMEOUT_LABEL    = 0     # Zaman aşımı = 0 (kayıp)

# ============================================================
# SINYAL EŞİKLERİ (FAZ B1 & C: Multiclass Kalibre Değerler)
# ============================================================
# Multiclass modda P(kazanma)=P(1)+P(2) taban %31.4 oranına göre kalibre edilmiştir.
SINYAL_ESIGI_NORMAL   = 0.45   # Normal rejimde P(kazanma) >= %45 (En üst %20 dilim)
SINYAL_ESIGI_DUSUS    = 0.50   # Güçlü Düşüş rejiminde ekstra katı %50 eşik
SINYAL_ESIGI_HIZLI_TP = 0.30   # P(label=2) için Hızlı TP minimum eşiği
CONSENSUS_STD_MAX     = 0.10   # Ensemble modeller arası maksimum sapma (fikir birliği)

# ============================================================
# F1: MODEL GÜVEN SERT BLOĞU (Aşama 1 — Yeni)
# ============================================================
# model_olasiligi bu değerin altındaysa hiçbir koşulda AL/GÜÇLÜ_AL üretilmez.
# Backtest ile optimize edilebilir — şimdilik kaynak %31.4 taban oranının üstünde tutuldu.
MODEL_GUVEN_MIN_BLOK  = 0.40   # < 0.40 → kesinlikle AL üretme (hard stop)
MODEL_GUVEN_KUCUK_POZ = 0.45   # 0.40-0.45 arası → sadece küçük pozisyon (İZLE)

# ============================================================
# A2: KÂR BÜYÜMESİ ETİKET EŞİKLERİ (Aşama 1 — Yeni)
# ============================================================
# Üç boyutlu karar kuralında kullanılan eşikler.
KAR_BUYUME_GUCLU_ARTIS_ESIK  = 0.10   # YoY/QoQ > %10 → pozitif katkı
KAR_BUYUME_ZAYIF_DARALMA_ESIK = -0.05  # YoY < -%5 → negatif katkı
KAR_BUYUME_QOQ_ESIK          = 0.15   # QoQ > %15 → ivme pozitif
KAR_BUYUME_QOQ_NEGATIF_ESIK  = -0.10  # QoQ < -%10 → ivme negatif
KAR_BUYUME_GUCLU_ESIK        = 1.1    # Ağırlıklı skor >= 1.1 → Güçlü Artış
# NOT: yfinance aynı kaynaktan YoY+QoQ verince kaynaklar_ayni=True → QoQ ağırlığı 0.25'e iner.
# Bu durumda maks. skor 1.0+0.25=1.25. Eşik 1.1 ile güvenli ayrım sağlanır.
KAR_BUYUME_DARALMA_ESIK      = -1.0   # Ağırlıklı skor <= -1.0 → Daralma

# ============================================================
# H1: SEKTÖRE ÖZEL DEĞERLEME ÇARPANLARI (Aşama 3 — Yeni)
# ============================================================
# Bankacılık hisseleri için F/K yerine PD/DD + ROE birleşik iskonto skoru kullanılır.
# Nedeni: Banka karları kredi karşılıklarına aşırı duyarlı → F/K yanıltıcı.
# Diğer sektörler için F/K primary, PD/DD secondary çarpan olarak kalır.

# Bankacılık Hissesi Grupları (Bu sektörde H1 aktif)
BANKA_SEKTORU = "XBANK.IS"

# PD/DD (Price-to-Book) Eşikleri
PDDD_COKUCUZ        = 0.80   # PD/DD < 0.80 → Tarihi ucuzluk (+2 puan bonus)
PDDD_UCUZ           = 1.10   # PD/DD < 1.10 → İskontolu  (+1 puan bonus)
PDDD_PAHALI         = 2.00   # PD/DD > 2.00 → Pahalı     (-1 puan ceza)
PDDD_COKPAHALI      = 3.00   # PD/DD > 3.00 → Aşırı değerli (-2 puan ceza)

# Varsayılan Sektör Medyan PD/DD (BIST Tarihsel Ortalamaları)
VARSAYILAN_SEKTOR_PDDD: dict = {
    "XBANK.IS":       1.20,   # Bankacılık: 2020-2024 ortalama PD/DD
    "MINI_PERAKENDE": 4.50,   # Perakende (Migros, BİM yüksek PD/DD)
    "XUSIN.IS":       1.80,   # Sanayi genel
    "XU100.IS":       2.00,   # BIST 100 genel medyan
}

# ROE (Return on Equity) Eşikleri — Banka için kritik
ROE_GUCLU           = 0.18   # ROE > %18 → Güçlü kârlılık (+1 puan)
ROE_KABUL           = 0.12   # ROE > %12 → Kabul edilebilir (0 puan)
ROE_ZAYIF           = 0.08   # ROE < %8  → Zayıf kârlılık  (-1 puan)

# ROA (Return on Assets) Eşikleri — Banka için ikincil gösterge
ROA_SAGLIKLI        = 0.015  # ROA > %1.5 → Sağlıklı banka
ROA_ZAYIF           = 0.008  # ROA < %0.8 → Zayıf aktif getirisi

# Ağırlıklandırma (Banka için Bileşik İskonto Skoru)
H1_PDDD_AGIRLIK     = 0.55   # PD/DD ağırlığı (dominant)
H1_ROE_AGIRLIK      = 0.30   # ROE ağırlığı
H1_ROA_AGIRLIK      = 0.15   # ROA ağırlığı (ikincil)

# ============================================================
# G1: EMSAL GRUBU (PEER GROUP) PARAMETRELERİ (Aşama 3 — Yeni)
# ============================================================
# Emsal grubu: Benzer sektör + benzer büyüme profili + benzer değerleme bandındaki hisseler.
# Hissenin skor yüksekliği emsal grubuna göre normalize edilir.
G1_GRUP_MIN_UYELIK  = 2      # Emsal grubu en az kaç üyeli olmalı
G1_BUYUME_BANT      = 0.15   # Emsal için kâr büyümesi benzerlik bandı (±%15)
G1_DEGER_BANT       = 0.30   # Emsal için F/K veya PD/DD benzerlik bandı (±%30)
G1_GUCLU_USTU_ESIK  = 0.70   # Emsal grubunun üst %30'una giriyorsa → "Emsal Lider"

# ============================================================
# F2: RİSK/ÖDÜL HESAPLAMA KURALLARI (Aşama 1 — Yeni)
# ============================================================
# R:R kapanış fiyatı yerine gerçek planlanan giriş fiyatından hesaplanır.
# Giriş fiyatı: kapanış × (1 - LIMIT_GIRIS_ ISKONTO) — limit emir ile %X altından giriş
LIMIT_GIRIS_ISKONTO  = 0.003   # Kapanış fiyatından %0.3 altında limit emir
MIN_RISK_ODUL_ORANI  = 1.5     # Minimum R:R — bu altında sinyal üretme

# ============================================================
# B2: MOMENTUM TÜKENMESİ EŞİKLERİ (Aşama 1 — Yeni)
# ============================================================
MOM_MA20_SAPMA_KRITIK    = 0.10   # Fiyat MA20'nin %10+ üstünde → kritik (35 puan)
MOM_MA20_SAPMA_UYARI     = 0.06   # Fiyat MA20'nin %6+ üstünde → uyarı (20 puan)
MOM_RET_5G_HIZLI         = 0.08   # Son 5 günde %8+ getiri → hızlı yükseliş (25 puan)
MOM_RET_5G_ORTA          = 0.05   # Son 5 günde %5+ getiri → orta (15 puan)
MOM_RET_10G_ASIRI        = 0.12   # Son 10 günde %12+ getiri → aşırı uzama (25 puan)
MOM_RET_10G_YUKSEK       = 0.08   # Son 10 günde %8+ getiri → yüksek (15 puan)
MOM_RSI_ASIRI_ALIM       = 72     # RSI bu değerin üstünde → aşırı alım (+15 puan)
MOM_TUKENMESI_BLOK       = 60     # Toplam skor >= 60 → sinyal üretme
MOM_TUKENMESI_UYARI      = 35     # Toplam skor 35-59 → islem_skoru -10

# ============================================================
# D1: GÜÇLENDİRİLMİŞ PİYASA REJİMİ EŞİKLERİ (Aşama 2 — Yeni)
# ============================================================
REJIM_PANIK_ATR_ZSCORE          = 2.0   # ATR Z-score > 2.0 → Panik / Kriz
REJIM_GUCLU_YUKSELIS_MA_ESIK    = 0.03  # Fiyat MA50'nin %3+ üstünde
REJIM_GUCLU_YUKSELIS_RET20_ESIK = 0.03  # 20 günlük getiri %3+ pozitif
REJIM_YUKSELIS_MA_ESIK          = 0.01  # Fiyat MA50'nin %1+ üstünde
REJIM_GUCLU_DUSUS_MA_ESIK       = -0.03 # Fiyat MA50'nin %3+ altında
REJIM_DUSUS_MA_ESIK             = -0.01 # Fiyat MA50'nin %1+ altında

# ============================================================
# A4: DEĞERLEME — MOMENTUM ÇELİŞKİSİ EŞİKLERİ (Aşama 2 — Yeni)
# ============================================================
CELISKI_FK_ISKANTO_ESIK = -0.15  # Sektör medyanına göre en az %15 iskontolu (ucuz)
CELISKI_MA20_SAPMA_ESIK = 0.08   # Fiyat MA20'nin %8+ üstünde (aşırı uzamış)
CELISKI_RET10G_ESIK     = 0.10   # Son 10 günde %10+ yükselmiş

# ============================================================
# E3: SİNYAL LOGLAMA AYARLARI (Aşama 2 — Yeni)
# ============================================================
SIGNAL_LOG_DB_PATH  = BASE_DIR / "data" / "signals_log.db"
SIGNAL_LOG_CSV_PATH = BASE_DIR / "data" / "signals_log.csv"

# ============================================================
# PORTFÖY VE RİSK KURALLARI (FAZ 5 & C3: Korelasyon Kalkanı)
# ============================================================
MAX_RISK_PER_ISLEM       = 0.005  # İşlem başına maksimum portföy riski (%0.5)
MAX_POZISYON_AGIRLIGI    = 0.20   # Tek pozisyon maksimum nominal ağırlığı (%20)
MAX_ESSZAMANLI_POZISYON  = 5      # Aynı anda maksimum açık pozisyon sayısı
MAX_SEKTOR_POZISYON      = 2      # Aynı sektörden maksimum pozisyon sayısı
PORTFOLIO_HEAT_MAX       = 0.03   # Toplam açık risk (%3 portföy)
KORELASYON_ESIGI         = 0.70   # Bu değerin üstündeki korelasyon = Portföy Kalkanı tarafından İPTAL

# ============================================================
# ENTRY / EXIT KURALLARI (Faz 5)
# ============================================================
GAP_ESIK_MUTLAK          = 0.04   # %4 üstü gap → işlemi atla
GAP_ESIK_ATR_ORANI       = 0.75   # ATR'nin %75'i üstü gap → işlemi atla
LIMIT_EMIR_TOLERANS      = 0.005  # Limit emir: kapanış × (1 + 0.005) maksimum

# ============================================================
# MALIYET VARSAYIMLARI (Faz 5)
# ============================================================
KOMISYON_ORANI: float    = float(os.getenv("KOMISYON_ORANI", "0.001"))

# Hisse bazlı slippage (likit vs düşük likidite)
SLIPPAGE: dict[str, float] = {
    "default": 0.002,   # %0.2 — likit hisseler
    "dusuk":   0.004,   # %0.4 — TERA, FORTE, TUREX gibi düşük hacimli
}

# ============================================================
# ZAMANLAMA (Faz 7)
# ============================================================
# BIST 18:10'da kapanır; settlement gecikmesi nedeniyle 18:45'te çalıştır
CALISMA_SAATI   = 18
CALISMA_DAKIKA  = 45

# ============================================================
# VIX MAKRO FİLTRESİ (Faz 2.4.1)
# ============================================================
VIX_ARTIS_UYARI_ESIK    = 0.10   # %10 artış → 10 puan skor cezası
VIX_PANIK_ESIK          = 0.20   # %20 artış → 20 puan skor cezası / sinyal durdur
VIX_DEGISIM_PERIYOT     = 3      # Son kaç günlük değişime bakılacak

# ============================================================
# PSI DRIFT TESTİ (Faz 5.5)
# ============================================================
PSI_UYARI_ESIGI          = 0.20   # PSI > 0.20 → orta düzey rejim kayması
PSI_KRITIK_ESIGI         = 0.50   # PSI > 0.50 → ciddi rejim değişimi, yeniden eğitim
PSI_MIN_ORNEK            = 120    # Minimum örneklem sayısı

# ============================================================
# PAPER TRADING BİTİŞ KRİTERLERİ (Faz 6)
# ============================================================
PAPER_MIN_SINYAL         = 30     # Minimum tamamlanmış sinyal sayısı
PAPER_MAX_WINRATE_SAPMA  = 0.15   # Backtest ile paper trading win rate farkı
PAPER_MAX_BRIER_SAPMA    = 0.05   # Brier Score maksimum sapma
PAPER_MAX_DRIFT_UYARI    = 2      # Son 4 haftada maksimum PSI uyarı sayısı
PAPER_MIN_KAP_BASARI     = 0.90   # KAP filtresi minimum başarılı sorgu oranı
PAPER_MIN_STABIL_GUN     = 30     # Kesintisiz çalışma (gün)

# ============================================================
# SPLIT / TEMETTÜ MASKELEME (Faz 5.0.3)
# ============================================================
MASKELEME_GUN            = 5      # Kurumsal aksiyon sonrası sinyal üretme süresi (iş günü)
MASKELEME_BAK_GERIYE     = 7      # Kaç gün geriye bakılacak (takvim günü)

# ============================================================
# CMF (CHAIKIN MONEY FLOW) KURUMSAL PARA AKIŞI PARAMETRELERİ
# ============================================================
CMF_PERIYOT              = 20     # CMF hesaplama periyodu (günlük)
CMF_GUCLU_GIRIS_ESIK     = 0.08   # CMF >= +0.08 -> Güçlü kurumsal akümülasyon (+5 puan bonus)
CMF_CIKIS_BLOK_ESIK      = -0.05  # CMF < -0.05 -> Para çıkışı / boğa tuzağı (-30 puan ceza / blokaj)

# ============================================================
# TTM VOLATİLİTE SIKIŞMASI (BOLLINGER INSIDE KELTNER) PARAMETRELERİ
# ============================================================
BB_PERIYOT               = 20     # Bollinger periyodu
BB_STD                   = 2.0    # Bollinger standart sapma katsayısı
KC_PERIYOT               = 20     # Keltner Kanal periyodu
KC_ATR_MULT              = 1.5    # Keltner ATR çarpanı
SQUEEZE_FIRE_BONUS       = 5.0    # Sıkışmadan yukarı patlama anı bonusu (+5 puan)

# ============================================================
# KADEMELİ KÂR ALMA & BAŞA BAŞ (BREAKEVEN) STOP PARAMETRELERİ
# ============================================================
KADEMELI_TP1_ORAN        = 0.50   # TP1'de realize edilecek pozisyon oranı (%50)
BREAKEVEN_TOLERANS       = 0.001  # Giriş stopuna çekilirken ufak komisyon payı

# ============================================================
# SIĞ TAHTA & LİKİDİTE FİLTRESİ (CRO RİSK KURALI)
# ============================================================
MIN_GUNLUK_TL_HACIM_ESIK = 25_000_000.0  # Günlük 25M TL altı hacim = Sığ Tahta / Fiktif Hacim Riski

