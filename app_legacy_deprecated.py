"""
app.py — FAZ 9: BIST Sniper Web Terminali & Portföy Yönetim Paneli
===================================================================
Plan referansı: FAZ 9 (bist_sinyal_botu_proje_plani_v2.md)

Özellikler:
  1. 50 Hisse BIST Evreni & VIP Özel Portföy (TUPRS, MGROS, SAHOL, TERA, FORTE, TUREX)
  2. FAZ C Temel Değerleme Katmanı: F/K İskontosu, Net Kâr Trendi, EPS Sürprizi
  3. Net Al-Sat Eylem Rehberi & Alınacak Kâr (TL ve %) Tablosu
  4. Portföy Yönetimi: Arayüzden kolayca hisse/pozisyon ekleme, silme ve kapatma.
  5. Canlı Kâr/Zarar, Trailing Stop ve Kilitli Kâr Takibi.
  6. Plotly İnteraktif Mum Grafiği & Al-Sat Seviyeleri.
  7. Otomatik Risk Sizing Lot Hesaplayıcısı.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
import sqlite3

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

# Proje kökünü ekle
sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
from bot.paper_trader import (
    init_db, anlik_pnl_durumu_cek, getir_tum_islemler, getir_acik_pozisyonlar,
    yeni_pozisyon_ac, pozisyon_sil, pozisyon_manuel_kapat, bakiye_guncelle, bakiye_getir, DB_PATH
)
from bot.sinyal_skoru import hesapla_islem_skoru
from bot.health_check import health_check_verisi
from bot.telegram_messages_tr import formatla_yeni_sinyal_mesaji
from run_daily import calistir_gunluk
from bot.kap_filter import cek_hisse_haberleri, analiz_et_kap_riski

# ─── YARDIMCI FORMATLAYICI ───────────────────────────────────────────────────
def format_hisse_secimi(sembol: str) -> str:
    """Hisse seçim kutusunda VIP ve Sektör rozetini gösterir."""
    clean = sembol.replace(".IS", "")
    is_vip = sembol in cfg.VIP_HISSELER or clean in [s.replace(".IS", "") for s in cfg.VIP_HISSELER]
    sektor = cfg.HISSE_SEKTOR.get(sembol, "BIST").replace(".IS", "")
    vip_str = "👑 [VIP] " if is_vip else ""
    return f"{vip_str}#{clean} ({sektor})"

# ─── STREAMLIT SAYFA AYARLARI ────────────────────────────────────────────────
st.set_page_config(
    page_title="BIST Sniper Al-Sat Terminali",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── ÖZEL CSS STİLİ (DARK THEME & MODERN FINTECH) ───────────────────────────
st.markdown("""
<style>
    .profit-card {
        background: linear-gradient(135deg, rgba(0, 230, 118, 0.12) 0%, rgba(0, 80, 40, 0.22) 100%);
        border: 2px solid #00e676;
        border-radius: 12px;
        padding: 16px 20px;
        text-align: center;
    }
    .loss-card {
        background: linear-gradient(135deg, rgba(255, 23, 68, 0.12) 0%, rgba(120, 0, 20, 0.22) 100%);
        border: 2px solid #ff1744;
        border-radius: 12px;
        padding: 16px 20px;
        text-align: center;
    }
    .ratio-card {
        background: linear-gradient(135deg, rgba(0, 176, 255, 0.12) 0%, rgba(0, 60, 120, 0.22) 100%);
        border: 2px solid #00b0ff;
        border-radius: 12px;
        padding: 16px 20px;
        text-align: center;
    }
    .fundamental-card {
        background: #1e222d;
        border: 1px solid #363c4e;
        border-left: 5px solid #ffab00;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .news-card {
        background: #1e222d;
        border: 1px solid #363c4e;
        border-left: 5px solid #00b0ff;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .action-guide-box {
        background: #1e222d;
        border-left: 6px solid #00e676;
        border-radius: 10px;
        padding: 20px 24px;
        margin-top: 15px;
        margin-bottom: 20px;
    }
    .action-guide-neutral {
        background: #1e222d;
        border-left: 6px solid #ffab00;
        border-radius: 10px;
        padding: 20px 24px;
        margin-top: 15px;
        margin-bottom: 20px;
    }
    .action-guide-pos {
        background: #1e222d;
        border-left: 6px solid #29b6f6;
        border-radius: 10px;
        padding: 20px 24px;
        margin-top: 15px;
        margin-bottom: 20px;
    }
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 13px;
        margin-right: 8px;
    }
    .badge-vip { background-color: #ffd700; color: #000; }
    .badge-buy { background-color: #00e676; color: #000; }
    .badge-tp { background-color: #00b0ff; color: #000; }
    .badge-sl { background-color: #ff1744; color: #fff; }
    .badge-time { background-color: #ff9100; color: #000; }
</style>
""", unsafe_allow_html=True)


# ─── YAN MENÜ (SIDEBAR) ─────────────────────────────────────────────────────
st.sidebar.title("🎯 BIST Sniper Terminali")
st.sidebar.caption("v3.0 — 50 Hisse BIST Evreni & VIP Portföy")
st.sidebar.divider()

sayfa = st.sidebar.radio(
    "Menü",
    [
        "📈 Hızlı Analiz & Al-Sat Rehberi",
        "📰 Canlı KAP & Haber Radarı",
        "💼 Portföyüm & Pozisyon Yönetimi",
        "⚙️ Hisse Evreni & Manuel Tarama",
        "🛡️ Sistem Sağlığı (Health Check)"
    ],
    index=0
)

st.sidebar.divider()

# Kaydedilmiş Bakiye
mevcut_bakiye = bakiye_getir(varsayilan=100_000.0)
st.sidebar.markdown(f"💰 **Kayıtlı Kasa:** `{mevcut_bakiye:,.0f} TL`")

with st.sidebar.expander("⚙️ Portföy & Risk Ayarları"):
    yeni_kasa_girdisi = st.number_input("Yeni Portföy Bakiyesi (TL):", min_value=5_000.0, value=float(mevcut_bakiye), step=10_000.0)
    max_poz_limiti = st.slider("Maksimum Açık Pozisyon Limiti:", min_value=3, max_value=20, value=int(getattr(cfg, "MAX_ESSZAMANLI_POZISYON", 10)), step=1)
    if st.button("Ayarları Kaydet"):
        bakiye_guncelle(yeni_kasa_girdisi)
        cfg.MAX_ESSZAMANLI_POZISYON = max_poz_limiti
        st.success("Ayarlar güncellendi!")
        st.rerun()

st.sidebar.divider()
st.sidebar.caption("🛡️ Risk Kuralı: Max %0.5 / İşlem\n🎯 Hedef: 1.5x ATR | Stop: 1.0x ATR\n👑 VIP Portföy: 6 Hisse Kalıcı")


@st.cache_data(ttl=60)
def yukle_hisse_feature_df(dosya_yolu: str) -> Optional[pd.DataFrame]:
    """Parquet feature dosyasını önbellekli okur (Yüksek Hız)."""
    p = Path(dosya_yolu)
    if p.exists():
        return pd.read_parquet(p).sort_index()
    return None


# ═════════════════════════════════════════════════════════════════════════════
# SAYFA 1: HIZLI ANALİZ & NET AL-SAT REHBERİ (ALINACAK KÂR DETAYI)
# ═════════════════════════════════════════════════════════════════════════════
if sayfa == "📈 Hızlı Analiz & Al-Sat Rehberi":
    st.title(f"📈 {len(cfg.HISSELER)} Hisse BIST Analizi & Net Al-Sat Eylem Rehberi")
    
    col_filter, col_sel, col_port_kasa = st.columns([1.5, 2.5, 2])
    with col_filter:
        filtre_kategori = st.selectbox(
            "Filtrele:",
            [
                f"Tüm Hisseler ({len(cfg.HISSELER)})",
                f"👑 VIP Özel Portföy ({len(cfg.VIP_HISSELER)})",
                "Bankacılık (XBANK)",
                "Perakende & Gıda",
                "Sanayi / Otomotiv / Havacılık",
                "Teknoloji / Yan Tahta / Büyüme"
            ],
            index=0
        )
        
    # Filtrelenmiş liste
    if "VIP" in filtre_kategori:
        hisse_listesi = [h for h in cfg.HISSELER if h in cfg.VIP_HISSELER]
    elif "Bankacılık" in filtre_kategori:
        hisse_listesi = [h for h in cfg.HISSELER if cfg.HISSE_SEKTOR.get(h) == "XBANK.IS"]
    elif "Perakende" in filtre_kategori:
        hisse_listesi = [h for h in cfg.HISSELER if cfg.HISSE_SEKTOR.get(h) == "MINI_PERAKENDE" or h in ["CCOLA.IS", "AEFES.IS", "ULKER.IS", "TABGD.IS", "GOKNR.IS"]]
    elif "Teknoloji" in filtre_kategori:
        hisse_listesi = [h for h in cfg.HISSELER if h in ["AGROT.IS", "BINHO.IS", "REEDR.IS", "SDTTR.IS", "MIATK.IS", "FORTE.IS", "TERA.IS", "TUREX.IS", "MTRKS.IS", "LOGO.IS", "PASEU.IS", "PLTUR.IS", "INVES.IS", "KBORU.IS", "ALVES.IS", "ONCSM.IS", "SURGY.IS"]]
    elif "Sanayi" in filtre_kategori:
        hisse_listesi = [h for h in cfg.HISSELER if cfg.HISSE_SEKTOR.get(h) == "XUSIN.IS" and h not in ["CCOLA.IS", "AEFES.IS", "ULKER.IS", "TABGD.IS", "GOKNR.IS"]]
    else:
        hisse_listesi = cfg.HISSELER

    with col_sel:
        secilen_hisse = st.selectbox(
            "Analiz Edilecek Hisseyi Seçiniz:",
            hisse_listesi,
            format_func=format_hisse_secimi,
            index=0
        )
    with col_port_kasa:
        kullanici_kasasi = st.number_input("Hesaplamada Kullanılacak Kasa (TL):", min_value=10_000.0, value=float(mevcut_bakiye), step=10_000.0)

    feat_dosya = cfg.DATA_FEAT / f"{secilen_hisse.replace('.', '_')}.parquet"
    df_feat = yukle_hisse_feature_df(str(feat_dosya))
    
    if df_feat is not None and not df_feat.empty:
        son_bar = df_feat.iloc[-1]
        kapanis = float(son_bar["close"])
        atr = float(son_bar["atr_14"])
        kalibre_p = float(son_bar.get("kalibre_olasilik", 0.42)) if "kalibre_olasilik" in son_bar else 0.42
        p_hizli_tp = float(son_bar.get("p_hizli_tp", 0.0))
        is_hizli = (p_hizli_tp >= cfg.SINYAL_ESIGI_HIZLI_TP) or (kalibre_p >= 0.45)
        
        is_vip = secilen_hisse in cfg.VIP_HISSELER
        vip_rozet_html = '<span class="badge badge-vip">👑 VIP ÖZEL PORTFÖY</span>' if is_vip else ''
        hiz_rozet_html = '<span class="badge badge-tp">🚀 Hızlı Sniper (1-3 Gün)</span>' if is_hizli else '<span class="badge badge-buy">🎯 Standart Sniper (1-5 Gün)</span>'

        # VIX ve Rejim
        vix_durum = "NORMAL"
        if "vix_ret_3d" in son_bar and not pd.isna(son_bar["vix_ret_3d"]):
            if son_bar["vix_ret_3d"] > cfg.VIX_PANIK_ESIK:
                vix_durum = "KURESEL_PANIK"
            elif son_bar["vix_ret_3d"] > cfg.VIX_ARTIS_UYARI_ESIK:
                vix_durum = "ARTIS_UYARISI"

        rejim = str(son_bar.get("xu100_rejim", "GUCLU_YUKSELIS"))

        skor_res = hesapla_islem_skoru(
            model_olasiligi=kalibre_p,
            risk_odul=1.5,
            vol_ratio_20=float(son_bar.get("vol_ratio_20", 1.0)),
            hacim_soku=int(son_bar.get("hacim_soku", 0)),
            rel_str_xu100_5d=float(son_bar.get("rel_str_xu100_5d", 0.0)),
            rel_str_sektor_5d=float(son_bar.get("rel_str_sektor_5d", 0.0)),
            vix_durum=vix_durum,
            piyasa_rejimi=rejim,
            fx_beta_60d=float(son_bar.get("fx_beta_60d", 0.0)) if "fx_beta_60d" in son_bar else 0.0,
            usdtry_ret_5d=float(son_bar.get("usdtry_ret_5d", 0.0)) if "usdtry_ret_5d" in son_bar else 0.0,
            vol_rejim_orani=float(son_bar.get("vol_rejim_orani", 1.0)) if "vol_rejim_orani" in son_bar else 1.0,
            fk_sektor_orani=float(son_bar.get("fk_sektor_orani", 0.0)) if "fk_sektor_orani" in son_bar else 0.0,
            eps_surpriz_yonu=int(son_bar.get("eps_surpriz_yonu", 0)) if "eps_surpriz_yonu" in son_bar else 0,
            cmf_20=float(son_bar.get("cmf_20", 0.0)) if "cmf_20" in son_bar else 0.0,
            squeeze_on=int(son_bar.get("squeeze_on", 0)) if "squeeze_on" in son_bar else 0,
            squeeze_fired=int(son_bar.get("squeeze_fired", 0)) if "squeeze_fired" in son_bar else 0,
            squeeze_momentum=float(son_bar.get("squeeze_momentum", 0.0)) if "squeeze_momentum" in son_bar else 0.0,
            gunluk_tl_hacim=float(son_bar.get("close", 0.0)) * float(son_bar.get("volume", 0.0)),
        )
        islem_skoru = skor_res["islem_skoru"]

        # Seviyeler
        limit_giris = kapanis * (1.0 - getattr(cfg, "LIMIT_GIRIS_ISKONTO", 0.003))
        limit_tavan = limit_giris * (1.0 + getattr(cfg, "MAX_GAP_UP_GIRIS_TOLERANS", 0.02))
        tp1 = limit_giris + (1.5 * atr)
        tp2 = limit_giris + (2.5 * atr)
        sl  = limit_giris - (1.0 * atr)

        tp1_pct = ((tp1 - limit_giris) / limit_giris) * 100.0
        tp2_pct = ((tp2 - limit_giris) / limit_giris) * 100.0
        sl_pct  = ((sl - limit_giris) / limit_giris) * 100.0

        # Lot ve Kâr Hesaplaması
        stop_mesafesi = atr * cfg.K2
        risk_butcesi = kullanici_kasasi * cfg.MAX_RISK_PER_ISLEM  # %0.5
        onerilen_lot = int(risk_butcesi / stop_mesafesi) if stop_mesafesi > 0 else 0
        toplam_yatirim_tl = onerilen_lot * limit_giris
        max_nominal_tavan = kullanici_kasasi * cfg.MAX_POZISYON_AGIRLIGI

        if toplam_yatirim_tl > max_nominal_tavan:
            onerilen_lot = int(max_nominal_tavan / limit_giris)
            toplam_yatirim_tl = onerilen_lot * limit_giris

        satilan_lot_tp1 = max(1, onerilen_lot // 2) if onerilen_lot > 1 else onerilen_lot
        kalan_lot_tp2 = onerilen_lot - satilan_lot_tp1

        tp1_net_kar_tl = satilan_lot_tp1 * (tp1 - limit_giris)
        tp2_net_kar_tl = kalan_lot_tp2 * (tp2 - limit_giris)
        toplam_hedef_kar_tl = tp1_net_kar_tl + tp2_net_kar_tl
        sl_zarar_tl = onerilen_lot * (limit_giris - sl)

        # Açık pozisyonda mı?
        acik_pozlar = getir_acik_pozisyonlar()
        acik_mi = any(p["sembol"] == secilen_hisse for p in acik_pozlar)

        # ─── METRİK KARTLARI (TEMEL + 3 ALTIN TEKNİK) ────────────────────────
        st.markdown(f"### 📊 #{secilen_hisse.replace('.IS', '')} {vip_rozet_html} {hiz_rozet_html}", unsafe_allow_html=True)
        
        tf1, tf2, tf3, tf4, tf5, tf6 = st.columns(6)
        with tf1:
            fk_val = float(son_bar.get("fk_orani", 0.0)) if "fk_orani" in son_bar else 0.0
            st.metric("F/K Oranı", f"{fk_val:.1f}" if fk_val > 0 else "N/A")
        with tf2:
            fks_val = float(son_bar.get("fk_sektor_orani", 0.0)) if "fk_sektor_orani" in son_bar else 0.0
            iskonto_text = f"%{abs(fks_val)*100:.0f} İskontolu" if fks_val <= -0.10 else (f"%{fks_val*100:.0f} Primli" if fks_val >= 0.20 else "Sektöre Paralel")
            st.metric("Sektör F/K", iskonto_text)
        with tf3:
            eps_val = int(son_bar.get("eps_surpriz_yonu", 0)) if "eps_surpriz_yonu" in son_bar else 0
            eps_str = "🟢 Güçlü Artış" if eps_val == 1 else ("🔴 Daralma" if eps_val == -1 else "🟡 Dengeli")
            st.metric("Net Kâr", eps_str)
        with tf4:
            cmf_v = float(son_bar.get("cmf_20", 0.0)) if "cmf_20" in son_bar else 0.0
            cmf_badge = "🟢 Güçlü Giriş" if cmf_v >= 0.08 else ("🟡 Pozitif" if cmf_v >= 0.0 else "🔴 Çıkış Var")
            st.metric("CMF Para Akışı", f"{cmf_v:+.2f}", cmf_badge)
        with tf5:
            sq_on = int(son_bar.get("squeeze_on", 0)) if "squeeze_on" in son_bar else 0
            sq_fired = int(son_bar.get("squeeze_fired", 0)) if "squeeze_fired" in son_bar else 0
            sq_text = "🔥 PATLADI" if sq_fired == 1 else ("⏳ SIKIŞTI" if sq_on == 1 else "NORMAL")
            st.metric("Volatilite Sıkışması", sq_text)
        with tf6:
            fx_beta = float(son_bar.get("fx_beta_60d", 0.0)) if "fx_beta_60d" in son_bar else 0.0
            st.metric("FX-Beta", f"{fx_beta:+.2f}")

        # ─── 1. BÜYÜK ALINACAK KÂR VE ZARAR KARTLARI (2 KADEMELİ) ─────────────
        st.markdown("### 💰 2 Kademeli Kâr & Risk Simülatörü")
        k1, k2, k3, k4 = st.columns(4)

        with k1:
            st.markdown(f"""
            <div class="profit-card">
                <div style="font-size:14px; color:#cfd8dc; font-weight:600;">🎯 TP1 (%50 KÂR KİLİTLE)</div>
                <div style="font-size:26px; color:#00e676; font-weight:800; margin:6px 0;">+{tp1_net_kar_tl:,.1f} TL</div>
                <div style="font-size:13px; color:#a5d6a7;"><b>{satilan_lot_tp1} Lot @ {tp1:.2f} TL</b> (+%{tp1_pct:.1f})<br><i>Stop Maliyete Çekilir</i></div>
            </div>
            """, unsafe_allow_html=True)

        with k2:
            st.markdown(f"""
            <div class="profit-card" style="border-color:#00b0ff; background:rgba(0, 176, 255, 0.12);">
                <div style="font-size:14px; color:#cfd8dc; font-weight:600;">🚀 TP2 (KALAN %50 TREND)</div>
                <div style="font-size:26px; color:#00b0ff; font-weight:800; margin:6px 0;">+{tp2_net_kar_tl:,.1f} TL</div>
                <div style="font-size:13px; color:#81d4fa;"><b>{kalan_lot_tp2} Lot @ {tp2:.2f} TL</b> (+%{tp2_pct:.1f})<br><i>Toplam Kâr: +{toplam_hedef_kar_tl:,.1f} TL</i></div>
            </div>
            """, unsafe_allow_html=True)

        with k3:
            st.markdown(f"""
            <div class="loss-card">
                <div style="font-size:14px; color:#cfd8dc; font-weight:600;">🛑 İLK STOP KAYBI (SL)</div>
                <div style="font-size:26px; color:#ff1744; font-weight:800; margin:6px 0;">-{sl_zarar_tl:,.1f} TL</div>
                <div style="font-size:13px; color:#ef9a9a;"><b>{onerilen_lot} Lot @ {sl:.2f} TL</b> (-%{abs(sl_pct):.1f})<br><i>TP1 Sonrası Stop: 0 TL Risk</i></div>
            </div>
            """, unsafe_allow_html=True)

        with k4:
            st.markdown(f"""
            <div class="ratio-card">
                <div style="font-size:14px; color:#cfd8dc; font-weight:600;">⚖️ RİSK / ÖDÜL ORANI</div>
                <div style="font-size:26px; color:#00b0ff; font-weight:800; margin:6px 0;">1 : {skor_res.get('gercek_rr', 1.5):.2f}</div>
                <div style="font-size:13px; color:#90caf9;">İşlem Skoru: <b>{islem_skoru} / 100</b><br>Karar: <b>{skor_res.get('karar_aksiyonu')}</b></div>
            </div>
            """, unsafe_allow_html=True)

        # ─── 2. YAZILI ADIM ADIM AL-SAT TALİMATI ─────────────────────────────
        st.markdown("### 📋 Yazılı Al-Sat Eylem Rehberi (Nereden Alıp Nerede Satacaksınız?)")

        if acik_mi:
            st.markdown(f"""
            <div class="action-guide-pos">
                <h3 style="color:#29b6f6; margin-top:0;">🔵 BU HİSSE ŞU AN PORTFÖYÜNÜZDE TAŞINIYOR</h3>
                <p style="font-size:16px;">Giriş yapılmış aktif pozisyonunuz bulunmaktadır. Aşağıdaki satış hedeflerine göre emir veriniz:</p>
                <hr style="border-color:#29b6f6;">
                <p>🎯 <span class="badge badge-tp">KÂRLA SATIŞ SEVİYESİ</span> Fiyat <b>{tp1:.2f} TL (+%{tp1_pct:.1f})</b> seviyesine geldiğinde lotlarınızı kârla satıp çıkınız.</p>
                <p>🛑 <span class="badge badge-sl">ZARAR KES SATIŞ SEVİYESİ</span> Fiyat <b>{sl:.2f} TL (-%{abs(sl_pct):.1f})</b> altına düşerse lotları tereddütsüz satınız.</p>
                <p>⏳ <span class="badge badge-time">ZAMAN KURALI</span> 5 işlem günü dolduğunda hedefe ulaşılamadıysa cuma kapanışında çıkınız.</p>
            </div>
            """, unsafe_allow_html=True)

        elif islem_skoru >= 65:
            st.markdown(f"""
            <div class="action-guide-box">
                <h3 style="color:#00e676; margin-top:0;">🟢 İŞLEM KARARI: GÜÇLÜ AL SİNYALİ (İşlem Skoru: {islem_skoru} / 100)</h3>
                <p style="font-size:16px;">Model ve piyasa rejimi yüksek olasılıklı alım fırsatına işaret ediyor. Aşağıdaki adımları uygulayınız:</p>
                <hr style="border-color:#00e676;">
                <p><b>1. <span class="badge badge-buy">NEREDEN ALACAKSINIZ?</span></b> <b>T+1 Sabah Açılışında (09:55-10:00)</b> piyasa emri ile veya maksimum <b>{limit_tavan:.2f} TL</b> limit fiyat ile <b>{onerilen_lot:,} Lot</b> alınız.</p>
                <p><b>2. <span class="badge badge-tp">NEREDE SATACAKSINIZ (KÂR AL - TP1)?</span></b> Fiyat <b>{tp1:.2f} TL</b> seviyesine geldiğinde lotlarınızı satın ➔ <b>+{tp1_net_kar_tl:,.1f} TL Net Kâr</b> cebinize girer.</p>
                <p><b>3. <span class="badge badge-tp">GENİŞLETİLMİŞ HEDEF (TP2)</span></b> Güçlü trendde 2. hedef: <b>{tp2:.2f} TL</b> ➔ <b>+{tp2_net_kar_tl:,.1f} TL Net Kâr</b>.</p>
                <p><b>4. <span class="badge badge-sl">NEREDE ZARAR DURDURACAKSINIZ (STOP-LOSS)?</span></b> Fiyat <b>{sl:.2f} TL</b> altına inerse pozisyonu kapatın ➔ Kaybınız maksimum <b>-{sl_zarar_tl:,.1f} TL (%0.5 kasa riski)</b> ile sınırlanır.</p>
                <p><b>5. <span class="badge badge-time">ZAMAN STOPU</span></b> 5 işlem günü dolduğunda hedefe varılmadıysa cuma günü piyasa fiyatından çıkınız.</p>
                <p style="color:#ffcc80; font-size:14px;"><i>⚠️ Not: Sabah açılışında %4'ten büyük yukarı gap oluşursa peşinden koşmayınız, işlemi İPTAL ediniz.</i></p>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.markdown(f"""
            <div class="action-guide-neutral">
                <h3 style="color:#ffab00; margin-top:0;">🟡 İŞLEM KARARI: NÖTR / BEKLEMEDE (İşlem Skoru: {islem_skoru} / 100)</h3>
                <p style="font-size:16px;">Bu hisse için şu an <b>Sniper giriş kriterleri oluşmamıştır</b>. Yeni alım yapılması önerilmez.</p>
                <hr style="border-color:#ffab00;">
                <p>• Son Kapanış: <b>{kapanis:.2f} TL</b> | ATR Volatilitesi: <b>{atr:.2f} TL</b></p>
                <p>• Olası Hedef: <b>{tp1:.2f} TL (+%{tp1_pct:.1f})</b> | Olası Stop: <b>{sl:.2f} TL (-%{abs(sl_pct):.1f})</b></p>
                <p><i>Sistem sadece skoru 65 ve üzeri olan yüksek olasılıklı fırsatlarda alım önerir.</i></p>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # ─── 3. PLOTLY ULTRA OKUNABİLİR TRADING GRAFİĞİ ───────────────────────
        st.subheader("📊 Fiyat Grafiği, İndikatörler & Al-Sat Hedef Bölgeleri")

        g_col1, g_col2, g_col3 = st.columns([2, 3, 3])
        with g_col1:
            zaman_secimi = st.selectbox(
                "📅 Görünüm Aralığı:",
                ["Son 1 Ay (22 Bar)", "Son 3 Ay (65 Bar)", "Son 6 Ay (130 Bar)", "Son 1 Yıl (260 Bar)"],
                index=1
            )
        with g_col2:
            st.write("📈 **İndikatör Seçenekleri:**")
            ind_ma = st.checkbox("Hareketli Ortalamalar (SMA 20 / 50)", value=True)
            ind_bb = st.checkbox("Bollinger Bantları (Volatilite)", value=True)
        with g_col3:
            st.write("🎯 **Hedef & Osilatörler:**")
            ind_zones = st.checkbox("Kâr / Stop Gölgeli Hedef Alanları", value=True)
            ind_rsi = st.checkbox("RSI (14) Momentum Paneli", value=True)

        bar_limit = 65
        if "1 Ay" in zaman_secimi:
            bar_limit = 22
        elif "6 Ay" in zaman_secimi:
            bar_limit = 130
        elif "1 Yıl" in zaman_secimi:
            bar_limit = 260

        df_plot = df_feat.iloc[-bar_limit:].copy()

        # Alt grafik satır sayısı
        if ind_rsi:
            fig = make_subplots(
                rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                row_heights=[0.60, 0.20, 0.20],
                subplot_titles=(f"#{secilen_hisse.replace('.IS', '')} Fiyat & Hedef Seviyeleri", "Hacim", "RSI (14) Momentum")
            )
        else:
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                row_heights=[0.75, 0.25],
                subplot_titles=(f"#{secilen_hisse.replace('.IS', '')} Fiyat & Hedef Seviyeleri", "Hacim")
            )

        # 1. Mumlar (Candlestick)
        fig.add_trace(go.Candlestick(
            x=df_plot.index,
            open=df_plot['open'],
            high=df_plot['high'],
            low=df_plot['low'],
            close=df_plot['close'],
            name="Fiyat Mumları",
            increasing_line_color="#00e676",
            increasing_fillcolor="#00e676",
            decreasing_line_color="#ff1744",
            decreasing_fillcolor="#ff1744",
            line_width=1.2
        ), row=1, col=1)

        # 2. Bollinger Bantları
        if ind_bb and "bb_high_20_2" in df_plot and "bb_low_20_2" in df_plot:
            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot["bb_high_20_2"],
                line=dict(color="rgba(144, 202, 249, 0.4)", width=1, dash="dot"),
                name="Bollinger Üst", hoverinfo="skip"
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot["bb_low_20_2"],
                line=dict(color="rgba(144, 202, 249, 0.4)", width=1, dash="dot"),
                fill='tonexty', fillcolor="rgba(144, 202, 249, 0.05)",
                name="Bollinger Bant Alanı"
            ), row=1, col=1)

        # 3. Hareketli Ortalamalar
        if ind_ma:
            if "close_sma_20" in df_plot:
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["close_sma_20"], line=dict(color="#29b6f6", width=2), name="SMA 20 (Kısa Vade)"), row=1, col=1)
            if "close_sma_50" in df_plot:
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["close_sma_50"], line=dict(color="#ffa726", width=2), name="SMA 50 (Orta Vade)"), row=1, col=1)

        # 4. Gölgeli Kâr ve Zarar Hedef Alanları
        son_tarih = df_plot.index[-1]
        ilk_tarih_zone = df_plot.index[-min(15, len(df_plot))]

        if ind_zones:
            # Yeşil Kâr Bölgesi
            fig.add_shape(
                type="rect", xref="x", yref="y",
                x0=ilk_tarih_zone, x1=son_tarih, y0=kapanis, y1=tp1,
                fillcolor="rgba(0, 230, 118, 0.15)", line=dict(width=0),
                row=1, col=1
            )
            # Kırmızı Stop Bölgesi
            fig.add_shape(
                type="rect", xref="x", yref="y",
                x0=ilk_tarih_zone, x1=son_tarih, y0=sl, y1=kapanis,
                fillcolor="rgba(255, 23, 68, 0.15)", line=dict(width=0),
                row=1, col=1
            )

        # 5. Seviye Çizgileri & Etiketler
        fig.add_hline(y=tp1, line_dash="solid", line_color="#00e676", line_width=2.5,
                      annotation_text=f"🎯 TP1 KÂR AL: {tp1:.2f} TL (+{tp1_net_kar_tl:,.0f} TL | %{tp1_pct:+.1f})",
                      annotation_position="top right", annotation_font_color="#00e676", annotation_font_size=13, row=1, col=1)

        fig.add_hline(y=kapanis, line_dash="dash", line_color="#ffd600", line_width=1.5,
                      annotation_text=f"📍 GİRİŞ / KAPANIŞ: {kapanis:.2f} TL",
                      annotation_position="bottom right", annotation_font_color="#ffd600", annotation_font_size=12, row=1, col=1)

        fig.add_hline(y=sl, line_dash="solid", line_color="#ff1744", line_width=2.5,
                      annotation_text=f"🛑 STOP-LOSS: {sl:.2f} TL (-{sl_zarar_tl:,.0f} TL | %{sl_pct:.1f})",
                      annotation_position="bottom right", annotation_font_color="#ff1744", annotation_font_size=13, row=1, col=1)

        # 6. Hacim Paneli
        vol_colors = ["#00e676" if c >= o else "#ff1744" for c, o in zip(df_plot['close'], df_plot['open'])]
        fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['volume'], marker_color=vol_colors, name="Hacim", opacity=0.85), row=2, col=1)

        # 7. RSI (14) Paneli
        if ind_rsi and "rsi_14" in df_plot:
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["rsi_14"], line=dict(color="#e040fb", width=2), name="RSI (14)"), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#ff5252", line_width=1, annotation_text="Aşırı Alım (70)", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#69f0ae", line_width=1, annotation_text="Aşırı Satım (30)", row=3, col=1)
            fig.add_hline(y=50, line_dash="dot", line_color="#78909c", line_width=1, row=3, col=1)
            fig.update_yaxes(range=[15, 85], row=3, col=1)

        fig.update_layout(
            height=720,
            template="plotly_dark",
            paper_bgcolor="#131722",
            plot_bgcolor="#1e222d",
            xaxis_rangeslider_visible=False,
            margin=dict(l=40, r=40, t=40, b=30),
            hovermode="x unified",
            legend=dict(orientation="h", y=1.04, x=0.01, bgcolor="rgba(0,0,0,0.5)")
        )
        fig.update_xaxes(gridcolor="#2a2e39", showgrid=True)
        fig.update_yaxes(gridcolor="#2a2e39", showgrid=True)

        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ─── 4. CANLI KAP & FİNANS HABERLERİ ─────────────────────────────────
        st.subheader(f"📰 #{secilen_hisse.replace('.IS', '')} — Canlı KAP & Şirket Haberleri")
        
        with st.spinner("Son 7 günün KAP ve finans haberleri taranıyor..."):
            haberler = cek_hisse_haberleri(secilen_hisse, max_haber=5, max_gun=7)
            risk_durumu, eslesen_kelimeler, riskli_basliklar, has_bilanco = analiz_et_kap_riski(haberler)

        c_risk1, c_risk2 = st.columns([1, 3])
        with c_risk1:
            if has_bilanco:
                st.info("📊 **Bilanço / Finansal Rapor**\n\nBu hissede güncel finansal sonuç bildirimi tespit edildi.")
            
            if risk_durumu == "DUSUK":
                st.success("🟢 **KAP Riski: DÜŞÜK**\n\nSon 7 günde olumsuz risk tespiti yok.")
            elif risk_durumu == "ORTA":
                st.warning(f"🟡 **KAP Riski: ORTA**\n\nEşleşen: {', '.join(eslesen_kelimeler)}")
            else:
                st.error(f"🔴 **KAP Riski: YÜKSEK!**\n\nEşleşen: {', '.join(eslesen_kelimeler)}")

        with c_risk2:
            if haberler:
                for h in haberler:
                    bilanco_etiketi = '<span style="background:#7c4dff; color:#fff; padding:2px 6px; border-radius:4px; font-size:11px; margin-left:6px; font-weight:700;">📊 BİLANÇO</span>' if h.get("is_bilanco") else ""
                    st.markdown(f"""
                    <div class="news-card">
                        <div style="display:flex; justify-content:space-between; font-size:12px; color:#90a4ae;">
                            <span>🏢 <b>{h.get('kaynak', 'KAP / Finans')}</b> {bilanco_etiketi}</span>
                            <span>🕒 {h.get('tarih', 'Son 7 Gün')}</span>
                        </div>
                        <div style="font-size:15px; font-weight:600; color:#eceff1; margin-top:4px;">
                            {h.get('baslik', '')}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Bu hisse için son 7 günde yeni bir KAP bildirimi veya olağandışı haber bulunmuyor (Haber akışı sakin).")

    else:
        st.warning(f"{secilen_hisse} için veri bulunamadı.")


# ═════════════════════════════════════════════════════════════════════════════
# SAYFA 2: CANLI KAP & HABER RADARI
# ═════════════════════════════════════════════════════════════════════════════
elif sayfa == "📰 Canlı KAP & Haber Radarı":
    st.title("📰 BIST 50 & VIP — Canlı KAP & Bilanço Radarı (Son 7 Gün)")
    st.write("Sistemdeki **50 BIST hissesinin ve 6 VIP portföy hissesinin** yalnızca son 7 günlük güncel KAP açıklamaları, bilanço bildirimleri ve finans haberleri taranır:")

    col_h_sel, col_h_btn = st.columns([3, 1])
    with col_h_sel:
        secilen_haber_hisse = st.selectbox(
            "Haberleri İncelenecek Hisseyi Seçiniz:",
            cfg.HISSELER,
            format_func=format_hisse_secimi,
            key="kap_radar_secim"
        )
    with col_h_btn:
        st.write("")
        st.write("")
        tara_btn = st.button("🔄 Bu Hisseyi Canlı Tara", type="primary", use_container_width=True)

    with st.spinner(f"#{secilen_haber_hisse.replace('.IS', '')} için son 7 günün KAP ve finans haberleri taranıyor..."):
        h_list = cek_hisse_haberleri(secilen_haber_hisse, max_haber=6, max_gun=7)
        r_durum, r_kelimeler, _, h_bilanco = analiz_et_kap_riski(h_list)

    c_r1, c_r2 = st.columns([1, 3])
    with c_r1:
        if h_bilanco:
            st.info("📊 **Bilanço / Finansal Rapor**\n\nBu hissede güncel finansal sonuç bildirimi tespit edildi.")
        
        if r_durum == "DUSUK":
            st.success("🟢 **KAP Riski: DÜŞÜK**\n\nSon 7 günde olumsuz risk tespiti yok.")
        elif r_durum == "ORTA":
            st.warning(f"🟡 **KAP Riski: ORTA**\n\nEşleşen: {', '.join(r_kelimeler)}")
        else:
            st.error(f"🔴 **KAP Riski: YÜKSEK!**\n\nEşleşen: {', '.join(r_kelimeler)}")

    with c_r2:
        if h_list:
            for h in h_list:
                bilanco_etiketi = '<span style="background:#7c4dff; color:#fff; padding:2px 6px; border-radius:4px; font-size:11px; margin-left:6px; font-weight:700;">📊 BİLANÇO</span>' if h.get("is_bilanco") else ""
                st.markdown(f"""
                <div class="news-card">
                    <div style="display:flex; justify-content:space-between; font-size:12px; color:#90a4ae;">
                        <span>🏢 <b>{h.get('kaynak', 'KAP / Finans')}</b> {bilanco_etiketi}</span>
                        <span>🕒 {h.get('tarih', 'Son 7 Gün')}</span>
                    </div>
                    <div style="font-size:15px; font-weight:600; color:#eceff1; margin-top:4px;">
                        {h.get('baslik', '')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Bu hisse için son 7 günde yeni bir KAP bildirimi veya olağandışı haber bulunmuyor (Haber akışı sakin).")

    st.divider()
    st.subheader("👑 VIP Özel Portföy Hızlı Haber Özeti")
    vip_cols = st.columns(3)
    for idx, v_sembol in enumerate(cfg.VIP_HISSELER):
        with vip_cols[idx % 3]:
            with st.expander(f"👑 **#{v_sembol.replace('.IS', '')}**"):
                v_haberler = cek_hisse_haberleri(v_sembol, max_haber=2, max_gun=7)
                if v_haberler:
                    for vh in v_haberler:
                        st.markdown(f"• {vh.get('baslik', '')}")
                else:
                    st.caption("Son 7 günde olağandışı haber yok.")


# ═════════════════════════════════════════════════════════════════════════════
# SAYFA 3: PORTFÖYÜM & POZİSYON YÖNETİMİ
# ═════════════════════════════════════════════════════════════════════════════
elif sayfa == "💼 Portföyüm & Pozisyon Yönetimi":
    st.title("💼 Portföyüm & Canlı Pozisyon Takibi")
    init_db()

    # ─── YENİ POZİSYON EKLEME MODÜLÜ (DİNAMİK HESAPLAMALI) ───────────────────
    with st.expander("➕ Portföyüme Yeni Hisse / Pozisyon Ekle", expanded=True):
        st.markdown("Gerçekte aldığınız veya takip etmek istediğiniz hisseyi seçtiğinizde **güncel fiyatı ve hedefleri otomatik olarak** gelir:")

        f_top1, f_top2 = st.columns([2, 2])
        with f_top1:
            yeni_sembol = st.selectbox("1. Hisse Seçiniz (50 Hisse):", cfg.HISSELER, format_func=format_hisse_secimi, key="sel_yeni_hisse")

        # Seçilen hissenin güncel fiyatını ve ATR değerini oku
        dosya = cfg.DATA_FEAT / f"{yeni_sembol.replace('.', '_')}.parquet"
        varsayilan_fiyat = 100.0
        varsayilan_atr = 5.0
        if dosya.exists():
            df_temp = pd.read_parquet(dosya)
            varsayilan_fiyat = float(df_temp["close"].iloc[-1])
            varsayilan_atr = float(df_temp["atr_14"].iloc[-1])

        # Dinamik TP ve SL varsayılanları
        varsayilan_tp = round(varsayilan_fiyat + (1.5 * varsayilan_atr), 2)
        varsayilan_sl = round(varsayilan_fiyat - (1.0 * varsayilan_atr), 2)

        with f_top2:
            is_vip_ekle = yeni_sembol in cfg.VIP_HISSELER
            vip_ekle_str = " 👑 [VIP ÖZEL PORTFÖY]" if is_vip_ekle else ""
            st.info(f"⚡ **#{yeni_sembol.replace('.IS', '')}**{vip_ekle_str} Son Borsa Kapanışı: **{varsayilan_fiyat:.2f} TL** | Volatilite (ATR): **{varsayilan_atr:.2f} TL**")

        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            yeni_giris_fiyati = st.number_input(
                "2. Alış / Maliyet Fiyatınız (TL):",
                min_value=0.01,
                value=varsayilan_fiyat,
                step=0.25,
                key=f"in_fiyat_{yeni_sembol}"
            )
        with f_col2:
            yeni_lot = st.number_input(
                "3. Alınan Lot Adedi:",
                min_value=1,
                value=100,
                step=10,
                key=f"in_lot_{yeni_sembol}"
            )
        with f_col3:
            yeni_tarih = st.date_input("4. İşlem Tarihi:", datetime.now(), key=f"in_date_{yeni_sembol}")

        f_col4, f_col5 = st.columns(2)
        with f_col4:
            yeni_tp = st.number_input(
                "5. Kâr Al (TP) Hedef Fiyatı (TL):",
                min_value=0.01,
                value=varsayilan_tp,
                step=0.25,
                key=f"in_tp_{yeni_sembol}"
            )
        with f_col5:
            yeni_sl = st.number_input(
                "6. Zarar Durdur (SL) Fiyatı (TL):",
                min_value=0.01,
                value=varsayilan_sl,
                step=0.25,
                key=f"in_sl_{yeni_sembol}"
            )

        # ─── CANLI POZİSYON HESAPLAMA KARTI ─────────────────────────────────
        toplam_yatirim = yeni_lot * yeni_giris_fiyati
        potansiyel_kar_tl = yeni_lot * (yeni_tp - yeni_giris_fiyati)
        potansiyel_kar_pct = ((yeni_tp - yeni_giris_fiyati) / yeni_giris_fiyati) * 100.0
        potansiyel_kayip_tl = yeni_lot * (yeni_giris_fiyati - yeni_sl)
        potansiyel_kayip_pct = ((yeni_giris_fiyati - yeni_sl) / yeni_giris_fiyati) * 100.0
        rr_orani = (potansiyel_kar_tl / potansiyel_kayip_tl) if potansiyel_kayip_tl > 0 else 1.50

        st.markdown(f"""
        <div style="background:#1e222d; border:1px solid #363c4e; border-radius:10px; padding:14px 20px; margin:15px 0;">
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:16px;">
                <div>💵 <b>Toplam Yatırım Tutarı:</b> <span style="font-size:16px; font-weight:800; color:#fff;">{toplam_yatirim:,.2f} TL</span></div>
                <div>🎯 <b>Kâr Hedefine Ulaşırsa:</b> <span style="font-size:16px; font-weight:800; color:#00e676;">+{potansiyel_kar_tl:,.1f} TL (%{potansiyel_kar_pct:+.2f})</span></div>
                <div>🛑 <b>Stop Olursa Kayıp:</b> <span style="font-size:16px; font-weight:800; color:#ff1744;">-{potansiyel_kayip_tl:,.1f} TL (-%{potansiyel_kayip_pct:.2f})</span></div>
                <div>⚖️ <b>Risk/Kazanç Oranı:</b> <span style="font-size:16px; font-weight:800; color:#00b0ff;">1 : {rr_orani:.2f}</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("💾 Bu Pozisyonu Portföyüme Kaydet", type="primary", use_container_width=True):
            pid = yeni_pozisyon_ac(
                sembol=yeni_sembol,
                giris_fiyati=yeni_giris_fiyati,
                lot_adedi=yeni_lot,
                upper_barrier=yeni_tp,
                lower_barrier=yeni_sl,
                atr=varsayilan_atr,
                islem_skoru=75,
                kalibre_olasilik=0.45,
                sektor=cfg.HISSE_SEKTOR.get(yeni_sembol, "BIST"),
                tarih_str=str(yeni_tarih)
            )
            st.success(f"✅ #{yeni_sembol} ({yeni_lot:,} Lot, {yeni_giris_fiyati:.2f} TL) başarıyla portföye kaydedildi!")
            st.rerun()

    st.divider()

    # ─── CANLI AÇIK POZİSYONLAR ──────────────────────────────────────────────
    canli_aciklar = anlik_pnl_durumu_cek()
    tum_islemler = getir_tum_islemler()
    kapananlar = [i for i in tum_islemler if i["durum"] != "ACIK"]

    toplam_kar_tl = sum(k["net_pnl_tl"] for k in kapananlar)
    kazanan_sayisi = sum(1 for k in kapananlar if k["net_pnl_tl"] > 0)
    win_rate = (kazanan_sayisi / len(kapananlar) * 100.0) if kapananlar else 0.0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Açık Pozisyon Sayısı", f"{len(canli_aciklar)} / {getattr(cfg, 'MAX_ESSZAMANLI_POZISYON', 10)} Adet")
    with m2:
        toplam_anlik_pnl = sum(p["anlik_pnl_tl"] for p in canli_aciklar)
        st.metric("Açık Pozisyonlar Anlık PnL", f"{toplam_anlik_pnl:+,.2f} TL")
    with m3:
        st.metric("Gerçekleşen Toplam Net Kâr", f"{toplam_kar_tl:+,.2f} TL")
    with m4:
        st.metric("Tarihsel Win-Rate", f"%{win_rate:.1f}")

    st.divider()

    st.subheader("🟢 Aktif Pozisyonlarım (Canlı yfinance Fiyatları)")

    if canli_aciklar:
        for p in canli_aciklar:
            poz_id = p["id"]
            kar_renk = "#00e676" if p["anlik_pnl_%"] >= 0 else "#ff1744"
            tp_kazanc_tl = p["lot_adedi"] * (p["tp_hedef"] - p["giris_fiyati"])
            sl_kayip_tl = p["lot_adedi"] * (p["giris_fiyati"] - p["sl_stop"])
            is_vip_p = (p["sembol"] in cfg.VIP_HISSELER or p["sembol"] in [s.replace(".IS", "") for s in cfg.VIP_HISSELER])
            vip_p_str = " 👑 [VIP]" if is_vip_p else ""

            with st.container():
                st.markdown(f"""
                <div style="background:#1e222d; border-left: 6px solid {kar_renk}; padding:18px 24px; border-radius:10px; margin-bottom:15px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h2 style="margin:0; color:#fff;">#{p['sembol']}{vip_p_str} <span style="font-size:15px; color:#90a4ae;">({p['lot_adedi']:,} Lot | Gün: {p['elde_tutma_gun']}/5)</span></h2>
                        <h2 style="margin:0; color:{kar_renk};">%{p['anlik_pnl_%']:+.2f} ({p['anlik_pnl_tl']:+,.1f} TL)</h2>
                    </div>
                    <div style="display:flex; gap:30px; margin-top:12px; font-size:15px; color:#eceff1;">
                        <div>📥 <b>Giriş Fiyatı:</b> {p['giris_fiyati']:.2f} TL</div>
                        <div>⚡ <b>Canlı Fiyat:</b> <span style="color:{kar_renk}; font-weight:800;">{p['anlik_fiyat']:.2f} TL</span></div>
                        <div>🎯 <b>Kâr Hedefi:</b> {p['tp_hedef']:.2f} TL <i>(Hedefe Kalan: %{p['tp_mesafe_%']:.1f} ➔ <b>+{tp_kazanc_tl:,.0f} TL Kâr</b>)</i></div>
                        <div>🛑 <b>Stop-Loss:</b> {p['sl_stop']:.2f} TL <i>(Stopa Mesafe: %{p['sl_mesafe_%']:.1f} ➔ <b>-{sl_kayip_tl:,.0f} TL Risk</b>)</i></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 6])
                with btn_col1:
                    if st.button(f"💰 Canlı Fiyattan Kapat ({p['sembol']})", key=f"close_{poz_id}"):
                        pozisyon_manuel_kapat(poz_id, cikis_fiyati=p['anlik_fiyat'], cikis_nedeni="MANUEL_SATIS")
                        st.success(f"#{p['sembol']} başarıyla kapatıldı!")
                        st.rerun()
                with btn_col2:
                    if st.button(f"🗑️ Pozisyonu Sil ({p['sembol']})", key=f"del_{poz_id}"):
                        pozisyon_sil(poz_id)
                        st.warning(f"#{p['sembol']} silindi!")
                        st.rerun()
                st.write("")
    else:
        st.info("Portföyünüzde henüz açık hisse bulunmamaktadır. Yukarıdaki formdan aldığınız hisseleri ekleyebilirsiniz.")

    st.divider()

    st.subheader("📜 Geçmiş Kapanan İşlem Günlüğü")
    if kapananlar:
        df_kapanan = pd.DataFrame(kapananlar)
        st.dataframe(
            df_kapanan[["sembol", "giris_tarihi", "cikis_tarihi", "giris_fiyati", "cikis_fiyati", "cikis_nedeni", "net_pnl_tl", "net_getiri_pct", "elde_tutma_gun"]],
            use_container_width=True,
            column_config={
                "net_pnl_tl": st.column_config.NumberColumn("Net PnL (TL)", format="%.2f TL"),
                "net_getiri_pct": st.column_config.NumberColumn("Net Getiri %", format="%.2f%%"),
            }
        )
    else:
        st.caption("Henüz kapanmış bir işlem bulunmuyor.")


# ═════════════════════════════════════════════════════════════════════════════
# SAYFA 4: HİSSE EVRENİ & MANUEL TARAMA
# ═════════════════════════════════════════════════════════════════════════════
elif sayfa == "⚙️ Hisse Evreni & Manuel Tarama":
    st.title("⚙️ Takip Edilen Hisse Evreni & Manuel Tarama")

    st.subheader(f"📋 {len(cfg.HISSELER)} Hisse BIST Evreni & VIP Özel Portföy")
    
    e1, e2, e3 = st.columns(3)
    with e1:
        st.metric("Toplam Takip Edilen Hisse", f"{len(cfg.HISSELER)} Adet")
    with e2:
        st.metric("👑 VIP Kalıcı Portföy", f"{len(cfg.VIP_HISSELER)} Hisse")
    with e3:
        st.metric("Aktif Sektör Grupları", "10 Sektör")

    st.markdown("---")

    # Sektörlere göre gruplama
    sektor_gruplari = {}
    for h in cfg.HISSELER:
        if h in cfg.VIP_HISSELER:
            sektor_gruplari.setdefault("👑 VIP Özel Portföy", []).append(h)
        else:
            s = cfg.HISSE_SEKTOR.get(h, "DİĞER").replace(".IS", "")
            sektor_gruplari.setdefault(s, []).append(h)

    cols = st.columns(3)
    for idx, (sektor, hisse_listesi) in enumerate(sektor_gruplari.items()):
        with cols[idx % 3]:
            st.markdown(f"**🏢 {sektor} ({len(hisse_listesi)})**")
            for h in hisse_listesi:
                vip_badge = "👑 " if h in cfg.VIP_HISSELER else ""
                st.write(f"• `{vip_badge}#{h.replace('.IS', '')}`")

    st.divider()

    st.subheader("🔍 Manuel Günlük Tarama Tetikle")
    st.write(f"Aşağıdaki butona basarak tüm {len(cfg.HISSELER)} hisseyi güncelleyebilir, model tahminlerini koşturabilir ve yeni Sniper sinyallerini tarayabilirsiniz:")

    if st.button(f"🚀 Günlük Taramayı Şimdi Çalıştır ({len(cfg.HISSELER)} Hisse)", type="primary", use_container_width=True):
        with st.spinner(f"{len(cfg.HISSELER)} BIST hissesi taranıyor, modeller çalıştırılıyor ve KAP haberleri kontrol ediliyor..."):
            try:
                adaylar = calistir_gunluk(min_islem_skoru=60)
                if adaylar:
                    st.success(f"🎯 **{len(adaylar)} Adet Sniper Sinyali Bulundu!**")
                    for a in adaylar:
                        st.markdown(f"```text\n{formatla_yeni_sinyal_mesaji(a)}\n```")
                else:
                    st.info("Bugün Sniper kriterlerine (Skor >= 60, Güven >= %45) uyan alım fırsatı bulunamadı. Sermaye nakitte korunuyor.")
            except Exception as e:
                st.error(f"Tarama sırasında hata oluştu: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# SAYFA 5: HEALTH CHECK & SİSTEM SAĞLIĞI
# ═════════════════════════════════════════════════════════════════════════════
elif sayfa == "🛡️ Sistem Sağlığı (Health Check)":
    st.title("🛡️ Sistem & Veri Sağlık Denetimi (Health Check)")

    with st.spinner(f"{len(cfg.HISSELER)} hissenin veri serileri ve PSI drift ölçülüyor..."):
        hc = health_check_verisi()

    durum = hc["durum"]
    if durum == "SAGLIKLI":
        st.success(f"✅ Sistem Durumu: **{durum}** — Tüm {len(cfg.HISSELER)} hissenin veri serileri stabil.")
    elif durum == "UYARI":
        st.warning(f"⚠️ Sistem Durumu: **{durum}** — Bazı hisselerde piyasa momentumu/kayması (PSI drift) tespit edildi.")
    else:
        st.error(f"🚨 Sistem Durumu: **{durum}** — Kritik veri hataları tespit edildi!")

    h1, h2, h3 = st.columns(3)
    with h1:
        st.metric("Kontrol Edilen Hisse", f"{hc['kontrol_edilen_hisse']} / {len(cfg.HISSELER)}")
    with h2:
        st.metric("Kritik Hatalar", hc["kritik_uyari_sayisi"])
    with h3:
        st.metric("Drift (Hareketlilik) Sayısı", hc["drift_uyari_sayisi"])

    if hc["kritik_uyarilar"]:
        st.subheader("🚨 Kritik Uyarılar")
        for u in hc["kritik_uyarilar"]:
            st.error(u)

    if hc["drift_uyarilari"]:
        st.subheader("📈 Piyasa Hareketi (PSI Drift) Raporu")
        st.info("💡 **PSI (Population Stability Index) Nedir?** Son 50 günlük volatilite ve RSI dağılımlarının referans döneme göre hareketliliğini ölçer. Güçlü rallilerde PSI doğal olarak yükselir.")
        for d in hc["drift_uyarilari"][:10]:
            st.warning(d)

    st.divider()
    st.subheader("🔄 Otomatik Model Yeniden Eğitimi (Retraining)")
    st.write("Modeli son 50 hisselik piyasa verileri ve multiclass etiketleriyle yeniden eğitebilirsiniz:")
    
    if st.button("🚀 Modeli Şimdi Yeniden Eğit (Retrain Model)", type="secondary", use_container_width=True):
        from models.retrain import modeli_yeniden_egit
        with st.spinner("Model 50 hisse üzerinden eğitiliyor ve kalibre ediliyor (Bu işlem ~1-2 dakika sürebilir)..."):
            ok = modeli_yeniden_egit(veri_guncelle_dahil=False)
            if ok:
                st.success("✅ Model başarıyla yeniden eğitildi ve 'models/aktif' güncellendi!")
            else:
                st.error("❌ Model eğitimi sırasında bir hata oluştu.")

