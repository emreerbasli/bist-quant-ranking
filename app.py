"""
app.py — BIST V3 KANTİTATİF PORTFÖY & KARAR DESTEK TERMİNALİ
============================================================
PRODUCTION-CANDIDATE: STREAMLIT YÖNETİM VE İZLEME PANELİ (ADIM 5)
-----------------------------------------------------------------
KRİTİK KURUMSAL SINIR (İHLAL EDİLEMEZ):
Bu sistem SADECE bildirim, analiz ve karar destek çıktısı üretir — hiçbir şekilde
otomatik emir göndermez, aracı kuruma bağlanmaz veya canlı sermaye ile
al-sat kararı VERMEZ. Tüm işlemler sanal portföy (paper trading) takibidir.
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Kök dizin yolu
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Windows UTF-8 stdout desteği
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config as cfg

# ─── SAYFA YAPILANDIRMASI ──────────────────────────────────────────────────
st.set_page_config(
    page_title="BIST V3 Quant Terminal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── AESTHETICS: DARK FINTECH CURATED DESIGN SYSTEM ────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    .stApp {
        background-color: #0b0f19;
        color: #e2e8f0;
    }

    /* Glassmorphism Kartları */
    .quant-card {
        background: rgba(17, 24, 39, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 20px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(12px);
        margin-bottom: 18px;
    }

    /* KPI Metrik Kartları */
    .metric-container {
        background: linear-gradient(145deg, rgba(26, 34, 52, 0.85), rgba(15, 23, 42, 0.95));
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 16px 18px;
        text-align: left;
    }
    .metric-title {
        font-size: 0.82rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94a3b8;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 1.65rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 4px;
    }
    .metric-subtitle {
        font-size: 0.80rem;
        font-weight: 400;
        color: #64748b;
    }

    /* Pozisyon Kartı */
    .position-card {
        background: #131a29;
        border: 1px solid #1f293d;
        border-left: 5px solid #3b82f6;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 12px;
        transition: border-color 0.2s;
    }
    .position-card:hover {
        border-color: #3b82f6;
    }

    /* Kritik Sınır Banner */
    .disclaimer-banner {
        background: linear-gradient(90deg, rgba(239, 68, 68, 0.15) 0%, rgba(185, 28, 28, 0.05) 100%);
        border: 1px solid rgba(239, 68, 68, 0.35);
        border-left: 5px solid #ef4444;
        border-radius: 10px;
        padding: 12px 18px;
        margin-bottom: 22px;
    }
    .disclaimer-title {
        color: #fca5a5;
        font-weight: 600;
        font-size: 0.92rem;
        margin-bottom: 4px;
    }
    .disclaimer-text {
        color: #cbd5e1;
        font-size: 0.82rem;
        line-height: 1.4;
    }

    /* Rozetler (Badges) */
    .badge-stable {
        display: inline-block;
        padding: 4px 10px;
        background: rgba(16, 185, 129, 0.18);
        border: 1px solid #10b981;
        color: #34d399;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .badge-alert {
        display: inline-block;
        padding: 4px 10px;
        background: rgba(239, 68, 68, 0.18);
        border: 1px solid #ef4444;
        color: #f87171;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .badge-lock {
        background: rgba(245, 158, 11, 0.18);
        border: 1px solid #f59e0b;
        color: #fbbf24;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-free {
        background: rgba(16, 185, 129, 0.18);
        border: 1px solid #10b981;
        color: #34d399;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ─── VERİ YÜKLEME VE CACHE ─────────────────────────────────────────────────
def load_portfolio_data(file_path: Union[Path, str]) -> Dict[str, Any]:
    """Portföy JSON verisini dayanıklı (retry ile) yükler."""
    file_path = Path(file_path)
    if file_path.exists():
        for attempt in range(3):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, PermissionError):
                time.sleep(0.05)
            except Exception as e:
                st.error(f"Portföy verisi okunamadı ({file_path.name}): {e}")
                break
    return {
        "last_check_date": None,
        "equity": 1.0,
        "peak_equity": 1.0,
        "drawdown": 0.0,
        "dd_kesici_aktif": False,
        "last_xu100_price": None,
        "positions": {}
    }


def load_trading_logs(file_path: Union[Path, str]) -> pd.DataFrame:
    """İşlem günlüğü CSV dosyasını dayanıklı (retry ile) yükler."""
    file_path = Path(file_path)
    if file_path.exists():
        for attempt in range(3):
            try:
                df = pd.read_csv(file_path, encoding="utf-8")
                return df
            except PermissionError:
                time.sleep(0.05)
            except Exception:
                break
    return pd.DataFrame()


@st.cache_data(ttl=600)
def load_latest_ranking(file_path_str: str) -> Optional[pd.DataFrame]:
    """Önbellekteki 88 hisse sıralama tablosunu yükler (WinError 32 kilit korumalı)."""
    p = Path(file_path_str)
    if p.exists():
        for attempt in range(5):
            try:
                df = pd.read_parquet(p)
                if df is not None and not df.empty:
                    return df
            except Exception:
                if attempt < 4:
                    time.sleep(0.05)
    return None


@st.cache_data(ttl=600)
def load_latest_selection(file_path_str: str) -> Optional[pd.DataFrame]:
    """Yalnızca likidite ve sektör filtresinden geçmiş adayları yükler (WinError 32 kilit korumalı)."""
    p = Path(file_path_str)
    if p.exists():
        for attempt in range(5):
            try:
                df = pd.read_parquet(p)
                if df is not None and not df.empty:
                    return df
            except Exception:
                if attempt < 4:
                    time.sleep(0.05)
    return None


@st.cache_data(ttl=300)
def load_market_alignment() -> Dict[str, Any]:
    """Paneldeki verilerin aynı PIT işlem gününe ait olup olmadığını gösterir."""
    try:
        from models.v4_ranking.data_loader_v4 import yukle_veriler, check_market_date_alignment
        fiyat_dict, seri_xu100, _, _, _, _ = yukle_veriler()
        return check_market_date_alignment(fiyat_dict, seri_xu100)
    except Exception as exc:
        return {"aligned": False, "market_date": None, "stale_symbols": [], "missing_symbols": [], "reason": f"Veri hizası doğrulanamadı: {exc}"}


@st.cache_data(ttl=300)
def load_latest_drift_report(file_path_str: str) -> Optional[Dict[str, Any]]:
    p = Path(file_path_str)
    if p.exists():
        for attempt in range(5):
            try:
                with p.open("r", encoding="utf-8") as source:
                    data = json.load(source)
                    if data:
                        return data
            except Exception:
                if attempt < 4:
                    time.sleep(0.05)
    return None


@st.cache_data(ttl=60)
def load_v3_vs_v4_comparison() -> Optional[Dict[str, Any]]:
    p = ROOT_DIR / "reports" / "v3_vs_v4_comparison.json"
    if p.exists():
        for attempt in range(5):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data:
                        return data
            except Exception:
                if attempt < 4:
                    time.sleep(0.05)
    return None


@st.cache_data(ttl=300)
def load_stock_history(sembol: str) -> Optional[pd.DataFrame]:
    """Seçilen hissenin OHLCV mum verisini diskten yükler."""
    clean_sym = sembol.replace("^", "IDX_").replace(".", "_").replace("=", "_")
    p_file = cfg.DATA_RAW / f"{clean_sym}.parquet"
    if p_file.exists():
        try:
            df = pd.read_parquet(p_file)
            return df.sort_index()
        except Exception:
            pass
    return None


def compute_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Teknik analiz göstergelerini (SMA, Bollinger, RSI, MACD, Hacim SMA) tam geçmiş üzerinden hesaplar."""
    if df is None or df.empty or "close" not in df.columns:
        return df
    
    df_res = df.copy()
    c = df_res["close"]

    # Hareketli Ortalamalar (Trend)
    df_res["sma_20"] = c.rolling(20, min_periods=1).mean()
    df_res["sma_50"] = c.rolling(50, min_periods=1).mean()
    df_res["sma_200"] = c.rolling(200, min_periods=1).mean()

    # Bollinger Bantları (Volatilite, 20 gün, 2 standart sapma)
    std_20 = c.rolling(20, min_periods=5).std().fillna(0)
    df_res["bb_upper"] = df_res["sma_20"] + (std_20 * 2.0)
    df_res["bb_lower"] = df_res["sma_20"] - (std_20 * 2.0)

    # RSI (14 Günlük Momentum)
    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14, min_periods=5).mean()
    avg_loss = loss.rolling(14, min_periods=5).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df_res["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

    # MACD (12, 26, 9)
    ema_12 = c.ewm(span=12, adjust=False).mean()
    ema_26 = c.ewm(span=26, adjust=False).mean()
    df_res["macd"] = ema_12 - ema_26
    df_res["macd_signal"] = df_res["macd"].ewm(span=9, adjust=False).mean()
    df_res["macd_hist"] = df_res["macd"] - df_res["macd_signal"]

    # Hacim Ortalaması
    if "volume" in df_res.columns:
        df_res["vol_sma_20"] = df_res["volume"].rolling(20, min_periods=1).mean()

    return df_res


@st.cache_data(ttl=600)
def load_fundamentals(sembol: str) -> Optional[pd.DataFrame]:
    """Seçilen hissenin Point-in-Time (PIT) çeyreklik bilanço kayıtlarını yükler."""
    clean_sym = sembol.replace("^", "IDX_").replace(".", "_").replace("=", "_")
    f_path = cfg.BASE_DIR / "data" / "fundamentals" / f"{clean_sym}.parquet"
    if f_path.exists():
        try:
            return pd.read_parquet(f_path)
        except Exception:
            pass
    return None


@st.cache_data(ttl=600)
def load_benchmark_xu100() -> Optional[pd.Series]:
    """BIST 100 endeks kapanış serisini yükler."""
    xu_path = cfg.DATA_RAW / "XU100_IS.parquet"
    if not xu_path.exists():
        xu_path = cfg.DATA_RAW / "IDX_XU100_IS.parquet"
    if xu_path.exists():
        try:
            df = pd.read_parquet(xu_path)
            if "close" in df.columns:
                return df["close"].sort_index()
        except Exception:
            pass
    return None


def compute_relative_metrics(df_st: pd.DataFrame, xu_c: Optional[pd.Series]) -> Dict[str, Any]:
    """BIST 100'e göre 1A/3A Alfa, 60g Beta ve 52 Hafta Zirve/Dip metriklerini hesaplar."""
    res = {
        "alfa_1m": None, "alfa_3m": None, "beta_60d": None,
        "high_52w": None, "low_52w": None, "dist_52w_high": None, "dist_52w_low": None
    }
    if df_st is None or df_st.empty or "close" not in df_st.columns:
        return res
    
    st_close = df_st["close"]
    sub_250 = df_st.tail(250)
    high_52 = float(sub_250["high"].max()) if "high" in sub_250.columns else float(st_close.tail(250).max())
    low_52 = float(sub_250["low"].min()) if "low" in sub_250.columns else float(st_close.tail(250).min())
    last_p = float(st_close.iloc[-1])
    res["high_52w"] = high_52
    res["low_52w"] = low_52
    res["dist_52w_high"] = ((last_p - high_52) / high_52 * 100.0) if high_52 > 0 else 0.0
    res["dist_52w_low"] = ((last_p - low_52) / low_52 * 100.0) if low_52 > 0 else 0.0

    if xu_c is not None and not xu_c.empty:
        common_idx = df_st.index.intersection(xu_c.index)
        if len(common_idx) >= 22:
            sc = st_close.loc[common_idx]
            xc = xu_c.loc[common_idx]
            r_st_1m = ((sc.iloc[-1] / sc.iloc[-22]) - 1.0) * 100.0 if sc.iloc[-22] > 0 else 0.0
            r_xu_1m = ((xc.iloc[-1] / xc.iloc[-22]) - 1.0) * 100.0 if xc.iloc[-22] > 0 else 0.0
            res["alfa_1m"] = r_st_1m - r_xu_1m
            if len(common_idx) >= 64:
                r_st_3m = ((sc.iloc[-1] / sc.iloc[-64]) - 1.0) * 100.0 if sc.iloc[-64] > 0 else 0.0
                r_xu_3m = ((xc.iloc[-1] / xc.iloc[-64]) - 1.0) * 100.0 if xc.iloc[-64] > 0 else 0.0
                res["alfa_3m"] = r_st_3m - r_xu_3m
            ret_st = sc.tail(60).pct_change().dropna()
            ret_xu = xc.tail(60).pct_change().dropna()
            if len(ret_st) >= 20 and len(ret_xu) >= 20:
                cov = np.cov(ret_st, ret_xu)[0, 1]
                var_x = np.var(ret_xu)
                if var_x > 1e-9:
                    res["beta_60d"] = float(cov / var_x)
    return res


def trigger_paper_trader_check():
    """Arka planda tek seferlik zorunlu V3 kontrolünü tetikler."""
    try:
        from run_paper_trader import periyodik_gorev_calistir
        with st.spinner("V3 Model ve piyasa verileri taranıyor..."):
            basarili = periyodik_gorev_calistir(force=False)
        if basarili:
            st.cache_data.clear()
            st.success("✅ V3 kontrolü tamamlandı.")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("⚠️ V3 kontrolü beklemede: 14 gün, piyasa açıklığı veya süreç kilidi koşulları sağlanmadı.")
    except Exception as e:
        st.error(f"❌ V3 Çalıştırma hatası: {str(e)}")


def trigger_paper_trader_check_v4():
    """Arka planda tek seferlik zorunlu V4 kontrolünü tetikler."""
    try:
        from run_paper_trader_v4 import periyodik_gorev_calistir_v4
        with st.spinner("V4 Model ve piyasa verileri taranıyor, Faz 0 filtreleri denetleniyor..."):
            basarili = periyodik_gorev_calistir_v4(force=False)
        if basarili:
            st.cache_data.clear()
            st.success("✅ V4 rebalance kontrolü tamamlandı.")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("⚠️ V4 kontrolü beklemede: 14 gün, piyasa açıklığı veya süreç kilidi koşulları henüz dolmadı.")
    except Exception as e:
        st.error(f"❌ V4 Çalıştırma hatası: {str(e)}")


def trigger_comparison_refresh():
    """Çift model karşılaştırma raporunu yeniler."""
    try:
        from models.v4_ranking.v3_v4_comparator import generate_v3_vs_v4_comparison
        with st.spinner("Çift model karşılaştırma raporu güncelleniyor..."):
            generate_v3_vs_v4_comparison()
        st.cache_data.clear()
        st.success("✅ Çift model karşılaştırma raporu yenilendi.")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"❌ Karşılaştırma güncelleme hatası: {e}")


# ─── KULLANICI CÜZDAN YARDIMCI FONKSİYONLARI ─────────────────────────────────
WALLET_FILE = ROOT_DIR / "data" / "user_real_portfolio.json"


def wallet_load() -> dict:
    """Kullanıcı gerçek portföy JSON'unu güvenli şekilde okur. V4 motorundan bağımsız."""
    if WALLET_FILE.exists():
        for _ in range(3):
            try:
                with open(WALLET_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, PermissionError):
                time.sleep(0.05)
    return {"schema_version": "1.0", "son_guncelleme": None, "holdings": []}


def wallet_save(data: dict) -> bool:
    """Atomik yazma (tmp → os.replace) — V4 portföyüyle aynı güvenlik standardı."""
    tmp_path = WALLET_FILE.with_suffix(".tmp")
    try:
        data["son_guncelleme"] = datetime.now().isoformat(timespec="seconds")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, WALLET_FILE)
        return True
    except Exception as e:
        st.error(f"Cüzdan kaydedilemedi: {e}")
        return False


def wallet_compute_avg_cost(islemler: list) -> float:
    """Ağırlıklı ortalama maliyet hesaplar (çoklu alım/ortalama düşürme desteği)."""
    toplam_tutar = sum(float(i.get("lot", 0)) * float(i.get("maliyet_fiyat", 0)) for i in islemler)
    toplam_lot = sum(float(i.get("lot", 0)) for i in islemler)
    return round(toplam_tutar / toplam_lot, 4) if toplam_lot > 0 else 0.0


def wallet_get_last_price(sembol: str):
    """
    Mevcut load_stock_history() fonksiyonunu yeniden kullanır — kod tekrarı yok.
    Returns: (son_fiyat: float | None, veri_tarihi: str | None)
    """
    df = load_stock_history(sembol)
    if df is not None and not df.empty and "close" in df.columns:
        return float(df["close"].iloc[-1]), str(df.index[-1])[:10]
    return None, None


# ─── YAN PANEL (SIDEBAR) ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏛️ BIST QUANT TERMİNALİ")
    st.markdown("**Kurumsal Karar Destek & Portföy Sistemi**")
    
    st.divider()

    # 1. MODEL SEÇİCİ (V4 DEFAULT)
    secilen_model = st.selectbox(
        "🎯 Aktif Model / Görünüm",
        [
            "🏆 V4-Raw Canlı Üretim (9F / K=15)",
            "⚖️ Çift Model Karşılaştırma (V3 vs V4)",
            "🏛️ V3-Kontrol Referans (8F / K=10)"
        ],
        index=0
    )

    st.divider()

    if secilen_model != "⚖️ Çift Model Karşılaştırma (V3 vs V4)":
        sayfa = st.radio(
            "Menü Gezintisi",
            [
                "💼 Portföyüm & Pozisyon Yönetimi",
                "🏆 BIST 88 Model Sıralaması",
                "🛡️ Çok Katmanlı Drift Monitör",
                "📈 Kümülatif Getiri & Performans",
                "👤 Gerçek Portföyüm (Kişisel)",
                "🔍 Hisse Röntgeni (X-Ray)",
            ],
            index=0
        )
    else:
        sayfa = "⚖️ Çift Model Karşılaştırma"

    st.divider()

    # Model Yapılandırması ve Yolları
    if secilen_model == "🏆 V4-Raw Canlı Üretim (9F / K=15)":
        PORTFOLIO_FILE = ROOT_DIR / "models" / "v4_ranking" / "paper_portfolio_v4.json"
        LOG_FILE = ROOT_DIR / "models" / "v4_ranking" / "paper_trading_log_v4.csv"
        RANKING_CACHE_FILE = ROOT_DIR / "models" / "v4_ranking" / "latest_ranking_cache_v4.parquet"
        SELECTION_CACHE_FILE = ROOT_DIR / "models" / "v4_ranking" / "latest_selection_cache_v4.parquet"
        DRIFT_REPORT_FILE = ROOT_DIR / "models" / "v4_ranking" / "latest_drift_report_v4.json"
        SERVICE_LOG_FILE = ROOT_DIR / "logs" / "paper_trading_service_v4.log"
        target_k = 15
        model_badge = "🟢 CANLI ÜRETİM (V4-RAW)"
        st.markdown(r"""
        **Model:** `V4-Raw LGBMRanker (9 Faktör)`  
        **Öncü Motor:** `reel_eps_growth (%54.5)`  
        **Portföy:** $K=15$ Eşit Ağırlıklı (%6.67)  
        **Rotasyon:** $H=60$ İşlem Günü Sabit  
        **Kalkan:** Faz 0 Taban Veto (PASEU Kalkanı)  
        **Risk Radarı:** 5 Katmanlı Drift & Tazelik  
        **Kilit Kutu:** 2026-09-14 ($p=0.000$)
        """)
    elif secilen_model == "🏛️ V3-Kontrol Referans (8F / K=10)":
        PORTFOLIO_FILE = ROOT_DIR / "models" / "v3_ranking" / "paper_portfolio.json"
        LOG_FILE = ROOT_DIR / "models" / "v3_ranking" / "paper_trading_log.csv"
        RANKING_CACHE_FILE = ROOT_DIR / "models" / "v3_ranking" / "latest_ranking_cache.parquet"
        SELECTION_CACHE_FILE = ROOT_DIR / "models" / "v3_ranking" / "latest_selection_cache.parquet"
        DRIFT_REPORT_FILE = ROOT_DIR / "models" / "v3_ranking" / "latest_drift_report.json"
        SERVICE_LOG_FILE = ROOT_DIR / "logs" / "paper_trading_service.log"
        target_k = 10
        model_badge = "🔒 DONDURULMUŞ REFERANS (V3)"
        st.markdown(r"""
        **Model:** `V3-Kontrol LGBMRanker (8 Faktör)`  
        **Portföy:** $K=10$ Eşit Ağırlıklı (%10)  
        **Rotasyon:** $H=60$ İşlem Günü Sabit  
        **Devre Kesici:** Zirveden $\le -\%25$ DD  
        **Durum:** İzole Referans Havuzu
        """)
    else:
        PORTFOLIO_FILE = ROOT_DIR / "models" / "v4_ranking" / "paper_portfolio_v4.json"
        LOG_FILE = ROOT_DIR / "models" / "v4_ranking" / "paper_trading_log_v4.csv"
        RANKING_CACHE_FILE = ROOT_DIR / "models" / "v4_ranking" / "latest_ranking_cache_v4.parquet"
        SELECTION_CACHE_FILE = ROOT_DIR / "models" / "v4_ranking" / "latest_selection_cache_v4.parquet"
        DRIFT_REPORT_FILE = ROOT_DIR / "models" / "v4_ranking" / "latest_drift_report_v4.json"
        SERVICE_LOG_FILE = ROOT_DIR / "logs" / "paper_trading_service_v4.log"
        target_k = 15
        model_badge = "⚖️ ÇİFT MODEL MUKAYESE"
        st.markdown(r"""
        **Karşılaştırma:** V3-Kontrol vs V4-Raw  
        **V3:** 8-Faktör / K=10 (%10)  
        **V4:** 9-Faktör / K=15 (%6.67)  
        **Aktif Alfa:** +%13.46 (V4 Lehine)  
        **Max DD:** -%9.73 (V4) vs -%13.39 (V3)
        """)

    st.divider()

    # Manuel Tetikleme Butonu
    st.markdown("#### ⚡ Manuel Operasyon")
    if secilen_model == "🏆 V4-Raw Canlı Üretim (9F / K=15)":
        if st.button("V4 Rebalance Kontrolünü Çalıştır", width="stretch", type="primary"):
            trigger_paper_trader_check_v4()
    elif secilen_model == "🏛️ V3-Kontrol Referans (8F / K=10)":
        if st.button("V3 Rebalance Kontrolünü Çalıştır", width="stretch", type="secondary"):
            trigger_paper_trader_check()
    else:
        if st.button("Karşılaştırma Raporunu Güncelle", width="stretch", type="primary"):
            trigger_comparison_refresh()

    st.caption("14 günlük zamanlama, piyasa açıklığı ve PIT veri tazeliği sağlanırsa çalışır.")

    st.divider()

    # Servis Log Özeti
    st.markdown("#### 📝 Son Servis Logu")
    if SERVICE_LOG_FILE.exists():
        try:
            with open(SERVICE_LOG_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                if lines:
                    st.code("\n".join(lines[-4:]), language="log")
                else:
                    st.caption("Henüz log kaydı yok.")
        except Exception:
            st.caption("Log okunamadı.")
    else:
        st.caption("Log dosyası bulunamadı.")


# ─── ANA BAŞLIK VE KRİTİK KURUMSAL SINIR BİLGİLENDİRMESİ ─────────────────────
st.title(f"🏛️ BIST Kantitatif Karar Destek Terminali — {model_badge}")
st.markdown(
    "**30 Yıllık Kurumsal Disiplin:** Point-in-Time Temel Rasyolar, 60 Günlük Vasicek Beta-Residual Etiketleme, "
    "Dondurulmuş LambdaMART Sıralama Modeli ve Çok Katmanlı Risk Kalkanı."
)

st.markdown("""
<div class="disclaimer-banner">
    <div class="disclaimer-title">🛑 KRİTİK KURUMSAL SINIR (İHLAL EDİLEMEZ)</div>
    <div class="disclaimer-text">
        Bu sistem <b>SADECE bildirim, simülasyon ve karar destek çıktısı</b> üretir — hiçbir şekilde aracı kurum API'sine bağlanmaz,
        otomatik emir iletmez veya canlı sermaye ile al-sat kararı <b>VERMEZ</b>. Tüm veriler ve pozisyonlar sanal portföy (paper trading)
        takibidir; nihai yatırım kararları tamamen kullanıcının kendi hür takdirindedir.
    </div>
</div>
""", unsafe_allow_html=True)


# ─── VERİLERİ ÇEK ──────────────────────────────────────────────────────────
portfolio_data = load_portfolio_data(PORTFOLIO_FILE)
df_logs = load_trading_logs(LOG_FILE)
df_ranking = load_latest_ranking(str(RANKING_CACHE_FILE))
df_selection = load_latest_selection(str(SELECTION_CACHE_FILE))
market_alignment = load_market_alignment()
drift_snapshot = load_latest_drift_report(str(DRIFT_REPORT_FILE))
comparison_data = load_v3_vs_v4_comparison()

equity = float(portfolio_data.get("equity", 1.0))
peak_equity = float(portfolio_data.get("peak_equity", 1.0))
drawdown = float(portfolio_data.get("drawdown", 0.0))
dd_aktif = bool(portfolio_data.get("dd_kesici_aktif", False))
positions = portfolio_data.get("positions", {})
last_date = portfolio_data.get("last_check_date", "Bilinmiyor")

if market_alignment.get("aligned"):
    st.caption(f"✅ Veri tarihi hizalı: {market_alignment.get('market_date')}")
else:
    stale_count = len(market_alignment.get("stale_symbols", []))
    st.error(
        f"🛑 Veri hizası doğrulanamadı — {market_alignment.get('reason')} "
        f"Panel yalnızca son kaydı gösterir; yeni portföy kontrolü engellenir."
    )


# ─── ÜST KPI METRİK KARTLARI ───────────────────────────────────────────────
kasa_buyuklugu = equity * 100_000.0
k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-title">Toplam Kasa Değeri</div>
        <div class="metric-value">₺{kasa_buyuklugu:,.0f}</div>
        <div class="metric-subtitle">Net Getiri: %{((equity - 1.0) * 100):+.2f}</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-title">Zirve Kasa Değeri</div>
        <div class="metric-value">₺{(peak_equity * 100_000):,.0f}</div>
        <div class="metric-subtitle">Zirve Endeks: {peak_equity:.3f}</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    dd_color = "#10b981" if drawdown >= -0.05 else ("#f59e0b" if drawdown >= -0.15 else "#ef4444")
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-title">Zirveden Drawdown</div>
        <div class="metric-value" style="color: {dd_color};">%{drawdown * 100:.2f}</div>
        <div class="metric-subtitle">Devre Kesici Eşiği: %-25.0</div>
    </div>
    """, unsafe_allow_html=True)

with k4:
    if dd_aktif:
        breaker_badge = "<span class='badge-alert'>🚨 %50 NAKİT AKTİF</span>"
        breaker_sub = "Zirveden %-15'e toparlanma bekleniyor"
    else:
        breaker_badge = "<span class='badge-stable'>🟢 %100 HİSSE (NORMAL)</span>"
        breaker_sub = f"Hisse başı ağırlık: %{(100.0 / max(1, target_k)):.1f}"
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-title">Risk Kalkanı</div>
        <div class="metric-value" style="font-size: 1.15rem; padding-top: 5px;">{breaker_badge}</div>
        <div class="metric-subtitle">{breaker_sub}</div>
    </div>
    """, unsafe_allow_html=True)

with k5:
    son_drift_icon = "🟢"
    if drift_snapshot and "overall_status" in drift_snapshot:
        son_drift_icon = drift_snapshot["overall_status"]
    elif not df_logs.empty and "drift_durumu" in df_logs.columns:
        son_drift_icon = df_logs.iloc[-1].get("drift_durumu", "🟢")
    drift_text = "🟢 STABİL" if "🟢" in son_drift_icon else ("🟡 İZLEME" if "🟡" in son_drift_icon else "🔴 ALARM")
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-title">Drift Durumu</div>
        <div class="metric-value" style="font-size: 1.15rem; padding-top: 5px;">{drift_text}</div>
        <div class="metric-subtitle">Son Kontrol: {last_date}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# SAYFA: ÇİFT MODEL KARŞILAŞTIRMA (V3 VS V4)
# ═══════════════════════════════════════════════════════════════════════════
if sayfa == "⚖️ Çift Model Karşılaştırma":
    st.subheader("⚖️ Çift Model Canlı Paper Trading Mukayese Paneli")
    st.caption("V3-Kontrol (8-Faktör / K=10) ile V4-Raw (9-Faktör / K=15) canlı performans, risk ve portföy ayrışması.")

    comp = comparison_data or {}
    if comp:
        v3 = comp.get("v3", {})
        v4 = comp.get("v4", {})
        c = comp.get("karsilastirma", {})

        # Karşılaştırmalı 4 KPI Kartı
        cp1, cp2, cp3, cp4 = st.columns(4)
        with cp1:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-title">Mevcut Sermaye</div>
                <div class="metric-value">V3: {float(v3.get('sermaye') or 1.0):.4f} | V4: {float(v4.get('sermaye') or 1.0):.4f}</div>
                <div class="metric-subtitle">Sermaye Farkı: {float(c.get('sermaye_farki') or 0.0):+.4f}</div>
            </div>
            """, unsafe_allow_html=True)

        with cp2:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-title">Kümülatif Getiri</div>
                <div class="metric-value">V3: %{float(v3.get('getiri_pct') or 0.0):.2f} | V4: %{float(v4.get('getiri_pct') or 0.0):.2f}</div>
                <div class="metric-subtitle">Getiri Farkı: %{float(c.get('getiri_farki_pct') or 0.0):+.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        with cp3:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-title">Tepe Drawdown</div>
                <div class="metric-value">V3: %{float(v3.get('drawdown_pct') or 0.0):.2f} | V4: %{float(v4.get('drawdown_pct') or 0.0):.2f}</div>
                <div class="metric-subtitle">Max DD OOS: -%13.39 vs -%9.73 (%27.3 İyileşme)</div>
            </div>
            """, unsafe_allow_html=True)

        with cp4:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-title">Aktif Pozisyon / K Hedef</div>
                <div class="metric-value">V3: {int(v3.get('portfoy_boyutu') or 10)}/10 | V4: {int(v4.get('portfoy_boyutu') or 15)}/15</div>
                <div class="metric-subtitle">Ortak Hisse: {int(c.get('ortak_hisseler_sayisi') or 0)} Adet</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

        # Portföy Ayrışması ve Hisseler
        st.markdown("#### 🎯 Portföy Hisseleri Ayrışma Matrisi")
        col_ortak, col_v4, col_v3 = st.columns(3)

        with col_ortak:
            st.markdown(f"**🤝 Ortak Hisseler ({c.get('ortak_hisseler_sayisi', 0)} Adet):**")
            ortak_list = c.get("ortak_hisseler", [])
            if ortak_list:
                for h in ortak_list:
                    st.markdown(f"<span class='badge-stable' style='margin: 3px;'>{h}</span>", unsafe_allow_html=True)
            else:
                st.caption("Ortak hisse bulunmuyor.")

        with col_v4:
            v4_ozel = c.get("yalnizca_v4_hisseler", [])
            st.markdown(f"**🏆 Yalnızca V4 Hisseleri ({len(v4_ozel)} Adet):**")
            if v4_ozel:
                for h in v4_ozel:
                    st.markdown(f"<span class='badge-free' style='margin: 3px;'>{h}</span>", unsafe_allow_html=True)
            else:
                st.caption("Özel hisse yok.")

        with col_v3:
            v3_ozel = c.get("yalnizca_v3_hisseler", [])
            st.markdown(f"**🏛️ Yalnızca V3 Hisseleri ({len(v3_ozel)} Adet):**")
            if v3_ozel:
                for h in v3_ozel:
                    st.markdown(f"<span class='badge-lock' style='margin: 3px;'>{h}</span>", unsafe_allow_html=True)
            else:
                st.caption("Özel hisse yok.")

        st.divider()

        # Kurumsal Mukayese Tablosu
        st.markdown("#### 📊 Kurumsal Model Mukayese Tablosu (4-Fold Walk-Forward OOS)")
        df_comp_table = pd.DataFrame([
            {"Metrik": "Model Mimarisi", "V3-Kontrol (Referans)": "8 Faktörlü LambdaMART", "V4-Raw (Canlı Üretim)": "9 Faktörlü LambdaMART (+reel_eps_growth)", "Kurumsal Yorum": "PB tekeli %57'den %14'e kırıldı"},
            {"Metrik": "Portföy Boyutu", "V3-Kontrol (Referans)": "K=10 Eşit Ağırlık (%10.0)", "V4-Raw (Canlı Üretim)": "K=15 Eşit Ağırlık (%6.67)", "Kurumsal Yorum": "Daha yüksek çeşitlendirme"},
            {"Metrik": "OOS Sharpe Oranı", "V3-Kontrol (Referans)": "0.994", "V4-Raw (Canlı Üretim)": "0.972", "Kurumsal Yorum": "|Δ| = 0.022 ≤ 0.05 tolerans dahilinde"},
            {"Metrik": "Maksimum Drawdown", "V3-Kontrol (Referans)": "-%13.39", "V4-Raw (Canlı Üretim)": "-%9.73", "Kurumsal Yorum": "Sermaye çekilmesinde %27.3 net düşüş"},
            {"Metrik": "Information Ratio (IR)", "V3-Kontrol (Referans)": "-0.713", "V4-Raw (Canlı Üretim)": "+0.509", "Kurumsal Yorum": "Güçlü pozitif aktif alfa"},
            {"Metrik": "Yıllık Aktif Alfa", "V3-Kontrol (Referans)": "-%9.60", "V4-Raw (Canlı Üretim)": "+%13.46", "Kurumsal Yorum": "Piyasa kıstasına karşı +%13.46 üstünlük"},
            {"Metrik": "Dönem B Sıkılaşma Ayı Piyasası", "V3-Kontrol (Referans)": "-%13.39 Zarar", "V4-Raw (Canlı Üretim)": "+%8.15 Net Kâr", "Kurumsal Yorum": "Zombi şirketleri ezip kâr yazdı"},
            {"Metrik": "CAGR / Kümülatif Getiri", "V3-Kontrol (Referans)": "%86.02 / %651.7", "V4-Raw (Canlı Üretim)": "%87.09 / %665.9", "Kurumsal Yorum": "Daha düşük riskle daha yüksek getiri"},
            {"Metrik": "Emniyet Kalkanı", "V3-Kontrol (Referans)": "Likidite + Sektör Tavanı", "V4-Raw (Canlı Üretim)": "Faz 0 Taban Veto + VBTS Kalkanı", "Kurumsal Yorum": "PASEU benzeri çöküşler doğrudan vetolu"}
        ])
        st.dataframe(df_comp_table, width="stretch", hide_index=True)
    else:
        st.info("Karşılaştırma raporu henüz oluşturulmadı. Sol menüdeki 'Karşılaştırma Raporunu Güncelle' butonunu kullanabilirsiniz.")


# ═══════════════════════════════════════════════════════════════════════════
# SAYFA 1: PORTFÖYÜM & POZİSYON YÖNETİMİ (ESKİSİ GİBİ ZENGİN GÖRÜNÜM)
# ═══════════════════════════════════════════════════════════════════════════
elif sayfa == "💼 Portföyüm & Pozisyon Yönetimi":
    st.subheader(f"💼 Aktif Portföy — {len(positions)} / {target_k} Hisse")
    st.caption("Pozisyonlar, çeyreklik rotasyonla en az 60 işlem günü tutulur. Listeden düşse bile 60 gün dolmadan satış yapılmaz.")

    if positions:
        # Özet Tablo Listesi
        pos_rows = []
        toplam_portfoy_pnl_tl = 0.0

        for sembol, info in positions.items():
            entry_p = float(info.get("entry_price", 100.0))
            last_p = float(info.get("last_price", entry_p))
            peak_p = float(info.get("personal_peak_price", max(entry_p, last_p)))
            peak_dd = float(info.get("peak_drawdown_pct", ((last_p - peak_p) / peak_p * 100.0) if peak_p > 0 else 0.0))
            pnl_pct = ((last_p - entry_p) / entry_p * 100) if entry_p > 0 else 0.0
            days_held = int(info.get("days_held", 0))
            weight_pct = float(info.get("weight") or (1.0 / max(1, target_k))) * 100
            tutar_tl = kasa_buyuklugu * (weight_pct / 100.0)
            pnl_tl = tutar_tl * (pnl_pct / 100.0)
            toplam_portfoy_pnl_tl += pnl_tl
            
            kalan_gun = max(0, 60 - days_held)
            kilit_metin = f"⏳ {kalan_gun} gün kaldı" if kalan_gun > 0 else "✅ Çıkışa Uygun (≥60g)"
            
            clean_ticker = sembol.replace(".IS", "")
            sektor_v2 = cfg.HISSE_SEKTOR_V2.get(sembol, "DİĞER")
            peak_dd_str = f"%{peak_dd:.1f} 🚨" if peak_dd <= -20.0 else f"%{peak_dd:.1f}"
            
            pos_rows.append({
                "Hisse": f"#{clean_ticker} ({sektor_v2})",
                "sembol": sembol,
                "Giriş Tarihi": info.get("entry_date", last_date),
                "Alış Fiyatı (TL)": f"₺{entry_p:,.2f}",
                "Son Fiyat (TL)": f"₺{last_p:,.2f}",
                "Zirve Fiyat (TL)": f"₺{peak_p:,.2f}",
                "Zirveden Çekilme": peak_dd_str,
                "Kâr / Zarar (%)": f"%{pnl_pct:+.2f}",
                "Kâr / Zarar (TL)": f"₺{pnl_tl:+,.2f}",
                "Pozisyon Tutarı": f"₺{tutar_tl:,.0f}",
                "Elde Tutulan": f"{days_held} gün",
                "60 Gün Kuralı": kilit_metin,
                "Hedef Ağırlık": f"%{weight_pct:.1f}",
                "raw_pnl_pct": pnl_pct,
                "raw_days": days_held,
                "raw_entry": entry_p,
                "raw_last": last_p,
                "raw_peak": peak_p,
                "raw_peak_dd": peak_dd
            })

        # İki sütunlu özet kartı
        c_p1, c_p2, c_p3 = st.columns([1.5, 1.5, 1.5])
        with c_p1:
            st.metric("Toplam Açık Pozisyon Tutarı", f"₺{kasa_buyuklugu:,.0f}")
        with c_p2:
            st.metric("Portföy Anlık Net Kâr/Zarar", f"₺{toplam_portfoy_pnl_tl:+,.2f}")
        with c_p3:
            st.metric("Nakit Rezervi", f"₺{(kasa_buyuklugu * 0.50):,.0f}" if dd_aktif else "₺0 (Tam Yatırımda)")

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # Tablo
        df_table = pd.DataFrame(pos_rows)
        table_cols = [
            "Hisse", "Giriş Tarihi", "Alış Fiyatı (TL)", "Son Fiyat (TL)",
            "Zirve Fiyat (TL)", "Zirveden Çekilme", "Kâr / Zarar (%)",
            "Kâr / Zarar (TL)", "Pozisyon Tutarı", "Elde Tutulan", "60 Gün Kuralı", "Hedef Ağırlık"
        ]
        st.dataframe(
            df_table[table_cols],
            width="stretch",
            hide_index=True
        )

        st.divider()

        # ─── SEÇİLEN HİSSE İÇİN GRAFİK VE DETAYLI ANALİZ (PROFESYONEL TRADINGVIEW STİLİ) ───
        st.subheader("🔍 Portföy Hissesi Detaylı Grafiği & Mum Analizi")

        c_sel1, c_sel2 = st.columns([3, 1])
        with c_sel1:
            tum_evren_sec = st.checkbox("🌐 Tüm BIST 88 Evrenini Göster", value=False, help="İşaretlendiğinde portföy dışındaki 88 BIST hissesini de teknik ve model analizi için seçebilirsiniz.")
            if tum_evren_sec and df_ranking is not None and not df_ranking.empty:
                hisse_secenekleri = df_ranking["sembol"].tolist()
            else:
                hisse_secenekleri = [r["sembol"] for r in pos_rows] if pos_rows else (df_ranking["sembol"].tolist() if df_ranking is not None else cfg.HISSELER[:10])

            secilen_hisse = st.selectbox(
                "Detaylı İncelenecek Hisseyi Seçiniz:",
                hisse_secenekleri,
                format_func=lambda s: f"#{s.replace('.IS', '')} ({cfg.HISSE_SEKTOR.get(s, 'BIST')})" + (" 💼 [PORTFÖYDE]" if s in positions else "")
            )

        # ─── İNTERAKTİF GRAFİK KONTROL VE İNDİKATÖR ARAÇ ÇUBUĞU ───
        c_ctrl1, c_ctrl2, c_ctrl3, c_ctrl4 = st.columns([2.2, 2.8, 2.8, 2.2])
        with c_ctrl1:
            zaman_secimi = st.selectbox(
                "📅 Görünüm Aralığı:",
                ["1 Ay (22 Bar)", "3 Ay (65 Bar)", "6 Ay (130 Bar)", "1 Yıl (250 Bar)", "Tüm Geçmiş"],
                index=2
            )
        with c_ctrl2:
            st.markdown("<p style='font-size:0.82rem; font-weight:600; color:#94a3b8; margin-bottom:4px;'>📈 TREND İNDİKATÖRLERİ</p>", unsafe_allow_html=True)
            ind_ma = st.checkbox("SMA (20, 50, 200)", value=True)
            ind_bb = st.checkbox("Bollinger Bantları (20, 2)", value=True)
        with c_ctrl3:
            st.markdown("<p style='font-size:0.82rem; font-weight:600; color:#94a3b8; margin-bottom:4px;'>🎯 MALİYET & HEDEFLER</p>", unsafe_allow_html=True)
            ind_maliyet = st.checkbox("Alış Maliyeti & Kâr Alanı", value=True)
            ind_52w = st.checkbox("52H Zirve / Dip Seviyeleri", value=True)
        with c_ctrl4:
            st.markdown("<p style='font-size:0.82rem; font-weight:600; color:#94a3b8; margin-bottom:4px;'>📊 ALT OSİLATÖR</p>", unsafe_allow_html=True)
            osc_secim = st.selectbox(
                "Osilatör Seçimi:",
                ["RSI (14) Momentum", "MACD (12, 26, 9)", "Kapalı"],
                index=0,
                label_visibility="collapsed"
            )

        df_mum = load_stock_history(secilen_hisse)
        if df_mum is not None and not df_mum.empty and "close" in df_mum.columns:
            # Tüm geçmiş üzerinden tam göstergeleri hesapla
            df_ti = compute_technical_indicators(df_mum)

            # Zaman aralığı dilimleme
            if "1 Ay" in zaman_secimi:
                df_sub = df_ti.tail(22).copy()
            elif "3 Ay" in zaman_secimi:
                df_sub = df_ti.tail(65).copy()
            elif "6 Ay" in zaman_secimi:
                df_sub = df_ti.tail(130).copy()
            elif "1 Yıl" in zaman_secimi:
                df_sub = df_ti.tail(250).copy()
            else:
                df_sub = df_ti.copy()

            son_fiyat = float(df_sub["close"].iloc[-1])
            alis_fiyati = positions[secilen_hisse].get("entry_price", son_fiyat) if secilen_hisse in positions else son_fiyat
            fark_pct = ((son_fiyat - alis_fiyati) / alis_fiyati * 100) if alis_fiyati > 0 else 0.0
            gunluk_degisim = ((son_fiyat - float(df_sub["close"].iloc[-2])) / float(df_sub["close"].iloc[-2]) * 100) if len(df_sub) >= 2 else 0.0

            # ─── HİSSE HIZLI METRİK KARTLARI (6 KPI KARTI) ───
            m_c1, m_c2, m_c3, m_c4, m_c5, m_c6 = st.columns(6)
            with m_c1:
                st.metric("Son Kapanış", f"₺{son_fiyat:.2f}", f"{gunluk_degisim:+.2f}% Günlük")
            with m_c2:
                if secilen_hisse in positions:
                    st.metric("Alış Maliyeti", f"₺{alis_fiyati:.2f}", f"{fark_pct:+.2f}% Kâr/Zarar")
                else:
                    st.metric("Portföy Durumu", "İzleme Listesi", "Taşınmıyor")
            with m_c3:
                if secilen_hisse in positions:
                    pos_weight = float(positions[secilen_hisse].get("weight") or (1.0 / max(1, target_k)))
                    hisse_pnl_tl = (kasa_buyuklugu * pos_weight) * (fark_pct / 100.0)
                    st.metric("Pozisyon Net Kâr", f"₺{hisse_pnl_tl:+,.2f}")
                else:
                    st.metric("Açık Pozisyon", "₺0", "Nakit")
            with m_c4:
                zirve_52 = float(df_mum["high"].tail(252).max()) if len(df_mum) >= 50 else float(df_sub["high"].max())
                dip_52 = float(df_mum["low"].tail(252).min()) if len(df_mum) >= 50 else float(df_sub["low"].min())
                zirve_fark = ((son_fiyat - zirve_52) / zirve_52 * 100) if zirve_52 > 0 else 0.0
                st.metric("52H Zirve / Dip", f"₺{zirve_52:.2f} / ₺{dip_52:.2f}", f"{zirve_fark:+.1f}% Zirveye")
            with m_c5:
                ort_vol = float(df_sub["volume"].tail(20).mean()) if "volume" in df_sub.columns else 0.0
                st.metric("20g Ort. Hacim", f"{ort_vol:,.0f} Lot")
            with m_c6:
                rsi_son = float(df_sub["rsi_14"].iloc[-1]) if "rsi_14" in df_sub.columns and not pd.isna(df_sub["rsi_14"].iloc[-1]) else 50.0
                rsi_durum = "🔴 Aşırı Alım" if rsi_son >= 70 else ("🟢 Aşırı Satım" if rsi_son <= 30 else "🟡 Nötr")
                st.metric("RSI (14) Osilatör", f"{rsi_son:.1f}", rsi_durum)

            # ─── 2 VEYA 3 PANELLİ GELİŞMİŞ PLOTLY GRAFİĞİ ───
            has_osc = (osc_secim != "Kapalı")
            if has_osc:
                fig = make_subplots(
                    rows=3, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.03,
                    row_heights=[0.62, 0.18, 0.20],
                    subplot_titles=(None, "İşlem Hacmi (Lot)", osc_secim)
                )
                chart_height = 680
            else:
                fig = make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.04,
                    row_heights=[0.75, 0.25],
                    subplot_titles=(None, "İşlem Hacmi (Lot)")
                )
                chart_height = 560

            # 1. Mum Grafiği (OHLC) - TradingView Emerald/Crimson
            fig.add_trace(go.Candlestick(
                x=df_sub.index,
                open=df_sub['open'],
                high=df_sub['high'],
                low=df_sub['low'],
                close=df_sub['close'],
                name="Fiyat (OHLC)",
                increasing_line_color="#00e676",
                decreasing_line_color="#ff1744",
                increasing_fillcolor="#00e676",
                decreasing_fillcolor="#ff1744",
                line_width=1.2
            ), row=1, col=1)

            # 2. Bollinger Bantları (20, 2)
            if ind_bb and "bb_upper" in df_sub.columns and "bb_lower" in df_sub.columns:
                fig.add_trace(go.Scatter(
                    x=df_sub.index, y=df_sub["bb_upper"],
                    line=dict(color="rgba(144, 202, 249, 0.45)", width=1, dash="dot"),
                    name="Bollinger Üst", hoverinfo="skip"
                ), row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=df_sub.index, y=df_sub["bb_lower"],
                    line=dict(color="rgba(144, 202, 249, 0.45)", width=1, dash="dot"),
                    fill='tonexty', fillcolor="rgba(59, 130, 246, 0.07)",
                    name="Bollinger Bant Alanı", hoverinfo="skip"
                ), row=1, col=1)

            # 3. Hareketli Ortalamalar (SMA 20, SMA 50, SMA 200)
            if ind_ma:
                if "sma_20" in df_sub.columns:
                    fig.add_trace(go.Scatter(
                        x=df_sub.index,
                        y=df_sub["sma_20"],
                        line=dict(color="#00d4ff", width=1.8),
                        name="SMA 20 (Kısa Vade)"
                    ), row=1, col=1)

                if "sma_50" in df_sub.columns:
                    fig.add_trace(go.Scatter(
                        x=df_sub.index,
                        y=df_sub["sma_50"],
                        line=dict(color="#ffa726", width=1.8),
                        name="SMA 50 (Orta Vade)"
                    ), row=1, col=1)

                if "sma_200" in df_sub.columns:
                    fig.add_trace(go.Scatter(
                        x=df_sub.index,
                        y=df_sub["sma_200"],
                        line=dict(color="#c084fc", width=2.0, dash="dash"),
                        name="SMA 200 (Kurumsal Trend)"
                    ), row=1, col=1)

            # 4. Alış Maliyeti Seviye Çizgisi & Gölgeli Kâr Alanı
            if ind_maliyet and secilen_hisse in positions:
                fig.add_hline(
                    y=alis_fiyati,
                    line_dash="dash",
                    line_color="#ffd600",
                    line_width=2.5,
                    annotation_text=f"📍 ALIŞ MALİYETİ: ₺{alis_fiyati:.2f} ({fark_pct:+.2f}%)",
                    annotation_position="top right",
                    annotation_font_color="#ffd600",
                    annotation_font_size=12,
                    row=1, col=1
                )
                zone_color = "rgba(0, 230, 118, 0.14)" if son_fiyat >= alis_fiyati else "rgba(255, 23, 68, 0.14)"
                fig.add_hrect(
                    y0=alis_fiyati, y1=son_fiyat,
                    fillcolor=zone_color, line_width=0,
                    row=1, col=1
                )

            # 5. 52 Haftalık Zirve / Dip Çizgileri
            if ind_52w:
                fig.add_hline(
                    y=zirve_52, line_dash="dot", line_color="#34d399", line_width=1.2,
                    annotation_text=f"52H Zirve: ₺{zirve_52:.2f}",
                    annotation_position="top left", annotation_font_color="#34d399", annotation_font_size=10,
                    row=1, col=1
                )
                fig.add_hline(
                    y=dip_52, line_dash="dot", line_color="#f87171", line_width=1.2,
                    annotation_text=f"52H Dip: ₺{dip_52:.2f}",
                    annotation_position="bottom left", annotation_font_color="#f87171", annotation_font_size=10,
                    row=1, col=1
                )

            # 6. Hacim Barları (Row 2)
            vol_colors = ["rgba(0, 230, 118, 0.85)" if c >= o else "rgba(255, 23, 68, 0.85)" 
                          for c, o in zip(df_sub['close'], df_sub['open'])]
            fig.add_trace(go.Bar(
                x=df_sub.index,
                y=df_sub['volume'],
                marker_color=vol_colors,
                name="Hacim",
                showlegend=False
            ), row=2, col=1)

            if "vol_sma_20" in df_sub.columns:
                fig.add_trace(go.Scatter(
                    x=df_sub.index,
                    y=df_sub["vol_sma_20"],
                    line=dict(color="#94a3b8", width=1.4, dash="dot"),
                    name="Hacim Ort (20g)"
                ), row=2, col=1)

            # 7. Alt Osilatör Paneli (Row 3: RSI veya MACD)
            if has_osc:
                if osc_secim == "RSI (14) Momentum":
                    fig.add_trace(go.Scatter(
                        x=df_sub.index,
                        y=df_sub["rsi_14"],
                        line=dict(color="#c084fc", width=2),
                        name="RSI (14)"
                    ), row=3, col=1)
                    fig.add_hline(y=70, line_dash="dash", line_color="#ff5252", line_width=1, annotation_text="Aşırı Alım (70)", annotation_position="top left", row=3, col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="#69f0ae", line_width=1, annotation_text="Aşırı Satım (30)", annotation_position="bottom left", row=3, col=1)
                    fig.add_hline(y=50, line_dash="dot", line_color="#64748b", line_width=1, row=3, col=1)
                    fig.add_hrect(y0=30, y1=70, fillcolor="rgba(192, 132, 252, 0.04)", line_width=0, row=3, col=1)
                    fig.update_yaxes(range=[15, 85], row=3, col=1)

                elif osc_secim == "MACD (12, 26, 9)":
                    hist_colors = ["#34d399" if h >= 0 else "#f87171" for h in df_sub["macd_hist"]]
                    fig.add_trace(go.Bar(
                        x=df_sub.index,
                        y=df_sub["macd_hist"],
                        marker_color=hist_colors,
                        name="MACD Hist",
                        showlegend=False
                    ), row=3, col=1)
                    fig.add_trace(go.Scatter(
                        x=df_sub.index,
                        y=df_sub["macd"],
                        line=dict(color="#38bdf8", width=1.8),
                        name="MACD"
                    ), row=3, col=1)
                    fig.add_trace(go.Scatter(
                        x=df_sub.index,
                        y=df_sub["macd_signal"],
                        line=dict(color="#fb923c", width=1.8),
                        name="Sinyal"
                    ), row=3, col=1)
                    fig.add_hline(y=0, line_dash="dash", line_color="#64748b", line_width=1, row=3, col=1)

            # Layout ve Etkileşimli Butonlar
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0b0f19",
                plot_bgcolor="#111827",
                height=chart_height,
                margin=dict(l=30, r=30, t=30, b=30),
                xaxis_rangeslider_visible=False,
                hovermode="x unified",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    bgcolor="rgba(17, 24, 39, 0.8)",
                    bordercolor="rgba(255, 255, 255, 0.1)",
                    borderwidth=1
                )
            )

            # Hafta sonu boşluklarını kaldır (Rangebreaks) & Crosshair Spikelines
            fig.update_xaxes(
                rangebreaks=[dict(bounds=["sat", "mon"])],
                gridcolor="#1f293d",
                showspikes=True,
                spikemode="across",
                spikesnap="cursor",
                spikethickness=1,
                spikecolor="#64748b"
            )
            fig.update_yaxes(gridcolor="#1f293d")
            fig.update_yaxes(title="Fiyat (TL)", row=1, col=1)

            st.plotly_chart(fig, width="stretch")

            # Temel Göstergeler Kartı
            if df_ranking is not None and not df_ranking.empty:
                sub_rank = df_ranking[df_ranking["sembol"] == secilen_hisse]
                if not sub_rank.empty:
                    row_r = sub_rank.iloc[0]
                    st.markdown("#### 📊 Model Faktör Değerleri (Point-in-Time)")
                    has_growth = "reel_eps_growth" in row_r
                    cols_f = st.columns(6 if has_growth else 5)
                    with cols_f[0]:
                        st.metric("Model Skoru", f"{float(row_r.get('ml_score') or 0.0):.4f}")
                    idx = 1
                    if has_growth:
                        with cols_f[idx]:
                            st.metric("Reel Kâr Büyümesi", f"%{float(row_r.get('reel_eps_growth') or 0.0)*100:+.1f}")
                        idx += 1
                    with cols_f[idx]:
                        st.metric("Ters P/B (Değerleme)", f"{float(row_r.get('z_pb') or 0.0):.2f}")
                    with cols_f[idx+1]:
                        st.metric("Net Borç / EBITDA", f"{float(row_r.get('z_borc') or 0.0):.2f}")
                    with cols_f[idx+2]:
                        st.metric("12-1 Momentum", f"{float(row_r.get('z_mom') or 0.0):.2f}")
                    with cols_f[idx+3]:
                        st.metric("Özsermaye Kârlılığı (ROE)", f"{float(row_r.get('z_roe') or 0.0):.2f}")
        else:
            st.info(f"{secilen_hisse} için mum verisi bulunamadı.")

        st.divider()
        st.markdown("#### 📜 Rebalance ve İşlem Geçmişi Kütüğü")
        if not df_logs.empty:
            st.dataframe(df_logs.sort_index(ascending=False), width="stretch", hide_index=True)
    else:
        st.info("Portföyde henüz aktif pozisyon bulunmamaktadır. Sol menüdeki 'Rebalance & Bildirim Kontrolü Çalıştır' butonu ile ilk portföyü kurabilirsiniz.")


# ═══════════════════════════════════════════════════════════════════════════
# SAYFA 2: BIST 88 MODEL SIRALAMASI
# ═══════════════════════════════════════════════════════════════════════════
elif sayfa == "🏆 BIST 88 Model Sıralaması":
    st.subheader("🏆 BIST 88 Kesitsel Model Sıralaması (LambdaMART)")
    st.caption("Point-in-Time bilançolar ve kurumsal rasyolarla beslenen dondurulmuş sıralama motoru çıktısı.")

    st.markdown(f"#### ✅ Filtrelenmiş K={target_k} Paper-Portfolio Adayları")
    if df_selection is not None and not df_selection.empty:
        selected_display = df_selection.copy()
        selected_display["Portföy Adayı"] = "✅ Likidite + sektör filtresinden geçti"
        selected_display["Sektör (V2)"] = selected_display["sektor_v2"].fillna("DİĞER")
        selected_columns = ["rank", "sembol", "Sektör (V2)", "ml_score", "avg_tl_hacim_m", "data_age_days", "Portföy Adayı"]
        st.dataframe(
            selected_display[[column for column in selected_columns if column in selected_display.columns]],
            width="stretch",
            hide_index=True,
        )
        st.caption("Bu tablo, paper trader'ın kullandığı post-model filtreli seçimi gösterir; ham model sırası aşağıdadır.")
    else:
        st.warning("Filtreli seçim önbelleği henüz yok. Son başarılı, hizalı rebalance kontrolünden sonra oluşturulur.")

    if df_ranking is not None and not df_ranking.empty:
        st.markdown("#### Ham Model Sıralaması — Filtre Öncesi")
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            arama = st.text_input("🔍 Hisse Ara (örn: THYAO, LOGO, ASELS):", "").strip().upper()
        with col_s2:
            sadece_top10 = st.checkbox(f"Sadece Ham Model İlk {target_k}'u Göster", value=False)

        df_disp = df_ranking.copy()
        df_disp["Sıra"] = range(1, len(df_disp) + 1)
        secilen_set = set(df_selection["sembol"].tolist()) if df_selection is not None and not df_selection.empty else set()
        
        def filtre_karar_metni(row):
            sym = row["sembol"]
            if sym in secilen_set:
                return f"✅ Top-{target_k} Portföy Adayı"
            if sym == "BIZIM.IS":
                return "❌ Likidite Elendi (<20M TL)"
            if row["Sıra"] <= target_k:
                return "⚠️ Sektör Kısıtıyla Elendi"
            return "—"
        
        df_disp["Nihai Karar"] = df_disp.apply(filtre_karar_metni, axis=1)
        df_disp["Sektör (V2)"] = df_disp["sembol"].map(lambda s: cfg.HISSE_SEKTOR_V2.get(s, "DİĞER"))
        
        if "data_age_days" in df_disp.columns:
            esik = getattr(cfg, "BILANCO_ESKILIK_ESIGI_GUN", 100)
            df_disp["Bilanço Tazeliği"] = df_disp["data_age_days"].apply(
                lambda d: f"⚠️ {int(d)}g (Eski)" if d > esik else f"✅ {int(d)}g"
            )
        
        if arama:
            df_disp = df_disp[df_disp["sembol"].str.contains(arama, na=False)]
        if sadece_top10:
            df_disp = df_disp[df_disp["Sıra"] <= target_k]

        cols_show = ["Sıra", "sembol", "Sektör (V2)", "ml_score", "Nihai Karar", "Bilanço Tazeliği", "reel_eps_growth", "z_pb", "z_borc", "z_mom", "z_roe", "z_fcf"]
        avail = [c for c in cols_show if c in df_disp.columns]

        st.dataframe(df_disp[avail], width="stretch", hide_index=True)
    else:
        st.info("Sıralama önbelleği hazır değil. Sol menüdeki 'Rebalance & Bildirim Kontrolü Çalıştır' butonuyla önbelleği oluşturabilirsiniz.")


# ═══════════════════════════════════════════════════════════════════════════
# SAYFA 3: ÇOK KATMANLI DRİFT VE RİSK MONİTÖRÜ
# ═══════════════════════════════════════════════════════════════════════════
elif sayfa == "🛡️ Çok Katmanlı Drift Monitör" or sayfa == "🛡️ 3 Katmanlı Drift Monitör":
    st.subheader("🛡️ Kurumsal Çok Katmanlı Drift ve Risk Radarı")
    st.caption("Piyasa rejim değişimlerini, model tahmin dağılımındaki kaymaları, veri tazeliğini ve sağlık denetimini sürekli izler.")

    if drift_snapshot:
        as_of_d = drift_snapshot.get("as_of", "Bilinmiyor")
        overall_d = drift_snapshot.get("overall_status", "🟢 YEŞİL")
        summary_d = drift_snapshot.get("summary_message", "Tüm risk katmanları normal sınırlarda.")
        
        status_box_color = "rgba(16, 185, 129, 0.12)" if "🟢" in overall_d else ("rgba(245, 158, 11, 0.12)" if "🟡" in overall_d else "rgba(239, 68, 68, 0.12)")
        status_border_color = "#10b981" if "🟢" in overall_d else ("#f59e0b" if "🟡" in overall_d else "#ef4444")
        
        st.markdown(f"""
        <div style="background: {status_box_color}; border: 1px solid {status_border_color}; border-left: 5px solid {status_border_color}; border-radius: 10px; padding: 12px 18px; margin-bottom: 20px;">
            <div style="font-weight: 600; font-size: 0.95rem; color: #f8fafc; margin-bottom: 3px;">
                GENEL SİSTEM DURUMU: {overall_d} (As-Of: {as_of_d})
            </div>
            <div style="font-size: 0.84rem; color: #cbd5e1;">
                {summary_d}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        macro_d = drift_snapshot.get("macro", {}) or {}
        score_d = drift_snapshot.get("score", {}) or {}
        perf_d = drift_snapshot.get("performance", {}) or {}
    else:
        st.info("ℹ️ Henüz kaydedilmiş drift raporu bulunmuyor. Canlı rebalance kontrolü sonrasında otomatik oluşturulur.")
        macro_d = {}
        score_d = {}
        perf_d = {}

    d_col1, d_col2, d_col3 = st.columns(3)

    with d_col1:
        m_alarm = macro_d.get("is_alarm", False)
        m_badge = "<span class='badge-alert'>🔴 Makro Alarm</span>" if m_alarm else "<span class='badge-stable'>🟢 Stabil Rejim</span>"
        reel_f = macro_d.get("reel_faiz", 5.3)
        usd_m = macro_d.get("usd_mom_60", 0.033) * 100
        pol_f = macro_d.get("politika_faizi", 32.5)
        tufe_y = macro_d.get("yillik_tufe", 27.2)
        m_det = macro_d.get("details", "TCMB politika faizi pozitif reel faiz bölgesinde seyretmektedir.")
        
        st.markdown(f"""
        <div class="quant-card">
            <h4 style="color: #60a5fa; margin-top: 0;">Katman 1 — Makro Rejim</h4>
            <p style="font-size: 0.84rem; color: #94a3b8;">
                TCMB faizi, 12 aylık TÜFE ve USD/TRY 60g ivmesiyle negatif reel faiz krizlerini ve kur şoklarını izler.
            </p>
            <hr style="border-color: rgba(255,255,255,0.06); margin: 12px 0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>Cari Reel Faiz:</span>
                <b style="color: {'#f87171' if reel_f <= -10 else '#34d399'};">%{reel_f:.1f}</b>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>TCMB Faiz / Yıllık TÜFE:</span>
                <b>%{pol_f:.1f} / %{tufe_y:.1f}</b>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>USD 60g İvmesi:</span>
                <b style="color: {'#f87171' if usd_m >= 20 else '#e2e8f0'};">%{usd_m:.1f}</b>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>Cari Makro Durum:</span>
                {m_badge}
            </div>
            <p style="font-size: 0.78rem; color: #64748b; margin-top: 10px;">
                <i>*{m_det}</i>
            </p>
        </div>
        """, unsafe_allow_html=True)

    with d_col2:
        s_drift = score_d.get("is_drift", False)
        s_badge = "<span class='badge-alert'>🟡 Skor Drifti</span>" if s_drift else "<span class='badge-stable'>🟢 Dağılım Normal</span>"
        s_mean = score_d.get("current_mean", -0.1352)
        s_std = score_d.get("current_std", 0.1449)
        z_mean = score_d.get("z_score_mean", -0.71)
        z_std = score_d.get("z_score_std", -1.72)
        s_det = score_d.get("details", "Model tahmin dağılımı eğitim dönemi normallik sınırları içerisindedir.")
        
        st.markdown(f"""
        <div class="quant-card">
            <h4 style="color: #60a5fa; margin-top: 0;">Katman 2 — Model Skor Drifti</h4>
            <p style="font-size: 0.84rem; color: #94a3b8;">
                Evrendeki 88 hisseye verilen ham model skorlarının tarihsel ortalama ve standart sapmadan sapmasını denetler.
            </p>
            <hr style="border-color: rgba(255,255,255,0.06); margin: 12px 0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>Tarihsel μ / σ:</span>
                <b>-0.1008 / 0.0482</b>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>Cari Evren μ / σ:</span>
                <b>{s_mean:.4f} / {s_std:.4f}</b>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>Z-Skor (Ortalama / Std):</span>
                <b>{z_mean:+.2f} / {z_std:+.2f}</b>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>Model Dağılım Durumu:</span>
                {s_badge}
            </div>
            <p style="font-size: 0.78rem; color: #64748b; margin-top: 10px;">
                <i>*{s_det}</i>
            </p>
        </div>
        """, unsafe_allow_html=True)

    with d_col3:
        if perf_d:
            p_alarm = perf_d.get("is_alarm", False)
            p_sharpe = perf_d.get("realized_sharpe", 1.26)
            p_badge = "<span class='badge-alert'>🔴 Sharpe Alarmı</span>" if p_alarm else "<span class='badge-stable'>🟢 Stabil</span>"
            p_det = perf_d.get("details", f"Gerçekleşen Sharpe={p_sharpe:.2f}")
            sharpe_display = f"{p_sharpe:.2f}"
        else:
            p_badge = "<span class='badge-stable'>🟢 Beklemede (Paper Başlangıcı)</span>"
            p_det = "İlk 6-8 rebalance kontrolü sonrasında hareketli Sharpe hesaplanmaya başlayacaktır."
            sharpe_display = "Hesaplanıyor..."
            
        st.markdown(f"""
        <div class="quant-card">
            <h4 style="color: #60a5fa; margin-top: 0;">Katman 3 — Performans Aşınması</h4>
            <p style="font-size: 0.84rem; color: #94a3b8;">
                Sistemin hareketli Sharpe oranının kilit kutu seviyesinden belirgin (%40+) sapma gösterip göstermediğini izler.
            </p>
            <hr style="border-color: rgba(255,255,255,0.06); margin: 12px 0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>Referans Sharpe:</span>
                <b style="color: #34d399;">1.26</b>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>%40 Düşüş Alarm Eşiği:</span>
                <b style="color: #f87171;">≤ 0.75</b>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>Gerçekleşen Sharpe:</span>
                <b>{sharpe_display}</b>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span>Kritik Eşik Kontrolü:</span>
                {p_badge}
            </div>
            <p style="font-size: 0.78rem; color: #64748b; margin-top: 10px;">
                <i>*{p_det}</i>
            </p>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# SAYFA 4: KÜMÜLATİF GETİRİ VE PERFORMANS
# ═══════════════════════════════════════════════════════════════════════════
elif sayfa == "📈 Kümülatif Getiri & Performans":
    st.subheader("📈 Kümülatif Getiri ve Karşılaştırmalı Performans")
    st.caption("Dondurulmuş modelin kilit kutu (out-of-sample) resmi performansı ve cari paper trading kümülatif getiri takibi.")

    tab_kilit, tab_paper = st.tabs([
        "🏛️ Kilit Kutu Doğrulanmış Resmi Performans (2025Q2 - 2026Q2)",
        "🟢 Cari Paper Trading Takibi (2026-09 ve Sonrası)"
    ])

    with tab_kilit:
        st.markdown("#### 🏛️ 15 Aylık Kilit Kutu (Out-of-Sample) Kesinleşmiş Doğrulama Raporu")
        st.caption("Model parametreleri dondurulmuş (depth=2, leaves=3, lr=0.03), 2018-2025 verisiyle eğitilmiş ve ilk kez kilit kutuda test edilmiştir.")

        # 5 Büyük KPI Kartı
        kc1, kc2, kc3, kc4, kc5 = st.columns(5)
        with kc1:
            st.metric("Model K=10 Getiri", "+%137.3", "+%75.9 BIST 100 Üstü Alfa")
        with kc2:
            st.metric("BIST 100 Endeksi", "+%61.4", "Piyasa Kıstası")
        with kc3:
            st.metric("Resmi Sharpe Oranı", "3.41", "Eşik: 1.26 (+2.15 Prim)")
        with kc4:
            st.metric("Maksimum Drawdown", "%0.0", "5 Çeyrek Sıfır DD")
        with kc5:
            st.metric("Monte Carlo p-Değeri", "p = 0.000", "100 Tohum Placebo")

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # 2 Panelli Kilit Kutu Grafiği
        fig_kk = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[0.70, 0.30],
            subplot_titles=("Kümülatif Sermaye Büyümesi (Başlangıç = 100 TL)", "Dönemsel Net Alfa (Model - BIST 100 %)")
        )

        ceyrekler = ["2025Q1 (Baz)", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"]
        k10_cum = [100.0, 124.67, 127.39, 147.12, 182.88, 237.30]
        k15_cum = [100.0, 124.67, 127.39, 147.12, 182.88, 195.90]
        xu100_cum = [100.0, 125.21, 123.39, 152.26, 156.34, 161.40]
        placebo_cum = [100.0, 129.33, 123.88, 143.25, 158.39, 153.10]

        # 1. K=10 Çizgisi
        fig_kk.add_trace(go.Scatter(
            x=ceyrekler, y=k10_cum,
            mode="lines+markers",
            name="Model K=10 (Nihai Portföy)",
            line=dict(color="#00e676", width=3.5),
            marker=dict(size=9, color="#00e676")
        ), row=1, col=1)

        # 2. K=15 Çizgisi
        fig_kk.add_trace(go.Scatter(
            x=ceyrekler, y=k15_cum,
            mode="lines+markers",
            name="Model K=15 (Genişletilmiş)",
            line=dict(color="#38bdf8", width=2.2, dash="dash"),
            marker=dict(size=6, color="#38bdf8")
        ), row=1, col=1)

        # 3. BIST 100 Çizgisi
        fig_kk.add_trace(go.Scatter(
            x=ceyrekler, y=xu100_cum,
            mode="lines+markers",
            name="BIST 100 (XU100 Kıstas)",
            line=dict(color="#f59e0b", width=2.5, dash="dot"),
            marker=dict(size=6, color="#f59e0b")
        ), row=1, col=1)

        # 4. Placebo Çizgisi
        fig_kk.add_trace(go.Scatter(
            x=ceyrekler, y=placebo_cum,
            mode="lines",
            name="100 Tohum Placebo Ort.",
            line=dict(color="#64748b", width=1.5, dash="dot")
        ), row=1, col=1)

        # Çeyreklik Alfa Barları
        alfa_ceyrekler = ["2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"]
        alfalar = [-0.54, 3.63, -7.91, 21.63, 3.88]
        alfa_colors = ["#10b981" if a >= 0 else "#ef4444" for a in alfalar]

        fig_kk.add_trace(go.Bar(
            x=alfa_ceyrekler, y=alfalar,
            marker_color=alfa_colors,
            name="Çeyreklik Alfa (%)",
            text=[f"%{a:+.2f}" for a in alfalar],
            textposition="outside",
            showlegend=False
        ), row=2, col=1)
        fig_kk.add_hline(y=0, line_dash="solid", line_color="#64748b", line_width=1, row=2, col=1)

        fig_kk.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0b0f19",
            plot_bgcolor="#111827",
            height=600,
            margin=dict(l=30, r=30, t=30, b=30),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig_kk.update_xaxes(gridcolor="#1f293d")
        fig_kk.update_yaxes(gridcolor="#1f293d")
        fig_kk.update_yaxes(title="Portföy Değeri (TL)", row=1, col=1)
        fig_kk.update_yaxes(title="Alfa (%)", row=2, col=1)

        st.plotly_chart(fig_kk, width="stretch")

        # Kilit Kutu Detaylı Tablo
        st.markdown("##### 📋 Çeyreklik Ayrışma Tablosu")
        df_kk_table = pd.DataFrame([
            {"Çeyrek": "2025Q2", "Model K=10 (%)": "+%24.67", "BIST 100 (%)": "+%25.21", "Çeyreklik Net Alfa": "-%0.54", "Placebo (%)": "+%29.33", "Sonuç": "Piyasaya Paralel"},
            {"Çeyrek": "2025Q3", "Model K=10 (%)": "+%2.18", "BIST 100 (%)": "-%1.45", "Çeyreklik Net Alfa": "+%3.63", "Placebo (%)": "-%4.21", "Sonuç": "Piyasa Düşerken Pozitif"},
            {"Çeyrek": "2025Q4", "Model K=10 (%)": "+%15.49", "BIST 100 (%)": "+%23.40", "Çeyreklik Net Alfa": "-%7.91", "Placebo (%)": "+%15.63", "Sonuç": "Ralliye Katıldı"},
            {"Çeyrek": "2026Q1", "Model K=10 (%)": "+%24.31", "BIST 100 (%)": "+%2.68", "Çeyreklik Net Alfa": "+%21.63", "Placebo (%)": "+%10.57", "Sonuç": "🔥 Büyük Pozitif Ayrışma"},
            {"Çeyrek": "2026Q2", "Model K=10 (%)": "+%7.12", "BIST 100 (%)": "+%3.24", "Çeyreklik Net Alfa": "+%3.88", "Placebo (%)": "-%3.65", "Sonuç": "🔥 Pozitif Alfa"}
        ])
        st.dataframe(df_kk_table, width="stretch", hide_index=True)

    with tab_paper:
        st.markdown("#### 🟢 Cari Paper Trading Kümülatif Getiri İzleme")
        st.caption("İnkübasyon döneminde gerçekleşen 14 günlük periyot getirileri ve kıyaslama eğrisi.")

        if not df_logs.empty and len(df_logs) >= 1:
            fig_cum = go.Figure()
            tarihler = df_logs["tarih"].tolist()
            m_rets = [float(str(r).replace("%", "")) for r in df_logs["model_getiri_yuzde"]]
            x_rets = [float(str(r).replace("%", "")) for r in df_logs["bist100_getiri_yuzde"]]
            m_cum = np.cumprod(1.0 + np.array(m_rets) / 100.0) - 1.0
            x_cum = np.cumprod(1.0 + np.array(x_rets) / 100.0) - 1.0

            fig_cum.add_trace(go.Scatter(
                x=tarihler,
                y=m_cum * 100,
                mode="lines+markers",
                name="V3 Quant Model",
                line=dict(color="#00e676", width=3),
                marker=dict(size=8, color="#00e676")
            ))
            fig_cum.add_trace(go.Scatter(
                x=tarihler,
                y=x_cum * 100,
                mode="lines+markers",
                name="BIST 100 (XU100)",
                line=dict(color="#f59e0b", width=2, dash="dot"),
                marker=dict(size=6, color="#f59e0b")
            ))
            fig_cum.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0b0f19",
                plot_bgcolor="#111827",
                height=420,
                margin=dict(l=20, r=20, t=30, b=20),
                xaxis=dict(gridcolor="#1f293d"),
                yaxis=dict(gridcolor="#1f293d", title="Kümülatif Getiri (%)"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_cum, width="stretch")

            st.markdown("##### 📜 Paper Trading İşlem Geçmişi")
            st.dataframe(df_logs.sort_index(ascending=False), width="stretch", hide_index=True)
        else:
            st.info("Kümülatif getiri grafiği için en az bir dönem log kaydı gerekmektedir.")


# ═══════════════════════════════════════════════════════════════════════════
# SAYFA 5: GERÇEK PORTFÖYÜM (KİŞİSEL TAKİP)
# KRİTİK İZOLASYON: paper_portfolio_v4.json, V4 motoru, Telegram botu ve
# drift sistemi bu bloğu hiç görmez. Sadece data/user_real_portfolio.json
# okunur/yazılır. kasa_buyuklugu değişkeni bu blokta kesinlikle kullanılmaz.
# ═══════════════════════════════════════════════════════════════════════════
elif sayfa == "👤 Gerçek Portföyüm (Kişisel)":
    import uuid as _uuid
    from datetime import date as _date

    st.subheader("👤 Gerçek Portföyüm — Kişisel BİST Takip Defteri")
    st.caption("Kendi hisse alımlarınızı kaydedin ve kâr/zarar takibi yapın. V4 quant motorundan tamamen bağımsızdır.")

    # Bilgi Baneri
    st.markdown("""
    <div style="background: rgba(59, 130, 246, 0.10); border: 1px solid rgba(59, 130, 246, 0.35);
                border-left: 5px solid #3b82f6; border-radius: 10px; padding: 12px 18px; margin-bottom: 22px;">
        <div style="color: #93c5fd; font-weight: 600; font-size: 0.92rem; margin-bottom: 4px;">
            ℹ️ KİŞİSEL TAKİP SEKMESİ — V4 Motorundan Tam Bağımsız
        </div>
        <div style="color: #cbd5e1; font-size: 0.82rem; line-height: 1.5;">
            Bu sekme <b>tamamen kişisel takip amaçlıdır</b>. Veriler <code>data/user_real_portfolio.json</code>
            dosyasına kaydedilir. V4 quant motoru, drift sistemi, Telegram bildirimleri ve
            <code>paper_portfolio_v4.json</code> bu veriden <b>habersizdir ve etkilenmez</b>.
            Fiyat verileri <b>diskteki son günlük kapanış verisinden</b> okunur — gerçek zamanlı akış değildir.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Cüzdan verisini yükle (V4 portföyü ile sıfır kesişim)
    _wallet_data = wallet_load()
    _holdings = _wallet_data.get("holdings", [])

    # ─── KPI ÖZET KARTLARI (Sadece pozisyon varsa) ───────────────────────────
    if _holdings:
        _toplam_maliyet = 0.0
        _toplam_piyasa = 0.0
        _eskime_sayaci = 0
        _today = _date.today().isoformat()
        _satirlar = []

        for _h in _holdings:
            _sembol = _h["sembol"]
            _islemler = _h.get("islemler", [])
            _toplam_lot = sum(float(i.get("lot", 0)) for i in _islemler)
            _ort_maliyet = float(_h.get("ortalama_maliyet", 0.0))
            _maliyet_t = _toplam_lot * _ort_maliyet

            _son_fiyat, _veri_tarihi = wallet_get_last_price(_sembol)

            if _son_fiyat is not None and _veri_tarihi is not None:
                _piyasa_t = _toplam_lot * _son_fiyat
                _kz_tl = _piyasa_t - _maliyet_t
                _kz_pct = (_kz_tl / _maliyet_t * 100.0) if _maliyet_t > 0 else 0.0
                try:
                    _gun_farki = (_date.fromisoformat(_today) - _date.fromisoformat(_veri_tarihi)).days
                    _veri_durum = f"⚠️ {_gun_farki}g eski" if _gun_farki > 5 else f"✅ {_veri_tarihi}"
                    if _gun_farki > 5:
                        _eskime_sayaci += 1
                except Exception:
                    _veri_durum = f"✅ {_veri_tarihi}"
                _fiyat_s = f"₺{_son_fiyat:,.2f}"
                _piyasa_s = f"₺{_piyasa_t:,.0f}"
                _kz_pct_s = f"%{_kz_pct:+.2f}"
                _kz_tl_s = f"₺{_kz_tl:+,.2f}"
            else:
                _piyasa_t = 0.0
                _kz_tl = 0.0
                _kz_pct = 0.0
                _veri_durum = "🔴 Veri Yok"
                _fiyat_s = "—"
                _piyasa_s = "—"
                _kz_pct_s = "—"
                _kz_tl_s = "—"

            _toplam_maliyet += _maliyet_t
            _toplam_piyasa += _piyasa_t
            _satirlar.append({
                "Hisse": _sembol.replace(".IS", ""),
                "Sektör": cfg.HISSE_SEKTOR_V2.get(_sembol, "DİĞER"),
                "Toplam Lot": int(_toplam_lot),
                "Ort. Maliyet (₺)": f"₺{_ort_maliyet:,.2f}",
                "Son Fiyat (₺)": _fiyat_s,
                "Piyasa Değeri (₺)": _piyasa_s,
                "K/Z (%)": _kz_pct_s,
                "K/Z (₺)": _kz_tl_s,
                "Veri Tarihi": _veri_durum,
            })

        _toplam_kz = _toplam_piyasa - _toplam_maliyet
        _toplam_kz_pct = (_toplam_kz / _toplam_maliyet * 100.0) if _toplam_maliyet > 0 else 0.0
        _kz_renk = "#34d399" if _toplam_kz >= 0 else "#f87171"
        _stale_badge = (
            f"<span class='badge-alert'>⚠️ {_eskime_sayaci} Eski Fiyat</span>"
            if _eskime_sayaci > 0
            else "<span class='badge-stable'>✅ Veriler Güncel</span>"
        )
        _son_kayit = str(_wallet_data.get("son_guncelleme") or "Henüz kaydedilmedi")[:19]

        wk1, wk2, wk3, wk4 = st.columns(4)
        with wk1:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-title">Toplam Maliyet</div>
                <div class="metric-value">₺{_toplam_maliyet:,.0f}</div>
                <div class="metric-subtitle">{len(_holdings)} hisse pozisyonu</div>
            </div>
            """, unsafe_allow_html=True)
        with wk2:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-title">Güncel Piyasa Değeri</div>
                <div class="metric-value">₺{_toplam_piyasa:,.0f}</div>
                <div class="metric-subtitle">Diskten son kapanış</div>
            </div>
            """, unsafe_allow_html=True)
        with wk3:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-title">Toplam Net K/Z</div>
                <div class="metric-value" style="color: {_kz_renk};">₺{_toplam_kz:+,.0f}</div>
                <div class="metric-subtitle">%{_toplam_kz_pct:+.2f} toplam getiri</div>
            </div>
            """, unsafe_allow_html=True)
        with wk4:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-title">Veri Tazeliği</div>
                <div class="metric-value" style="font-size: 1.05rem; padding-top: 6px;">{_stale_badge}</div>
                <div class="metric-subtitle">Son kayıt: {_son_kayit}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

        # ─── HOLDİNG TABLOSU ─────────────────────────────────────────────────
        st.markdown("#### 📋 Hisse Pozisyonları")
        _gorsel_sutunlar = ["Hisse", "Sektör", "Toplam Lot", "Ort. Maliyet (₺)",
                            "Son Fiyat (₺)", "Piyasa Değeri (₺)", "K/Z (%)", "K/Z (₺)", "Veri Tarihi"]
        st.dataframe(pd.DataFrame(_satirlar)[_gorsel_sutunlar], width="stretch", hide_index=True)

        # ─── V4 SİNYAL ÖRTÜŞME PANELİ (salt okunur) ─────────────────────────
        st.markdown("#### 🔗 V4 Model Sinyal Örtüşmesi (Salt Okunur Bilgi)")
        st.caption("V4 portföyü bu bilgiden etkilenmez. Hangi hisselerinizin model listesinde olduğunu gösterir.")
        _v4_set = set(positions.keys())   # positions: app.py üstünde V4'ten yüklü
        _wallet_set = {h["sembol"] for h in _holdings}
        _oc1, _oc2 = st.columns(2)
        with _oc1:
            _ortusen = sorted(_wallet_set & _v4_set)
            st.markdown(f"**✅ V4 ile Örtüşen ({len(_ortusen)} hisse):**")
            if _ortusen:
                for _s in _ortusen:
                    st.markdown(f"<span class='badge-stable' style='margin: 3px;'>{_s.replace('.IS','')}</span>",
                                unsafe_allow_html=True)
            else:
                st.caption("V4 portföyüyle örtüşen hisse yok.")
        with _oc2:
            _yalniz = sorted(_wallet_set - _v4_set)
            st.markdown(f"**⬜ Sadece Cüzdanınızda ({len(_yalniz)} hisse):**")
            if _yalniz:
                for _s in _yalniz:
                    st.markdown(f"<span class='badge-lock' style='margin: 3px;'>{_s.replace('.IS','')}</span>",
                                unsafe_allow_html=True)
            else:
                st.caption("Tüm hisseleriniz V4'te mevcut.")

        st.divider()
    else:
        st.info("📭 Henüz hisse kaydı yok. Aşağıdaki formu kullanarak ilk alımınızı girin.")

    # ─── YENİ ALIM EKLEME FORMU ──────────────────────────────────────────────
    with st.expander("➕ Yeni Hisse Alımı Ekle", expanded=not bool(_holdings)):
        with st.form("wallet_add_form", clear_on_submit=True):
            _fa1, _fa2 = st.columns(2)
            with _fa1:
                _bist88 = sorted([s for s in getattr(cfg, "HISSELER", []) if isinstance(s, str)])
                _yeni_sembol = st.selectbox(
                    "Hisse (BIST 88):",
                    _bist88,
                    format_func=lambda s: f"{s.replace('.IS', '')} — {cfg.HISSE_SEKTOR.get(s, 'BIST')}"
                )
                _yeni_lot = st.number_input("Lot Miktarı:", min_value=1, max_value=1_000_000, value=100, step=1)
            with _fa2:
                _yeni_fiyat = st.number_input("Alış Fiyatı (₺):", min_value=0.01, max_value=999_999.0,
                                              value=100.0, step=0.01, format="%.2f")
                _yeni_tarih = st.date_input("İşlem Tarihi:", value=datetime.now().date())
            _yeni_not = st.text_input("Not (opsiyonel):", placeholder="Örn: İlk alım, ortalama düşürme...")

            if st.form_submit_button("➕ Bu Alımı Kaydet", type="primary"):
                _yeni_islem = {
                    "tarih": str(_yeni_tarih),
                    "lot": int(_yeni_lot),
                    "maliyet_fiyat": float(_yeni_fiyat),
                    "not": _yeni_not.strip(),
                }
                _mevcut_idx = next((i for i, h in enumerate(_holdings) if h["sembol"] == _yeni_sembol), None)
                if _mevcut_idx is not None:
                    _holdings[_mevcut_idx]["islemler"].append(_yeni_islem)
                    _holdings[_mevcut_idx]["lot"] = sum(float(i["lot"]) for i in _holdings[_mevcut_idx]["islemler"])
                    _holdings[_mevcut_idx]["ortalama_maliyet"] = wallet_compute_avg_cost(_holdings[_mevcut_idx]["islemler"])
                    _msg = f"✅ {_yeni_sembol.replace('.IS','')} için yeni alım eklendi — ort. maliyet güncellendi."
                else:
                    _holdings.append({
                        "id": str(_uuid.uuid4()),
                        "sembol": _yeni_sembol,
                        "lot": float(_yeni_lot),
                        "islemler": [_yeni_islem],
                        "ortalama_maliyet": float(_yeni_fiyat),
                    })
                    _msg = f"✅ {_yeni_sembol.replace('.IS','')} portföye eklendi — {_yeni_lot} lot @ ₺{_yeni_fiyat:.2f}"
                _wallet_data["holdings"] = _holdings
                if wallet_save(_wallet_data):
                    st.success(_msg)
                    time.sleep(0.5)
                    st.rerun()

    # ─── POZİSYON SİLME ─────────────────────────────────────────────────────
    if _holdings:
        with st.expander("🗑️ Pozisyon Yönetimi — Hisse Kaldır", expanded=False):
            st.caption("Seçilen hissenin tüm alım kayıtları kalıcı olarak silinir.")
            _sil_options = [h["sembol"] for h in _holdings]
            _sil_sec = st.selectbox(
                "Kaldırılacak Hisse:",
                _sil_options,
                format_func=lambda s: (
                    f"{s.replace('.IS', '')} — "
                    f"{int(sum(float(i.get('lot', 0)) for i in next((h for h in _holdings if h['sembol'] == s), {}).get('islemler', [])))} lot"
                )
            )
            if st.button(f"🗑️ {_sil_sec.replace('.IS', '')} Kaydını Sil", type="secondary", key="wallet_sil_btn"):
                st.session_state["wallet_confirm_delete"] = _sil_sec

            if st.session_state.get("wallet_confirm_delete") == _sil_sec:
                st.warning(f"⚠️ **{_sil_sec.replace('.IS', '')}** için tüm alım kayıtları silinecek. Bu işlem **geri alınamaz!**")
                _cc1, _cc2 = st.columns(2)
                with _cc1:
                    if st.button("✅ Evet, Kalıcı Sil", type="primary", key="wallet_sil_evet"):
                        _wallet_data["holdings"] = [h for h in _holdings if h["sembol"] != _sil_sec]
                        if wallet_save(_wallet_data):
                            st.success(f"✅ {_sil_sec.replace('.IS', '')} portföyden kaldırıldı.")
                            st.session_state.pop("wallet_confirm_delete", None)
                            time.sleep(0.4)
                            st.rerun()
                with _cc2:
                    if st.button("❌ İptal", key="wallet_sil_iptal"):
                        st.session_state.pop("wallet_confirm_delete", None)
                        st.rerun()

        # ─── TEHLİKELİ BÖLGE: TÜM PORTFÖYÜ SIFIRLA ─────────────────────────
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        with st.expander("🚨 Tehlikeli Bölge — Tüm Kişisel Portföyü Sıfırla", expanded=False):
            st.error("🚨 Bu işlem tüm kişisel hisse kayıtlarını kalıcı olarak siler. **V4 paper portföyü ve motoru kesinlikle etkilenmez.**")
            if st.button("🚨 Tüm Portföyü Sıfırla", type="secondary", key="wallet_reset_btn"):
                st.session_state["wallet_confirm_reset"] = True
            if st.session_state.get("wallet_confirm_reset"):
                st.warning("⚠️ **SON UYARI:** Tüm kişisel portföy sıfırlanacak. İşlem **GERİ ALINAMAZ!**")
                _rc1, _rc2 = st.columns(2)
                with _rc1:
                    if st.button("✅ Evet, Tümünü Sıfırla", type="primary", key="wallet_reset_evet"):
                        _wallet_data["holdings"] = []
                        if wallet_save(_wallet_data):
                            st.success("✅ Tüm kişisel portföy sıfırlandı.")
                            st.session_state.pop("wallet_confirm_reset", None)
                            time.sleep(0.4)
                            st.rerun()
                with _rc2:
                    if st.button("❌ Vazgeç", key="wallet_reset_iptal"):
                        st.session_state.pop("wallet_confirm_reset", None)
                        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# SAYFA 6: KANTITATIF HiSSE RoNTGENi (X-RAY)
# YERLESİM KARAR GEREKCEṠI: Tam genislik Bloomberg Terminal layoutu,
# ranking sekmesine sigamaz. Kullanici akisi: Siralama -> Rontgen (derin incele).
# SALT OKUMA: Hicbir dosyaya, JSON'a veya model yapina yazma yapilmaz.
# Tum degiskenler _xr_ prefix'i ile izole edilmistir.
# ═══════════════════════════════════════════════════════════════════════════
elif sayfa == "🔍 Hisse Röntgeni (X-Ray)":

    # X-Ray 2.0 Bloomberg Grid CSS
    st.markdown("""
    <style>
    .xray-header {
        background: linear-gradient(135deg, rgba(15,23,42,0.97) 0%, rgba(30,41,59,0.92) 100%);
        border: 1px solid rgba(99,102,241,0.45);
        border-left: 6px solid #6366f1;
        border-radius: 14px;
        padding: 20px 28px;
        margin-bottom: 20px;
        box-shadow: 0 10px 40px -10px rgba(99,102,241,0.30);
    }
    .xray-ticker { font-size: 2.3rem; font-weight: 800; color: #f1f5f9; letter-spacing: -0.03em; }
    .xray-sector { font-size: 0.83rem; color: #64748b; font-weight: 500; letter-spacing: 0.09em; text-transform: uppercase; margin-top: 4px; }
    .xr-grid-box {
        background: rgba(17,24,39,0.72);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 16px;
    }
    .xr-factor-wrap {
        background: rgba(17,24,39,0.65);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 13px;
        padding: 18px 20px;
        margin-bottom: 16px;
    }
    .xr-factor-row { display: flex; align-items: center; gap: 10px; margin-bottom: 11px; }
    .xr-fak-label { width: 195px; flex-shrink: 0; }
    .xr-fak-name { font-size: 0.82rem; font-weight: 500; color: #cbd5e1; }
    .xr-fak-sub  { font-size: 0.69rem; color: #475569; margin-top: 1px; }
    .xr-bar-bg   { flex: 1; height: 8px; background: rgba(255,255,255,0.06); border-radius: 999px; overflow: hidden; }
    .xr-bar-fill { height: 100%; border-radius: 999px; }
    .xr-fak-val  { width: 75px; text-align: right; font-size: 0.84rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; flex-shrink: 0; }
    .xr-fak-pct  { width: 36px; text-align: right; font-size: 0.69rem; color: #475569; flex-shrink: 0; }
    .xr-chip-pos {
        background: rgba(52,211,153,0.14);
        border: 1px solid rgba(52,211,153,0.35);
        color: #34d399;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.77rem;
        font-weight: 600;
        margin: 3px 4px 3px 0;
        display: inline-block;
    }
    .xr-chip-neg {
        background: rgba(248,113,113,0.14);
        border: 1px solid rgba(248,113,113,0.35);
        color: #f87171;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.77rem;
        font-weight: 600;
        margin: 3px 4px 3px 0;
        display: inline-block;
    }
    .xr-stat-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 10px;
        margin-top: 10px;
    }
    .xr-stat-card {
        background: rgba(30,41,59,0.50);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 8px;
        padding: 10px 12px;
    }
    .xr-stat-title { font-size: 0.70rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
    .xr-stat-val { font-size: 1.05rem; font-weight: 700; color: #f1f5f9; font-family: 'JetBrains Mono', monospace; margin-top: 2px; }
    .xr-risk-panel { background: rgba(17,24,39,0.75); border: 1px solid rgba(255,255,255,0.07); border-radius: 12px; padding: 18px 20px; margin-bottom: 16px; }
    .xr-risk-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .xr-risk-label { font-size: 0.79rem; color: #94a3b8; }
    .xr-divider { border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 12px 0; }
    .xr-rel-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
        margin-top: 10px;
    }
    .xr-rel-box {
        background: rgba(30,41,59,0.45);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 8px;
        padding: 10px 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    </style>
    """, unsafe_allow_html=True)

    st.subheader("🔍 Kantitatif Hisse Röntgeni 2.0 — Bloomberg Terminal Paneli")
    st.caption(
        "V4 LambdaMART 7 faktör karnesi, PIT çeyreklik bilanço otopsisi, BIST 100 göreceli güç ve teknik görünüm. "
        "**%100 Salt Okunur** — V4 otonom motoruna ve portföy dosyalarına hiçbir yazma yapılmaz."
    )

    if df_ranking is None or df_ranking.empty:
        st.warning(
            "⚠️ V4 Sıralama önbelleği henüz mevcut değil. Sol menüdeki "
            "'V4 Rebalance Kontrolünü Çalıştır' butonu ile önbelleği oluşturun."
        )
    else:
        # ─── 1. HİSSE SEÇİCİ & CÜZDAN ENTEGRASYONU ──────────────────────────────────
        _xr_df = df_ranking.sort_values("ml_score", ascending=False).reset_index(drop=True)
        _xr_sembol_listesi = _xr_df["sembol"].tolist()
        
        # Kişisel cüzdan durumunu kontrol et
        _xr_wallet = wallet_load()
        _xr_wallet_positions = _xr_wallet.get("positions", {}) if _xr_wallet else {}

        _xr_sc1, _xr_sc2 = st.columns([3, 1])
        with _xr_sc1:
            def _xr_format_sembol(s):
                _tiker = s.replace(".IS", "")
                _sektor = cfg.HISSE_SEKTOR_V2.get(s, cfg.HISSE_SEKTOR.get(s, "BIST"))
                _sira = _xr_sembol_listesi.index(s) + 1
                _flags = []
                if s in positions:
                    _flags.append("💼 V4")
                if s in _xr_wallet_positions:
                    _flags.append("👤 Cüzdan")
                _flag_str = f" — [{', '.join(_flags)}]" if _flags else ""
                return f"#{_sira:02d} • {_tiker} — {_sektor}{_flag_str}"

            _xr_secilen = st.selectbox(
                "🔎 88 Hisse Evreninden Seçin (Arama Destekli):",
                _xr_sembol_listesi,
                format_func=_xr_format_sembol
            )
        with _xr_sc2:
            _xr_rank = _xr_sembol_listesi.index(_xr_secilen) + 1
            _xr_rank_renk = "#34d399" if _xr_rank <= 15 else ("#f59e0b" if _xr_rank <= 30 else "#f87171")
            _xr_rank_label = "Top-15 ✅" if _xr_rank <= 15 else ("Top-30" if _xr_rank <= 30 else "İlk 30 Dışı")
            st.markdown(f"""
            <div style="text-align:center; padding: 10px 0;">
                <div style="font-size:0.75rem; color:#64748b; text-transform:uppercase; letter-spacing:.09em;">Model Sırası</div>
                <div style="font-size:2.8rem; font-weight:800; color:{_xr_rank_renk}; line-height:1.1;">
                    #{_xr_rank}<span style="font-size:1.1rem; color:#475569;">/88</span>
                </div>
                <div style="font-size:0.78rem; color:{_xr_rank_renk}; font-weight:600;">{_xr_rank_label}</div>
            </div>
            """, unsafe_allow_html=True)

        # ─── 2. SEÇİLİ HİSSE VERİLERİ VE GERÇEK HACİM HESABI ───────────────────────
        _xr_row = _xr_df[_xr_df["sembol"] == _xr_secilen].iloc[0]
        _xr_ticker = _xr_secilen.replace(".IS", "")
        _xr_sektor = cfg.HISSE_SEKTOR_V2.get(_xr_secilen, cfg.HISSE_SEKTOR.get(_xr_secilen, "BIST"))
        _xr_skor = float(_xr_row.get("ml_score", 0.0))
        _xr_data_age = int(_xr_row.get("data_age_days", 999))
        _xr_decile = int(_xr_row.get("decile", 5))
        _xr_portfoy_var = _xr_secilen in positions
        _xr_pos_data = positions.get(_xr_secilen, {})
        _xr_cuzdan_var = _xr_secilen in _xr_wallet_positions
        _xr_cuzdan_pos = _xr_wallet_positions.get(_xr_secilen, {})

        # Diskten fiyat serisini yükle
        _xr_df_fiyat = load_stock_history(_xr_secilen)

        # Gerçek 20 günlük ortalama TL hacmini hesapla
        _xr_hacim = float(_xr_row.get("avg_tl_hacim_m", 0.0))
        if _xr_hacim <= 0.0 and _xr_df_fiyat is not None and not _xr_df_fiyat.empty and "volume" in _xr_df_fiyat.columns and "close" in _xr_df_fiyat.columns:
            _xr_son20 = _xr_df_fiyat.tail(20)
            _xr_hacim = float((_xr_son20["close"] * _xr_son20["volume"]).mean() / 1e6)

        # ─── 3. BLOOMBERG TERMINAL ÖZET BAŞLIK KARTI ───────────────────────────────
        _xr_badges = []
        if _xr_portfoy_var:
            _xr_badges.append(
                "<span style='background:rgba(52,211,153,.18);border:1px solid #34d399;"
                "color:#34d399;padding:3px 10px;border-radius:6px;font-size:.80rem;font-weight:600;'>"
                "💼 V4 Model Portföyünde</span>"
            )
        if _xr_cuzdan_var:
            _xr_badges.append(
                "<span style='background:rgba(99,102,241,.20);border:1px solid #6366f1;"
                "color:#a5b4fc;padding:3px 10px;border-radius:6px;font-size:.80rem;font-weight:600;'>"
                "👤 Gerçek Cüzdanımda</span>"
            )
        if not _xr_badges:
            _xr_badges.append(
                "<span style='background:rgba(100,116,139,.15);border:1px solid #475569;"
                "color:#94a3b8;padding:3px 10px;border-radius:6px;font-size:.80rem;font-weight:600;'>"
                "⬜ Portföyde Değil</span>"
            )
        _xr_badges_html = " ".join(_xr_badges)
        _xr_decile_bar = "█" * (11 - _xr_decile) + "░" * (_xr_decile - 1)

        st.markdown(f"""
        <div class="xray-header">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
                <div>
                    <div class="xray-ticker">
                        {_xr_ticker}
                        <span style="font-size:1.15rem;color:#6366f1;font-weight:600;margin-left:10px;">
                            • #{_xr_rank}/88
                        </span>
                    </div>
                    <div class="xray-sector">
                        {_xr_sektor} &nbsp;&nbsp;{_xr_badges_html}
                    </div>
                    <div style="font-size:.78rem;color:#475569;margin-top:10px;font-family:'JetBrains Mono',monospace;">
                        Desil [{_xr_decile_bar}] #{_xr_decile}/10
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:.75rem;color:#475569;text-transform:uppercase;letter-spacing:.07em;">V4 LambdaMART Skoru</div>
                    <div style="font-size:2.3rem;font-weight:800;color:#e2e8f0;font-family:'JetBrains Mono',monospace;letter-spacing:-.02em;">{_xr_skor:+.4f}</div>
                    <div style="font-size:.73rem;color:#475569;">Yüksek skor = Daha üst sıra modeli</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ─── 4. 4'LÜ KPI KARTLARI (GERÇEK RAKAMLARLA) ───────────────────────────────
        _xr_kc1, _xr_kc2, _xr_kc3, _xr_kc4 = st.columns(4)
        with _xr_kc1:
            _xr_sira_delta = "Top-15 Portföy Adayı ✅" if _xr_rank <= 15 else ("Top-30 İzleme" if _xr_rank <= 30 else "İlk 30 Dışı")
            st.metric("Model Sırası", f"#{_xr_rank}", _xr_sira_delta)
        with _xr_kc2:
            if _xr_hacim >= 1000:
                _xr_hac_str = f"{_xr_hacim/1000:.1f} Mlyr ₺/gün"
            elif _xr_hacim > 0:
                _xr_hac_str = f"{_xr_hacim:.0f}M ₺/gün"
            else:
                _xr_hac_str = "Hacim Hesaplanıyor"
            _xr_hac_delta = "✅ Likit (>20M)" if _xr_hacim >= 20 else "⚠️ Likidite Düşük (<20M)"
            st.metric("Ort. Günlük Hacim", _xr_hac_str, _xr_hac_delta)
        with _xr_kc3:
            _xr_bil_delta = "✅ Taze Bilanço" if _xr_data_age <= 100 else f"⚠️ {_xr_data_age - 100}g Aşıldı"
            st.metric("Bilanço Yaşı", f"{_xr_data_age} gün", _xr_bil_delta)
        with _xr_kc4:
            if _xr_portfoy_var:
                _xr_ep = float(_xr_pos_data.get("entry_price") or 1.0)
                _xr_lp = float(_xr_pos_data.get("last_price") or _xr_ep)
                _xr_kz = ((_xr_lp / _xr_ep) - 1.0) * 100.0 if _xr_ep > 0 else 0.0
                _xr_days = int(_xr_pos_data.get("days_held") or 0)
                st.metric("V4 Portföy Getirisi", f"%{float(_xr_kz or 0.0):+.2f}", f"{_xr_days} gün tutuldu")
            elif _xr_cuzdan_var:
                _xr_c_lot = int(_xr_cuzdan_pos.get("lot", 0))
                _xr_c_cost = float(_xr_cuzdan_pos.get("maliyet", 0.0))
                _xr_c_last = float(_xr_df_fiyat["close"].iloc[-1]) if _xr_df_fiyat is not None and not _xr_df_fiyat.empty else _xr_c_cost
                _xr_c_kz_pct = ((_xr_c_last - _xr_c_cost) / _xr_c_cost * 100) if _xr_c_cost > 0 else 0.0
                st.metric("Cüzdan Kâr/Zarar", f"%{_xr_c_kz_pct:+.2f}", f"{_xr_c_lot} lot pozisyon")
            else:
                st.metric("Portföy Durumu", "Takipte", "Portföy Dışı")

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        # ═══════════════════════════════════════════════════════════════════════════
        # 5. İKİ SÜTUNLU BLOOMBERG GRID (SOL: QUANT & BİLANÇO | SAĞ: TEKNİK & RİSK)
        # ═══════════════════════════════════════════════════════════════════════════
        _xr_col_l, _xr_col_r = st.columns([1.05, 1.15])

        # ───────────────────────────────────────────────────────────────────────────
        # SOL SÜTUN: QUANT KARNESİ + MODEL AÇIKLAMASI + BİLANÇO OTOPSİSİ
        # ───────────────────────────────────────────────────────────────────────────
        with _xr_col_l:
            
            # ── A. 7 FAKTÖR KARNESİ ────────────────────────────────────────────────
            st.markdown("#### 🧦 Faktör Karnesi (Kesitsel Evren Konumu)")
            st.caption("Her çubuk hissenin 88 hisseli evrendeki göreceli konumunu gösterir (%0-%100 kesitsel skala).")

            _xr_faktorler = [
                {
                    "key": "reel_eps_growth",
                    "label": "📊 Reel Kâr Büyümesi",
                    "sub": "V4 öncü faktör — Enflasyondan arındırılmış EPS",
                    "val_fmt": lambda v: f"%{v*100:+.1f}",
                    "bar_fn": lambda v: min(max(int((v + 1.0) / 2.0 * 100), 0), 100),
                    "ana": True, "tag": "🔑 ANA",
                },
                {
                    "key": "z_roe",
                    "label": "💰 Özsermaye Kârlılığı (ROE)",
                    "sub": "Return on Equity — kesitsel Z-Skoru",
                    "val_fmt": lambda v: f"{v:+.2f}σ",
                    "bar_fn": lambda v: min(max(int((v + 3.0) / 6.0 * 100), 0), 100),
                    "ana": False, "tag": None,
                },
                {
                    "key": "z_pb",
                    "label": "📉 Ters F/DD (Değerleme)",
                    "sub": "Düşük F/DD = yüksek skor (ucuz hisse)",
                    "val_fmt": lambda v: f"{v:+.2f}σ",
                    "bar_fn": lambda v: min(max(int((v + 3.0) / 6.0 * 100), 0), 100),
                    "ana": False, "tag": None,
                },
                {
                    "key": "z_borc",
                    "label": "🏦 Borç/EBITDA (Ters)",
                    "sub": "Düşük borç = yüksek skor (sağlam bilanço)",
                    "val_fmt": lambda v: f"{v:+.2f}σ",
                    "bar_fn": lambda v: min(max(int((v + 3.0) / 6.0 * 100), 0), 100),
                    "ana": False, "tag": None,
                },
                {
                    "key": "z_mom",
                    "label": "🚀 12-1 Momentum",
                    "sub": "12 aylık getiride son 1 ay hariç ivme",
                    "val_fmt": lambda v: f"{v:+.2f}σ",
                    "bar_fn": lambda v: min(max(int((v + 3.0) / 6.0 * 100), 0), 100),
                    "ana": False, "tag": None,
                },
                {
                    "key": "z_fcf",
                    "label": "💵 Serbest Nakit Akışı (FCF)",
                    "sub": "FCF Verimi kesitsel sırası",
                    "val_fmt": lambda v: f"{v:+.2f}σ",
                    "bar_fn": lambda v: min(max(int((v + 3.0) / 6.0 * 100), 0), 100),
                    "ana": False, "tag": None,
                },
            ]

            _xr_rows_html = []
            _xr_toplam_skor = 0.0
            _xr_faktor_sayisi = 0
            _xr_positives = []
            _xr_negatives = []

            for _fak in _xr_faktorler:
                _fk = _fak["key"]
                if _fk not in _xr_row.index:
                    continue
                try:
                    _fv = float(_xr_row[_fk])
                except (ValueError, TypeError):
                    continue

                _fp = _fak["bar_fn"](_fv)
                _fval_str = _fak["val_fmt"](_fv)
                _fana = _fak["ana"]

                # Explainability sınıflandırması
                if _fk == "reel_eps_growth":
                    if _fv >= 0.05:
                        _xr_positives.append((_fak["label"].split()[1], _fval_str))
                    elif _fv <= -0.05:
                        _xr_negatives.append((_fak["label"].split()[1], _fval_str))
                else:
                    if _fv >= 0.30:
                        _xr_positives.append((_fak["label"].split()[1], _fval_str))
                    elif _fv <= -0.30:
                        _xr_negatives.append((_fak["label"].split()[1], _fval_str))

                # Renk belirleme
                if _fp >= 65:
                    _fbar_grad = "linear-gradient(90deg, #059669, #34d399)"
                    _fval_color = "#34d399"
                elif _fp >= 42:
                    _fbar_grad = "linear-gradient(90deg, #b45309, #fbbf24)"
                    _fval_color = "#fbbf24"
                else:
                    _fbar_grad = "linear-gradient(90deg, #991b1b, #f87171)"
                    _fval_color = "#f87171"

                _ftag_html = ""
                if _fak["tag"]:
                    _ftag_html = (
                        f"<span style='background:rgba(99,102,241,.22);border:1px solid #6366f1;"
                        f"color:#a5b4fc;padding:1px 6px;border-radius:4px;font-size:.69rem;"
                        f"font-weight:700;margin-left:4px;'>{_fak['tag']}</span>"
                    )

                _frow_bg = "background:rgba(99,102,241,.06);border-radius:8px;padding:8px 10px;" if _fana else "padding:3px 0;"
                _xr_rows_html.append(
                    f'<div class="xr-factor-row" style="{_frow_bg}">'
                    f'<div class="xr-fak-label">'
                    f'<div class="xr-fak-name">{_fak["label"]} {_ftag_html}</div>'
                    f'<div class="xr-fak-sub">{_fak["sub"]}</div>'
                    f'</div>'
                    f'<div class="xr-bar-bg">'
                    f'<div class="xr-bar-fill" style="width:{_fp}%;background:{_fbar_grad};"></div>'
                    f'</div>'
                    f'<div class="xr-fak-val" style="color:{_fval_color};">{_fval_str}</div>'
                    f'<div class="xr-fak-pct">%{_fp}</div>'
                    f'</div>'
                )
                _xr_toplam_skor += _fp
                _xr_faktor_sayisi += 1

            _xr_karne_skor = int(_xr_toplam_skor / _xr_faktor_sayisi) if _xr_faktor_sayisi > 0 else 0
            _xr_karne_renk = "#34d399" if _xr_karne_skor >= 65 else ("#fbbf24" if _xr_karne_skor >= 42 else "#f87171")
            _xr_karne_label = "🔹 GÜÇLÜ" if _xr_karne_skor >= 65 else ("🟡 ORTA" if _xr_karne_skor >= 42 else "🔴 ZAYIF")

            st.markdown(
                f'<div class="xr-factor-wrap">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">'
                f'<div style="font-size:.75rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em;">Bileşik Karne Skoru</div>'
                f'<div style="font-size:1.35rem;font-weight:800;color:{_xr_karne_renk};">{_xr_karne_skor}/100 &nbsp; {_xr_karne_label}</div>'
                f'</div>'
                + "".join(_xr_rows_html)
                + "</div>",
                unsafe_allow_html=True
            )

            # ── B. MODEL KARAR AÇIKLAMASI (EXPLAINABILITY) ─────────────────────────
            st.markdown("#### 💡 Model Karar Notu: Neden Bu Sırada?")
            
            _xr_pos_chips = "".join([f'<span class="xr-chip-pos">▲ {k}: {v}</span>' for k, v in _xr_positives])
            _xr_neg_chips = "".join([f'<span class="xr-chip-neg">▼ {k}: {v}</span>' for k, v in _xr_negatives])
            
            _xr_pos_html = _xr_pos_chips if _xr_pos_chips else "<span style='font-size:.80rem;color:#64748b;'>Belirgin pozitif ayrışma yok.</span>"
            _xr_neg_html = _xr_neg_chips if _xr_neg_chips else "<span style='font-size:.80rem;color:#34d399;'>🛡️ Belirgin baskı unsuru tespit edilmedi.</span>"

            st.markdown(f"""
            <div class="xr-grid-box">
                <div style="font-size:.78rem; font-weight:700; color:#34d399; margin-bottom:4px;">🟢 MODELİ YUKARI TAŞIYAN POZİTİF FAKTÖRLER:</div>
                <div style="margin-bottom:10px;">{_xr_pos_html}</div>
                <div style="font-size:.78rem; font-weight:700; color:#f87171; margin-bottom:4px;">🔴 PUANI BASKILAYAN RİSK VE ZAYIFLIKLAR:</div>
                <div>{_xr_neg_html}</div>
            </div>
            """, unsafe_allow_html=True)

            # ── C. PIT ÇEYREKLİK BİLANÇO OTOPSİSİ (GERÇEK VERİLERLE) ───────────────
            _xr_df_fund = load_fundamentals(_xr_secilen)
            
            if _xr_df_fund is not None and not _xr_df_fund.empty:
                _xr_last_fund = _xr_df_fund.iloc[-1]
                _xr_is_bank = bool(_xr_last_fund.get("is_bank", False))
                _xr_fund_q = str(_xr_last_fund.get("ceyrek", "Bilanço"))

                # Rakamları derle (sıfır NaN kuralı)
                _xr_net_kar_val = _xr_last_fund.get("net_kar")
                _xr_ozk_val = _xr_last_fund.get("ozkaynaklar")
                _xr_net_kar_str = f"₺{_xr_net_kar_val/1e9:,.1f} Mlyr" if pd.notna(_xr_net_kar_val) else "—"
                _xr_ozk_str = f"₺{_xr_ozk_val/1e9:,.1f} Mlyr" if pd.notna(_xr_ozk_val) else "—"

                _xr_roe_val = _xr_last_fund.get("roe")
                if pd.notna(_xr_roe_val):
                    _xr_roe_str = f"%{_xr_roe_val*100:+.1f}"
                elif pd.notna(_xr_ozk_val) and _xr_ozk_val < 0:
                    _xr_roe_str = "Negatif Özkaynak"
                else:
                    _xr_roe_str = "Nötr"

                _xr_pb_val = _xr_last_fund.get("pb")
                if pd.notna(_xr_pb_val) and _xr_pb_val > 0:
                    _xr_pb_str = f"{_xr_pb_val:.2f}x"
                elif pd.notna(_xr_ozk_val) and _xr_ozk_val <= 0:
                    _xr_pb_str = "Negatif Özkaynak"
                else:
                    _xr_pb_str = "Nötr"

                if _xr_is_bank:
                    _xr_satis_bnk = float(_xr_last_fund.get("satislar") or 0.0) / 1e9
                    _xr_pd_bnk = float(_xr_last_fund.get("piyasa_degeri") or 0.0) / 1e9
                    _xr_npl_val = _xr_last_fund.get("npl_orani")
                    _xr_risk_item = (
                        ("NPL (Takip) Oranı", f"%{_xr_npl_val*100:.2f}")
                        if pd.notna(_xr_npl_val) and _xr_npl_val > 0
                        else ("Piyasa Değeri", f"₺{_xr_pd_bnk:,.1f} Mlyr")
                    )
                    _xr_fund_cards = [
                        ("Net Kâr", _xr_net_kar_str),
                        ("Özkaynaklar", _xr_ozk_str),
                        ("Faiz / Prim Geliri", f"₺{_xr_satis_bnk:,.1f} Mlyr"),
                        ("Özsermaye Kârlılığı", _xr_roe_str),
                        ("F/DD Oranı", _xr_pb_str),
                        _xr_risk_item
                    ]
                else:
                    _xr_satis_val = _xr_last_fund.get("satislar")
                    _xr_satis_str = f"₺{_xr_satis_val/1e9:,.1f} Mlyr" if pd.notna(_xr_satis_val) else "—"
                    _xr_ebitda_val = _xr_last_fund.get("ebitda")
                    _xr_ebitda_str = f"₺{_xr_ebitda_val/1e9:,.1f} Mlyr" if pd.notna(_xr_ebitda_val) else "—"
                    _xr_borc_val = _xr_last_fund.get("net_borc")
                    if pd.notna(_xr_borc_val):
                        _xr_borc_str = f"₺{_xr_borc_val/1e9:,.1f} Mlyr" if abs(_xr_borc_val) > 1e7 else "Nakit Pozitif"
                    else:
                        _xr_borc_str = "Nakit Pozitif"

                    _xr_fund_cards = [
                        ("Net Satışlar (Ciro)", _xr_satis_str),
                        ("Net Kâr", _xr_net_kar_str),
                        ("FAVÖK (EBITDA)", _xr_ebitda_str),
                        ("Net Borç", _xr_borc_str),
                        ("Özsermaye Kârlılığı", _xr_roe_str),
                        ("F/DD Oranı", _xr_pb_str),
                    ]

                _xr_cards_html = "".join([
                    f'<div class="xr-stat-card">'
                    f'<div class="xr-stat-title">{t}</div>'
                    f'<div class="xr-stat-val">{v}</div>'
                    f'</div>'
                    for t, v in _xr_fund_cards
                ])

                st.markdown(f"#### 🏛️ Çeyreklik Bilanço Otopsisi ({_xr_fund_q})")
                st.markdown(f"""
                <div class="xr-grid-box">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                        <span style="font-size:.76rem;color:#94a3b8;font-weight:600;">POINT-IN-TIME KURUMSAL VERİ</span>
                        <span style="font-size:.74rem;color:#34d399;font-weight:600;">✅ {_xr_data_age} gün önce açıklandı</span>
                    </div>
                    <div class="xr-stat-grid">
                        {_xr_cards_html}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info(f"📊 {_xr_ticker} için Point-in-Time bilanço tablosu diskte bulunamadı.")

        # ───────────────────────────────────────────────────────────────────────────
        # SAĞ SÜTUN: FİNANSAL MUM GRAFİĞİ + BIST 100 GÖRECELİ GÜÇ + RİSK KALKANI
        # ───────────────────────────────────────────────────────────────────────────
        with _xr_col_r:
            
            # ── A. 65 GÜNLÜK FİNANSAL MUM GRAFİĞİ (PLOTLY) ─────────────────────────
            st.markdown("#### 📈 Son 65 İşlem Günü — Mum Grafik, Hacim & RSI")

            if _xr_df_fiyat is not None and not _xr_df_fiyat.empty and "close" in _xr_df_fiyat.columns and len(_xr_df_fiyat) >= 20:
                _xr_df_ti = compute_technical_indicators(_xr_df_fiyat)
                _xr_df_sub = _xr_df_ti.tail(65).copy()

                _xr_fig = make_subplots(
                    rows=3, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.03,
                    row_heights=[0.60, 0.18, 0.22],
                    subplot_titles=(None, "İşlem Hacmi", "RSI (14) Momentum")
                )

                # Mum
                _xr_fig.add_trace(go.Candlestick(
                    x=_xr_df_sub.index,
                    open=_xr_df_sub["open"], high=_xr_df_sub["high"],
                    low=_xr_df_sub["low"], close=_xr_df_sub["close"],
                    name="OHLC",
                    increasing_line_color="#00e676", decreasing_line_color="#ff1744",
                    increasing_fillcolor="#00e676", decreasing_fillcolor="#ff1744",
                    line_width=1.2
                ), row=1, col=1)

                # SMA 20 & SMA 50
                if "sma_20" in _xr_df_sub.columns:
                    _xr_fig.add_trace(go.Scatter(
                        x=_xr_df_sub.index, y=_xr_df_sub["sma_20"],
                        line=dict(color="#00d4ff", width=1.8), name="SMA 20"
                    ), row=1, col=1)
                if "sma_50" in _xr_df_sub.columns:
                    _xr_fig.add_trace(go.Scatter(
                        x=_xr_df_sub.index, y=_xr_df_sub["sma_50"],
                        line=dict(color="#ffa726", width=1.5, dash="dot"), name="SMA 50"
                    ), row=1, col=1)

                # V4 Alış Fiyatı Seviyesi
                if _xr_portfoy_var:
                    _xr_ep2 = float(_xr_pos_data.get("entry_price", 0))
                    if _xr_ep2 > 0:
                        _xr_fig.add_hline(
                            y=_xr_ep2,
                            line_dash="dash", line_color="#ffd600", line_width=2.0,
                            annotation_text=f"📍 V4 Alış: ₺{_xr_ep2:.2f}",
                            annotation_position="top right",
                            annotation_font_color="#ffd600", annotation_font_size=10,
                            row=1, col=1
                        )

                # Hacim barları
                _xr_vol_clr = [
                    "rgba(0,230,118,.75)" if c >= o else "rgba(255,23,68,.75)"
                    for c, o in zip(_xr_df_sub["close"], _xr_df_sub["open"])
                ]
                _xr_fig.add_trace(go.Bar(
                    x=_xr_df_sub.index, y=_xr_df_sub["volume"],
                    marker_color=_xr_vol_clr, name="Hacim", showlegend=False
                ), row=2, col=1)

                # RSI
                if "rsi_14" in _xr_df_sub.columns:
                    _xr_fig.add_trace(go.Scatter(
                        x=_xr_df_sub.index, y=_xr_df_sub["rsi_14"],
                        line=dict(color="#c084fc", width=1.9), name="RSI 14"
                    ), row=3, col=1)
                    _xr_fig.add_hline(y=70, line_dash="dash", line_color="#ff5252", line_width=0.9, row=3, col=1)
                    _xr_fig.add_hline(y=30, line_dash="dash", line_color="#69f0ae", line_width=0.9, row=3, col=1)
                    _xr_fig.update_yaxes(range=[15, 85], row=3, col=1)

                _xr_fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#0b0f19", plot_bgcolor="#111827",
                    height=510,
                    margin=dict(l=25, r=25, t=20, b=25),
                    xaxis_rangeslider_visible=False,
                    hovermode="x unified",
                    legend=dict(
                        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                        bgcolor="rgba(17,24,39,.8)", bordercolor="rgba(255,255,255,.1)", borderwidth=1
                    )
                )
                _xr_fig.update_xaxes(
                    rangebreaks=[dict(bounds=["sat", "mon"])],
                    gridcolor="#1f293d", showspikes=True, spikemode="across", spikethickness=1
                )
                _xr_fig.update_yaxes(gridcolor="#1f293d")
                st.plotly_chart(_xr_fig, width="stretch")
            else:
                st.info(f"📊 {_xr_ticker} için yeterli fiyat serisi bulunamadı.")

            # ── B. BIST 100 GÖRECELİ GÜÇ & BETA ANALİZİ ────────────────────────────
            st.markdown("#### ⚖️ BIST 100 Göreceli Güç & Ekstremler")
            _xr_xu_series = load_benchmark_xu100()
            _xr_rel = compute_relative_metrics(_xr_df_fiyat, _xr_xu_series)

            _xr_alfa_1m = _xr_rel.get("alfa_1m")
            _xr_alfa_3m = _xr_rel.get("alfa_3m")
            _xr_beta = _xr_rel.get("beta_60d")
            _xr_dist_high = _xr_rel.get("dist_52w_high")
            _xr_high_52 = _xr_rel.get("high_52w")

            _xr_a1_str = f"%{_xr_alfa_1m:+.1f}" if _xr_alfa_1m is not None else "Hesaplanıyor"
            _xr_a1_clr = "#34d399" if (_xr_alfa_1m or 0) >= 0 else "#f87171"

            _xr_a3_str = f"%{_xr_alfa_3m:+.1f}" if _xr_alfa_3m is not None else "Hesaplanıyor"
            _xr_a3_clr = "#34d399" if (_xr_alfa_3m or 0) >= 0 else "#f87171"

            _xr_beta_str = f"{_xr_beta:.2f}" if _xr_beta is not None else "—"
            _xr_beta_lbl = "Defansif (<1)" if (_xr_beta or 1.0) < 0.95 else ("Piyasa Üstü (>1)" if (_xr_beta or 1.0) > 1.05 else "Piyasa İle Uyumlu")

            _xr_dist_str = f"%{_xr_dist_high:+.1f}" if _xr_dist_high is not None else "—"
            _xr_high_str = f"₺{_xr_high_52:,.2f}" if _xr_high_52 is not None else "—"

            st.markdown(f"""
            <div class="xr-grid-box">
                <div class="xr-rel-grid">
                    <div class="xr-rel-box">
                        <div>
                            <div class="xr-stat-title">1 Aylık Aktif Alfa (vs BIST 100)</div>
                            <div style="font-size:1.15rem; font-weight:700; color:{_xr_a1_clr}; font-family:'JetBrains Mono',monospace;">{_xr_a1_str}</div>
                        </div>
                        <div style="font-size:.70rem; color:#64748b;">Endekse Fark</div>
                    </div>
                    <div class="xr-rel-box">
                        <div>
                            <div class="xr-stat-title">3 Aylık Aktif Alfa (vs BIST 100)</div>
                            <div style="font-size:1.15rem; font-weight:700; color:{_xr_a3_clr}; font-family:'JetBrains Mono',monospace;">{_xr_a3_str}</div>
                        </div>
                        <div style="font-size:.70rem; color:#64748b;">Orta Vade Fark</div>
                    </div>
                    <div class="xr-rel-box">
                        <div>
                            <div class="xr-stat-title">60 Günlük Rolling Beta</div>
                            <div style="font-size:1.15rem; font-weight:700; color:#e2e8f0; font-family:'JetBrains Mono',monospace;">{_xr_beta_str}</div>
                        </div>
                        <div style="font-size:.70rem; color:#64748b;">{_xr_beta_lbl}</div>
                    </div>
                    <div class="xr-rel-box">
                        <div>
                            <div class="xr-stat-title">52H Zirvesine Uzaklık</div>
                            <div style="font-size:1.15rem; font-weight:700; color:#f87171; font-family:'JetBrains Mono',monospace;">{_xr_dist_str}</div>
                        </div>
                        <div style="font-size:.70rem; color:#64748b;">Zirve: {_xr_high_str}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ── C. FAZ-0 TABAN & SAVUNMA KALKANI ───────────────────────────────────
            _xr_faz0_risk = False
            _xr_taban_sayisi = 0
            _xr_faz0_aciklama = "Veri Yetersiz"

            if _xr_df_fiyat is not None and not _xr_df_fiyat.empty and "close" in _xr_df_fiyat.columns and len(_xr_df_fiyat) >= 12:
                _xr_son12 = _xr_df_fiyat.tail(12)
                _xr_getiriler = _xr_son12["close"].pct_change().dropna() * 100
                _xr_taban_sayisi = int((_xr_getiriler <= -9.5).sum())
                _xr_faz0_risk = _xr_taban_sayisi >= 5
                if _xr_faz0_risk:
                    _xr_faz0_aciklama = f"🔴 VETO: Son 10g'de {_xr_taban_sayisi}/5 taban tespit edildi!"
                else:
                    _xr_faz0_aciklama = f"🟢 Temiz: Son 10g'de yalnızca {_xr_taban_sayisi} taban günü."

            _xr_likidite_ok = _xr_hacim >= 20.0
            _xr_bilanco_ok = _xr_data_age <= 100
            _xr_risk_puan = (50 if _xr_faz0_risk else 0) + (25 if not _xr_likidite_ok else 0) + (25 if not _xr_bilanco_ok else 0)
            _xr_genel_risk_str = "🟢 DÜŞÜK" if _xr_risk_puan == 0 else ("🟡 ORTA" if _xr_risk_puan <= 25 else "🔴 YÜKSEK")
            _xr_risk_renk = "#34d399" if _xr_risk_puan == 0 else ("#f59e0b" if _xr_risk_puan <= 25 else "#ef4444")
            _xr_taban_bar_pct = min(_xr_taban_sayisi / 5 * 100, 100)
            _xr_taban_bar_renk = "#ef4444" if _xr_faz0_risk else ("#f59e0b" if _xr_taban_sayisi >= 2 else "#34d399")

            # Portföy / Cüzdan detay kutusu
            _xr_portfoy_detay_html = ""
            if _xr_portfoy_var:
                _xr_p_entry = float(_xr_pos_data.get("entry_price", 0))
                _xr_p_last = float(_xr_pos_data.get("last_price", _xr_p_entry))
                _xr_p_dd = float(_xr_pos_data.get("peak_drawdown_pct", 0.0))
                _xr_p_days = int(_xr_pos_data.get("days_held", 0))
                _xr_p_dd_renk = "#f87171" if _xr_p_dd <= -20 else ("#f59e0b" if _xr_p_dd <= -10 else "#34d399")
                _xr_portfoy_detay_html = (
                    '<hr class="xr-divider">'
                    '<div style="font-size:.80rem;font-weight:600;color:#94a3b8;margin-bottom:8px;">💼 V4 Model Pozisyon Bilgisi</div>'
                    f'<div class="xr-risk-row"><span class="xr-risk-label">Model Giriş Fiyatı</span><span style="font-size:.82rem;font-weight:600;color:#e2e8f0;">₺{_xr_p_entry:,.2f}</span></div>'
                    f'<div class="xr-risk-row"><span class="xr-risk-label">Zirveden Çekilme</span><span style="font-size:.82rem;font-weight:700;color:{_xr_p_dd_renk};">%{_xr_p_dd:.1f}</span></div>'
                    f'<div class="xr-risk-row"><span class="xr-risk-label">Elde Tutulan Süre</span><span style="font-size:.82rem;font-weight:600;color:#e2e8f0;">{_xr_p_days} gün / 60 gün</span></div>'
                )
            elif _xr_cuzdan_var:
                _xr_c_lot = int(_xr_cuzdan_pos.get("lot", 0))
                _xr_c_cost = float(_xr_cuzdan_pos.get("maliyet", 0.0))
                _xr_c_last = float(_xr_df_fiyat["close"].iloc[-1]) if _xr_df_fiyat is not None and not _xr_df_fiyat.empty else _xr_c_cost
                _xr_c_tutar = _xr_c_lot * _xr_c_last
                _xr_c_kz_tl = (_xr_c_last - _xr_c_cost) * _xr_c_lot
                _xr_c_kz_pct = ((_xr_c_last - _xr_c_cost) / _xr_c_cost * 100) if _xr_c_cost > 0 else 0.0
                _xr_c_renk = "#34d399" if _xr_c_kz_tl >= 0 else "#f87171"
                _xr_portfoy_detay_html = (
                    '<hr class="xr-divider">'
                    '<div style="font-size:.80rem;font-weight:600;color:#94a3b8;margin-bottom:8px;">👤 Kişisel Cüzdan Bilgisi</div>'
                    f'<div class="xr-risk-row"><span class="xr-risk-label">Adet / Ortalama Maliyet</span><span style="font-size:.82rem;font-weight:600;color:#e2e8f0;">{_xr_c_lot} lot @ ₺{_xr_c_cost:,.2f}</span></div>'
                    f'<div class="xr-risk-row"><span class="xr-risk-label">Piyasa Değeri</span><span style="font-size:.82rem;font-weight:600;color:#e2e8f0;">₺{_xr_c_tutar:,.2f}</span></div>'
                    f'<div class="xr-risk-row"><span class="xr-risk-label">Kâr / Zarar</span><span style="font-size:.82rem;font-weight:700;color:{_xr_c_renk};">₺{_xr_c_kz_tl:+,.2f} (%{_xr_c_kz_pct:+.2f})</span></div>'
                )

            st.markdown(f"""
            <div class="xr-risk-panel">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <div style="font-size:.75rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em;">Savunma Kalkanı</div>
                    <div style="font-size:1.3rem;font-weight:800;color:{_xr_risk_renk};">{_xr_genel_risk_str}</div>
                </div>
                <hr class="xr-divider">
                <div style="font-size:.79rem;font-weight:600;color:#94a3b8;margin-bottom:4px;">⚡ Faz-0 Ardışık Taban Riski (Son 10 Gün)</div>
                <div style="font-size:.81rem;color:{_xr_taban_bar_renk};margin-bottom:6px;">{_xr_faz0_aciklama}</div>
                <div style="height:6px;background:rgba(255,255,255,.06);border-radius:999px;margin-bottom:4px;">
                    <div style="width:{_xr_taban_bar_pct:.0f}%;height:100%;background:{_xr_taban_bar_renk};border-radius:999px;"></div>
                </div>
                <div style="font-size:.70rem;color:#475569;margin-bottom:12px;">{_xr_taban_sayisi}/5 eşik (≤-%9.5 kapanış)</div>
                <hr class="xr-divider">
                <div class="xr-risk-row">
                    <span class="xr-risk-label">💧 Likidite Kapısı</span>
                    <span style="font-size:.81rem;font-weight:600;color:{"#34d399" if _xr_likidite_ok else "#f87171"};">
                    {"✅ Geçti" if _xr_likidite_ok else "❌ Yetersiz"}</span>
                </div>
                <div class="xr-risk-row">
                    <span class="xr-risk-label">📊 Bilanço Tazeliği</span>
                    <span style="font-size:.81rem;font-weight:600;color:{"#34d399" if _xr_bilanco_ok else "#f59e0b"};">
                    {"✅ " + str(_xr_data_age) + " gün" if _xr_bilanco_ok else "⚠️ " + str(_xr_data_age) + " gün"}</span>
                </div>
                {_xr_portfoy_detay_html}
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

        # ═══════════════════════════════════════════════════════════════════════════
        # 6. ALT BÖLGE (FULL WIDTH): EVREN DAĞILIMI + SEKTOREL EMSAL + ÖZET RAPOR
        # ═══════════════════════════════════════════════════════════════════════════
        
        # ── A. 88 HİSSE EVREN SKOR DAĞILIMI ────────────────────────────────────────
        st.markdown("#### 🏙️ 88 Hisse Evreni — Skor Dağılım Perspektifi")
        st.caption(f"Mor = {_xr_ticker} (seçili) · Yeşil = Top-15 Portföy Adayları · Sarı = Top-30 İzleme · Koyu = Evren Dışı")

        _xr_df_sorted = _xr_df.copy()
        _xr_bar_clrs = []
        for _xi, _xs in enumerate(_xr_df_sorted["sembol"]):
            if _xs == _xr_secilen:
                _xr_bar_clrs.append("#6366f1")
            elif _xi < 15:
                _xr_bar_clrs.append("#34d399")
            elif _xi < 30:
                _xr_bar_clrs.append("#f59e0b")
            else:
                _xr_bar_clrs.append("#1e2d40")

        _xr_fig2 = go.Figure(go.Bar(
            x=_xr_df_sorted["sembol"].str.replace(".IS", ""),
            y=_xr_df_sorted["ml_score"],
            marker_color=_xr_bar_clrs,
            hovertemplate="<b>%{x}</b><br>V4 Skor: %{y:.4f}<extra></extra>"
        ))
        _xr_fig2.add_hline(
            y=_xr_skor,
            line_dash="dot", line_color="#818cf8", line_width=1.8,
            annotation_text=f"↑ {_xr_ticker} ({_xr_skor:+.4f})",
            annotation_font_color="#a5b4fc", annotation_font_size=11,
            annotation_position="top right"
        )
        _xr_fig2.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0b0f19", plot_bgcolor="#111827",
            height=280,
            margin=dict(l=20, r=20, t=20, b=40),
            yaxis=dict(title="V4 LambdaMART Skoru", gridcolor="#1f293d"),
            xaxis=dict(gridcolor="#1f293d", tickangle=-55, tickfont=dict(size=8.5))
        )
        st.plotly_chart(_xr_fig2, width="stretch")

        # ── B. SEKTOREL AKRAN KIYASLAMA TABLOSU ────────────────────────────────────
        st.markdown(f"#### 👥 Sektörel Akran Kıyaslaması ({_xr_sektor})")
        st.caption(f"{_xr_ticker} hissesinin ait olduğu sektördeki diğer hisselerle model sırası ve temel çarpan karşılaştırması.")

        _xr_sektor_df = _xr_df[
            _xr_df["sembol"].apply(lambda s: cfg.HISSE_SEKTOR_V2.get(s, cfg.HISSE_SEKTOR.get(s, "")) == _xr_sektor)
        ].copy()

        if not _xr_sektor_df.empty:
            _xr_sektor_rows = []
            for _si, _srow in _xr_sektor_df.reset_index().iterrows():
                _s_sym = _srow["sembol"]
                _s_tiker = _s_sym.replace(".IS", "")
                _s_is_sel = (_s_sym == _xr_secilen)
                _s_prefix = "👉 " if _s_is_sel else ""
                _s_v4_flag = "💼 Top-15" if _s_sym in positions else ("⭐ İzleme" if int(_srow["rank"]) <= 30 else "—")
                
                _xr_sektor_rows.append({
                    "Hisse": f"{_s_prefix}{_s_tiker}",
                    "Model Sırası": f"#{int(_srow.get('rank') or 0):02d}",
                    "V4 Skoru": f"{float(_srow.get('ml_score') or 0.0):+.4f}",
                    "ROE (Z-Skor)": f"{float(_srow.get('z_roe') or 0.0):+.2f}σ",
                    "F/DD (Z-Skor)": f"{float(_srow.get('z_pb') or 0.0):+.2f}σ",
                    "Reel Büyüme": f"%{float(_srow.get('reel_eps_growth') or 0.0)*100:+.1f}",
                    "Bilanço Yaşı": f"{int(_srow.get('data_age_days') or 0)} gün",
                    "Durum": _s_v4_flag
                })
            
            _xr_df_peer = pd.DataFrame(_xr_sektor_rows)
            st.dataframe(_xr_df_peer, width="stretch", hide_index=True)
        else:
            st.caption("Bu sektörde başka hisse bulunamadı.")

        # ── C. TEK TIKLA ÖZET RÖNTGEN RAPORU KOPYALA ──────────────────────────────
        st.markdown("#### 📋 Tek Tıkla Özet Röntgen Raporu")
        _xr_report_text = f"""🏛️ BIST V4 QUANT HİSSE RÖNTGENİ — {_xr_ticker}
────────────────────────────────────────────────────
• Tarih & Sektör: {datetime.now().strftime('%Y-%m-%d')} | {_xr_sektor}
• Model Sırası: #{_xr_rank} / 88 (Desil #{_xr_decile})
• V4 LambdaMART Skoru: {_xr_skor:+.4f} | Karne Skoru: {_xr_karne_skor}/100 ({_xr_karne_label})
• BIST 100 Göreceli Güç: 1A Alfa: {_xr_a1_str} | 3A Alfa: {_xr_a3_str} | 60g Beta: {_xr_beta_str}
• 52 Hafta Zirve Uzaklığı: {_xr_dist_str} (Zirve: {_xr_high_str})
• Faz-0 Savunma Kalkanı: {_xr_genel_risk_str} (Taban: {_xr_taban_sayisi}/5 | Likidite: {_xr_hac_str})
• Pozitif Katalizörler: {', '.join([f'{k} ({v})' for k, v in _xr_positives]) if _xr_positives else 'Nötr'}
• Negatif Baskılar: {', '.join([f'{k} ({v})' for k, v in _xr_negatives]) if _xr_negatives else 'Yok'}
────────────────────────────────────────────────────
Kurumsal Karar Destek Çıktısıdır | Yatırım Tavsiyesi Değildir"""

        st.code(_xr_report_text, language="markdown")
        st.caption("Yukarıdaki kutunun sağ üstündeki kopyalama ikonuna tıklayarak Telegram, WhatsApp veya notlarınıza yapıştırabilirsiniz.")

st.markdown("---")
st.caption("BIST V3 Algoritmik Quant Sistemi | © 2026 Kurumsal Karar Destek Altyapısı")
