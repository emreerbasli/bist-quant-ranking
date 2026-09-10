"""
features/veri_cek.py — FAZ 1: Veri Toplama ve Temizleme
=========================================================
Plan referansı: FAZ 1 (bist_sinyal_botu_proje_plani_v2.md)

Çekilen veriler:
  - Hisse OHLCV (HISSELER listesi)
  - XU100 + sektörel endeksler (ENDEKS_SEMBOLLERI)
  - USD/TRY + VIX (MAKRO_SEMBOLLERI)

Kalite kontrolleri:
  - Eksik günler düşürülür (forward-fill YOK)
  - Split/temettü tarihleri kaydedilir (maskeleme için)
  - Sıfır hacimli günler işaretlenir
  - Tüm veriler aynı tarih index'ine hizalanır

Kullanım:
  python features/veri_cek.py                 # tüm veriyi çek
  python features/veri_cek.py --test          # sadece 3 hisse ile hızlı test
  python features/veri_cek.py --ticker THYAO  # tek hisse
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf
from loguru import logger

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

# Hacim verisi olmayan semboller (FX, endeks) — hacim=0 uyarısı üretme
HACIM_YOK_SEMBOLLER = {"TRY=X", "^VIX", "XU100.IS", "XBANK.IS", "XUSIN.IS"}

# ─── Log ayarı ───────────────────────────────────────────────────────────────
logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add(cfg.LOGS_DIR / "veri_cek_{time:YYYY-MM-DD}.log",
           rotation="1 day", retention="30 days", level="DEBUG", encoding="utf-8")


# ─── YARDIMCI FONKSİYONLAR ───────────────────────────────────────────────────

def _yfinance_indir(
    sembol: str,
    baslangic: str,
    bitis: Optional[str] = None,
    yeniden_deneme: int = 3,
    bekleme: float = 2.0,
) -> Optional[pd.DataFrame]:
    """
    yfinance ile OHLCV çeker. Başarısız olursa 'yeniden_deneme' kadar tekrar dener.
    Sütun isimlerini küçük harfe çevirir.
    """
    for deneme in range(1, yeniden_deneme + 1):
        try:
            ticker = yf.Ticker(sembol)
            df = ticker.history(
                start=baslangic,
                end=bitis,
                auto_adjust=True,   # split/temettü düzeltmesi otomatik
                actions=True,       # Dividends + Stock Splits sütunlarını getir
            )
            if df.empty:
                logger.warning(f"{sembol}: Veri boş döndü (deneme {deneme}/{yeniden_deneme})")
                time.sleep(bekleme * deneme)
                continue

            # Sütun isimlerini normalize et
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]

            # Timezone bilgisini düşür (tüm seriler UTC-naive olsun)
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            # Son bar kapanış kontrolü (Yahoo Finance Cuma/Hafta sonu NaN düzeltmesi)
            if not df.empty and pd.isna(df["close"].iloc[-1]):
                fast = getattr(ticker, "fast_info", None)
                if fast:
                    lp = getattr(fast, "last_price", None)
                    if lp and not pd.isna(lp):
                        df.iloc[-1, df.columns.get_loc("close")] = float(lp)
                        if pd.isna(df["open"].iloc[-1]):
                            df.iloc[-1, df.columns.get_loc("open")] = getattr(fast, "open", lp) or lp
                        if pd.isna(df["high"].iloc[-1]):
                            df.iloc[-1, df.columns.get_loc("high")] = getattr(fast, "day_high", lp) or lp
                        if pd.isna(df["low"].iloc[-1]):
                            df.iloc[-1, df.columns.get_loc("low")] = getattr(fast, "day_low", lp) or lp
                        logger.info(f"{sembol}: Son gün NaN kapanışı fast_info ile onarıldı (Kapanış: {lp:.2f} TL)")

            logger.debug(f"{sembol}: {len(df)} gün çekildi ({df.index[0].date()} → {df.index[-1].date()})")
            return df

        except Exception as e:
            logger.warning(f"{sembol}: Hata — {e} (deneme {deneme}/{yeniden_deneme})")
            time.sleep(bekleme * deneme)

    logger.error(f"{sembol}: {yeniden_deneme} denemede veri çekilemedi, atlanıyor.")
    return None


def _kalite_kontrolu(df: pd.DataFrame, sembol: str) -> dict:
    """
    Temel veri kalite kontrolleri.
    Sorunları loglar, problemli günleri işaretler ama silmez
    (silme kararı hizalama sonrasına bırakılır).

    Returns:
        dict: kalite raporu
    """
    hacim_kontrol = sembol not in HACIM_YOK_SEMBOLLER
    vix_benzeri = sembol in {"^VIX"}  # Endekslerde %20+ değişim normal

    rapor = {
        "sembol": sembol,
        "toplam_gun": len(df),
        "tarih_araligi": f"{df.index[0].date()} → {df.index[-1].date()}",
        "eksik_deger": int(df[["open", "high", "low", "close", "volume"]].isnull().sum().sum()),
        "sifir_hacim_gun": int((df["volume"] == 0).sum()) if hacim_kontrol else 0,
        "negatif_fiyat_gun": int((df["close"] <= 0).sum()),
        "buyuk_hareket_gun": int((df["close"].pct_change().abs() > 0.20).sum()),
        "split_tarihler": [],
        "temettü_tarihler": [],
        "uyari": [],
    }

    # Split tarihleri
    if "stock_splits" in df.columns:
        splits = df[df["stock_splits"] > 0]["stock_splits"]
        rapor["split_tarihler"] = [str(d.date()) for d in splits.index]
        if splits.any():
            logger.warning(f"{sembol}: {len(splits)} split tespit edildi → {rapor['split_tarihler']}")
            rapor["uyari"].append(f"Split tespit edildi: {rapor['split_tarihler']}")

    # Temettü tarihleri
    if "dividends" in df.columns:
        divs = df[df["dividends"] > 0]["dividends"]
        rapor["temettü_tarihler"] = [str(d.date()) for d in divs.index]
        if divs.any():
            logger.info(f"{sembol}: {len(divs)} temettü kaydı")

    # Sıfır hacim uyarısı (FX ve endeksler için atla — hacim gelmez)
    if hacim_kontrol and rapor["sifir_hacim_gun"] > 0:
        rapor["uyari"].append(f"Sıfır hacimli gün: {rapor['sifir_hacim_gun']}")
        logger.warning(f"{sembol}: {rapor['sifir_hacim_gun']} gün hacim=0 (işlem askıya alma?)")

    # Aşırı fiyat hareketi (VIX gibi endekslerde %20+ normal — atla)
    if not vix_benzeri and rapor["buyuk_hareket_gun"] > 0:
        rapor["uyari"].append(f"%20+ günlük değişim sayısı: {rapor['buyuk_hareket_gun']}")
        logger.warning(f"{sembol}: {rapor['buyuk_hareket_gun']} gün %20+ değişim — split veya hatalı veri?")

    # Negatif fiyat
    if rapor["negatif_fiyat_gun"] > 0:
        rapor["uyari"].append(f"Geçersiz fiyat (<=0): {rapor['negatif_fiyat_gun']} gün")
        logger.error(f"{sembol}: {rapor['negatif_fiyat_gun']} gün geçersiz kapanış fiyatı!")

    return rapor


def _temizle(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sadece OHLCV + Dividends + Stock Splits sütunlarını tut.
    Eksik OHLCV satırlarını düşür (forward-fill YAPMA — plan FAZ 1).
    """
    ohlcv_sutunlar = ["open", "high", "low", "close", "volume"]
    ekstra_sutunlar = ["dividends", "stock_splits"]

    mevcut = [c for c in ohlcv_sutunlar + ekstra_sutunlar if c in df.columns]
    df = df[mevcut].copy()

    # Eksik OHLCV satırları: düşür (forward-fill yok)
    once = len(df)
    df = df.dropna(subset=ohlcv_sutunlar)
    sonra = len(df)
    if once != sonra:
        logger.debug(f"  {once - sonra} eksik OHLCV satırı düşürüldü")

    # Dividends / Stock Splits yoksa 0 ile doldur (NaN değil)
    for col in ekstra_sutunlar:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    return df


def _kaydet(df: pd.DataFrame, dosya_yolu: Path) -> None:
    """Parquet olarak kaydeder."""
    dosya_yolu.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dosya_yolu, engine="pyarrow", compression="snappy")
    boyut_kb = dosya_yolu.stat().st_size / 1024
    logger.info(f"  → Kaydedildi: {dosya_yolu.name} ({boyut_kb:.1f} KB, {len(df)} satır)")


# ─── ANA FONKSİYONLAR ────────────────────────────────────────────────────────
import concurrent.futures

def _tek_sembol_cek_ve_kaydet(
    sembol: str,
    baslangic: str,
    bitis: Optional[str],
) -> tuple:
    """Tek bir sembolün verisini çeker, temizler ve kaydeder (Thread-safe worker)."""
    try:
        df = _yfinance_indir(sembol, baslangic, bitis)
        if df is None or df.empty:
            return sembol, {"hata": "Veri çekilemedi"}, False

        rapor = _kalite_kontrolu(df, sembol)
        df = _temizle(df)

        dosya_adi = sembol.replace('^', 'IDX_').replace('.', '_').replace('=', '_')
        dosya = cfg.DATA_RAW / f"{dosya_adi}.parquet"
        _kaydet(df, dosya)
        return sembol, rapor, True
    except Exception as e:
        logger.error(f"{sembol} indirme hatası: {e}")
        return sembol, {"hata": str(e)}, False


def hisse_verisi_cek(
    semboller: list[str],
    baslangic: str = cfg.VERI_BASLANGIC,
    bitis: Optional[str] = cfg.VERI_BITIS,
    max_workers: int = 12,
) -> dict:
    """
    Verilen semboller için ThreadPoolExecutor ile paralel OHLCV çeker.

    Returns:
        dict: her sembol için kalite raporu
    """
    raporlar = {}
    basarili = 0
    basarisiz = 0

    logger.info(f"{'─'*60}")
    logger.info(f"Hisse verisi paralel çekiliyor: {len(semboller)} sembol ({max_workers} thread) — {baslangic} → {bitis or 'bugün'}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_tek_sembol_cek_ve_kaydet, s, baslangic, bitis): s
            for s in semboller
        }
        for future in concurrent.futures.as_completed(futures):
            sembol, rapor, basarili_mi = future.result()
            raporlar[sembol] = rapor
            if basarili_mi:
                basarili += 1
            else:
                basarisiz += 1

    logger.info(f"{'─'*60}")
    logger.info(f"Hisse verisi tamamlandı: {basarili} başarılı, {basarisiz} başarısız")
    return raporlar


def endeks_verisi_cek(
    baslangic: str = cfg.VERI_BASLANGIC,
    bitis: Optional[str] = cfg.VERI_BITIS,
    max_workers: int = 6,
) -> dict:
    """
    XU100, sektörel endeksler ve makro sembolleri (USDTRY, VIX) paralel çeker.
    """
    tum_semboller = cfg.ENDEKS_SEMBOLLERI + cfg.MAKRO_SEMBOLLERI
    raporlar = {}

    logger.info(f"{'─'*60}")
    logger.info(f"Endeks/makro verisi paralel çekiliyor: {len(tum_semboller)} sembol")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_tek_sembol_cek_ve_kaydet, s, baslangic, bitis): s
            for s in tum_semboller
        }
        for future in concurrent.futures.as_completed(futures):
            sembol, rapor, _ = future.result()
            raporlar[sembol] = rapor

    return raporlar


def tarih_hizalama_kontrolu(
    hisseler: list[str],
    referans_sembol: str = "XU100.IS",
) -> pd.DataFrame:
    """
    Tüm hisselerin ve endeksin aynı tarih index'ine oturduğunu doğrular.

    Plan FAZ 1: "Her hisse + XU100 + USDTRY verisi aynı tarih index'ine oturmalı.
    Hizalama hatası tüm modeli baştan bozar."

    Returns:
        DataFrame: her sembol için veri kapsama yüzdesi (referansa göre)
    """
    logger.info(f"{'─'*60}")
    logger.info("Tarih hizalama kontrolü yapılıyor...")

    # Referans endeksi yükle
    ref_dosya = cfg.DATA_RAW / f"{referans_sembol.replace('.', '_')}.parquet"
    if not ref_dosya.exists():
        logger.error(f"Referans dosyası bulunamadı: {ref_dosya}")
        return pd.DataFrame()

    ref_df = pd.read_parquet(ref_dosya)
    ref_index = ref_df.index
    logger.info(f"Referans: {referans_sembol} — {len(ref_index)} işlem günü")

    hizalama_raporu = []

    tum_semboller = hisseler + cfg.MAKRO_SEMBOLLERI
    for sembol in tum_semboller:
        dosya_adi = sembol.replace('^', 'IDX_').replace('.', '_').replace('=', '_')
        dosya = cfg.DATA_RAW / f"{dosya_adi}.parquet"

        if not dosya.exists():
            hizalama_raporu.append({
                "sembol": sembol,
                "gun_sayisi": 0,
                "referans_gun": len(ref_index),
                "kapsama_yuzde": 0.0,
                "eksik_gunler": len(ref_index),
                "durum": "DOSYA YOK",
            })
            continue

        df = pd.read_parquet(dosya)
        ortak = ref_index.intersection(df.index)
        eksik = len(ref_index) - len(ortak)
        kapsama = len(ortak) / len(ref_index) * 100

        durum = "OK" if kapsama >= 95 else ("UYARI" if kapsama >= 80 else "HATA")

        hizalama_raporu.append({
            "sembol": sembol,
            "gun_sayisi": len(df),
            "referans_gun": len(ref_index),
            "kapsama_yuzde": round(kapsama, 1),
            "eksik_gunler": eksik,
            "durum": durum,
        })

        if durum != "OK":
            logger.warning(f"  {sembol}: Kapsama %{kapsama:.1f} — {eksik} eksik gün [{durum}]")
        else:
            logger.debug(f"  {sembol}: OK (%{kapsama:.1f})")

    rapor_df = pd.DataFrame(hizalama_raporu).sort_values("kapsama_yuzde")
    logger.info(f"Hizalama kontrolü tamamlandı.")
    return rapor_df


def kalite_raporu_yazdir(raporlar: dict) -> None:
    """Kalite raporunu konsola ve log'a yazar."""
    logger.info(f"\n{'═'*60}")
    logger.info("VERİ KALİTE RAPORU")
    logger.info(f"{'═'*60}")

    uyarilar = []
    for sembol, rapor in raporlar.items():
        if "hata" in rapor:
            logger.error(f"{sembol:15s} ❌ {rapor['hata']}")
            continue

        durum = "✅" if not rapor["uyari"] else "⚠️"
        logger.info(
            f"{sembol:15s} {durum}  {rapor['tarih_araligi']}  "
            f"{rapor['toplam_gun']} gün"
        )
        for u in rapor["uyari"]:
            logger.warning(f"  └─ {u}")
            uyarilar.append(f"{sembol}: {u}")

    logger.info(f"{'─'*60}")
    logger.info(f"Toplam uyarı: {len(uyarilar)}")
    if uyarilar:
        logger.warning("Uyarıların bir kısmı split/temettü kaynaklı olabilir — manuel kontrol önerilir.")


def veri_guncelle(
    hisseler: Optional[list[str]] = None,
    baslangic: str = cfg.VERI_BASLANGIC,
    bitis: Optional[str] = cfg.VERI_BITIS,
    sadece_endeks: bool = False,
) -> dict:
    """
    Pipeline'dan çağrılan ana fonksiyon.
    Hem hisseleri hem endeks/makroyu çeker ve hizalama kontrolü yapar.
    """
    if hisseler is None:
        hisseler = cfg.HISSELER

    tum_raporlar = {}

    if not sadece_endeks:
        hisse_raporlar = hisse_verisi_cek(hisseler, baslangic, bitis)
        tum_raporlar.update(hisse_raporlar)

    endeks_raporlar = endeks_verisi_cek(baslangic, bitis)
    tum_raporlar.update(endeks_raporlar)

    # Hizalama kontrolü
    hizalama_df = tarih_hizalama_kontrolu(hisseler)
    if not hizalama_df.empty:
        sorunlu = hizalama_df[hizalama_df["durum"] != "OK"]
        if not sorunlu.empty:
            logger.warning(f"\nHizalama sorunlu semboller:\n{sorunlu.to_string(index=False)}")

    kalite_raporu_yazdir(tum_raporlar)
    return tum_raporlar


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FAZ 1 — BIST Veri Çekme")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Hızlı test: sadece 3 hisse + endeksler",
    )
    parser.add_argument(
        "--ticker",
        type=str,
        help="Tek hisse çek (örn: THYAO veya THYAO.IS)",
    )
    parser.add_argument(
        "--sadece-endeks",
        action="store_true",
        help="Sadece endeks ve makro veriyi çek",
    )
    parser.add_argument(
        "--baslangic",
        type=str,
        default=cfg.VERI_BASLANGIC,
        help=f"Başlangıç tarihi (varsayılan: {cfg.VERI_BASLANGIC})",
    )
    args = parser.parse_args()

    # Sembol listesi belirle
    if args.ticker:
        sembol = args.ticker if args.ticker.endswith(".IS") else f"{args.ticker}.IS"
        hisseler = [sembol]
    elif args.test:
        hisseler = ["THYAO.IS", "TUPRS.IS", "ISCTR.IS"]
        logger.info("TEST MODU: 3 hisse + endeksler")
    else:
        hisseler = cfg.HISSELER

    veri_guncelle(
        hisseler=hisseler,
        baslangic=args.baslangic,
        sadece_endeks=args.sadece_endeks,
    )
