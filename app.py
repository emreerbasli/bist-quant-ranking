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
import shadow_reader
import pandas as pd
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


@st.cache_data(ttl=600)
def load_rc_research_evidence(candidate_id: str) -> Dict[str, Any]:
    """RC adayları için dondurulmuş araştırma JSON artifact'larından doğrulanmış kanıtları dinamik olarak çeker."""
    manifest_path = ROOT_DIR / "research" / "frozen_candidates" / candidate_id / "candidate_manifest.json"
    port_path = ROOT_DIR / "research" / "results" / "EXP-PORT-001_summary.json"
    rob_path = ROOT_DIR / "research" / "results" / "EXP-ROBUST-001_summary.json"
    fin_path = ROOT_DIR / "research" / "results" / "EXP-FINAL-001_summary.json"
    act_path = ROOT_DIR / "research" / "forward_infrastructure" / "forward_activation.json"
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    port_sum = json.loads(port_path.read_text(encoding="utf-8")) if port_path.exists() else {}
    rob_sum = json.loads(rob_path.read_text(encoding="utf-8")) if rob_path.exists() else {}
    fin_sum = json.loads(fin_path.read_text(encoding="utf-8")) if fin_path.exists() else {}
    act = json.loads(act_path.read_text(encoding="utf-8")) if act_path.exists() else {}
    
    arch = "LGBM_REGRESSION" if "LGBM" in candidate_id else "LAMBDAMART"
    
    port_cls = next((c for c in port_sum.get("classifications", []) if c.get("architecture") == arch), {})
    rob_cls = next((c for c in rob_sum.get("classifications", []) if c.get("architecture") == arch), {})
    fin_arch = next((a for a in fin_sum.get("architectures", []) if a.get("architecture") == arch), {})
    
    return {
        "candidate_id": candidate_id,
        "architecture": arch,
        "model_type": manifest.get("model_type", arch),
        "target_procedure": manifest.get("target_procedure", "N/A"),
        "horizon_procedure": manifest.get("horizon_procedure", 60),
        "features": [f.get("name") for f in manifest.get("features", [])],
        "model_sha256": manifest.get("model_sha256", "N/A"),
        "training_start": manifest.get("training_start", "N/A"),
        "training_cutoff": manifest.get("training_cutoff", "N/A"),
        "clean_forward_start": act.get("clean_forward_start", "N/A"),
        # Port metrics from EXP-PORT-001
        "mean_net_return": port_cls.get("mean_net_return"),
        "mean_cagr": port_cls.get("mean_cagr"),
        "mean_sharpe": port_cls.get("mean_sharpe"),
        "worst_daily_maxdd": port_cls.get("worst_daily_maxdd"),
        "worst_day": port_cls.get("worst_day"),
        "mean_turnover": port_cls.get("mean_turnover"),
        "mean_fill_rate": port_cls.get("mean_fill_rate"),
        "k": port_cls.get("k", 10),
        "classification": port_cls.get("classification", "N/A"),
        # Robust metrics from EXP-ROBUST-001
        "robust_classification": rob_cls.get("classification", "N/A"),
        "dimensions_passed": rob_cls.get("dimensions_passed"),
        "bootstrap_prob_ic_positive": rob_cls.get("bootstrap_prob_ic_positive"),
        "bootstrap_prob_net_positive": rob_cls.get("bootstrap_prob_net_positive"),
        # Final decision from EXP-FINAL-001
        "final_decision": fin_sum.get("decision", "N/A")
    }


@st.cache_data(ttl=600)
def load_rc_research_nav(candidate_id: str) -> pd.DataFrame:
    """EXP-PORT-001 OOS araştırma simülasyonunun günlük NAV ve getiri serisini yükler.
    
    Metodolojik İlkeler:
    1. EXP-PORT-001 içinde her OOS fold (O1, O2, O3, O4) bağımsız olarak 1.0 başlangıç sermayesiyle başlar.
    2. Fold içi günlük getiri: r_t = NAV_t / NAV_{t-1} - 1 (t=0 için r_0 = NAV_0 - 1.0).
    3. Fold sınırları arasında return hesaplanmaz; fold reset düşüşleri filtrelenir.
    4. Kümülatif bileşik seri: chained_nav_t = chained_nav_{t-1} * (1 + r_t).
    """
    nav_file = ROOT_DIR / "research" / "results" / "EXP-PORT-001_daily_nav.csv"
    if not nav_file.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(nav_file)
        arch = "LGBM_REGRESSION" if "LGBM" in candidate_id else "LAMBDAMART"
        sub = df[
            (df["case"] == "K_SENSITIVITY") &
            (df["k"] == 10) &
            (df["cost_bps"] == 50) &
            (df["delay_sessions"] == 0) &
            (df["architecture"] == arch)
        ].copy()
        if sub.empty:
            return pd.DataFrame()
        
        # Kronolojik ve fold sırasına göre sırala
        sub = sub.sort_values(["outer_fold", "date"]).reset_index(drop=True)
        
        daily_rets = []
        fold_nav_pct = []
        for fold, fdf in sub.groupby("outer_fold", sort=False):
            f_navs = fdf["nav"].values
            for i, val in enumerate(f_navs):
                if i == 0:
                    ret = float(val - 1.0)
                else:
                    ret = float(val / f_navs[i - 1] - 1.0)
                daily_rets.append(ret)
                fold_nav_pct.append(float(val - 1.0) * 100.0)
                
        sub["daily_return"] = daily_rets
        sub["fold_nav_pct"] = fold_nav_pct
        sub["chained_nav"] = (1.0 + sub["daily_return"]).cumprod()
        sub["chained_nav_pct"] = (sub["chained_nav"] - 1.0) * 100.0
        return sub
    except Exception:
        return pd.DataFrame()


def build_rc_oos_figure(
    df_nav: pd.DataFrame,
    candidate_label: str,
    base_color: str = "#00e676",
    view_mode: str = "CONTINUOUS_CHAIN",
    is_dash: bool = False
) -> go.Figure:
    """EXP-PORT-001 OOS NAV grafiğini metodolojik kurallara uygun olarak çizer.
    
    1. CONTINUOUS_CHAIN: Her fold'un bileşik günlük getirisi önceki fold'un son NAV seviyesinden devam eder.
       Fold aralarındaki ambargo/purge periyodu boş bırakılır; sahte diagonal bağlantı veya reset düşüşü çizilmez.
    2. SEPARATE_FOLD_TRACES: Her fold (O1, O2, O3, O4) bağımsız olarak %0 (1.0) seviyesinden ayrı trace olarak çizilir.
    """
    fig = go.Figure()
    if view_mode == "CONTINUOUS_CHAIN":
        first = True
        for fold, fdf in df_nav.groupby("outer_fold", sort=False):
            fig.add_trace(go.Scatter(
                x=fdf["date"],
                y=fdf["chained_nav_pct"],
                mode="lines",
                name=f"{candidate_label} (Kümülatif OOS NAV)",
                legendgroup=candidate_label,
                showlegend=first,
                line=dict(color=base_color, width=2.5, dash="dash" if is_dash else "solid"),
                hovertemplate="<b>%{x}</b><br>Kümülatif Getiri: +%{y:.2f}%<extra></extra>"
            ))
            first = False
    else:
        fold_palette = ["#00e676", "#38bdf8", "#f59e0b", "#ec4899"]
        for idx, (fold, fdf) in enumerate(df_nav.groupby("outer_fold", sort=False)):
            col = fold_palette[idx % len(fold_palette)]
            end_ret = fdf["fold_nav_pct"].iloc[-1]
            fig.add_trace(go.Scatter(
                x=fdf["date"],
                y=fdf["fold_nav_pct"],
                mode="lines",
                name=f"{fold} (+%{end_ret:.1f})",
                line=dict(color=col, width=2.2),
                hovertemplate=f"<b>%{{x}}</b><br>{fold} Getirisi: +%{{y:.2f}}%<extra></extra>"
            ))
            
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0f19",
        plot_bgcolor="#111827",
        height=400,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(gridcolor="#1f293d", title="Tarih"),
        yaxis=dict(
            gridcolor="#1f293d",
            title="OOS Net Kümülatif Getiri (%)" if view_mode == "CONTINUOUS_CHAIN" else "Fold İçi Net Getiri (%)"
        ),
        hovermode="x unified"
    )
    return fig


def load_rc_forward_status(candidate_id: str) -> Dict[str, Any]:
    """Official clean-forward infrastructure ve committed kayıt durumunu sorgular."""
    act_path = ROOT_DIR / "research" / "forward_infrastructure" / "forward_activation.json"
    act = json.loads(act_path.read_text(encoding="utf-8")) if act_path.exists() else {}
    
    events_path = ROOT_DIR / "research" / "forward_infrastructure" / "events" / f"{candidate_id}.jsonl"
    tx_dir = ROOT_DIR / "research" / "forward_infrastructure" / "transactions" / candidate_id
    
    completed_observations = []
    if tx_dir.exists():
        for tx_file in tx_dir.glob("*.json"):
            try:
                tx_data = json.loads(tx_file.read_text(encoding="utf-8"))
                if tx_data.get("status") == "COMMITTED" and "return" in tx_data:
                    completed_observations.append(tx_data)
            except Exception:
                pass
                
    return {
        "clean_forward_start": act.get("clean_forward_start", "N/A"),
        "activation_mode": act.get("activation_mode", "N/A"),
        "manifest_ref": act.get("approved_forward_manifest_reference", "N/A"),
        "audit_status": act.get("audit_status", "N/A"),
        "completed_count": len(completed_observations),
        "observations": completed_observations
    }


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
    """Arka planda tek seferlik zorunlu V4.1 kontrolünü tetikler."""
    try:
        from run_paper_trader_v4 import periyodik_gorev_calistir_v4
        with st.spinner("V4.1 Şampiyon Model ve piyasa verileri taranıyor..."):
            basarili = periyodik_gorev_calistir_v4(force=False)
        if basarili:
            st.cache_data.clear()
            st.success("✅ V4.1 Gölge Mod kontrolü tamamlandı.")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("⚠️ V4.1 kontrolü beklemede: 14 gün, piyasa açıklığı veya süreç kilidi koşulları sağlanmadı.")
    except Exception as e:
        st.error(f"❌ V4.1 Çalıştırma hatası: {str(e)}")



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

    # 1. MODEL SEÇİCİ (ÇİFT MOTOR MİMARİSİ)
    secilen_model = st.selectbox(
        "🎯 Aktif Model / Görünüm",
        [
            "🚀 PRIMARY SHADOW MODEL — RC-LGBMR-001",
            "⭐ SECONDARY SHADOW MODEL — RC-LAMBDAMART-001",
            "⚖️ Çift Motor Karşılaştırma (Primary vs Secondary)",
            "🕰️ LEGACY PRODUCTION — V3"
        ],
        index=0
    )

    st.divider()

    if secilen_model != "⚖️ Çift Motor Karşılaştırma (Primary vs Secondary)":
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
    if secilen_model == "🚀 PRIMARY SHADOW MODEL — RC-LGBMR-001":
        SERVICE_LOG_FILE = ROOT_DIR / "logs" / "shadow_service.log"
        model_badge = "🚀 PRIMARY SHADOW (RC-LGBMR-001)"
        target_k = 10
        st.markdown(r"""
        **Model:** `RC-LGBMR-001` (Primary)  
        **Portföy:** $K=10$ Eşit Ağırlıklı (%10)  
        **Mimari:** Yeni nesil shadow architecture.  
        **Durum:** 🟢 YENİ SİSTEM DEVREDE
        """)
    elif secilen_model == "⭐ SECONDARY SHADOW MODEL — RC-LAMBDAMART-001":
        SERVICE_LOG_FILE = ROOT_DIR / "logs" / "shadow_service.log"
        model_badge = "⭐ SECONDARY SHADOW (RC-LAMBDAMART-001)"
        target_k = 10
        st.markdown(r"""
        **Model:** `RC-LAMBDAMART-001` (Secondary)  
        **Portföy:** $K=10$ Eşit Ağırlıklı (%10)  
        **Mimari:** Yeni nesil shadow architecture (LambdaMART).  
        **Durum:** 🟢 YENİ SİSTEM DEVREDE
        """)
    elif secilen_model == "🕰️ LEGACY PRODUCTION — V3":
        PORTFOLIO_FILE = ROOT_DIR / "models" / "v3_ranking" / "paper_portfolio.json"
        LOG_FILE = ROOT_DIR / "models" / "v3_ranking" / "paper_trading_log.csv"
        RANKING_CACHE_FILE = ROOT_DIR / "models" / "v3_ranking" / "latest_ranking_cache.parquet"
        SELECTION_CACHE_FILE = ROOT_DIR / "models" / "v3_ranking" / "latest_selection_cache.parquet"
        DRIFT_REPORT_FILE = ROOT_DIR / "models" / "v3_ranking" / "latest_drift_report.json"
        SERVICE_LOG_FILE = ROOT_DIR / "logs" / "paper_trading_service.log"
        target_k = 10
        model_badge = "🕰️ LEGACY V3"
        st.markdown(r"""
        **Model:** `V3.2 LGBMRanker` (Eski Nesil)  
        **Durum:** ⚠️ V3 Production continues seamlessly without changes.
        """)
    else:
        SERVICE_LOG_FILE = ROOT_DIR / "logs" / "shadow_service.log"
        model_badge = "⚖️ ÇİFT MOTOR (RC)"
        target_k = 10
        st.markdown(r"""
        **Karşılaştırma:** Primary (RC-LGBMR-001) vs Secondary (RC-LAMBDAMART-001)  
        **Mimari:** Çift Motor (Dual-Engine) Eşzamanlı Canlı Takip
        """)

    st.divider()

    # Manuel Tetikleme Butonu
    st.markdown("#### ⚡ Manuel Operasyon")
    if secilen_model == "🕰️ LEGACY PRODUCTION — V3":
        if st.button("V3 Rebalance Kontrolünü Çalıştır", width="stretch", type="primary"):
            trigger_paper_trader_check()
    else:
        st.info("Yeni RC modeller için manuel operasyonlar (forward_infrastructure) dışarıdan script ile tetiklenir.")

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
is_rc_model = "RC-" in secilen_model or "Çift Motor (RC)" in getattr(sys.modules[__name__], 'model_badge', '')

shadow_state = None
if is_rc_model:
    portfolio_data = {"equity": 1.0, "peak_equity": 1.0, "drawdown": 0.0, "positions": {}}
    df_logs = pd.DataFrame()
    df_ranking = pd.DataFrame()
    df_selection = pd.DataFrame()
    market_alignment = {"aligned": True, "market_date": "N/A"}
    drift_snapshot = None
    comparison_data = {}
    try:
        shadow_state = shadow_reader.get_shadow_system_state()
        if shadow_state:
            active_model = "primary"
            if "RC-LAMBDAMART-001" in secilen_model:
                active_model = "secondary"
            
            # Construct the full frozen cross-section from the chosen shadow model.
            # The reader exposes Top-10 as a convenience view, but X-Ray must not
            # silently discard the remaining eligible universe.
            if shadow_state.get(active_model):
                cross_section = shadow_state[active_model].get("cross_section") or shadow_state[active_model].get("ordered_top10", [])
                
                rows = []
                for item in cross_section:
                    rows.append({
                        "sembol": item["ticker"],
                        "ml_score": item["raw_score"],
                        "Sıra": item["rank"],
                        "selected_top10": bool(item.get("selected_top10", False)),
                    })
                df_ranking = pd.DataFrame(rows)
                df_selection = df_ranking[df_ranking["selected_top10"]].copy() if not df_ranking.empty else pd.DataFrame()
            
            market_alignment["market_date"] = shadow_state.get("session_date", "N/A")
            
    except Exception as e:
        print(f"Error reading shadow state: {e}")
        shadow_state = None
else:
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



if shadow_state:
    if shadow_state["status"] == "VALIDATED_DRY_RUN":
        st.warning(f"**VALIDATED DRY-RUN:** Bu gösterim official clean-forward signal DEĞİLDİR. (Tarih: {shadow_state['session_date']})")
    elif shadow_state["status"] == "OFFICIAL_CLEAN_FORWARD":
        st.success(f"**OFFICIAL CLEAN-FORWARD:** Canlı forward sinyal aktiftir. (Tarih: {shadow_state['session_date']})")

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

# ─── ORTAK GRAFİK FONKSİYONU ───────────────────────────────────────────────
def render_shared_price_chart(ticker: str, rank_label: str, score_label: str, model_badge_text: str):
    st.markdown("#### 📈 Hisse Detay Grafiği (X-Ray)")
    st.markdown(f"**Hisse:** `{ticker}` | **Sıra:** #{rank_label} | **Skor:** {score_label}")
    
    _xr_df_fiyat = load_stock_history(ticker)
    if _xr_df_fiyat is not None and not _xr_df_fiyat.empty and "close" in _xr_df_fiyat.columns and len(_xr_df_fiyat) >= 20:
        _xr_df_ti = compute_technical_indicators(_xr_df_fiyat)
        _xr_period_options = {
            "1 Ay": 22,
            "3 Ay": 66,
            "6 Ay": 132,
            "1 Yıl": 264,
            "Tüm Veri": None,
        }
        _xr_period_label = st.selectbox(
            "Grafik dönemi",
            list(_xr_period_options.keys()),
            index=2,
            key=f"xray_period_{ticker}_{model_badge_text}",
        )
        _xr_period_rows = _xr_period_options[_xr_period_label]
        _xr_df_sub = (
            _xr_df_ti.copy()
            if _xr_period_rows is None
            else _xr_df_ti.tail(_xr_period_rows).copy()
        )
        st.caption(f"Gösterilen dönem: {_xr_period_label} · {_xr_df_sub.index[0]} → {_xr_df_sub.index[-1]} · {_xr_df_sub.shape[0]} işlem günü")

        _xr_fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.48, 0.16, 0.17, 0.19],
            subplot_titles=(None, "İşlem Hacmi", "RSI (14) Momentum", "MACD (12,26,9)")
        )

        _xr_fig.add_trace(go.Candlestick(
            x=_xr_df_sub.index,
            open=_xr_df_sub["open"], high=_xr_df_sub["high"],
            low=_xr_df_sub["low"], close=_xr_df_sub["close"],
            name="OHLC",
            increasing_line_color="#00e676", decreasing_line_color="#ff1744",
            increasing_fillcolor="#00e676", decreasing_fillcolor="#ff1744",
            line_width=1.2
        ), row=1, col=1)

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
        for _bb_col, _bb_name, _bb_color, _bb_dash in (
            ("bb_upper", "Bollinger Üst", "#a78bfa", "dash"),
            ("bb_lower", "Bollinger Alt", "#a78bfa", "dash"),
        ):
            if _bb_col in _xr_df_sub.columns:
                _xr_fig.add_trace(go.Scatter(
                    x=_xr_df_sub.index, y=_xr_df_sub[_bb_col],
                    line=dict(color=_bb_color, width=1.0, dash=_bb_dash),
                    name=_bb_name, opacity=0.85
                ), row=1, col=1)

        _xr_vol_clr = [
            "rgba(0,230,118,.75)" if c >= o else "rgba(255,23,68,.75)"
            for c, o in zip(_xr_df_sub["close"], _xr_df_sub["open"])
        ]
        _xr_fig.add_trace(go.Bar(
            x=_xr_df_sub.index, y=_xr_df_sub["volume"],
            marker_color=_xr_vol_clr, name="Hacim", showlegend=False
        ), row=2, col=1)

        if "rsi_14" in _xr_df_sub.columns:
            _xr_fig.add_trace(go.Scatter(
                x=_xr_df_sub.index, y=_xr_df_sub["rsi_14"],
                line=dict(color="#c084fc", width=1.9), name="RSI 14"
            ), row=3, col=1)
            _xr_fig.add_hline(y=70, line_dash="dash", line_color="#ff5252", line_width=0.9, row=3, col=1)
            _xr_fig.add_hline(y=30, line_dash="dash", line_color="#69f0ae", line_width=0.9, row=3, col=1)
            _xr_fig.update_yaxes(range=[15, 85], row=3, col=1)

        if "macd" in _xr_df_sub.columns:
            _xr_fig.add_trace(go.Scatter(
                x=_xr_df_sub.index, y=_xr_df_sub["macd"],
                line=dict(color="#38bdf8", width=1.6), name="MACD"
            ), row=4, col=1)
        if "macd_signal" in _xr_df_sub.columns:
            _xr_fig.add_trace(go.Scatter(
                x=_xr_df_sub.index, y=_xr_df_sub["macd_signal"],
                line=dict(color="#f59e0b", width=1.3), name="Sinyal"
            ), row=4, col=1)
        if "macd_hist" in _xr_df_sub.columns:
            _xr_fig.add_trace(go.Bar(
                x=_xr_df_sub.index, y=_xr_df_sub["macd_hist"],
                marker_color="#64748b", name="MACD histogram", opacity=0.55,
                showlegend=False
            ), row=4, col=1)

        _xr_fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0b0f19", plot_bgcolor="#111827",
            height=680,
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
        st.error(f"📊 Bu hisse ({ticker}) için yeterli fiyat grafiği verisi bulunamadı.")


# ═══════════════════════════════════════════════════════════════════════════
# SAYFA 1: PORTFÖYÜM & POZİSYON YÖNETİMİ
# ═══════════════════════════════════════════════════════════════════════════
if sayfa == "💼 Portföyüm & Pozisyon Yönetimi":
    st.subheader(f"💼 Model Portföy Görünümü: {model_badge}")
    st.caption("Her shadow modelin bağımsız Top-10 seçimi ve hedef ağırlıkları.")

    # Primary ana sayfasında iki frozen shadow portföyünü birlikte göster.
    # Bu yalnızca committed/dry-run kayıtlarını okur; ensemble veya yeni inference üretmez.
    if (
        is_rc_model
        and active_model == "primary"
        and shadow_state
        and shadow_state.get("primary")
        and shadow_state.get("secondary")
    ):
        st.markdown("#### 🧭 İki Bağımsız Shadow Portföyü")
        st.caption(
            f"Sinyal tarihi: {shadow_state.get('session_date', 'N/A')} · "
            "Primary ve Secondary ayrı adaylardır; birleşik portföy değildir."
        )
        _home_p_col, _home_s_col = st.columns(2)
        for _home_col, _home_key, _home_title in (
            (_home_p_col, "primary", "🚀 PRIMARY — RC-LGBMR-001"),
            (_home_s_col, "secondary", "⭐ SECONDARY — RC-LAMBDAMART-001"),
        ):
            with _home_col:
                _home_rows = shadow_state[_home_key].get("ordered_top10", [])
                _home_table = pd.DataFrame(
                    [
                        {
                            "Sıra": row.get("rank"),
                            "Hisse": row.get("ticker"),
                            "Ham Skor": row.get("raw_score"),
                            "Hedef Ağırlık": "%10",
                        }
                        for row in _home_rows
                    ]
                )
                st.markdown(f"**{_home_title}**")
                if _home_table.empty:
                    st.info("Bu model için committed portföy kaydı yok.")
                else:
                    st.dataframe(_home_table, use_container_width=True, hide_index=True)

    if not df_selection.empty:
        # --- RC MODEL İÇİN X-RAY GRAFİĞİ ENTEGRASYONU ---
        if is_rc_model:
            st.divider()
            st.markdown("### 🔍 Primary Portföy Hisse Detaylı İnceleme (X-Ray)")
            _rc_tickers = df_selection["sembol"].tolist()
            if _rc_tickers:
                # Active model bazında eşsiz key vererek model değişiminde stale state hatasını önlüyoruz
                _sel_key = f"rc_xray_sel_{active_model}"
                _selected_ticker = st.selectbox(
                    "Grafik için hisse seçin:",
                    _rc_tickers,
                    key=_sel_key
                )
                if _selected_ticker:
                    _row = df_selection[df_selection["sembol"] == _selected_ticker].iloc[0]
                    _rank = _row.get("Sıra", "-")
                    _score = float(_row.get("ml_score", 0.0))
                    render_shared_price_chart(_selected_ticker, str(_rank), f"{_score:.4f}", model_badge)

    else:
        st.info("Portföy verisi bulunamadı. Lütfen motorun çalışmasını bekleyin.")

# ═══════════════════════════════════════════════════════════════════════════
# SAYFA 2: BIST 88 MODEL SIRALAMASI
# ═══════════════════════════════════════════════════════════════════════════
elif sayfa == "🏆 BIST 88 Model Sıralaması":
    st.subheader(f"🏆 Tüm Evren Sıralaması: {model_badge}")
    st.caption("Modelin ürettiği makine öğrenmesi skorları ve sıralaması.")
    if not df_ranking.empty:
        st.dataframe(df_ranking, use_container_width=True, hide_index=True)
    else:
        st.info("Sıralama verisi bulunamadı.")

# ═══════════════════════════════════════════════════════════════════════════
# SAYFA: ÇİFT MODEL KARŞILAŞTIRMA
# ═══════════════════════════════════════════════════════════════════════════
elif sayfa == "⚖️ Çift Model Karşılaştırma":
    st.subheader("⚖️ Primary / Secondary Karşılaştırması")
    st.caption("Primary (RC-LGBMR-001) ve Secondary (RC-LAMBDAMART-001) Shadow Modellerin güncel seçimleri ve ayrışmaları.")
    st.warning("⚠️ **EXP-ENS-001 Reddi & Ayrık Takip İlkesi:** Araştırma sürecinde eşit ağırlıklı ensemble modeli (EXP-ENS-001) başarısız olmuş ve reddedilmiştir. Primary ve Secondary iki bağımsız dondurulmuş shadow modeldir; aralarında sentetik birleşik portföy veya birleşik getiri/Sharpe üretilmez.")
    
    if shadow_state and shadow_state.get("primary") and shadow_state.get("secondary"):
        st.success(f"Sinyal Tarihi: {shadow_state['session_date']} | Tür: {shadow_state['status']}")
        
        p_top10 = {x["ticker"] for x in shadow_state["primary"]["ordered_top10"]}
        s_top10 = {x["ticker"] for x in shadow_state["secondary"]["ordered_top10"]}
        
        ortak = p_top10 & s_top10
        sadece_p = p_top10 - s_top10
        sadece_s = s_top10 - p_top10
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"### 🤝 Ortak ({len(ortak)})")
            for t in sorted(ortak): st.markdown(f"- **{t}**")
        with col2:
            st.markdown(f"### 🚀 Sadece Primary ({len(sadece_p)})")
            for t in sorted(sadece_p): st.markdown(f"- {t}")
        with col3:
            st.markdown(f"### ⭐ Sadece Secondary ({len(sadece_s)})")
            for t in sorted(sadece_s): st.markdown(f"- {t}")
            
    else:
        st.info("Karşılaştırma için yeterli veri yok.")

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
    # ─── MODEL BAZLI PERFORMANS VE KANIT PANELİ ─────────────────────────────
    if is_rc_model:
        # Aktif RC modelini belirle
        rc_candidate_id = "RC-LGBMR-001"
        rc_candidate_title = "RC-LGBMR-001 (Primary Shadow Model)"
        if "RC-LAMBDAMART-001" in secilen_model:
            rc_candidate_id = "RC-LAMBDAMART-001"
            rc_candidate_title = "RC-LAMBDAMART-001 (Secondary Shadow Model)"

        ev = load_rc_research_evidence(rc_candidate_id)
        fwd = load_rc_forward_status(rc_candidate_id)

        st.subheader(f"📈 Model Performans & Kanıt Paneli — {rc_candidate_title}")
        st.caption(f"Aday Kimliği: `{rc_candidate_id}` | Mimari: `{ev['architecture']}` | Hedef Yordamı: `{ev['target_procedure']}` (Ufuk: {ev['horizon_procedure']} Seans)")

        tab_res, tab_fwd, tab_comp = st.tabs([
            "📊 Araştırma / OOS Backtest Kanıtı",
            "🟢 Clean-Forward Shadow Takibi",
            "⚖️ Primary / Secondary Karşılaştırması"
        ])

        # ─────────────────────────────────────────────────────────────────
        # 1. ARAŞTIRMA / OOS BACKTEST KANITI (Dondurulmuş Araştırma Sonuçları)
        # ─────────────────────────────────────────────────────────────────
        with tab_res:
            st.markdown("#### 📊 Araştırma / OOS Backtest Sonuçları")
            st.warning("⚠️ **Metodolojik Sınır:** Bu değerler dondurulmuş araştırma fazı (OOS Backtest / EXP-PORT-001 / EXP-ROBUST-001) kanıtıdır. Canlı veya clean-forward gerçekleşmiş performans DEĞİLDİR.")
            st.caption(f"📁 **Resmi Kaynak:** `research/results/EXP-PORT-001_summary.json` & `EXP-ROBUST-001_summary.json` | Model Hash: `{ev['model_sha256'][:16]}...`")

            # 5 KPI Kartı
            r1, r2, r3, r4, r5 = st.columns(5)
            with r1:
                st.metric("Ortalama Net Getiri", f"+%{ev['mean_net_return']*100:.2f}" if ev['mean_net_return'] is not None else "N/A", "50 bps Maliyet Dahil")
            with r2:
                st.metric("Yıllık Bileşik Getiri (CAGR)", f"+%{ev['mean_cagr']*100:.2f}" if ev['mean_cagr'] is not None else "N/A", f"K={ev['k']} Eşit Ağırlık")
            with r3:
                st.metric("Resmi Sharpe Oranı", f"{ev['mean_sharpe']:.2f}" if ev['mean_sharpe'] is not None else "N/A", "Out-of-Sample Sharpe")
            with r4:
                st.metric("Maksimum Drawdown", f"%{ev['worst_daily_maxdd']*100:.2f}" if ev['worst_daily_maxdd'] is not None else "N/A", "En Kötü Günlük MaxDD")
            with r5:
                st.metric("En Kötü Günlük Kayıp", f"%{ev['worst_day']*100:.2f}" if ev['worst_day'] is not None else "N/A", "Worst Day Stres")

            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

            # Portföy ve Sağlamlık Detayları
            c_left, c_right = st.columns([1, 1])
            with c_left:
                st.markdown("##### ⚙️ Portföy & Yürütme Parametreleri (EXP-PORT-001)")
                df_port_details = pd.DataFrame([
                    {"Parametre": "Portföy Büyüklüğü (K)", "Değer": f"K = {ev['k']} (Eşit Ağırlıklı)"},
                    {"Parametre": "İşlem Maliyeti (Cost Reserve)", "Değer": "50 bps (0.0050) tek yönlü"},
                    {"Parametre": "Uygulama Gecikmesi (Delay)", "Değer": "0 seans (Kapanışta sinyal, ertesi Açılışta işlem)"},
                    {"Parametre": "Ortalama Devir Hızı (Turnover)", "Değer": f"{ev['mean_turnover']:.4f}" if ev['mean_turnover'] is not None else "N/A"},
                    {"Parametre": "Emir Gerçekleşme Oranı (Fill Rate)", "Değer": f"%{ev['mean_fill_rate']*100:.1f}" if ev['mean_fill_rate'] is not None else "N/A"},
                    {"Parametre": "Eğitim & Test Aralığı", "Değer": f"{ev['training_start']} → {ev['training_cutoff']}"}
                ])
                st.dataframe(df_port_details, hide_index=True, width="stretch")

            with c_right:
                st.markdown("##### 🛡️ Sağlamlık & Karar Özeti (EXP-ROBUST-001 & EXP-FINAL-001)")
                df_rob_details = pd.DataFrame([
                    {"Boyut": "Sağlamlık Sınıfı", "Sonuç": f"{ev['robust_classification']}"},
                    {"Boyut": "Geçilen Sağlamlık Boyutları", "Sonuç": f"{ev['dimensions_passed']} / 9 Boyut PASS" if ev['dimensions_passed'] is not None else "N/A"},
                    {"Boyut": "Bootstrap IC > 0 Olasılığı", "Sonuç": f"%{ev['bootstrap_prob_ic_positive']*100:.2f}" if ev['bootstrap_prob_ic_positive'] is not None else "N/A"},
                    {"Boyut": "Bootstrap Net Getiri > 0 Olasılığı", "Sonuç": f"%{ev['bootstrap_prob_net_positive']*100:.2f}" if ev['bootstrap_prob_net_positive'] is not None else "N/A"},
                    {"Boyut": "Model Öznitelikleri (Features)", "Sonuç": f"{', '.join(ev['features'])}"},
                    {"Boyut": "Phase J Finalist Kararı", "Sonuç": f"{ev['final_decision']}"}
                ])
                st.dataframe(df_rob_details, hide_index=True, width="stretch")

            # Gerçek Araştırma OOS NAV Çizelgesi (EXP-PORT-001_daily_nav.csv)
            df_nav = load_rc_research_nav(rc_candidate_id)
            if not df_nav.empty and len(df_nav) > 1:
                col_h, col_v = st.columns([3, 2])
                with col_h:
                    st.markdown("##### 📈 Dondurulmuş Araştırma OOS Kümülatif NAV Eğrisi (EXP-PORT-001)")
                with col_v:
                    view_mode = st.radio(
                        "Görünüm Seçimi:",
                        ["Kümülatif Bileşik NAV", "Fold Bazlı Ayrık NAV"],
                        horizontal=True,
                        key=f"nav_view_mode_{rc_candidate_id}"
                    )
                
                if "Kümülatif" in view_mode:
                    st.caption("Walk-forward OOS dönemlerindeki gerçekleşen günlük araştırma getirileri, fold resetleri hariç tutularak kronolojik olarak bileşiklenmiştir.")
                    fig_r = build_rc_oos_figure(
                        df_nav,
                        rc_candidate_id,
                        base_color="#00e676" if "LGBM" in rc_candidate_id else "#38bdf8",
                        view_mode="CONTINUOUS_CHAIN"
                    )
                else:
                    st.caption("Her OOS fold dönemi 1.0 (%0) seviyesinden bağımsız başlatılmış olup, fold aralarındaki tasfiye ve yeniden başlatma döngüleri izole gösterilmektedir.")
                    fig_r = build_rc_oos_figure(
                        df_nav,
                        rc_candidate_id,
                        view_mode="SEPARATE_FOLD_TRACES"
                    )
                st.plotly_chart(fig_r, width="stretch")
            else:
                st.info("Araştırma OOS zaman serisi bulunamadı.")

        # ─────────────────────────────────────────────────────────────────
        # 2. CLEAN-FORWARD SHADOW TAKİBİ (Gerçekleşmiş Forward Performans)
        # ─────────────────────────────────────────────────────────────────
        with tab_fwd:
            st.markdown("#### 🟢 Clean-Forward Shadow Takibi")
            st.caption(f"Resmi Kaynak: `research/forward_infrastructure/` | Manifest: `{fwd['manifest_ref']}`")

            st.markdown(f"""
            <div class="quant-card" style="border-left: 4px solid #10b981;">
                <div style="font-weight: 600; font-size: 1.05rem; color: #10b981; margin-bottom: 6px;">
                    🟢 Clean-Forward İzleme Aktif (Shadow Mode)
                </div>
                <div style="font-size: 0.9rem; color: #94a3b8; line-height: 1.6;">
                    <b>Aktivasyon Başlangıcı:</b> <code>{fwd['clean_forward_start']}</code><br>
                    <b>Aktivasyon Modu:</b> <code>{fwd['activation_mode']}</code> (Denetim Durumu: <code>{fwd['audit_status']}</code>)<br>
                    <b>Tamamlanan Resmi Forward Gözlem Sayısı:</b> <code>{fwd['completed_count']}</code>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if fwd["completed_count"] == 0:
                st.info(
                    "ℹ️ **Henüz tamamlanmış yeterli clean-forward dönem bulunmadığı için kümülatif gerçekleşmiş getiri eğrisi oluşturulmamıştır.**\n\n"
                    "• Model dondurulmuş (frozen) olup clean-forward saati aktiftir.\n"
                    "• Metodolojik kurallar gereği, geçmiş araştırma/backtest eğrileri veya dry-run verileri gerçekleşmiş getiri olarak **KESİNLİKLE** gösterilmez (0% sahte çizgi de üretilmez).\n"
                    "• İlk resmi COMMITTED forward işlem periyodu tamamlandığında gerçekleşmiş kümülatif getiri eğrisi ve seans logları bu alanda otomatik olarak görüntülenecektir."
                )
            else:
                st.success(f"Tamamlanan resmi forward gözlem sayısı: {fwd['completed_count']}")

        # ─────────────────────────────────────────────────────────────────
        # 3. PRIMARY / SECONDARY KARŞILAŞTIRMASI
        # ─────────────────────────────────────────────────────────────────
        with tab_comp:
            st.markdown("#### ⚖️ Primary / Secondary Karşılaştırması")
            st.warning("⚠️ **EXP-ENS-001 Reddi & Ayrık Takip İlkesi:** Araştırma sürecinde eşit ağırlıklı ensemble modeli (EXP-ENS-001) başarısız olmuş ve reddedilmiştir. Primary ve Secondary iki bağımsız dondurulmuş shadow modeldir; aralarında sentetik birleşik portföy veya birleşik getiri/Sharpe üretilmez.")

            ev_p = load_rc_research_evidence("RC-LGBMR-001")
            ev_s = load_rc_research_evidence("RC-LAMBDAMART-001")

            df_comp_table = pd.DataFrame([
                {"Özellik / Metrik": "Model Kimliği", "🏆 Primary Shadow": "RC-LGBMR-001", "🥈 Secondary Shadow": "RC-LAMBDAMART-001"},
                {"Özellik / Metrik": "Mimari", "🏆 Primary Shadow": "LGBM Regression", "🥈 Secondary Shadow": "LambdaMART"},
                {"Özellik / Metrik": "Hedef Yordamı (Target)", "🏆 Primary Shadow": f"{ev_p['target_procedure']} (H60)", "🥈 Secondary Shadow": f"{ev_s['target_procedure']} (H60)"},
                {"Özellik / Metrik": "Ortalama Net Getiri (50 bps)", "🏆 Primary Shadow": f"+%{ev_p['mean_net_return']*100:.2f}" if ev_p['mean_net_return'] is not None else "N/A", "🥈 Secondary Shadow": f"+%{ev_s['mean_net_return']*100:.2f}" if ev_s['mean_net_return'] is not None else "N/A"},
                {"Özellik / Metrik": "Yıllık Bileşik Getiri (CAGR)", "🏆 Primary Shadow": f"+%{ev_p['mean_cagr']*100:.2f}" if ev_p['mean_cagr'] is not None else "N/A", "🥈 Secondary Shadow": f"+%{ev_s['mean_cagr']*100:.2f}" if ev_s['mean_cagr'] is not None else "N/A"},
                {"Özellik / Metrik": "Resmi Sharpe Oranı", "🏆 Primary Shadow": f"{ev_p['mean_sharpe']:.2f}" if ev_p['mean_sharpe'] is not None else "N/A", "🥈 Secondary Shadow": f"{ev_s['mean_sharpe']:.2f}" if ev_s['mean_sharpe'] is not None else "N/A"},
                {"Özellik / Metrik": "Maksimum Drawdown (MaxDD)", "🏆 Primary Shadow": f"%{ev_p['worst_daily_maxdd']*100:.2f}" if ev_p['worst_daily_maxdd'] is not None else "N/A", "🥈 Secondary Shadow": f"%{ev_s['worst_daily_maxdd']*100:.2f}" if ev_s['worst_daily_maxdd'] is not None else "N/A"},
                {"Özellik / Metrik": "En Kötü Günlük Kayıp", "🏆 Primary Shadow": f"%{ev_p['worst_day']*100:.2f}" if ev_p['worst_day'] is not None else "N/A", "🥈 Secondary Shadow": f"%{ev_s['worst_day']*100:.2f}" if ev_s['worst_day'] is not None else "N/A"},
                {"Özellik / Metrik": "Devir Hızı (Turnover)", "🏆 Primary Shadow": f"{ev_p['mean_turnover']:.4f}" if ev_p['mean_turnover'] is not None else "N/A", "🥈 Secondary Shadow": f"{ev_s['mean_turnover']:.4f}" if ev_s['mean_turnover'] is not None else "N/A"},
                {"Özellik / Metrik": "Sağlamlık Geçiş Skoru", "🏆 Primary Shadow": f"{ev_p['dimensions_passed']}/9 Boyut" if ev_p['dimensions_passed'] is not None else "N/A", "🥈 Secondary Shadow": f"{ev_s['dimensions_passed']}/9 Boyut" if ev_s['dimensions_passed'] is not None else "N/A"},
                {"Özellik / Metrik": "Clean-Forward Durumu", "🏆 Primary Shadow": "İnkübasyon (0 Gözlem)", "🥈 Secondary Shadow": "İnkübasyon (0 Gözlem)"}
            ])
            st.dataframe(df_comp_table, hide_index=True, width="stretch")

            # İki modelin araştırma OOS NAV eğrilerini yan yana karşılaştır
            df_nav_p = load_rc_research_nav("RC-LGBMR-001")
            df_nav_s = load_rc_research_nav("RC-LAMBDAMART-001")
            if not df_nav_p.empty and not df_nav_s.empty:
                col_ch, col_cv = st.columns([3, 2])
                with col_ch:
                    st.markdown("##### 📈 Dondurulmuş Araştırma OOS Kümülatif NAV Karşılaştırması (EXP-PORT-001)")
                with col_cv:
                    view_comp_mode = st.radio(
                        "Kıyaslama Görünümü:",
                        ["Kümülatif Bileşik NAV", "Fold Bazlı Ayrık NAV"],
                        horizontal=True,
                        key="nav_comp_view_mode"
                    )
                
                fig_comp = go.Figure()
                if "Kümülatif" in view_comp_mode:
                    st.caption("Walk-forward OOS dönemlerindeki gerçekleşen günlük araştırma getirileri, fold resetleri hariç tutularak kronolojik olarak bileşiklenmiştir.")
                    
                    # Primary fold segments
                    first_p = True
                    for fold, fdf in df_nav_p.groupby("outer_fold", sort=False):
                        fig_comp.add_trace(go.Scatter(
                            x=fdf["date"],
                            y=fdf["chained_nav_pct"],
                            mode="lines",
                            name="RC-LGBMR-001 (Primary OOS NAV)",
                            legendgroup="primary",
                            showlegend=first_p,
                            line=dict(color="#00e676", width=2.5),
                            hovertemplate="<b>%{x}</b><br>Primary Kümülatif: +%{y:.2f}%<extra></extra>"
                        ))
                        first_p = False
                        
                    # Secondary fold segments
                    first_s = True
                    for fold, fdf in df_nav_s.groupby("outer_fold", sort=False):
                        fig_comp.add_trace(go.Scatter(
                            x=fdf["date"],
                            y=fdf["chained_nav_pct"],
                            mode="lines",
                            name="RC-LAMBDAMART-001 (Secondary OOS NAV)",
                            legendgroup="secondary",
                            showlegend=first_s,
                            line=dict(color="#38bdf8", width=2.5, dash="dash"),
                            hovertemplate="<b>%{x}</b><br>Secondary Kümülatif: +%{y:.2f}%<extra></extra>"
                        ))
                        first_s = False
                else:
                    st.caption("Her iki modelin her OOS fold dönemi için bağımsız (%0) seviyesinden hesaplanan getiri eğrileri izole olarak karşılaştırılır.")
                    
                    for fold, fdf_p in df_nav_p.groupby("outer_fold", sort=False):
                        fig_comp.add_trace(go.Scatter(
                            x=fdf_p["date"],
                            y=fdf_p["fold_nav_pct"],
                            mode="lines",
                            name=f"Primary {fold}",
                            line=dict(color="#00e676", width=2.2),
                            legendgroup=f"fold_{fold}"
                        ))
                    for fold, fdf_s in df_nav_s.groupby("outer_fold", sort=False):
                        fig_comp.add_trace(go.Scatter(
                            x=fdf_s["date"],
                            y=fdf_s["fold_nav_pct"],
                            mode="lines",
                            name=f"Secondary {fold}",
                            line=dict(color="#38bdf8", width=2.2, dash="dash"),
                            legendgroup=f"fold_{fold}"
                        ))

                fig_comp.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#0b0f19",
                    plot_bgcolor="#111827",
                    height=400,
                    margin=dict(l=20, r=20, t=30, b=20),
                    xaxis=dict(gridcolor="#1f293d", title="Tarih"),
                    yaxis=dict(
                        gridcolor="#1f293d",
                        title="OOS Net Kümülatif Getiri (%)" if "Kümülatif" in view_comp_mode else "Fold İçi Net Getiri (%)"
                    ),
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_comp, width="stretch")

    else:
        # ─────────────────────────────────────────────────────────────────
        # LEGACY PRODUCTION — V3
        # ─────────────────────────────────────────────────────────────────
        st.subheader("🏛️ LEGACY PRODUCTION — V3")
        st.caption("Eski V3 Quant Model referans takip ekranı (Yeni dondurulmuş RC modellerinden tamamen bağımsızdır).")

        tab_v3_kilit, tab_v3_paper = st.tabs([
            "🏛️ Kilit Kutu Doğrulanmış Resmi Performans (2025Q2 - 2026Q2)",
            "🟢 Cari Paper Trading Takibi (2026-09 ve Sonrası)"
        ])

        with tab_v3_kilit:
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

            fig_kk.add_trace(go.Scatter(
                x=ceyrekler, y=k10_cum,
                mode="lines+markers",
                name="Model K=10 (Nihai Portföy)",
                line=dict(color="#00e676", width=3.5),
                marker=dict(size=9, color="#00e676")
            ), row=1, col=1)

            fig_kk.add_trace(go.Scatter(
                x=ceyrekler, y=k15_cum,
                mode="lines+markers",
                name="Model K=15 (Genişletilmiş)",
                line=dict(color="#38bdf8", width=2.2, dash="dash"),
                marker=dict(size=6, color="#38bdf8")
            ), row=1, col=1)

            fig_kk.add_trace(go.Scatter(
                x=ceyrekler, y=xu100_cum,
                mode="lines+markers",
                name="BIST 100 (XU100 Kıstas)",
                line=dict(color="#f59e0b", width=2.5, dash="dot"),
                marker=dict(size=6, color="#f59e0b")
            ), row=1, col=1)

            fig_kk.add_trace(go.Scatter(
                x=ceyrekler, y=placebo_cum,
                mode="lines",
                name="100 Tohum Placebo Ort.",
                line=dict(color="#64748b", width=1.5, dash="dot")
            ), row=1, col=1)

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

            st.markdown("##### 📋 Çeyreklik Ayrışma Tablosu")
            df_kk_table = pd.DataFrame([
                {"Çeyrek": "2025Q2", "Model K=10 (%)": "+%24.67", "BIST 100 (%)": "+%25.21", "Çeyreklik Net Alfa": "-%0.54", "Placebo (%)": "+%29.33", "Sonuç": "Piyasaya Paralel"},
                {"Çeyrek": "2025Q3", "Model K=10 (%)": "+%2.18", "BIST 100 (%)": "-%1.45", "Çeyreklik Net Alfa": "+%3.63", "Placebo (%)": "-%4.21", "Sonuç": "Piyasa Düşerken Pozitif"},
                {"Çeyrek": "2025Q4", "Model K=10 (%)": "+%15.49", "BIST 100 (%)": "+%23.40", "Çeyreklik Net Alfa": "-%7.91", "Placebo (%)": "+%15.63", "Sonuç": "Ralliye Katıldı"},
                {"Çeyrek": "2026Q1", "Model K=10 (%)": "+%24.31", "BIST 100 (%)": "+%2.68", "Çeyreklik Net Alfa": "+%21.63", "Placebo (%)": "+%10.57", "Sonuç": "🔥 Büyük Pozitif Ayrışma"},
                {"Çeyrek": "2026Q2", "Model K=10 (%)": "+%7.12", "BIST 100 (%)": "+%3.24", "Çeyreklik Net Alfa": "+%3.88", "Placebo (%)": "-%3.65", "Sonuç": "🔥 Pozitif Alfa"}
            ])
            st.dataframe(df_kk_table, width="stretch", hide_index=True)

        with tab_v3_paper:
            st.markdown("#### 🟢 V3 Cari Paper Trading Kümülatif Getiri İzleme")
            st.caption("V3 inkübasyon döneminde gerçekleşen periyot getirileri ve kıyaslama eğrisi.")

            if not df_logs.empty and len(df_logs) >= 1:
                # 1. Güvenilir unique transaction / event identity kontrolü
                identity_cols = [c for c in df_logs.columns if c in ["tx_id", "event_id", "session_id", "id", "uuid"]]
                has_reliable_identity = len(identity_cols) > 0

                # Tarih frekans analizi
                tarih_sayilari = df_logs["tarih"].value_counts()
                ambiguous_dates = tarih_sayilari[tarih_sayilari > 1].index.tolist()

                if ambiguous_dates:
                    st.warning(
                        f"⚠️ **Tarihsel Kayıt Uyarısı:** {', '.join(str(d) for d in ambiguous_dates)} tarihinde "
                        f"birden fazla historical paper-trading kaydı bulunduğu için tekil performans noktası "
                        f"güvenilir şekilde belirlenemedi. Metodolojik kural gereği keyfi ilk/son satır seçilmemiş, "
                        f"tarihsel veri değiştirilmemiş ve bu tarih kümülatif getiri eğrisinden hariç tutulmuştur. "
                        f"Tüm kayıtlar aşağıdaki ham log tablosunda eksiksiz olarak incelenebilir."
                    )

                # Yalnızca tekil ve güvenilir olan periyotları grafiğe dahil et (Keyfi first/last seçimi YOKTUR)
                df_chart = df_logs[~df_logs["tarih"].isin(ambiguous_dates)].copy()

                if not df_chart.empty and len(df_chart) >= 1:
                    fig_cum = go.Figure()
                    tarihler = df_chart["tarih"].tolist()
                    m_rets = [float(str(r).replace("%", "")) for r in df_chart["model_getiri_yuzde"]]
                    x_rets = [float(str(r).replace("%", "")) for r in df_chart["bist100_getiri_yuzde"]]
                    m_cum = np.cumprod(1.0 + np.array(m_rets) / 100.0) - 1.0
                    x_cum = np.cumprod(1.0 + np.array(x_rets) / 100.0) - 1.0

                    fig_cum.add_trace(go.Scatter(
                        x=tarihler,
                        y=m_cum * 100,
                        mode="lines+markers",
                        name="V3 Quant Model (Güvenilir Tekil Noktalar)",
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
                else:
                    st.info("Kümülatif getiri grafiği için güvenilir tekil periyot kaydı bulunamadı.")

                st.markdown("##### 📜 V3 Paper Trading İşlem Geçmişi (Ham Kayıt)")
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
    if is_rc_model:
        st.caption(
            "PRIMARY/SECONDARY SHADOW modeli frozen cross-section sırası ve skorunu gösterir. "
            "RC adayları yalnız mom_12_1, mom_63 ve vol_63 frozen feature şemasına bağlıdır; "
            "**%100 Salt Okunur** — inference veya resmi kayıt üretmez."
        )
    else:
        st.caption(
            "Legacy V3 açıklayıcı teknik ve bilanço görünümü. "
            "**%100 Salt Okunur** — üretim portföy dosyalarına hiçbir yazma yapılmaz."
        )

    if df_ranking is None or df_ranking.empty:
        st.warning(
            "⚠️ Shadow/Legacy sıralama verisi henüz mevcut değil. Önce doğrulanmış bir sıralama kaynağı oluşturun."
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
                    _flags.append("💼 Portföy")
                if s in _xr_wallet_positions:
                    _flags.append("👤 Cüzdan")
                _flag_str = f" — [{', '.join(_flags)}]" if _flags else ""
                return f"#{_sira:02d} • {_tiker} — {_sektor}{_flag_str}"

            _xr_secilen = st.selectbox(
                f"🔎 {_xr_df.shape[0]} Hisse Evreninden Seçin (Arama Destekli):",
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
                    #{_xr_rank}<span style="font-size:1.1rem; color:#475569;">/{len(_xr_sembol_listesi)}</span>
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
                "💼 Portföyde</span>"
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
                            • #{_xr_rank}/{len(_xr_sembol_listesi)}
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
                    <div style="font-size:.75rem;color:#475569;text-transform:uppercase;letter-spacing:.07em;">{model_badge} — Ham Skor</div>
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
                st.metric("Portföy Getirisi", f"%{float(_xr_kz or 0.0):+.2f}", f"{_xr_days} gün tutuldu")
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
            st.caption(f"Her çubuk hissenin {_xr_df.shape[0]} hisseli evrendeki göreceli konumunu gösterir (%0-%100 kesitsel skala).")

            if is_rc_model:
                st.info(
                    "Bu RC röntgeni inference'ı yeniden çalıştırmaz. Frozen model girdileri: "
                    "mom_12_1 · mom_63 · vol_63. Dry-run/official reader kaydında bu ham feature değerleri "
                    "taşınmadığı için burada legacy faktörleri gösterilmez; aşağıdaki skor ve sıra committed "
                    "cross-section kaydından okunur."
                )

            _has_z_reel = ("z_reel_eps" in _xr_row.index) and pd.notna(_xr_row.get("z_reel_eps"))
            _reel_eps_key = "z_reel_eps" if _has_z_reel else "reel_eps_growth"
            _reel_eps_label = "📊 Sektörel Reel Kâr Büyümesi" if _has_z_reel else "📊 Reel Kâr Büyümesi"
            _reel_eps_sub = "Legacy öncü faktör — Sektörel Z-Skoru ([-1.5, +1.5] winsorized)" if _has_z_reel else "Legacy öncü faktör — Enflasyondan arındırılmış EPS"
            _reel_eps_val_fmt = (lambda v: f"{v:+.2f}σ") if _has_z_reel else (lambda v: f"%{v*100:+.1f}")
            _reel_eps_bar_fn = (lambda v: min(max(int((v + 1.5) / 3.0 * 100), 0), 100)) if _has_z_reel else (lambda v: min(max(int((v + 1.0) / 2.0 * 100), 0), 100))

            _xr_faktorler = [
                {
                    "key": _reel_eps_key,
                    "label": _reel_eps_label,
                    "sub": _reel_eps_sub,
                    "val_fmt": _reel_eps_val_fmt,
                    "bar_fn": _reel_eps_bar_fn,
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

            # RC records intentionally do not expose legacy fundamental-factor
            # columns. Never fabricate them (the old UI used a 0.0 placeholder).
            if is_rc_model:
                _xr_faktorler = []

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
                if _fk in ("z_reel_eps", "reel_eps_growth"):
                    _thr = 0.20 if _fk == "z_reel_eps" else 0.05
                    if _fv >= _thr:
                        _xr_positives.append((_fak["label"].split()[1], _fval_str))
                    elif _fv <= -_thr:
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

            if is_rc_model:
                # RC records intentionally contain the committed model score/rank,
                # not the legacy fundamental-factor columns.  Do not collapse every
                # stock to the old 0/100 fallback; expose a deterministic
                # cross-sectional card derived from the already committed rank.
                _xr_n = max(len(_xr_df), 1)
                _xr_rank_for_card = int(_xr_row.get("Sıra") or _xr_rank)
                _xr_karne_skor = 100 if _xr_n <= 1 else int(round(100.0 * (_xr_n - _xr_rank_for_card) / (_xr_n - 1)))
                _xr_karne_skor = max(0, min(100, _xr_karne_skor))
            else:
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

                # Model portföyü alış fiyatı seviyesi
                if _xr_portfoy_var:
                    _xr_ep2 = float(_xr_pos_data.get("entry_price", 0))
                    if _xr_ep2 > 0:
                        _xr_fig.add_hline(
                            y=_xr_ep2,
                            line_dash="dash", line_color="#ffd600", line_width=2.0,
                            annotation_text=f"📍 Alış: ₺{_xr_ep2:.2f}",
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
                    '<div style="font-size:.80rem;font-weight:600;color:#94a3b8;margin-bottom:8px;">💼 Model Pozisyon Bilgisi</div>'
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
        
        # ── A. EVREN SKOR DAĞILIMI ────────────────────────────────────────
        st.markdown(f"#### 🏙️ {_xr_df.shape[0]} Hisse Evreni — Skor Dağılım Perspektifi")
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
            hovertemplate="<b>%{x}</b><br>Shadow ham skor: %{y:.4f}<extra></extra>"
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
            yaxis=dict(title="Shadow ham skor", gridcolor="#1f293d"),
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
                    "Shadow Skoru": f"{float(_srow.get('ml_score') or 0.0):+.4f}",
                    "Seçim": "Top-10" if bool(_srow.get("selected_top10")) else "Evren",
                    "Durum": _s_v4_flag
                })
            
            _xr_df_peer = pd.DataFrame(_xr_sektor_rows)
            st.dataframe(_xr_df_peer, width="stretch", hide_index=True)
        else:
            st.caption("Bu sektörde başka hisse bulunamadı.")

        # ── C. TEK TIKLA ÖZET RÖNTGEN RAPORU KOPYALA ──────────────────────────────
        st.markdown("#### 📋 Tek Tıkla Özet Röntgen Raporu")
        _xr_report_text = f"""🏛️ BIST SHADOW HİSSE RÖNTGENİ — {_xr_ticker}
────────────────────────────────────────────────────
• Tarih & Sektör: {datetime.now().strftime('%Y-%m-%d')} | {_xr_sektor}
• Model: {model_badge}
• Model Sırası: #{_xr_rank} / {len(_xr_sembol_listesi)}
• Shadow Ham Skoru: {_xr_skor:+.4f}
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
