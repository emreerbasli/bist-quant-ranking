"""
main.py — BIST V3 KANTİTATİF SİSTEM MERKEZİ KONTROL KONSOLU
===========================================================
PRODUCTION-CANDIDATE: KOMUT VE KONTROL MERKEZİ (ADIM 5)
-------------------------------------------------------
KRİTİK KURUMSAL SINIR (İHLAL EDİLEMEZ):
Bu sistem SADECE bildirim, analiz ve karar destek çıktısı üretir — hiçbir şekilde
otomatik emir göndermez, aracı kuruma bağlanmaz veya canlı sermaye ile
al-sat kararı VERMEZ. Tüm işlemler sanal portföy (paper trading) takibidir.

Kullanım:
    python main.py                  -> İnteraktif Konsol Menüsü
    python main.py panel            -> Streamlit Web Yönetim Paneli
    python main.py kontrol          -> Anlık Paper Trading Kontrolü & Telegram
    python main.py oto              -> Zamanlanmış Otomasyon Servisi (Arka Plan)
    python main.py durum            -> Portföy ve Drift Durum Özeti
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
    """Streamlit V3 Web Yönetim Panelini başlatır."""
    print("\n" + "=" * 65)
    print("🌐 BIST V3 QUANT WEB YÖNETİM TERMİNALİ BAŞLATILIYOR...")
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
    """Tek seferlik paper trading kontrolünü icra eder ve Telegram'a bildirir."""
    print("\n" + "=" * 65)
    print("⚡ BIST V3: ANLIK PAPER TRADING KONTROLÜ BAŞLATILIYOR...")
    print("   (Model sıralaması üretilecek, portföy kontrol edilecek ve Telegram iletilecek)")
    print("=" * 65 + "\n")
    try:
        subprocess.run([str(VENV_PYTHON), "run_paper_trader.py", "--run-once"], cwd=str(BASE_DIR), check=True)
    except KeyboardInterrupt:
        print("\n🛑 İşlem kullanıcı tarafından durduruldu.")


def calistir_zamanlanmis_servis():
    """14 günlük periyodik otomasyon servisini başlatır."""
    print("\n" + "=" * 65)
    print("⏰ BIST V3: ZAMANLANMIŞ OTOMASYON SERVİSİ BAŞLATILIYOR...")
    print("   (Her iş günü 18:30 seans kapanış kontrolü, BIST tatil koruması, 14 gün döngüsü)")
    print("🛑 Servisi durdurmak için konsolda Ctrl+C tuşlayın.")
    print("=" * 65 + "\n")
    try:
        subprocess.run([str(VENV_PYTHON), "run_paper_trader.py"], cwd=str(BASE_DIR), check=True)
    except KeyboardInterrupt:
        print("\n🛑 Servis durduruldu.")


def goster_portfoy_durumu():
    """Konsolda güncel portföy ve drift durumunu basar."""
    print("\n" + "=" * 65)
    print("📊 BIST V3: CARİ PORTFÖY VE DRİFT DURUMU")
    print("=" * 65)
    p_file = BASE_DIR / "models" / "v3_ranking" / "paper_portfolio.json"
    if p_file.exists():
        with open(p_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"📅 Son Kontrol Tarihi : {data.get('last_check_date')}")
        print(f"💰 Cari Sermaye İndeksi: {data.get('equity'):.4f} (₺{data.get('equity', 1.0)*100000:,.0f})")
        print(f"🏔️ Zirve Sermaye       : {data.get('peak_equity'):.4f}")
        print(f"📉 Zirveden Drawdown   : %{data.get('drawdown', 0.0)*100:.2f}")
        print(f"🛡️ Devre Kesici        : {'🚨 %50 NAKİT AKTİF' if data.get('dd_kesici_aktif') else '🟢 NORMAL (%100 HİSSE)'}")
        print("\n💼 AKTİF 10 HİSSE LİSTESİ:")
        for s, info in data.get("positions", {}).items():
            entry_p = info.get("entry_price", 0)
            last_p = info.get("last_price", entry_p)
            pnl = ((last_p - entry_p) / entry_p * 100) if entry_p > 0 else 0
            print(f"  • {s:<10} | Alış: ₺{entry_p:<7.2f} | Son: ₺{last_p:<7.2f} | Kâr: %{pnl:<+6.2f} | Tutulan: {info.get('days_held')} gün | Ağırlık: %{info.get('weight', 0.1)*100:.0f}")
    else:
        print("⚠️ Henüz oluşturulmuş bir portföy bulunamadı.")
    print("=" * 65 + "\n")


def menu_goster():
    """İnteraktif Terminal Menüsü."""
    while True:
        print("\n" + "═" * 65)
        print("  🏛️  BIST V3 KANTİTATİF SİSTEM — MERKEZİ KONTROL PANELİ")
        print("═" * 65)
        print("  [1] 🌐 Web Yönetim Terminali    (Streamlit Modern Dashboard)")
        print("  [2] ⚡ Anlık Kontrol Çalıştır   (Model Sırala + Telegram İlet)")
        print("  [3] ⏰ Otomasyon Servisi Başlat (14 Günlük Planlı Servis)")
        print("  [4] 📊 Cari Portföy Durumunu Gör(Konsol Özeti)")
        print("  [0] ❌ Çıkış")
        print("─" * 65)
        
        try:
            secim = input("👉 Seçiminiz [0-4]: ").strip()
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
        elif secim in ("0", "q", "exit", "cikis"):
            print("\n👋 Sistemden çıkıldı. Disiplinli ve karlı yatırımlar!")
            break
        else:
            print("⚠️ Geçersiz seçim! Lütfen 0 ile 4 arasında bir seçim yapın.")


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().strip("-")
        if arg in ("panel", "web", "app", "dashboard", "1"):
            calistir_web_panel()
        elif arg in ("kontrol", "tarama", "run", "now", "scan", "2"):
            calistir_anlik_kontrol()
        elif arg in ("oto", "servis", "service", "schedule", "bot", "3"):
            calistir_zamanlanmis_servis()
        elif arg in ("durum", "status", "portfoy", "portfolio", "4"):
            goster_portfoy_durumu()
        elif arg in ("yardim", "help", "h"):
            print(__doc__)
        else:
            print(f"⚠️ Bilinmeyen komut: {sys.argv[1]}")
            print("Kullanılabilir komutlar: panel, kontrol, oto, durum")
    else:
        menu_goster()


if __name__ == "__main__":
    main()
