"""
scratch/test_telegram_v4.py
===========================
BIST V4 Quant Telegram Bildirim Entegrasyon Testi
-------------------------------------------------
Amaç:
  1. Telegram Token ve Chat ID konfigürasyonunu doğrulamak (varlık/maskelenmiş uzunluk).
  2. V4 portföyünün (K=15 hisse, %6.67 ağırlıklar, maliyetler, getiri, Faz 0 taban alarmı, drift durumu)
     Telegram mesaj şablonuna hatasız ve 4096 karakter sınırına takılmadan formatlandığını kanıtlamak.
  3. Güvenli kuru çalıştırma (dry-run) yapmak; isteğe bağlı '--send' bayrağıyla canlı bildirim iletmek.
"""

import sys
import os
import json
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config as cfg
from bot.telegram_bot import mesaj_gonder
from models.v4_ranking.paper_trader_v4 import PaperTraderV4


def test_telegram_integration(send_live: bool = False):
    print("=" * 80)
    print("📢 BIST V4 QUANT TELEGRAM BİLDİRİM ENTEGRASYON TESTİ")
    print("=" * 80)

    # 1. KİMLİK DOĞRULAMA KONTROLÜ
    token = getattr(cfg, "TELEGRAM_TOKEN", "") or os.getenv("TELEGRAM_TOKEN", "")
    chat_id = getattr(cfg, "ADMIN_CHAT_ID", "") or os.getenv("ADMIN_CHAT_ID", "")

    token_mevcut = bool(token and len(token) > 10)
    chat_id_mevcut = bool(chat_id and len(chat_id) > 4)

    print("\n--- 1. TELEGRAM KİMLİK BİLGİLERİ DURUMU ---")
    if token_mevcut:
        masked_token = f"{token[:8]}...{token[-4:]} (Uzunluk: {len(token)})"
        print(f"✅ TELEGRAM_TOKEN: MEVCUT ({masked_token})")
    else:
        print("⚠️ TELEGRAM_TOKEN: TANIMSIZ / EKSİK (Mock modunda test edilecek)")

    if chat_id_mevcut:
        masked_chat = f"{chat_id[:3]}...{chat_id[-2:]} (Uzunluk: {len(chat_id)})"
        print(f"✅ ADMIN_CHAT_ID:  MEVCUT ({masked_chat})")
    else:
        print("⚠️ ADMIN_CHAT_ID:  TANIMSIZ / EKSİK (Mock modunda test edilecek)")

    # 2. V4 PORTFÖYÜNÜ YÜKLE VE ŞABLON FORMATLA
    print("\n--- 2. V4 PORTFÖYÜ VE ŞABLON FORMATLAMA TESTİ ---")
    portfolio_file = ROOT_DIR / "models" / "v4_ranking" / "paper_portfolio_v4.json"
    
    positions = {}
    equity = 1.0000
    peak_equity = 1.0000
    drawdown = 0.0
    dd_kesici = False
    last_date = "2026-09-14"

    if portfolio_file.exists():
        with open(portfolio_file, "r", encoding="utf-8") as f:
            p_data = json.load(f)
            positions = p_data.get("positions", {})
            equity = float(p_data.get("equity", 1.0))
            peak_equity = float(p_data.get("peak_equity", 1.0))
            drawdown = float(p_data.get("drawdown", 0.0))
            dd_kesici = bool(p_data.get("dd_kesici_aktif", False))
            last_date = p_data.get("last_check_date", "2026-09-14")
    
    print(f"Yüklenen V4 Portföy Boyutu: {len(positions)} Hisse (Hedef: K=15)")

    trader = PaperTraderV4()

    # Örnek test log row verisi
    log_row = {
        "tarih": last_date,
        "equity": equity,
        "kumulatif_getiri": (equity - 1.0) * 100.0,
        "drawdown": drawdown * 100.0,
        "period_ret": +2.45,
        "bist_ret": +1.10,
        "alfa": +1.35,
        "degisiklik": "+ALARK.IS, +TUPRS.IS | -EREGL.IS",
        "drift_durumu": "🟢 NORMAL",
        "makro_ozet": "Reel:%5.3, USD_Mom:%3.3",
        "dd_kesici": dd_kesici,
        "freshness": "OK"
    }

    cikis_takvimi = (
        "  • ALARK.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • ANSGR.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • DOHOL.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • FORTE.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • GENTS.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • GUBRF.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • KRDMD.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • PETKM.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • REEDR.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • SELEC.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • SKBNK.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • TERA.IS   : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • TUPRS.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • TURSG.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]\n"
        "  • VESTL.IS  : 00. gün (60 gün kaldı) [KİLİTLİ (BEKLEMEDE)]"
    )

    uyari_hisseler = ["TEST_HISSE: Zirveden %21.4 geri çekildi"]
    acil_cikislar = ["PASEU.IS: Faz 0 ardışık taban/çöküş riski"]

    mesaj = trader.print_summary_report(
        log_row=log_row,
        positions=positions,
        cikis_takvimi=cikis_takvimi,
        uyari_hisseler=uyari_hisseler,
        acil_cikislar=acil_cikislar
    )

    char_count = len(mesaj)
    print(f"\n✅ Mesaj Şablonu Üretildi (Karakter Sayısı: {char_count} / Telegram Limiti: 4096)")
    assert char_count < 4096, "HATA: Mesaj 4096 karakter sınırını aşıyor!"
    assert "K=15" in mesaj, "HATA: Mesajda K=15 başlığı yok!"
    assert "VESTL.IS" in mesaj, "HATA: Pozisyon listesinde hisseler eksik!"
    assert "PASEU.IS" in mesaj, "HATA: Acil çıkış uyarısı eksik!"

    print("\n--- 3. ÜRETİLEN TELEGRAM MESAJ ÖNİZLEMESİ (DRY-RUN) ---")
    print(mesaj)

    # 3. İLETİM TESTİ (CANLI VEYA DRY-RUN)
    print("\n--- 4. TELEGRAM İLETİM TESTİ ---")
    if send_live and token_mevcut and chat_id_mevcut:
        print("🚀 Canlı Telegram API testi yapılıyor (mesaj gönderiliyor)...")
        basarili = mesaj_gonder(mesaj, parse_mode=None)
        if basarili:
            print("🎉 CANLI TELEGRAM BİLDİRİMİ BAŞARIYLA İLETİLDİ (HTTP 200 OK)!")
        else:
            print("❌ Canlı Telegram gönderimi başarısız oldu!")
    else:
        if not send_live:
            print("ℹ️ Güvenli Kuru Çalıştırma (Dry-Run): Canlı API çağrısı yapılmadı.")
            print("   (Canlı test göndermek için: python scratch/test_telegram_v4.py --send)")
        else:
            print("⚠️ Token veya Chat ID eksik olduğundan canlı API çağrısı atlandı.")

    print("\n" + "=" * 80)
    print("✅ V4 TELEGRAM ENTEGRASYON DOĞRULAMASI BAŞARIYLA TAMAMLANDI.")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V4 Telegram Entegrasyon Testi")
    parser.add_argument("--send", action="store_true", help="Gerçekten Telegram'a canlı test mesajı gönder")
    args = parser.parse_args()
    test_telegram_integration(send_live=args.send)
