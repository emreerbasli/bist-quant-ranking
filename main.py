"""
main.py — BIST V4 QUANT KANTİTATİF SİSTEM MERKEZİ KONTROL KONSOLU
================================================================
PRODUCTION: KOMUT VE KONTROL MERKEZİ (9-FAKTÖR / K=15 CANLI ÜRETİM)
-------------------------------------------------------------------
KRİTİK KURUMSAL SINIR (İHLAL EDİLEMEZ):
Bu sistem SADECE bildirim, analiz ve karar destek çıktısı üretir — hiçbir şekilde
otomatik emir göndermez, aracı kuruma bağlanmaz veya canlı sermaye ile
al-sat kararı VERMEZ. Tüm işlemler sanal portföy (paper trading) takibidir.

Kullanım:
    python main.py                  -> İnteraktif Konsol Menüsü
    python main.py panel            -> Streamlit Web Yönetim Paneli (app.py)
    python main.py kontrol          -> Anlık V4 Paper Trading Kontrolü & Telegram
    python main.py oto              -> V4 Zamanlanmış Otomasyon Servisi (18:35)
    python main.py durum            -> V4 Portföy ve Drift Durum Özeti (K=15)
    python main.py v3               -> V3-Kontrol Eski Referans Servisi
    python main.py karsilastir      -> Çift Model Karşılaştırma Raporu
"""

import sys
import os
import json
import subprocess
from pathlib import Path

# UTF-8 ve Windows terminal encoding ayarları
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).parent.resolve()
VENV_PYTHON = BASE_DIR / "venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)

VENV_STREAMLIT = BASE_DIR / "venv" / "Scripts" / "streamlit.exe"
if not VENV_STREAMLIT.exists():
    VENV_STREAMLIT = "streamlit"


def calistir_web_panel():
    """Streamlit Web Yönetim Panelini başlatır."""
    print("\n" + "=" * 65)
    print("🌐 BIST V4 QUANT WEB YÖNETİM TERMİNALİ BAŞLATILIYOR...")
    print(f"📁 Dizin: {BASE_DIR}")
    print("🚀 Tarayıcınızda otomatik açılacaktır (http://localhost:8501)...")
    print("💡 Paneli durdurmak için konsolda Ctrl+C tuşlarına basın.")
    print("=" * 65 + "\n")
    try:
        subprocess.run(
            [str(VENV_STREAMLIT), "run", "app.py", "--server.headless=false"],
            cwd=str(BASE_DIR),
            check=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Web paneli kapatıldı.")


def calistir_anlik_kontrol():
    """V4 tek seferlik paper trading kontrolünü icra eder ve Telegram'a bildirir."""
    print("\n" + "=" * 65)
    print("⚡ BIST V4: ANLIK PAPER TRADING KONTROLÜ BAŞLATILIYOR...")
    print("   (V4 9-Faktörlü Model Sıralaması, K=15 Portföy Denetimi ve Telegram Bildirimi)")
    print("=" * 65 + "\n")
    try:
        subprocess.run([str(VENV_PYTHON), "run_paper_trader_v4.py", "--now"], cwd=str(BASE_DIR), check=True)
    except KeyboardInterrupt:
        print("\n🛑 İşlem kullanıcı tarafından durduruldu.")


def calistir_zamanlanmis_servis():
    """V4 14 günlük periyodik otomasyon servisini başlatır (18:35 / 13:35)."""
    print("\n" + "=" * 65)
    print("⏰ BIST V4: ZAMANLANMIŞ OTOMASYON SERVİSİ BAŞLATILIYOR...")
    print("   (Her iş günü 18:35 seans kapanış kontrolü, BIST tatil koruması, 14 gün döngüsü)")
    print("🛑 Servisi durdurmak için konsolda Ctrl+C tuşlayın.")
    print("=" * 65 + "\n")
    try:
        subprocess.run([str(VENV_PYTHON), "run_paper_trader_v4.py"], cwd=str(BASE_DIR), check=True)
    except KeyboardInterrupt:
        print("\n🛑 Servis durduruldu.")


def goster_portfoy_durumu():
    """Konsolda güncel V4 portföy ve drift durumunu basar."""
    print("\n" + "=" * 65)
    print("📊 BIST V4: CARİ PORTFÖY VE DRİFT DURUMU (K=15)")
    print("=" * 65)
    p_file = BASE_DIR / "models" / "v4_ranking" / "paper_portfolio_v4.json"
    if p_file.exists():
        with open(p_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        eq = data.get('equity', 1.0)
        print(f"📅 Başlangıç Tarihi  : {data.get('baslangic_tarihi')}")
        print(f"📅 Son Kontrol Tarihi : {data.get('last_check_date')}")
        print(f"💰 Cari Sermaye İndeksi: {eq:.4f} (₺{eq*100000:,.0f})")
        print(f"🏔️ Zirve Sermaye       : {data.get('peak_equity', 1.0):.4f}")
        print(f"📉 Zirveden Drawdown   : %{data.get('drawdown', 0.0)*100:.2f}")
        print(f"🛡️ Devre Kesici        : {'🚨 %50 NAKİT AKTİF' if data.get('dd_kesici_aktif') else '🟢 NORMAL (%100 HİSSE)'}")
        print(f"\n💼 AKTİF V4 PORTFÖY LİSTESİ ({len(data.get('positions', {}))} Hisse):")
        for s, info in sorted(data.get("positions", {}).items()):
            entry_p = info.get("entry_price", 0)
            last_p = info.get("last_price", entry_p)
            pnl = ((last_p - entry_p) / entry_p * 100) if entry_p > 0 else 0
            w = info.get('weight', 1.0/15.0) * 100.0
            held = info.get('days_held', 0)
            print(f"  • {s:<10} | Alış: ₺{entry_p:<7.2f} | Son: ₺{last_p:<7.2f} | Kâr: %{pnl:<+6.2f} | Tutulan: {held:02d}/60 gün | Ağr: %{w:.1f}")
    else:
        print("⚠️ Henüz oluşturulmuş bir V4 portföyü bulunamadı.")
    print("=" * 65 + "\n")


def calistir_v3_kontrol():
    """Eski V3-Kontrol tek seferlik kontrolünü icra eder."""
    print("\n" + "=" * 65)
    print("🏛️ BIST V3: KONTROL REFERANS MODELİ ÇALIŞTIRILIYOR...")
    print("   (8-Faktör / K=10 Eski Model Denetimi)")
    print("=" * 65 + "\n")
    try:
        subprocess.run([str(VENV_PYTHON), "run_paper_trader.py", "--run-once"], cwd=str(BASE_DIR), check=True)
    except KeyboardInterrupt:
        print("\n🛑 İşlem durduruldu.")


def calistir_cift_model_karsilastirma():
    """Çift model karşılaştırma raporunu yeniler ve ekrana basar."""
    print("\n" + "=" * 65)
    print("⚖️ BIST V3 vs V4: ÇİFT MODEL KARŞILAŞTIRMA RAPORU")
    print("=" * 65 + "\n")
    try:
        from models.v4_ranking.v3_v4_comparator import generate_v3_vs_v4_comparison
        generate_v3_vs_v4_comparison()
    except Exception as e:
        print(f"❌ Karşılaştırma hatası: {e}")


def menu_goster():
    """İnteraktif Terminal Menüsü."""
    while True:
        print("\n" + "═" * 65)
        print("  🏛️  BIST V4 QUANT SİSTEMİ — MERKEZİ KONTROL PANELİ")
        print("═" * 65)
        print("  [1] 🌐 Web Yönetim Terminali      (Streamlit Modern Dashboard)")
        print("  [2] ⚡ V4 Anlık Kontrol Çalıştır  (9F / K=15 Sırala + Telegram)")
        print("  [3] ⏰ V4 Otomasyon Servisi Başlat(18:35 Seans Kapanış Servisi)")
        print("  [4] 📊 V4 Cari Portföy Durumunu Gör(Konsol Özeti - 15 Hisse)")
        print("  [5] ⚖️  Çift Model Karşılaştırma   (V3 vs V4 Metrik Özeti)")
        print("  [6] 🏛️  V3-Kontrol Eski Servisi    (Referans 8F / K=10)")
        print("  [0] ❌ Çıkış")
        print("─" * 65)

        try:
            secim = input("👉 Seçiminiz [0-6]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Görüşmek üzere!")
            break

        if secim == "1":
            calistir_web_panel()
        elif secim == "2":
            calistir_anlik_kontrol()
        elif secim == "3":
            calistir_zamanlanmis_servis()
        elif secim == "4":
            goster_portfoy_durumu()
        elif secim == "5":
            calistir_cift_model_karsilastirma()
        elif secim == "6":
            calistir_v3_kontrol()
        elif secim in ("0", "q", "exit", "cikis"):
            print("\n👋 Sistemden çıkıldı. Disiplinli ve karlı yatırımlar!")
            break
        else:
            print("⚠️ Geçersiz seçim! Lütfen 0 ile 6 arasında bir seçim yapın.")


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().strip("-")
        if arg in ("panel", "web", "app", "dashboard", "1"):
            calistir_web_panel()
        elif arg in ("kontrol", "tarama", "run", "now", "scan", "v4", "2"):
            calistir_anlik_kontrol()
        elif arg in ("oto", "servis", "service", "schedule", "bot", "3"):
            calistir_zamanlanmis_servis()
        elif arg in ("durum", "status", "portfoy", "portfolio", "4"):
            goster_portfoy_durumu()
        elif arg in ("karsilastir", "compare", "5"):
            calistir_cift_model_karsilastirma()
        elif arg in ("v3", "kontrol_v3", "6"):
            calistir_v3_kontrol()
        elif arg in ("yardim", "help", "h"):
            print(__doc__)
        else:
            print(f"⚠️ Bilinmeyen komut: {sys.argv[1]}")
            print("Kullanılabilir komutlar: panel, kontrol, oto, durum, karsilastir, v3")
    else:
        menu_goster()


if __name__ == "__main__":
    main()
