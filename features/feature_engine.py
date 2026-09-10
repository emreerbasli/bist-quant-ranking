"""
features/feature_engine.py — FAZ 2: Feature Engineering Motoru
===============================================================
Plan referansı: FAZ 2 (bist_sinyal_botu_proje_plani_v2.md)

Özellik Grupları:
  1. Teknik İndikatörler (pandas-ta):
     - Momentum: RSI(14), Stokastik (K/D), MACD (line, signal, hist)
     - Volatilite: ATR(14), Bollinger Band Genişliği (bb_width), %B (bb_pband)
     - Hacim: OBV, OBV 5g değişim, MFI(14), Hacim / MA20 oranı (vol_ratio_20)
  2. BIST'e Özgü Feature'lar:
     - Göreceli Güç (XU100): 5g ve 20g fark getirileri
     - Sektörel Göreceli Güç: 5g ve 20g fark getirileri (HISSE_SEKTOR eşlemesi)
     - Hacim Şoku: binary (volume > MA20 * 3)
     - USDTRY: 5g ve 20g değişim yüzdeleri
     - VIX: 3g getiri ve seviye
     - Zaman: Haftanın günü, ay başı/sonu 3 gün bayrağı
  3. Bilanço / KAP Etkinlik Takvimi:
     - gun_fark_bilanco, bilanco_penceresi
  4. Piyasa Rejimi:
     - xu100_rejim, xu100_ma50_farki, xu100_atr_zscore

SIFIR VERİ SIZINTISI (ZERO LEAKAGE) GARANTİSİ:
  - Tüm indikatörler ve farklar yalnızca geçmiş t anına kadarki kapanmış barlardan hesaplanır.
  - Normalizasyon/ölçekleme bu aşamada yapılmaz (Faz 4 model eğitiminde CV fold'larında fit edilir).
"""

import sys
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np
import pandas_ta as ta
from loguru import logger

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg
from features.piyasa_rejimi import hesapla_xu100_rejim_serisi, hesapla_vix_filtre_serisi
from features.events import hesapla_etkinlik_featurelari, yukle_etkinlik_tarihleri
from features.temel_analiz import getir_hisse_temel_featurelari

# ─── Log ayarı ───────────────────────────────────────────────────────────────
logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add(cfg.LOGS_DIR / "feature_engine_{time:YYYY-MM-DD}.log",
           rotation="1 day", retention="30 days", level="DEBUG", encoding="utf-8")


def _yukle_raw_parquet(sembol: str) -> Optional[pd.DataFrame]:
    """data/raw/ altındaki parquet dosyasını yükler."""
    dosya_adi = sembol.replace('^', 'IDX_').replace('.', '_').replace('=', '_')
    dosya = cfg.DATA_RAW / f"{dosya_adi}.parquet"
    if not dosya.exists():
        logger.error(f"Ham veri dosyası bulunamadı: {dosya}")
        return None
    df = pd.read_parquet(dosya)
    return df.sort_index()


def hesapla_teknik_indikatorler(df: pd.DataFrame) -> pd.DataFrame:
    """
    OHLCV verisinden teknik indikatörleri hesaplar.
    Zero-leakage: Sadece o ana kadarki barlar.
    """
    out = df.copy()
    
    # 1. Momentum: RSI(14)
    out["rsi_14"] = ta.rsi(out["close"], length=14)
    
    # 2. Momentum: Stokastik (14, 3, 3)
    stoch = ta.stoch(out["high"], out["low"], out["close"], k=14, d=3, smooth_k=3)
    if stoch is not None and not stoch.empty:
        out["stoch_k"] = stoch.iloc[:, 0]
        out["stoch_d"] = stoch.iloc[:, 1]
    else:
        out["stoch_k"] = np.nan
        out["stoch_d"] = np.nan
        
    # 3. Momentum: MACD (12, 26, 9)
    macd = ta.macd(out["close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        out["macd"] = macd.iloc[:, 0]
        out["macd_hist"] = macd.iloc[:, 1]
        out["macd_signal"] = macd.iloc[:, 2]
    else:
        out["macd"] = np.nan
        out["macd_hist"] = np.nan
        out["macd_signal"] = np.nan
        
    # 4. Volatilite: ATR(14) ve Normalize ATR (yüzde)
    out["atr_14"] = ta.atr(out["high"], out["low"], out["close"], length=14)
    out["natr_14"] = (out["atr_14"] / out["close"]) * 100.0
    
    # 5. Volatilite: Bollinger Bantları (20, 2)
    bb = ta.bbands(out["close"], length=20, std=2)
    if bb is not None and not bb.empty:
        # Sütunlar: BBL (alt), BBM (orta), BBU (üst), BBB (genişlik), BBP (%b)
        bbl = bb.iloc[:, 0]
        bbm = bb.iloc[:, 1]
        bbu = bb.iloc[:, 2]
        out["bb_width"] = (bbu - bbl) / (bbm + 1e-8)
        out["bb_pband"] = (out["close"] - bbl) / (bbu - bbl + 1e-8)
    else:
        out["bb_width"] = np.nan
        out["bb_pband"] = np.nan
        
    # 6. Hacim: OBV & OBV 5g Değişim
    out["obv"] = ta.obv(out["close"], out["volume"])
    out["obv_ret_5d"] = out["obv"].pct_change(5)
    
    # 7. Hacim: MFI(14)
    out["mfi_14"] = ta.mfi(out["high"], out["low"], out["close"], out["volume"], length=14)
    
    # 8. Hacim: 20 Günlük Hacim Ortalamasına Oran
    vol_ma20 = out["volume"].rolling(window=20, min_periods=5).mean()
    out["vol_ratio_20"] = out["volume"] / (vol_ma20 + 1e-8)
    
    # 9. Hacim Şoku (Spike): binary
    out["hacim_soku"] = (out["volume"] > (vol_ma20 * 3.0)).astype(int)
    
    # 10. Fiyat Değişimleri (Getiriler)
    out["ret_1d"]  = out["close"].pct_change(1)
    out["ret_5d"]  = out["close"].pct_change(5)
    out["ret_10d"] = out["close"].pct_change(10)
    out["ret_20d"] = out["close"].pct_change(20)
    out["ret_60d"] = out["close"].pct_change(60)

    # 10b. Mom_12-1: Jegadeesh & Titman (1993) Momentum Faktörü ─────────────
    # Akademik literatürde gelişen piyasalarda en güçlü kanıtlanmış faktör.
    # Son 252 işlem günü (≈12 ay) getirisi eksi son 21 günü (≈1 ay) getirisi.
    # 1 aylık kısa vadeli ortalamaya dönüş gürültüsünü filtreler.
    # Faz B.5 kaba skor ve Faz C temel feature setinde kullanılır.
    ret_252 = out["close"].pct_change(252)   # 12 aylık
    ret_21  = out["close"].pct_change(21)    # 1 aylık (kısa vade gürültüsü)
    out["mom_12_1"] = ret_252 - ret_21       # Net momentum (look-ahead yok)
    # Clip: aşırı uç değerleri sınırla (-3.0 ile +3.0 arası, %300 yeterli)
    out["mom_12_1"] = out["mom_12_1"].clip(-3.0, 3.0)

    # 11. B2: 20 Günlük Hareketli Ortalama Sapması (Aşırı Uzama Göstergesi)
    ma20 = out["close"].rolling(window=20, min_periods=5).mean()
    out["ma20"] = ma20
    out["fiyat_ma20_sapma"] = (out["close"] - ma20) / (ma20 + 1e-8)

    # 12. Kurumsal Para Akışı: CMF(20) — Chaikin Money Flow
    cmf_res = ta.cmf(out["high"], out["low"], out["close"], out["volume"], length=getattr(cfg, "CMF_PERIYOT", 20))
    out["cmf_20"] = cmf_res.fillna(0.0) if cmf_res is not None else 0.0

    # 13. TTM Volatilite Sıkışması: Bollinger Bands vs Keltner Channels
    kc = ta.kc(out["high"], out["low"], out["close"], length=getattr(cfg, "KC_PERIYOT", 20), scalar=getattr(cfg, "KC_ATR_MULT", 1.5))
    if bb is not None and not bb.empty and kc is not None and not kc.empty:
        bbl = bb.iloc[:, 0]
        bbu = bb.iloc[:, 2]
        kcl = kc.iloc[:, 0]
        kcu = kc.iloc[:, 2]
        # Squeeze On: Bollinger tamamen Keltner'in içindeyse (1: Enerji Sıkışması)
        squeeze_on = ((bbl > kcl) & (bbu < kcu)).astype(int)
        out["squeeze_on"] = squeeze_on
        # Squeeze Fired: Önceki gün sıkışmada olup bugün yukarı patlayan bar
        squeeze_prev = squeeze_on.shift(1).fillna(0)
        out["squeeze_fired"] = ((squeeze_prev == 1) & (squeeze_on == 0) & (out["close"] > ma20)).astype(int)
        # Squeeze Momentum İvmesi
        mom_mid = (out["high"].rolling(20).max() + out["low"].rolling(20).min()) / 2.0
        mom_diff = out["close"] - ((mom_mid + ma20) / 2.0)
        out["squeeze_momentum"] = mom_diff.rolling(5).mean().fillna(0.0)
    else:
        out["squeeze_on"] = 0
        out["squeeze_fired"] = 0
        out["squeeze_momentum"] = 0.0

    return out


# ─── B2: MOMENTUM TÜKENMESİ (MOMENTUM EXHAUSTION) HESAPLAYICI ────────────────
def hesapla_momentum_tukenmesi(df: pd.DataFrame) -> Dict[str, Any]:
    """
    B2: Hissenin son barda aşırı uzayıp uzamadığını 0-100 puan arasında skorlar.
    Yüksek skor (>=60) = Momentum tükenmesi / tepe riski (AL üretilmez).
    """
    if df.empty:
        return {"skor": 0, "karar": "NORMAL", "fiyat_ma20_sapma": 0.0, "ret_5d": 0.0, "ret_10d": 0.0, "rsi_14": 50.0}

    son = df.iloc[-1]
    fiyat_ma20_sapma = float(son.get("fiyat_ma20_sapma", 0.0))
    ret_5d  = float(son.get("ret_5d", 0.0))
    ret_10d = float(son.get("ret_10d", 0.0))
    rsi     = float(son.get("rsi_14", 50.0))

    puan = 0.0

    # 1. MA20 Sapması (Maksimum 35 puan)
    if fiyat_ma20_sapma > getattr(cfg, "MOM_MA20_SAPMA_KRITIK", 0.10):
        puan += 35.0
    elif fiyat_ma20_sapma > getattr(cfg, "MOM_MA20_SAPMA_UYARI", 0.06):
        puan += 20.0

    # 2. Son 5 Günlük Getiri (Maksimum 25 puan)
    if ret_5d > getattr(cfg, "MOM_RET_5G_HIZLI", 0.08):
        puan += 25.0
    elif ret_5d > getattr(cfg, "MOM_RET_5G_ORTA", 0.05):
        puan += 15.0

    # 3. Son 10 Günlük Getiri (Maksimum 25 puan)
    if ret_10d > getattr(cfg, "MOM_RET_10G_ASIRI", 0.12):
        puan += 25.0
    elif ret_10d > getattr(cfg, "MOM_RET_10G_YUKSEK", 0.08):
        puan += 15.0

    # 4. RSI Aşırı Alım (Maksimum 15 puan)
    if rsi > getattr(cfg, "MOM_RSI_ASIRI_ALIM", 72.0):
        puan += 15.0

    skor = int(min(100.0, round(puan)))

    if skor >= getattr(cfg, "MOM_TUKENMESI_BLOK", 60):
        karar = "ASIRI_UZAMIS"
        aciklama = f"⛔ Aşırı uzama ({skor}/100) — Fiyat MA20'nin %{fiyat_ma20_sapma*100:.1f} üstünde, 10g getiri %{ret_10d*100:.1f}"
    elif skor >= getattr(cfg, "MOM_TUKENMESI_UYARI", 35):
        karar = "DIKKATLI"
        aciklama = f"⚠️ Hızlı yükseliş sonrası yorulma riski ({skor}/100)"
    else:
        karar = "NORMAL"
        aciklama = "Dengeli momentum"

    return {
        "skor": skor,
        "karar": karar,
        "fiyat_ma20_sapma": round(fiyat_ma20_sapma, 4),
        "ret_5d": round(ret_5d, 4),
        "ret_10d": round(ret_10d, 4),
        "rsi_14": round(rsi, 1),
        "aciklama": aciklama,
    }


# ─── A4: DEĞERLEME — MOMENTUM ÇELİŞKİSİ ANALİZİ ─────────────────────────────
def hesapla_deger_momentum_celiskisi(
    fk_sektor_orani: float,
    momentum_tukenmesi_skoru: int,
    fiyat_ma20_sapma: float = 0.0,
    ret_10d: float = 0.0,
) -> Dict[str, Any]:
    """
    A4: 'Temel değerleme iskontolu (ucuz) ama hisse son 1-2 haftada aşırı yükselmiş'
    çelişkisini tespit eder.

    Returns:
        dict: {celiski_var: bool, risk_seviyesi: str, aciklama: str}
    """
    iskanto_esik = getattr(cfg, "CELISKI_FK_ISKANTO_ESIK", -0.15)
    ma20_esik    = getattr(cfg, "CELISKI_MA20_SAPMA_ESIK", 0.08)
    ret10_esik   = getattr(cfg, "CELISKI_RET10G_ESIK", 0.10)

    temel_ucuz = fk_sektor_orani < iskanto_esik
    teknik_asiri = (
        momentum_tukenmesi_skoru >= getattr(cfg, "MOM_TUKENMESI_UYARI", 35) or
        fiyat_ma20_sapma > ma20_esik or
        ret_10d > ret10_esik
    )

    celiski_var = bool(temel_ucuz and teknik_asiri)

    if celiski_var:
        aciklama = (
            f"⚠️ Değer-Momentum Çelişkisi: Hisse sektörüne göre %{abs(fk_sektor_orani)*100:.1f} iskontolu "
            f"ancak kısa vadede aşırı uzamış (MA20 farkı %{fiyat_ma20_sapma*100:.1f}, 10g getiri %{ret_10d*100:.1f}). "
            f"Düzeltme beklenmeli."
        )
        risk = "YUKSEK"
    else:
        aciklama = "Temel ve teknik göstergeler uyumlu."
        risk = "NORMAL"

    return {
        "celiski_var": celiski_var,
        "risk_seviyesi": risk,
        "aciklama": aciklama,
        "fk_sektor_orani": round(fk_sektor_orani, 3),
        "fiyat_ma20_sapma": round(fiyat_ma20_sapma, 4),
        "ret_10d": round(ret_10d, 4),
    }



def hesapla_bist_goreceli_featurelar(
    hisse_df: pd.DataFrame,
    sembol: str,
    xu100_df: pd.DataFrame,
    endeksler_dict: Dict[str, pd.DataFrame],
    usdtry_df: pd.DataFrame,
    vix_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    XU100, Sektör Endeksi, USD/TRY ve VIX göreceli feature'larını ekler.
    Tarih hizalaması inner-join benzeri güvenli reindex ile yapılır.
    """
    out = hisse_df.copy()
    
    # Ortak tarih index'i
    idx = out.index
    
    # 1. XU100 Getirileri ve Göreceli Güç
    xu100_close = xu100_df["close"].reindex(idx).ffill()
    xu100_ret_5d = xu100_close.pct_change(5)
    xu100_ret_20d = xu100_close.pct_change(20)
    
    out["rel_str_xu100_5d"] = out["ret_5d"] - xu100_ret_5d
    out["rel_str_xu100_20d"] = out["ret_20d"] - xu100_ret_20d
    
    # 2. Sektörel Göreceli Güç
    sektor_sembol = cfg.HISSE_SEKTOR.get(sembol, "XU100.IS")

    # ─── FAZ B2: Mini Perakende Endeksi ──────────────────────────────────────
    # BIMAS ve MGROS için XTUMT.IS Yahoo'da tarihsel veri yok.
    # Çözüm: BIMAS + MGROS kapanışlarının basit ortalamasını referans al.
    if sektor_sembol == "MINI_PERAKENDE":
        bimas_raw = _yukle_raw_parquet("BIMAS.IS")
        mgros_raw = _yukle_raw_parquet("MGROS.IS")
        if bimas_raw is not None and mgros_raw is not None:
            bimas_c = bimas_raw["close"].reindex(idx).ffill()
            mgros_c = mgros_raw["close"].reindex(idx).ffill()
            # Normalize: Her birini kendi ilk değerine böl → birleştirilebilir endeks
            bimas_norm = bimas_c / (bimas_c.iloc[0] + 1e-8)
            mgros_norm = mgros_c / (mgros_c.iloc[0] + 1e-8)
            sektor_close = (bimas_norm + mgros_norm) / 2.0
        else:
            sektor_close = xu100_close  # Fallback
    else:
        sektor_df    = endeksler_dict.get(sektor_sembol, xu100_df)
        sektor_close = sektor_df["close"].reindex(idx).ffill()
    # ─────────────────────────────────────────────────────────────────────────

    sektor_ret_5d  = sektor_close.pct_change(5)
    sektor_ret_20d = sektor_close.pct_change(20)

    
    out["rel_str_sektor_5d"] = out["ret_5d"] - sektor_ret_5d
    out["rel_str_sektor_20d"] = out["ret_20d"] - sektor_ret_20d
    out["sektor_kodu"] = sektor_sembol
    
    # 3. USD/TRY Kur Getirileri
    usd_close = usdtry_df["close"].reindex(idx).ffill()
    out["usdtry_ret_5d"] = usd_close.pct_change(5)
    out["usdtry_ret_20d"] = usd_close.pct_change(20)
    
    # 4. VIX Seviyesi ve 3 Günlük Değişimi
    vix_close = vix_df["close"].reindex(idx).ffill()
    out["vix_level"] = vix_close
    out["vix_ret_3d"] = vix_close.pct_change(3)
    
    # 5. XU100 Rejimi Metrikleri
    xu100_rejim_df = hesapla_xu100_rejim_serisi(xu100_df).reindex(idx).ffill()
    out["xu100_rejim"] = xu100_rejim_df["rejim"]
    out["xu100_fiyat_ma_farki"] = xu100_rejim_df["fiyat_ma_farki"]
    out["xu100_atr_zscore"] = xu100_rejim_df["atr_zscore"]

    # ─── YENİ A2: FX-Beta (60g Rolling Regresyon) ────────────────────────────
    # Hissenin USD/TRY hareketlerine olan duyarlılığını ölçer.
    # Yüksek (+) FX-beta: dolar artınca hisse yükseliyor (TUPRS, THYAO, ASELS)
    # Negatif / düşük FX-beta: dolar artınca hisse olumsuz etkileniyor (BIMAS, MGROS)
    hisse_ret_1d = out["close"].pct_change(1)
    usd_ret_1d   = usd_close.pct_change(1)

    def rolling_beta(hisse_r: pd.Series, kur_r: pd.Series, pencere: int = 60) -> pd.Series:
        """Basit OLS rolling regresyon β = Cov(hisse, kur) / Var(kur)"""
        cov = hisse_r.rolling(pencere, min_periods=30).cov(kur_r)
        var = kur_r.rolling(pencere, min_periods=30).var()
        return (cov / (var + 1e-10)).fillna(0.0)

    out["fx_beta_60d"] = rolling_beta(hisse_ret_1d, usd_ret_1d, pencere=60)

    # ─── YENİ A3: Volatilite Rejim Oranı ─────────────────────────────────────
    # Son 5 günün realized volatilitesi / Son 60 günün realized volatilitesi
    # Oran > 1.8 → hisse aşırı hareketli/ralli sonrası → sinyal skoru cezalanır
    ret_1d = out["close"].pct_change(1)
    vol_5d  = ret_1d.rolling(5,  min_periods=3).std()
    vol_60d = ret_1d.rolling(60, min_periods=30).std()
    out["vol_rejim_orani"] = (vol_5d / (vol_60d + 1e-10)).fillna(1.0).clip(0.0, 5.0)

    return out



def hesapla_zaman_featurelari(df: pd.DataFrame) -> pd.DataFrame:
    """Haftanın günü ve ayın başı/sonu zaman feature'ları."""
    out = df.copy()
    idx = out.index
    
    # Haftanın günü: 0=Pazartesi, 4=Cuma
    out["day_of_week"] = idx.dayofweek
    
    # Ayın ilk 3 veya son 3 iş günü mü? (Binary)
    # day <= 4 (ayın ilk günleri) veya day >= 25 (ayın son günleri)
    days = idx.day
    out["is_month_start_end"] = ((days <= 4) | (days >= 25)).astype(int)
    
    return out


def tek_hisse_feature_uret(
    sembol: str,
    xu100_df: pd.DataFrame,
    endeksler_dict: Dict[str, pd.DataFrame],
    usdtry_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    etkinlik_tarihleri: pd.DatetimeIndex,
    isinma_bariyer_bar: int = 50,
) -> Optional[pd.DataFrame]:
    """
    Belirtilen hisse için tüm feature'ları hesaplar ve döner.
    """
    raw_df = _yukle_raw_parquet(sembol)
    if raw_df is None or len(raw_df) < isinma_bariyer_bar:
        logger.warning(f"{sembol}: Yetersiz veri ({len(raw_df) if raw_df is not None else 0} bar)")
        return None
        
    # 1. Teknik İndikatörler
    df_feat = hesapla_teknik_indikatorler(raw_df)
    
    # 2. Göreceli & Makro Feature'lar
    df_feat = hesapla_bist_goreceli_featurelar(
        df_feat, sembol, xu100_df, endeksler_dict, usdtry_df, vix_df
    )
    
    # 3. Zaman Feature'ları
    df_feat = hesapla_zaman_featurelari(df_feat)
    
    # 4. Bilanço / Etkinlik Feature'ları
    df_events = hesapla_etkinlik_featurelari(df_feat.index, etkinlik_tarihleri)
    df_feat["gun_fark_bilanco"] = df_events["gun_fark_bilanco"]
    df_feat["bilanco_penceresi"] = df_events["bilanco_penceresi"]

    # 5. Temel Analiz Feature'ları (FAZ C2: F/K, Sektör İskonto Oranı, EPS Sürprizi)
    # KRİTİK CRO DÜZELTME: Tüm geçmişe bugünkü F/K'yı basmak modelde look-ahead bias (geleceği görme) yaratır!
    # Tarihsel satırlara nötr baseline değerler basılır; sadece SON BARA (canlı analiz anı) güncel temel veri atanır.
    df_feat["fk_orani"] = 8.5
    df_feat["fk_sektor_orani"] = 0.0
    df_feat["eps_surpriz_yonu"] = 0

    if not df_feat.empty:
        temel_dict = getir_hisse_temel_featurelari(sembol)
        son_idx = df_feat.index[-1]
        df_feat.loc[son_idx, "fk_orani"] = float(temel_dict.get("fk_orani", 8.5))
        df_feat.loc[son_idx, "fk_sektor_orani"] = float(temel_dict.get("fk_sektor_orani", 0.0))
        df_feat.loc[son_idx, "eps_surpriz_yonu"] = int(temel_dict.get("eps_surpriz_yonu", 0))

    # 6. Isınma (warm-up) periyodu NaN temizliği
    # İlk ~50 bar indikatör hesaplamaları (MA50, ATR Z-Score, MACD signal vb.) için NaN üretir.
    once_len = len(df_feat)
    df_feat = df_feat.dropna()
    sonra_len = len(df_feat)

    logger.debug(f"{sembol}: {once_len - sonra_len} ısınma satırı temizlendi. Kalan bar: {sonra_len}")
    return df_feat



def hesapla_tumunu(hisseler: Optional[list[str]] = None) -> dict:
    """
    Tüm hisseler için feature setlerini hesaplar ve data/features/ altına kaydeder.
    """
    if hisseler is None:
        hisseler = cfg.HISSELER

    logger.info(f"{'═'*60}")
    logger.info(f"FAZ 2: Feature Engineering Başlatıldı ({len(hisseler)} Hisse)")
    logger.info(f"{'═'*60}")

    # Ortak veri setlerini yükle
    xu100_df = _yukle_raw_parquet("XU100.IS")
    usdtry_df = _yukle_raw_parquet("TRY=X")
    vix_df = _yukle_raw_parquet("^VIX")
    
    if xu100_df is None or usdtry_df is None or vix_df is None:
        logger.error("XU100, USDTRY veya VIX ham verisi eksik! Önce Faz 1'i çalıştırın.")
        return {}

    # Sektörel endeksleri yükle
    endeksler_dict = {"XU100.IS": xu100_df}
    for endeks_sembol in cfg.ENDEKS_SEMBOLLERI:
        df_end = _yukle_raw_parquet(endeks_sembol)
        if df_end is not None:
            endeksler_dict[endeks_sembol] = df_end

    # Etkinlik takvimi
    etkinlik_tarihleri = yukle_etkinlik_tarihleri()

import concurrent.futures

def _tek_hisse_feature_isle_ve_kaydet(
    sembol: str,
    xu100_df: pd.DataFrame,
    endeksler_dict: Dict[str, pd.DataFrame],
    usdtry_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    etkinlik_tarihleri: pd.DatetimeIndex,
) -> tuple:
    """Tek bir hissenin feature setini hesaplar ve kaydeder (Thread-safe worker)."""
    try:
        df_feat = tek_hisse_feature_uret(
            sembol, xu100_df, endeksler_dict, usdtry_df, vix_df, etkinlik_tarihleri
        )
        if df_feat is None or df_feat.empty:
            logger.error(f"  ❌ {sembol} feature üretimi başarısız!")
            return sembol, {"durum": "BASARISIZ"}, False

        dosya_adi = f"{sembol.replace('.', '_')}.parquet"
        hedef_yol = cfg.DATA_FEAT / dosya_adi
        df_feat.to_parquet(hedef_yol, engine="pyarrow", compression="snappy")

        boyut_kb = hedef_yol.stat().st_size / 1024
        feature_kolon_sayisi = len(df_feat.columns)
        logger.info(f"  → Kaydedildi: {dosya_adi} ({feature_kolon_sayisi} sütun, {len(df_feat)} satır, {boyut_kb:.1f} KB)")
        
        info = {
            "durum": "BASARILI",
            "satir_sayisi": len(df_feat),
            "sutun_sayisi": feature_kolon_sayisi,
            "tarih_baslangic": str(df_feat.index[0].date()),
            "tarih_bitis": str(df_feat.index[-1].date()),
        }
        return sembol, info, True
    except Exception as e:
        logger.error(f"{sembol} feature hesaplama hatası: {e}")
        return sembol, {"durum": "BASARISIZ", "hata": str(e)}, False


def hesapla_tumunu(hisseler: Optional[list[str]] = None, max_workers: int = 8) -> dict:
    """
    Tüm hisseler için feature setlerini ThreadPoolExecutor ile paralel hesaplar ve kaydeder.
    """
    if hisseler is None:
        hisseler = cfg.HISSELER

    logger.info(f"{'═'*60}")
    logger.info(f"FAZ 2: Paralel Feature Engineering Başlatıldı ({len(hisseler)} Hisse, {max_workers} thread)")
    logger.info(f"{'═'*60}")

    # Ortak veri setlerini yükle
    xu100_df = _yukle_raw_parquet("XU100.IS")
    usdtry_df = _yukle_raw_parquet("TRY=X")
    vix_df = _yukle_raw_parquet("^VIX")
    
    if xu100_df is None or usdtry_df is None or vix_df is None:
        logger.error("XU100, USDTRY veya VIX ham verisi eksik! Önce Faz 1'i çalıştırın.")
        return {}

    # Sektörel endeksleri yükle
    endeksler_dict = {"XU100.IS": xu100_df}
    for endeks_sembol in cfg.ENDEKS_SEMBOLLERI:
        df_end = _yukle_raw_parquet(endeks_sembol)
        if df_end is not None:
            endeksler_dict[endeks_sembol] = df_end

    # Etkinlik takvimi
    etkinlik_tarihleri = yukle_etkinlik_tarihleri()

    rapor = {}
    basarili = 0
    basarisiz = 0

    cfg.DATA_FEAT.mkdir(parents=True, exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _tek_hisse_feature_isle_ve_kaydet,
                s, xu100_df, endeksler_dict, usdtry_df, vix_df, etkinlik_tarihleri
            ): s
            for s in hisseler
        }
        for future in concurrent.futures.as_completed(futures):
            sembol, info, basarili_mi = future.result()
            rapor[sembol] = info
            if basarili_mi:
                basarili += 1
            else:
                basarisiz += 1

    logger.info(f"{'═'*60}")
    logger.info(f"FAZ 2 Tamamlandı: {basarili} başarılı, {basarisiz} başarısız")
    logger.info(f"{'═'*60}")
    return rapor


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FAZ 2 — Feature Engineering")
    parser.add_argument("--ticker", type=str, help="Tek bir hisse için üret (örn: THYAO)")
    args = parser.parse_args()

    if args.ticker:
        sembol = args.ticker if args.ticker.endswith(".IS") else f"{args.ticker}.IS"
        hesapla_tumunu([sembol])
    else:
        hesapla_tumunu()
