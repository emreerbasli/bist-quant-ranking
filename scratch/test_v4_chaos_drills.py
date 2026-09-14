"""
scratch/test_v4_chaos_drills.py
===============================
BIST V4 QUANT: ACİL DURUM VE KAZA TATBİKATI (CHAOS DRILLS)
----------------------------------------------------------
Amaç:
  Canlı diskteki models/v4_ranking/paper_portfolio_v4.json dosyasına KESİNLİKLE dokunmadan,
  tamamen izole geçici bir mock nesne üzerinde iki kritik emniyet supabını doğrulamak:

  Tatbikat 1: Zirveden Kâr Geri Verme Kalkanı
              Hisse yerel zirvesinden %22 geri çekildiğinde, 60 günlük asgari tutma süresi
              delinerek acil kâr koruma çıkışı yapılıyor mu? (ASSERT PASS)

  Tatbikat 2: %25 Portföy Devre Kesicisi
              Portföy sermayesi 1.0'dan 0.74'e indiğinde (%26 drawdown <= -%25),
              dd_kesici_aktif = True olup portföy %100 nakde geçiriliyor mu? (ASSERT PASS)

  Doğrulama:  Canlı paper_portfolio_v4.json dosyasının zaman damgası ve sha256 özeti
              test sonrasında %100 aynı kalmalıdır.
"""

import sys
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config as cfg
from models.v4_ranking.paper_trader_v4 import PaperTraderV4

# Renkler
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def dosya_sha256(fpath: Path) -> str:
    """Dosyanın SHA256 özetini hesaplar."""
    h = hashlib.sha256()
    with open(fpath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def run_chaos_drills():
    print(f"\n{BOLD}{CYAN}{'=' * 80}{RESET}")
    print(f"{BOLD}{CYAN}🔥 BIST V4 ACİL DURUM VE KAZA TATBİKATI (CHAOS DRILLS){RESET}")
    print(f"{BOLD}{CYAN}{'=' * 80}{RESET}")

    # 1. CANLI DOSYA BÜTÜNLÜK BAŞLANGIÇ KAYDI
    live_portfolio_file = ROOT_DIR / "models" / "v4_ranking" / "paper_portfolio_v4.json"
    assert live_portfolio_file.exists(), f"HATA: Canlı portföy dosyası bulunamadı: {live_portfolio_file}"

    stat_before = live_portfolio_file.stat()
    mtime_before = stat_before.st_mtime
    hash_before = dosya_sha256(live_portfolio_file)

    print(f"\n📌 Canlı Portföy Dosyası İncelemesi:")
    print(f"   • Dosya: {live_portfolio_file}")
    print(f"   • Başlangıç Değiştirilme Zamanı: {datetime.fromtimestamp(mtime_before).isoformat()}")
    print(f"   • Başlangıç SHA256 Özeti: {hash_before[:16]}...{hash_before[-8:]}")

    temp_chaos_portfolio = ROOT_DIR / "scratch" / "temp_chaos_portfolio.json"
    temp_chaos_log = ROOT_DIR / "scratch" / "temp_chaos_log.csv"

    # Temizlik
    if temp_chaos_portfolio.exists():
        temp_chaos_portfolio.unlink()
    if temp_chaos_log.exists():
        temp_chaos_log.unlink()

    # -------------------------------------------------------------------------
    # TATBİKAT 1: ZİRVEDEN KÂR GERİ VERME KALKANI (%22 ÇEKİLME)
    # -------------------------------------------------------------------------
    print(f"\n{BOLD}--- TATBİKAT 1: Zirveden Kâr Geri Verme Kalkanı (Peak Drawdown %22) ---{RESET}")
    
    # İzole geçici portföy oluştur
    trader_drill1 = PaperTraderV4(
        portfolio_file=temp_chaos_portfolio,
        log_file=temp_chaos_log,
        k_size=15,
        min_hold_days=60
    )

    # Mock pozisyon: TEST_PEAK.IS henüz 14 gündür tutuluyor (60 gün dolmadı!),
    # Zirvesi 120.0 TL, güncel fiyat 93.6 TL (-%22.0 zirveden çekilme).
    mock_positions = {
        "TEST_PEAK.IS": {
            "entry_date": "2026-09-01",
            "entry_price": 100.0,
            "prev_check_price": 115.0,
            "personal_peak_price": 120.0,
            "last_price": 120.0,
            "days_held": 14,  # 60 gün kuralı normalde SATIŞA İZİN VERMEZ!
            "peak_drawdown_pct": 0.0,
            "weight": 0.0667
        },
        "NORMAL_HISSE.IS": {
            "entry_date": "2026-09-01",
            "entry_price": 50.0,
            "prev_check_price": 50.0,
            "personal_peak_price": 50.0,
            "last_price": 50.0,
            "days_held": 14,
            "peak_drawdown_pct": 0.0,
            "weight": 0.0667
        }
    }

    trader_drill1.portfolio_state["positions"] = mock_positions
    trader_drill1.portfolio_state["equity"] = 1.0
    trader_drill1.portfolio_state["peak_equity"] = 1.0
    trader_drill1._save_portfolio()

    t_drill1 = pd.Timestamp("2026-09-15")
    # Güncel fiyatlar: TEST_PEAK 93.6 TL (120'den %22 düşüş)
    current_prices_d1 = {
        "TEST_PEAK.IS": 93.60,
        "NORMAL_HISSE.IS": 50.00
    }
    # Model hala TEST_PEAK.IS'i ilk 15'te tutuyor olsa dahi kâr koruma çıkışı tetiklenmeli!
    top_k_with_peak = ["TEST_PEAK.IS", "NORMAL_HISSE.IS"]

    res_d1 = trader_drill1.execute_check(
        t=t_drill1,
        top_k_ranked=top_k_with_peak,
        current_prices=current_prices_d1,
        current_xu100_price=10000.0,
        seri_usdtry=pd.Series([34.0], index=[t_drill1]),
        tufe_aylik={},
        days_elapsed=14,
        send_telegram=False
    )

    pos_after_d1 = trader_drill1.portfolio_state["positions"]
    
    print(f"   • Giriş Fiyatı: 100.0 TL | Zirve: 120.0 TL | Güncel Fiyat: 93.60 TL")
    print(f"   • Zirveden Çekilme Oranı: %-22.0 (Eşik: %-20.0)")
    print(f"   • Elde Tutulan Gün Sayısı: 28 gün (< 60 gün kilit süresi)")
    print(f"   • TEST_PEAK.IS Portföyde Kaldı mı?: {'HAYIR (ÇIKARILDI)' if 'TEST_PEAK.IS' not in pos_after_d1 else 'EVET (HATA!)'}")
    print(f"   • Kalan Pozisyonlar: {list(pos_after_d1.keys())}")

    # DOĞRULAMA 1
    assert "TEST_PEAK.IS" not in pos_after_d1, "HATA: TEST_PEAK.IS zirveden %22 düşmesine rağmen 60 gün kuralını delip çıkış yapamadı!"
    assert "NORMAL_HISSE.IS" in pos_after_d1, "HATA: Normal hisse gereksiz yere tasfiye edildi!"
    print(f"{BOLD}{GREEN}✅ TATBİKAT 1 BAŞARILI (ASSERT PASS): Zirveden %22 düşen hisse 60 gün kuralını delerek derhal tasfiye edildi.{RESET}")

    # -------------------------------------------------------------------------
    # TATBİKAT 2: %25 PORTFÖY DEVRE KESİCİSİ (%100 NAKDE GEÇİŞ)
    # -------------------------------------------------------------------------
    print(f"\n{BOLD}--- TATBİKAT 2: %25 Portföy Devre Kesicisi (Sermaye: 1.0 -> 0.74) ---{RESET}")

    trader_drill2 = PaperTraderV4(
        portfolio_file=temp_chaos_portfolio,
        log_file=temp_chaos_log,
        k_size=15,
        min_hold_days=60
    )

    # 5 Hisse ile dolu portföy hazırla
    mock_positions_d2 = {
        f"STOCK_{i}.IS": {
            "entry_date": "2026-09-01",
            "entry_price": 100.0,
            "prev_check_price": 100.0,
            "personal_peak_price": 100.0,
            "last_price": 100.0,
            "days_held": 10,
            "peak_drawdown_pct": 0.0,
            "weight": 0.20
        } for i in range(1, 6)
    }

    # Sermaye 1.0'dan başlamış, şu an tepe 1.0 iken mevcut sermaye 0.74 (Drawdown: -%26.0)
    # Eşik: self.dd_trigger = -0.25 (-%25)
    trader_drill2.portfolio_state["positions"] = mock_positions_d2
    trader_drill2.portfolio_state["equity"] = 0.74
    trader_drill2.portfolio_state["peak_equity"] = 1.0
    trader_drill2.portfolio_state["drawdown"] = -0.26
    trader_drill2.portfolio_state["dd_kesici_aktif"] = False
    trader_drill2._save_portfolio()

    t_drill2 = pd.Timestamp("2026-09-15")
    current_prices_d2 = {f"STOCK_{i}.IS": 100.0 for i in range(1, 6)}
    top_k_candidates = [f"NEW_STOCK_{i}.IS" for i in range(1, 16)]

    res_d2 = trader_drill2.execute_check(
        t=t_drill2,
        top_k_ranked=top_k_candidates,
        current_prices=current_prices_d2,
        current_xu100_price=10000.0,
        seri_usdtry=pd.Series([34.0], index=[t_drill2]),
        tufe_aylik={},
        days_elapsed=14,
        send_telegram=False
    )

    state_after_d2 = trader_drill2.portfolio_state
    dd_aktif = state_after_d2.get("dd_kesici_aktif", False)
    pos_count_d2 = len(state_after_d2.get("positions", {}))

    print(f"   • Başlangıç Tepe Sermaye: 1.0000 | Mevcut Sermaye: {state_after_d2['equity']:.4f}")
    print(f"   • Gerçekleşen Drawdown: %{state_after_d2['drawdown']*100:.1f} (Eşik: %-25.0)")
    print(f"   • Devre Kesici Durumu: {'AKTİF (True)' if dd_aktif else 'PASİF (False)'}")
    print(f"   • Portföydeki Hisse Sayısı: {pos_count_d2} (Hedef: 0 Hisse / %100 Nakit)")

    # DOĞRULAMA 2
    assert dd_aktif is True, "HATA: Sermaye -%26 düşmesine rağmen dd_kesici_aktif True olmadı!"
    assert pos_count_d2 == 0, f"HATA: Devre kesici aktifken portföy %100 nakde geçmedi! (Kalan hisseler: {pos_count_d2})"
    print(f"{BOLD}{GREEN}✅ TATBİKAT 2 BAŞARILI (ASSERT PASS): Devre kesici tetiklendi, portföy %100 nakde geçti.{RESET}")

    # Geçici dosyaları temizle
    if temp_chaos_portfolio.exists():
        temp_chaos_portfolio.unlink()
    if temp_chaos_log.exists():
        temp_chaos_log.unlink()

    # -------------------------------------------------------------------------
    # TATBİKAT SONU: CANLI DOSYA DEĞİŞMEZLİK DENETİMİ (TIMESTAMP & HASH)
    # -------------------------------------------------------------------------
    print(f"\n{BOLD}--- CANLI DOSYA KORUMA & DEĞİŞMEZLİK KANITI ---{RESET}")
    stat_after = live_portfolio_file.stat()
    mtime_after = stat_after.st_mtime
    hash_after = dosya_sha256(live_portfolio_file)

    print(f"   • Canlı Dosya Yolu: {live_portfolio_file}")
    print(f"   • Önceki Timestamp: {mtime_before}")
    print(f"   • Sonraki Timestamp: {mtime_after}")
    print(f"   • Önceki SHA256:    {hash_before}")
    print(f"   • Sonraki SHA256:   {hash_after}")

    assert mtime_before == mtime_after, "HATA: Canlı paper_portfolio_v4.json dosyasının zaman damgası DEĞİŞTİ!"
    assert hash_before == hash_after, "HATA: Canlı paper_portfolio_v4.json dosyasının içeriği DEĞİŞTİ!"

    print(f"\n{BOLD}{GREEN}{'=' * 80}{RESET}")
    print(f"{BOLD}{GREEN}🎉 TÜM ACİL DURUM VE KAZA TATBİKATLARI BAŞARIYLA TAMAMLANDI.{RESET}")
    print(f"{BOLD}{GREEN}   CANLI PORTFÖYÜN BİR BYTE'INA DAHİ DOKUNULMADIĞI KANITLANMIŞTIR.{RESET}")
    print(f"{BOLD}{GREEN}{'=' * 80}{RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_chaos_drills())
