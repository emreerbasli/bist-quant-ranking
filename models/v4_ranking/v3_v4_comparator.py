"""
models/v4_ranking/v3_v4_comparator.py
======================================
ÇİFT MODEL CANLI PAPER TRADING KARŞILAŞTIRMA MODÜLÜ (V3 vs V4)
--------------------------------------------------------------
V3 (8-Faktör, K=10) ile V4 (9-Faktör, K=15) paper trading durumlarını
ve işlem kayıtlarını yan yana okuyarak kurumsal karşılaştırma raporu üretir.
Rapor: reports/v3_vs_v4_comparison.json
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logger = logging.getLogger("V3V4Comparator")

V3_PORTFOLIO_FILE = ROOT_DIR / "models" / "v3_ranking" / "paper_portfolio.json"
V4_PORTFOLIO_FILE = ROOT_DIR / "models" / "v4_ranking" / "paper_portfolio_v4.json"
V3_LOG_FILE = ROOT_DIR / "models" / "v3_ranking" / "paper_trading_log.csv"
V4_LOG_FILE = ROOT_DIR / "models" / "v4_ranking" / "paper_trading_log_v4.csv"
COMPARISON_JSON_FILE = ROOT_DIR / "reports" / "v3_vs_v4_comparison.json"


def generate_v3_vs_v4_comparison(tarih: str = None) -> Dict[str, Any]:
    """
    V3 ve V4 canlı paper trading durumlarını karşılaştırır ve JSON raporu döner.
    """
    t_str = tarih or datetime.now().strftime("%Y-%m-%d")

    v3_data = {}
    if V3_PORTFOLIO_FILE.exists():
        try:
            with open(V3_PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                v3_data = json.load(f)
        except Exception as e:
            logger.warning(f"V3 portföy okuma hatası: {e}")

    v4_data = {}
    if V4_PORTFOLIO_FILE.exists():
        try:
            with open(V4_PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                v4_data = json.load(f)
        except Exception as e:
            logger.warning(f"V4 portföy okuma hatası: {e}")

    v3_positions = set(v3_data.get("positions", {}).keys())
    v4_positions = set(v4_data.get("positions", {}).keys())

    ortak_hisseler = sorted(list(v3_positions.intersection(v4_positions)))
    v3_ozel = sorted(list(v3_positions - v4_positions))
    v4_ozel = sorted(list(v4_positions - v3_positions))

    v3_eq = float(v3_data.get("equity", 1.0))
    v4_eq = float(v4_data.get("equity", 1.0))

    v3_dd = float(v3_data.get("drawdown", 0.0))
    v4_dd = float(v4_data.get("drawdown", 0.0))

    # Log dosyalarından son durumlar
    v3_log_len = 0
    if V3_LOG_FILE.exists():
        try:
            df_v3_log = pd.read_csv(V3_LOG_FILE)
            v3_log_len = len(df_v3_log)
        except Exception:
            pass

    v4_log_len = 0
    if V4_LOG_FILE.exists():
        try:
            df_v4_log = pd.read_csv(V4_LOG_FILE)
            v4_log_len = len(df_v4_log)
        except Exception:
            pass

    # V4 Model bilgilerini dinamik yükle
    v4_model_name = "V4.1 LGBMRanker (9 Feature: z_reel_eps)"
    v4_feats = []
    v4_joblib = ROOT_DIR / "models" / "v4_ranking" / "winning_lgbm_ranker_v4.joblib"
    if v4_joblib.exists():
        try:
            import joblib
            m_data = joblib.load(v4_joblib)
            v4_model_name = m_data.get("model_name", v4_model_name)
            v4_feats = m_data.get("feature_cols", [])
        except Exception:
            pass

    comparison = {
        "tarih": t_str,
        "olusturulma_zamani": datetime.now().isoformat(),
        "v3": {
            "model": "V3.2 (Resmi Canlı Model / K=10)",
            "portfoy_boyutu": len(v3_positions),
            "k_hedef": 10,
            "sermaye": round(v3_eq, 6),
            "getiri_pct": round((v3_eq - 1.0) * 100.0, 2),
            "drawdown_pct": round(v3_dd * 100.0, 2),
            "dd_kesici_aktif": bool(v3_data.get("dd_kesici_aktif", False)),
            "hisseler": sorted(list(v3_positions)),
            "toplam_kontrol_sayisi": v3_log_len
        },
        "v4": {
            "model": v4_model_name,
            "ozellikler": v4_feats,
            "portfoy_boyutu": len(v4_positions),
            "k_hedef": 15,
            "sermaye": round(v4_eq, 6),
            "getiri_pct": round((v4_eq - 1.0) * 100.0, 2),
            "drawdown_pct": round(v4_dd * 100.0, 2),
            "dd_kesici_aktif": bool(v4_data.get("dd_kesici_aktif", False)),
            "hisseler": sorted(list(v4_positions)),
            "toplam_kontrol_sayisi": v4_log_len
        },
        "karsilastirma": {
            "sermaye_farki": round(v4_eq - v3_eq, 6),
            "getiri_farki_pct": round(((v4_eq - 1.0) - (v3_eq - 1.0)) * 100.0, 2),
            "drawdown_farki_pct": round((v4_dd - v3_dd) * 100.0, 2),
            "ortak_hisseler_sayisi": len(ortak_hisseler),
            "ortak_hisseler": ortak_hisseler,
            "yalnizca_v3_hisseler": v3_ozel,
            "yalnizca_v4_hisseler": v4_ozel
        }
    }

    COMPARISON_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_comp = COMPARISON_JSON_FILE.with_suffix(".tmp")
    with open(temp_comp, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    temp_comp.replace(COMPARISON_JSON_FILE)

    return comparison


def format_comparison_telegram(comp: Dict[str, Any]) -> str:
    """Telegram için kompakt ve okunabilir çift model karşılaştırma bülteni."""
    tarih = comp.get("tarih", datetime.now().strftime("%Y-%m-%d"))
    v3 = comp.get("v3", {})
    v4 = comp.get("v4", {})
    c = comp.get("karsilastirma", {})

    ortak = c.get("ortak_hisseler", [])
    ortak_str = ", ".join(ortak) if ortak else "Yok"
    v3_ozel = c.get("yalnizca_v3_hisseler", [])
    v4_ozel = c.get("yalnizca_v4_hisseler", [])

    msg = (
        f"⚖️ <b>BIST ÇİFT MOTOR (V3.2 vs V4.1) GÜNLÜK MUKAYESE</b> — [{tarih}]\n\n"
        f"📊 <b>Model Performans Kıyaslaması:</b>\n"
        f"• <b>V3.2 Üretim Kasası (8F / K=10):</b>\n"
        f"  ├ Sermaye: <code>{v3.get('sermaye', 1.0):.4f}</code> (%{v3.get('getiri_pct', 0.0):+.2f})\n"
        f"  ├ Drawdown: %{v3.get('drawdown_pct', 0.0):.2f}\n"
        f"  └ Devre Kesici: {'🚨 AKTİF' if v3.get('dd_kesici_aktif') else '🟢 Pasif'}\n\n"
        f"• <b>V4.1 Gölge Şampiyon (9F / K=15):</b>\n"
        f"  ├ Sermaye: <code>{v4.get('sermaye', 1.0):.4f}</code> (%{v4.get('getiri_pct', 0.0):+.2f})\n"
        f"  ├ Drawdown: %{v4.get('drawdown_pct', 0.0):.2f}\n"
        f"  └ Devre Kesici: {'🚨 AKTİF' if v4.get('dd_kesici_aktif') else '🟢 Pasif'}\n\n"
        f"📈 <b>Getiri Farkı (V4.1 - V3.2):</b> %{c.get('getiri_farki_pct', 0.0):+.2f}\n"
        f"🤝 <b>Ortak Hisseler ({len(ortak)}):</b> {ortak_str}\n"
        f"🔹 <b>Yalnızca V3.2 ({len(v3_ozel)}):</b> {', '.join(v3_ozel) if v3_ozel else 'Yok'}\n"
        f"🔸 <b>Yalnızca V4.1 ({len(v4_ozel)}):</b> {', '.join(v4_ozel) if v4_ozel else 'Yok'}\n\n"
        f"🛡️ <i>Not: V3.2 birincil canlı kasa, V4.1 ise gölge mod canlı referansıdır.</i>"
    )
    return msg


def send_comparison_telegram(comp: Dict[str, Any]) -> bool:
    """Çift model karşılaştırma raporunu Telegram üzerinden iletir."""
    try:
        from bot.telegram_bot import mesaj_gonder
        metin = format_comparison_telegram(comp)
        return mesaj_gonder(metin, parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ Karşılaştırma Telegram bildirimi gönderilemedi: {e}")
        return False


def print_comparison_card(comp: Dict[str, Any]):
    """Konsola kurumsal çift model karşılaştırma kartı yazdırır."""
    print("=" * 85)
    print(f"📊 ÇİFT MODEL CANLI PAPER TRADING KARŞILAŞTIRMA RAPORU — [{comp['tarih']}]")
    print("=" * 85)
    v3 = comp["v3"]
    v4 = comp["v4"]
    c = comp["karsilastirma"]

    print(f"{'Metrik':<28} | {'V3.2 Aktif (8F / K=10)':<28} | {'V4.1 Gölge (9F / K=15)':<28}")
    print("-" * 85)
    print(f"{'Mevcut Sermaye':<28} | {v3['sermaye']:<25.4f} | {v4['sermaye']:<25.4f}")
    print(f"{'Kümülatif Getiri':<28} | %{v3['getiri_pct']:<24.2f} | %{v4['getiri_pct']:<24.2f}")
    print(f"{'Tepe Drawdown':<28} | %{v3['drawdown_pct']:<24.2f} | %{v4['drawdown_pct']:<24.2f}")
    print(f"{'Devre Kesici Durumu':<28} | {'Aktif' if v3['dd_kesici_aktif'] else 'Pasif':<25} | {'Aktif' if v4['dd_kesici_aktif'] else 'Pasif':<25}")
    print(f"{'Açık Pozisyon Sayısı':<28} | {v3['portfoy_boyutu']:<25} | {v4['portfoy_boyutu']:<25}")
    print("-" * 85)
    print(f"Ortak Hisseler ({c['ortak_hisseler_sayisi']} adet): {', '.join(c['ortak_hisseler']) if c['ortak_hisseler'] else 'Yok'}")
    print(f"Yalnızca V3 Hisseleri ({len(c['yalnizca_v3_hisseler'])}): {', '.join(c['yalnizca_v3_hisseler'])}")
    print(f"Yalnızca V4 Hisseleri ({len(c['yalnizca_v4_hisseler'])}): {', '.join(c['yalnizca_v4_hisseler'])}")
    print("=" * 85)


if __name__ == "__main__":
    comp = generate_v3_vs_v4_comparison()
    print_comparison_card(comp)
