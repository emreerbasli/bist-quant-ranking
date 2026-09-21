"""
main.py — BIST QUANT KANTİTATİF SİSTEM MERKEZİ KONTROL KONSOLU
================================================================
PRODUCTION: KOMUT VE KONTROL MERKEZİ (V3 ANA KASA + PHASE H SHADOW)
-------------------------------------------------------------------
KRİTİK KURUMSAL SINIR (İHLAL EDİLEMEZ):
Bu sistem SADECE bildirim, analiz ve karar destek çıktısı üretir — hiçbir şekilde
otomatik emir göndermez, aracı kuruma bağlanmaz veya canlı sermaye ile
al-sat kararı VERMEZ. Tüm işlemler sanal portföy (paper trading) takibidir.

Kullanım:
    python main.py                  -> İnteraktif Konsol Menüsü (Tüm İşlemler)
    python main.py panel            -> Streamlit Web Yönetim Paneli (app.py)
    python main.py kontrol          -> Anlık Hibrid Motor (V3+Phase H) Kontrolü
    python main.py guncelle         -> Günlük Piyasa Verileri ve VBTS Güncelleme
    python main.py dogrula          -> Veri Bütünlüğü ve Kalite Güvence Denetimi
    python main.py oto              -> Hibrid Motor Otomasyon Servisi (18:35)
    python main.py durum            -> V3 Ana Kasa Portföy Özeti
    python main.py shadow           -> Phase H Shadow Sistem (Primary/Secondary) Durumu
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


def calistir_web_panel():
    """Streamlit Web Yönetim Panelini başlatır."""
    print("\n" + "=" * 65)
    print("🌐 BIST V4 QUANT WEB YÖNETİM TERMİNALİ BAŞLATILIYOR...")
    print(f"📁 Dizin: {BASE_DIR}")
    print("🚀 Tarayıcınızda otomatik açılacaktır (http://localhost:8501)...")
    print("💡 Paneli durdurmak için konsolda Ctrl+C tuşlarına basın.")
    print("=" * 65 + "\n")
    try:
        # python -m streamlit yöntemi venv uyumluluğu açısından en sağlam yöntemdir
        cmd = [str(VENV_PYTHON), "-m", "streamlit", "run", "app.py", "--server.headless=false"]
        subprocess.run(cmd, cwd=str(BASE_DIR), check=True)
    except KeyboardInterrupt:
        print("\n🛑 Web paneli kapatıldı.")


def calistir_anlik_kontrol():
    """Hibrid motor (V3 + Phase H) anlık kontrolünü icra eder."""
    print("\n" + "=" * 65)
    print("🚀 BIST HİBRİT MOTOR: ANLIK KONTROL BAŞLATILIYOR...")
    print("   1. Motor: V3 Legacy Production Ana Kasa")
    print("   2. Motor: Phase H Shadow Modelleri (RC-LGBMR, RC-LAMBDAMART)")
    print("=" * 65 + "\n")
    try:
        subprocess.run([str(VENV_PYTHON), "run_paper_trader.py", "--all"], cwd=str(BASE_DIR), check=True)
    except KeyboardInterrupt:
        print("\n🛑 İşlem kullanıcı tarafından durduruldu.")


def calistir_veri_guncelle():
    """88 hisse, endeksler ve makro kurları günceller, VBTS tedbirlerini arşivler."""
    print("\n" + "=" * 65)
    print("🔄 BIST QUANT: GÜNLÜK PİYASA VERİLERİ VE VBTS GÜNCELLENİYOR...")
    print("   (88 Hisse + XU100/XUSIN/XBANK/USDTRY/VIX + KAP Tedbir Arşivi)")
    print("=" * 65 + "\n")
    try:
        subprocess.run(
            [str(VENV_PYTHON), "tasks/data_sync_service.py", "--now", "--force"],
            cwd=str(BASE_DIR),
            check=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Veri güncelleme işlemi durduruldu.")


def calistir_veri_dogrula():
    """Ham verilerin ve Point-in-Time mali tabloların bütünlüğünü denetler."""
    print("\n" + "=" * 65)
    print("🛡️ BIST QUANT: VERİ BÜTÜNLÜĞÜ VE KALİTE GÜVENCE DENETİMİ...")
    print("   (Tarih Hizalama, Split Anomalileri, Sıfır Hacim ve PIT Kontrolü)")
    print("=" * 65 + "\n")
    try:
        subprocess.run(
            [str(VENV_PYTHON), "scripts/verify_data_integrity.py"],
            cwd=str(BASE_DIR),
            check=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Doğrulama işlemi durduruldu.")


def calistir_zamanlanmis_servis():
    """Hibrid motor periyodik otomasyon servisini başlatır (18:35 / 13:35)."""
    print("\n" + "=" * 65)
    print("⏰ BIST HİBRİT MOTOR: ZAMANLANMIŞ OTOMASYON SERVİSİ BAŞLATILIYOR...")
    print("   • 18:35 Seans Kapanışı: V3 -> Phase H Readiness -> Phase H Processing")
    print("   • 13:35 Yarım Seans: Arife günlerinde erken kontrol")
    print("🛑 Servisi durdurmak için konsolda Ctrl+C tuşlayın.")
    print("=" * 65 + "\n")
    try:
        subprocess.run([str(VENV_PYTHON), "run_paper_trader.py"], cwd=str(BASE_DIR), check=True)
    except KeyboardInterrupt:
        print("\n🛑 Servis durduruldu.")


def goster_portfoy_durumu():
    """Konsolda güncel V3.2 aktif portföy durumunu basar."""
    print("\n" + "=" * 65)
    print("📊 BIST V3.2: BİRİNCİL ÜRETİM KASASI PORTFÖY DURUMU (K=10)")
    print("=" * 65)
    p_file = BASE_DIR / "models" / "v3_ranking" / "paper_portfolio.json"
    if p_file.exists():
        with open(p_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        eq = data.get('equity', 1.0)
        print(f"📅 Son Kontrol Tarihi : {data.get('last_check_date')}")
        print(f"💰 Cari Sermaye İndeksi: {eq:.4f} (₺{eq*100000:,.0f})")
        print(f"🏔️ Zirve Sermaye       : {data.get('peak_equity', 1.0):.4f}")
        print(f"📉 Zirveden Drawdown   : %{data.get('drawdown', 0.0)*100:.2f}")
        print(f"🛡️ Devre Kesici        : {'🚨 %50 NAKİT AKTİF' if data.get('dd_kesici_aktif') else '🟢 NORMAL (%100 HİSSE)'}")
        print(f"\n💼 AKTİF V3.2 PORTFÖY LİSTESİ ({len(data.get('positions', {}))} Hisse):")
        for s, info in sorted(data.get("positions", {}).items()):
            entry_p = info.get("entry_price", 0)
            last_p = info.get("last_price", entry_p)
            pnl = ((last_p - entry_p) / entry_p * 100) if entry_p > 0 else 0
            w = info.get('weight', 0.1) * 100.0
            held = info.get('days_held', 0)
            print(f"  • {s:<10} | Alış: ₺{entry_p:<7.2f} | Son: ₺{last_p:<7.2f} | Kâr: %{pnl:<+6.2f} | Tutulan: {held:02d}/60 gün | Ağr: %{w:.1f}")
    else:
        print("⚠️ Henüz oluşturulmuş bir V3 portföyü bulunamadı.")
    print("=" * 65 + "\n")


def goster_shadow_sistem_durumu():
    """Konsolda Phase H Shadow Sistem (Primary & Secondary) durumunu basar."""
    print("\n" + "=" * 80)
    print("⭐ PHASE H SHADOW SİSTEM DURUMU")
    print("=" * 80)
    try:
        from shadow_reader import get_shadow_system_state
        state = get_shadow_system_state(BASE_DIR)
        
        if not state or not state.get("primary_model") or not state.get("secondary_model"):
            print("⚠️ Shadow system state henüz oluşturulmamış veya eksik.")
            print("=" * 80 + "\n")
            return

        status = state.get("status", "UNKNOWN")
        session = state.get("session_date", "UNKNOWN")
        
        if status == "VALIDATED_DRY_RUN":
            print("⚠️ VALIDATED DRY-RUN — OFFICIAL CLEAN-FORWARD SIGNAL DEĞİLDİR")
        elif status == "OFFICIAL_CLEAN_FORWARD":
            print("✅ OFFICIAL CLEAN-FORWARD SIGNAL")
        else:
            print(f" Durum: {status}")
            
        print(f" 📅 Session: {session}")
        
        primary = state["primary_model"]
        secondary = state["secondary_model"]
        
        print("\n[ PRIMARY SHADOW MODEL: RC-LGBMR-001 ]")
        p_top10 = primary.get("top_10", [])
        print("  Top 10: " + ", ".join(p_top10) if p_top10 else "  Yok")
        
        print("\n[ SECONDARY SHADOW MODEL: RC-LAMBDAMART-001 ]")
        s_top10 = secondary.get("top_10", [])
        print("  Top 10: " + ", ".join(s_top10) if s_top10 else "  Yok")
        
        if state.get("comparison"):
            comp = state["comparison"]
            print("\n[ KARŞILAŞTIRMA (PRIMARY vs SECONDARY) ]")
            common = comp.get("common", [])
            p_only = comp.get("primary_only", [])
            s_only = comp.get("secondary_only", [])
            print("  Ortak Hisseler   : " + (", ".join(common) if common else "Yok"))
            print("  Yalnız Primary   : " + (", ".join(p_only) if p_only else "Yok"))
            print("  Yalnız Secondary : " + (", ".join(s_only) if s_only else "Yok"))
        
        if state.get("exclusions"):
            print("\n[ KISITLAMALAR / EXCLUSIONS ]")
            for exc in state["exclusions"]:
                print(f"  • {exc}")
                
    except Exception as e:
        print(f"❌ Shadow sistem durumu okunurken hata: {e}")
        
    print("=" * 80 + "\n")


def menu_goster():
    """İnteraktif Terminal Menüsü."""
    while True:
        print("\n" + "═" * 65)
        print("  🏛️  BIST QUANT SİSTEMİ — MERKEZİ KONTROL (HİBRİT MOTOR)")
        print("═" * 65)
        print("  [1] 🌐 Web Yönetim Terminali        (Streamlit Dashboard)")
        print("  [2] ⚡ Hibrid Tarama                (V3 Legacy Production + Phase H Shadow)")
        print("  [3] 🔄 Günlük Veri Güncelleme       (88 Hisse + Endeksler + VBTS)")
        print("  [4] 🛡️ Veri Bütünlüğü Doğrulama     (Kalite Güvence Denetimi)")
        print("  [5] ⏰ Hibrid Motor Otomasyonu      (18:35 Seans Kapanış Servisi)")
        print("  [6] 📊 LEGACY PRODUCTION            (V3 Ana Kasa Portföyü)")
        print("  [7] ⭐ Phase H Shadow Sistem Durumu (Primary & Secondary RC)")
        print("  [0] ❌ Çıkış")
        print("─" * 65)

        try:
            secim = input("👉 Seçiminiz [0-7]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Görüşmek üzere!")
            break

        if secim == "1":
            calistir_web_panel()
        elif secim == "2":
            calistir_anlik_kontrol()
        elif secim == "3":
            calistir_veri_guncelle()
        elif secim == "4":
            calistir_veri_dogrula()
        elif secim == "5":
            calistir_zamanlanmis_servis()
        elif secim == "6":
            goster_portfoy_durumu()
        elif secim == "7":
            goster_shadow_sistem_durumu()
        elif secim in ("0", "q", "exit", "cikis"):
            print("\n👋 Sistemden çıkıldı. Disiplinli ve karlı yatırımlar!")
            break
        else:
            print("⚠️ Geçersiz seçim! Lütfen 0 ile 7 arasında bir seçim yapın.")


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().strip("-")
        if arg in ("panel", "web", "app", "dashboard", "1"):
            calistir_web_panel()
        elif arg in ("kontrol", "tarama", "run", "now", "scan", "v4", "all", "dual", "2"):
            calistir_anlik_kontrol()
        elif arg in ("guncelle", "sync", "indir", "download", "veri-guncelle", "3"):
            calistir_veri_guncelle()
        elif arg in ("dogrula", "verify", "check", "veri-dogrula", "test", "4"):
            calistir_veri_dogrula()
        elif arg in ("oto", "servis", "service", "schedule", "bot", "5"):
            calistir_zamanlanmis_servis()
        elif arg in ("durum", "status", "portfoy", "portfolio", "6"):
            goster_portfoy_durumu()
        elif arg in ("shadow", "golge", "phase_h", "7"):
            goster_shadow_sistem_durumu()
        elif arg in ("yardim", "help", "h"):
            print(__doc__)
        else:
            print(f"⚠️ Bilinmeyen komut: {sys.argv[1]}")
            print("Kullanılabilir komutlar: panel, kontrol, guncelle, dogrula, oto, durum, shadow")
            print("Veya interaktif menü için parametresiz çalıştırın: python main.py")
    else:
        menu_goster()


if __name__ == "__main__":
    main()
