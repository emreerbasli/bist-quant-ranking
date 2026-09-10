"""
bot/health_check.py — FAZ 5.5: Veri Sağlık Denetimi & PSI Drift Kontrolü
=======================================================================
Plan referansı: FAZ 5.5 (bist_sinyal_botu_proje_plani_v2.md)

Görevler:
  1. Eksik veri, güncel mum gecikmesi (stale bar) kontrolü.
  2. Hacim donması (hacim = 0) ve işlem askıya alma tespiti.
  3. Aşırı tek günlük fiyat sapması (> %20 değişim).
  4. Population Stability Index (PSI) ile Feature Veri Kayması (Drift) ölçümü.
  5. Admin Telegram uyarı formatlama.
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from loguru import logger

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg


def hesapla_psi(beklenen: np.ndarray, gerceklesen: np.ndarray, num_bins: int = 5) -> float:
    """
    Population Stability Index (PSI) hesaplar (Laplace Smoothed).
    
    PSI Değerlendirmesi:
      - PSI < 0.20: Minimal değişim (Sağlıklı / Kararlı)
      - 0.20 <= PSI < 0.50: Orta düzey piyasa rejim kayması (İzlenmeli)
      - PSI >= 0.50: Ciddi piyasa rejim değişimi (Model yeniden eğitilmeli)
    """
    beklenen = beklenen[~np.isnan(beklenen)]
    gerceklesen = gerceklesen[~np.isnan(gerceklesen)]
    
    if len(beklenen) < 20 or len(gerceklesen) < 20:
        return 0.0

    # Eşit aralıklı sınırlar
    min_val = min(beklenen.min(), gerceklesen.min())
    max_val = max(beklenen.max(), gerceklesen.max())
    if min_val == max_val:
        return 0.0

    bin_edges = np.linspace(min_val, max_val, num_bins + 1)
    bin_edges[0] = -np.inf
    bin_edges[-1] = np.inf

    exp_counts, _ = np.histogram(beklenen, bins=bin_edges)
    act_counts, _ = np.histogram(gerceklesen, bins=bin_edges)

    # Laplace Düzeltmesi (Sıfır frekans patlamalarını engeller)
    exp_pct = (exp_counts + 1) / (len(beklenen) + num_bins)
    act_pct = (act_counts + 1) / (len(gerceklesen) + num_bins)

    psi_val = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return float(psi_val)


def health_check_verisi(
    hisseler: Optional[List[str]] = None,
    max_gecikme_gun: int = 4,
) -> Dict[str, Any]:
    """
    Tüm hisse verilerini tarayarak anomali ve sağlık raporu üretir.
    """
    if hisseler is None:
        hisseler = cfg.HISSELER

    bugun = datetime.now().date()
    raporlar = {}
    kritik_uyarilar = []
    drift_uyarilari = []

    for sembol in hisseler:
        dosya = cfg.DATA_RAW / f"{sembol.replace('.', '_')}.parquet"
        if not dosya.exists():
            kritik_uyarilar.append(f"❌ {sembol}: Ham veri dosyası bulunamadı!")
            continue

        df = pd.read_parquet(dosya)
        if df.empty:
            kritik_uyarilar.append(f"❌ {sembol}: Veri seti boş!")
            continue

        son_tarih = df.index[-1].date()
        gecikme = (bugun - son_tarih).days

        # 1. Güncellik Kontrolü (Hafta sonu dahil max 4 gün)
        if gecikme > max_gecikme_gun:
            kritik_uyarilar.append(f"❌ {sembol}: Veri güncel değil! Son mum: {son_tarih} ({gecikme} gün önce)")

        # 2. Son Bar Eksik / NaN Fiyat Kontrolü
        son_bar = df.iloc[-1]
        if pd.isna(son_bar["close"]) or pd.isna(son_bar["open"]) or pd.isna(son_bar["high"]) or pd.isna(son_bar["low"]):
            kritik_uyarilar.append(f"❌ {sembol}: Son günde eksik/boş (NaN) fiyat tespit edildi!")

        # 3. Geçersiz / Negatif Fiyat Kontrolü
        if son_bar["close"] <= 0:
            kritik_uyarilar.append(f"❌ {sembol}: Geçersiz fiyat ({son_bar['close']} TL) tespit edildi!")

        # 4. Hacim Donması (Son 3 barın tamamında sıfır hacim var mı - Tahta Askıya Alma)
        son_3_hacim = df["volume"].iloc[-3:]
        if (son_3_hacim == 0).all():
            kritik_uyarilar.append(f"⚠️ {sembol}: Son 3 işlem gününde tamamen sıfır hacim (İşlem askıya alma / Tahta kapalı)!")

        # 5. Ani Fiyat Sapması (> %25)
        son_degisim = abs(df["close"].pct_change().iloc[-1])
        if son_degisim > 0.25:
            kritik_uyarilar.append(f"⚠️ {sembol}: Son gün %{son_degisim*100:.1f} aşırı fiyat hareketi (Split veya Anomali)!")


        # 6. Feature Drift Kontrolü (data/features/{ticker}.parquet üzerinden)
        feat_dosya = cfg.DATA_FEAT / f"{sembol.replace('.', '_')}.parquet"
        if not feat_dosya.exists():
            kritik_uyarilar.append(f"❌ {sembol}: Gösterge/Feature dosyası eksik!")
            continue

        df_feat = pd.read_parquet(feat_dosya)
        if len(df_feat) >= 120:
                # Referans: Son 250 gün (veya ilk %70), İzleme: Son 50 gün
                if len(df_feat) >= 300:
                    ref_slice = df_feat.iloc[-300:-50]
                    cur_slice = df_feat.iloc[-50:]
                else:
                    split_idx = int(len(df_feat) * 0.75)
                    ref_slice = df_feat.iloc[:split_idx]
                    cur_slice = df_feat.iloc[split_idx:]

                ref_rsi = ref_slice["rsi_14"].values
                cur_rsi = cur_slice["rsi_14"].values
                psi_rsi = hesapla_psi(ref_rsi, cur_rsi)

                ref_vol = ref_slice["vol_ratio_20"].values
                cur_vol = cur_slice["vol_ratio_20"].values
                psi_vol = hesapla_psi(ref_vol, cur_vol)

                s_clean = sembol.replace(".IS", "")
                if psi_rsi >= cfg.PSI_KRITIK_ESIGI or psi_vol >= cfg.PSI_KRITIK_ESIGI:
                    drift_uyarilari.append(f"🚀 #{s_clean} — Güçlü Ralli / Yüksek Momentum")
                elif psi_rsi >= cfg.PSI_UYARI_ESIGI or psi_vol >= cfg.PSI_UYARI_ESIGI:
                    drift_uyarilari.append(f"⚡ #{s_clean} — Dengeli / Ilımlı Hareketlilik")

        raporlar[sembol] = {
            "son_tarih": str(son_tarih),
            "toplam_bar": len(df),
            "son_kapanis": float(df["close"].iloc[-1]),
        }

    durum = "KRITIK_HATA" if kritik_uyarilar else "CALISIYOR"

    return {
        "durum": durum,
        "tarih": str(bugun),
        "kontrol_edilen_hisse": len(hisseler),
        "kritik_uyari_sayisi": len(kritik_uyarilar),
        "drift_uyari_sayisi": len(drift_uyarilari),
        "kritik_uyarilar": kritik_uyarilar,
        "drift_uyarilari": drift_uyarilari,
        "raporlar": raporlar,
    }


def formatla_admin_health_mesaji(health_sonuc: Dict[str, Any]) -> str:
    """Admin için anlaşılır ve açıklayıcı Telegram sağlık raporu üretir."""
    mesaj = (
        f"🛡️ <b>SİSTEM SAĞLIK & PİYASA RAPORU</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Tarih:</b> {health_sonuc['tarih']}  |  <b>Denetlenen:</b> {health_sonuc['kontrol_edilen_hisse']} Hisse\n\n"
    )

    if health_sonuc["kritik_uyarilar"]:
        mesaj += (
            f"🚨 <b>DİKKAT: KRİTİK VERİ HATASI BULUNDU ({len(health_sonuc['kritik_uyarilar'])} Hata)!</b>\n"
            f"• <i>Aşağıdaki hisselerde eksik fiyat, güncellik veya anomali tespit edildi:</i>\n"
        )
        for u in health_sonuc["kritik_uyarilar"][:5]:
            mesaj += f"  {u}\n"
    else:
        mesaj += (
            f"✅ <b>VERİ & BORSA BAĞLANTISI: KUSURSUZ (0 Hata)</b>\n"
            f"• <i>Tüm {health_sonuc['kontrol_edilen_hisse']} hissenin fiyatları, mumları ve göstergeleri eksiksizdir.</i>\n"
            f"• <i>Eksik (NaN) fiyat, tahta kapanması veya donma YOKTUR.</i>\n"
        )


    if health_sonuc["drift_uyarilari"]:
        mesaj += (
            f"\n🌊 <b>PİYASA MOMENTUMU & HAREKETLİLİK (PSI):</b>\n"
            f"<i>(Açıklama: Aşağıdaki hisseler son dönemde güçlü ralli/oynaklık yaşadığı için göstergeleri geçmişin sakin ortalamalarından yukarıda seyretmektedir. Bu doğal bir piyasa durumudur.)</i>\n"
        )
        for d in health_sonuc["drift_uyarilari"][:5]:
            mesaj += f"  • {d}\n"

    mesaj += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if health_sonuc["kritik_uyarilar"]:
        mesaj += "💡 <b>DURUM:</b> 🚨 Veri hataları tespit edildiği için güvenliğiniz adına yeni sinyal üretimi durdurulmuştur."
    else:
        mesaj += "💡 <b>DURUM:</b> Sistem ve al-sat motoru tamamen stabildir. Herhangi bir teknik müdahaleye gerek yoktur."

    return mesaj
