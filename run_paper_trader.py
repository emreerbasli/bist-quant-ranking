"""
run_paper_trader.py
===================
PRODUCTION-CANDIDATE: PAPER TRADING OTOMASYON SERVİSİ
------------------------------------------------------
KRİTİK KURUMSAL SINIR (İHLAL EDİLEMEZ):
Bu sistem SADECE bildirim gönderir — hiçbir şekilde otomatik emir veya
al-sat kararı VERMEZ. Canlı sermaye kesinlikle kullanılmaz; sadece sanal portföy
(paper trading) takibidir ve tüm kararlar yatırımcının kendi takdirindedir.

Çalışma Prensibi:
- `schedule` kütüphanesi ile periyodik zamanlama.
- Her iş gününde seans kapanışı sonrası kontrol eder (18:30); son rebalance üzerinden
  en az 14 gün geçmişse ve BIST açıksa (hafta içi / tatil dışı) paper_trader.py'yi tetikler.
- BIST kapalıysa (Cumartesi, Pazar, resmi/dini tatil) çalışmayı atlar.
- Çakışma Önleyici (Race Condition Shield): Aynı anda iki işlemin çalışmasını engelleyen PID kilit sistemi.
- Her çalışmada 'logs/paper_trading_service.log' dosyasına 'sistem çalıştı' yazar;
  böylece operasyonel belirsizlik yaşanmaz.
"""

import sys
import os
import time
import logging
from logging.handlers import RotatingFileHandler
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

try:
    import schedule
except ImportError:
    schedule = None
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from models.v3_ranking.data_loader import yukle_veriler, check_market_date_alignment
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline
from models.v3_ranking.paper_trader import PaperTrader
import config as cfg

# Log Yapılandırması (RotatingFileHandler: 5MB sınır, 5 yedek dosya koruması)
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SERVICE_LOG_FILE = LOGS_DIR / "paper_trading_service.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler(
            SERVICE_LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PaperTraderService")

# Süreç Kilitleme Dosyası (Race Condition Önleme)
LOCK_FILE = ROOT_DIR / "models" / "v3_ranking" / "paper_trader.lock"
SELECTION_CACHE_FILE = ROOT_DIR / "models" / "v3_ranking" / "latest_selection_cache.parquet"
DRIFT_REPORT_FILE = ROOT_DIR / "models" / "v3_ranking" / "latest_drift_report.json"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Persist dashboard-only metadata without partially written JSON."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


# BIST Resmi ve Dini Tatil Günleri (2024-2027 Kapsamlı Takvim)
SABIT_RESMI_TATILLER = {
    "01-01",  # Yılbaşı
    "04-23",  # Ulusal Egemenlik ve Çocuk Bayramı
    "05-01",  # Emek ve Dayanışma Günü
    "05-19",  # Atatürk'ü Anma, Gençlik ve Spor Bayramı
    "07-15",  # Demokrasi ve Milli Birlik Günü
    "08-30",  # Zafer Bayramı
    "10-28",  # Cumhuriyet Bayramı Arefesi (Yarım Gün - 12:40 kapanış)
    "10-29",  # Cumhuriyet Bayramı
}

DINI_VE_DEGISKEN_TATILLER = {
    # 2024
    "2024-04-09", "2024-04-10", "2024-04-11", "2024-04-12",  # Ramazan Bayramı
    "2024-06-15", "2024-06-16", "2024-06-17", "2024-06-18", "2024-06-19",  # Kurban Bayramı
    # 2025
    "2025-03-29", "2025-03-30", "2025-03-31", "2025-04-01",  # Ramazan Bayramı
    "2025-06-05", "2025-06-06", "2025-06-07", "2025-06-08", "2025-06-09",  # Kurban Bayramı
    # 2026
    "2026-03-19", "2026-03-20", "2026-03-21", "2026-03-22",  # Ramazan Bayramı
    "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30",  # Kurban Bayramı
    # 2027
    "2027-03-08", "2027-03-09", "2027-03-10", "2027-03-11",  # Ramazan Bayramı
    "2027-05-15", "2027-05-16", "2027-05-17", "2027-05-18", "2027-05-19",  # Kurban Bayramı
}


def bist_acik_mi(t: datetime) -> bool:
    """Hafta sonu, resmi veya dini bayram kontrolü."""
    if t.weekday() >= 5:  # 5: Cumartesi, 6: Pazar
        return False
    ay_gun = t.strftime("%m-%d")
    if ay_gun in SABIT_RESMI_TATILLER:
        return False
    tam_tarih = t.strftime("%Y-%m-%d")
    if tam_tarih in DINI_VE_DEGISKEN_TATILLER:
        return False
    return True


class SingleExecutionLock:
    """İki sürecin (örn: Streamlit ve Scheduler) aynı anda portföy çalıştırmasını önler."""
    def __init__(self, lock_file: Path, max_age_seconds: int = 600):
        self.lock_file = lock_file
        self.max_age_seconds = max_age_seconds
        self.acquired = False

    def __enter__(self):
        if self.lock_file.exists():
            try:
                mtime = self.lock_file.stat().st_mtime
                if (time.time() - mtime) < self.max_age_seconds:
                    logger.warning(f"Kilit aktif ({self.lock_file.name}). Başka bir kontrol çalışıyor.")
                    return False
                else:
                    logger.warning("Bayatlamış (stale) kilit tespit edildi, temizleniyor...")
            except Exception:
                pass

        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            self.lock_file.write_text(f"{os.getpid()}_{time.time()}", encoding="utf-8")
            self.acquired = True
            return True
        except Exception as e:
            logger.warning(f"Kilit dosyası oluşturulamadı: {e}")
            return False

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            try:
                if self.lock_file.exists():
                    self.lock_file.unlink()
            except Exception:
                pass


def periyodik_gorev_calistir(force: bool = False) -> bool:
    """
    14 günlük rebalance kontrolünü icra eden ana operasyon fonksiyonu.
    Tam exception korumalıdır; beklenmedik hatalar schedule döngüsünü öldüremez.
    """
    simdi = datetime.now()
    logger.info("--------------------------------------------------")
    logger.info(f"Paper Trading Servis Kontrolü Başladı: {simdi.strftime('%Y-%m-%d %H:%M:%S')}")

    if not force and not bist_acik_mi(simdi):
        logger.info("BIST piyasası kapalı (Hafta sonu veya resmi/dini tatil). Görev atlandı.")
        return False

    with SingleExecutionLock(LOCK_FILE) as acquired:
        if not acquired:
            logger.warning("Eşzamanlı işlem engellendi (Kilit dosyası meşgul).")
            return False

        try:
            trader = PaperTrader()
            last_check_str = trader.portfolio_state.get("last_check_date")

            # 14 gün kontrolü
            if not force and last_check_str:
                try:
                    last_date = datetime.strptime(last_check_str, "%Y-%m-%d").date()
                    fark_gun = (simdi.date() - last_date).days
                    if fark_gun < 14:
                        logger.info(f"Son rebalance kontrolü üzerinden {fark_gun} gün geçti. 14 günlük periyot dolmadı (Beklemede).")
                        return False
                except Exception as e:
                    logger.warning(f"Tarih karşılaştırma hatası: {e}")

            # Verileri yükle (Self-contained V3 DataLoader üzerinden)
            logger.info("Piyasa verileri ve model yükleniyor...")
            fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
            pipeline = LGBMRankingPipeline()

            # En son geçerli işlem günü
            t_now = seri_xu100.index[-1]

            alignment = check_market_date_alignment(fiyat_dict, seri_xu100)
            if not alignment["aligned"]:
                logger.error(
                    "VERİ HİZALAMA KAPISI: %s Paper portföy ve sıralama güncellenmedi.",
                    alignment["reason"],
                )
                return False

            # Katman 4: Veri Tazelik Kapısı (Faz -1.3)
            freshness = trader.drift_monitor.check_data_freshness(pd.Timestamp.now(), fiyat_dict, max_lag_business_days=2)
            if freshness.should_halt:
                logger.error("🚨 VERİ TAZELİK KAPISI DEVREDE: %s", freshness.details)
                return False

            # Model sıralamasını üret (V3.1 Sektör Kısıtı + Likidite Filtresi ile select_top_k_v2)
            df_features = pipeline.compute_features(t_now, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
            df_ranked = pipeline.rank_stocks(df_features)
            df_selected = pipeline.select_top_k_v2(df_features, k=10, fiyat_dict=fiyat_dict)
            top_10 = df_selected["sembol"].tolist()
            scores_all = df_ranked["ml_score"].values

            # Dashboard için sıralama önbelleğini atomik kaydet
            cache_path = ROOT_DIR / "models" / "v3_ranking" / "latest_ranking_cache.parquet"
            temp_cache = cache_path.with_suffix(".tmp")
            df_ranked.to_parquet(temp_cache, index=False)
            os.replace(temp_cache, cache_path)
            temp_selection = SELECTION_CACHE_FILE.with_suffix(".tmp")
            df_selected.to_parquet(temp_selection, index=False)
            os.replace(temp_selection, SELECTION_CACHE_FILE)

            # Kapanış fiyatları (Hem yeni Top-10 hem de portföyde açık bekleyen hisseler)
            tum_semboller = set(top_10) | set(trader.portfolio_state.get("positions", {}).keys())
            current_prices = {}
            for s in tum_semboller:
                if s in fiyat_dict:
                    sub_p = fiyat_dict[s][fiyat_dict[s].index <= t_now]
                    if len(sub_p) > 0:
                        current_prices[s] = float(sub_p.iloc[-1])
            
            current_xu = float(seri_xu100[seri_xu100.index <= t_now].iloc[-1])

            # Gün farkı hesabı
            days_elapsed = 14
            if last_check_str:
                try:
                    days_elapsed = (t_now - pd.Timestamp(last_check_str)).days
                except Exception:
                    days_elapsed = 14

            # Paper trader icrası (Terminal kartı ve Telegram bildirimi üretir)
            logger.info(f"Paper trading kontrolü icra ediliyor ({t_now.strftime('%Y-%m-%d')})...")
            execution = trader.execute_check(
                t=t_now,
                top_k_ranked=top_10,
                current_prices=current_prices,
                current_xu100_price=current_xu,
                seri_usdtry=seri_usdtry,
                tufe_aylik=tufe_aylik,
                scores_universe=scores_all,
                days_elapsed=max(0, days_elapsed),
                fiyat_dict=fiyat_dict
            )

            drift = execution["drift_report"]
            _atomic_write_json(
                DRIFT_REPORT_FILE,
                {
                    "as_of": t_now.date().isoformat(),
                    "generated_at": datetime.now().isoformat(),
                    "overall_status": drift.overall_status,
                    "summary_message": drift.summary_message,
                    "macro": asdict(drift.macro_result),
                    "score": asdict(drift.score_result) if drift.score_result else None,
                    "performance": asdict(drift.performance_result) if drift.performance_result else None,
                },
            )

            # Çift model karşılaştırma raporunu güncelle ve konsola bas
            try:
                from models.v4_ranking.v3_v4_comparator import generate_v3_vs_v4_comparison, print_comparison_card
                comp_data = generate_v3_vs_v4_comparison(tarih=t_now.strftime("%Y-%m-%d"))
                print_comparison_card(comp_data)
            except Exception as e:
                logger.debug(f"Karşılaştırma raporu güncelleme uyarısı: {e}")

            # ZORUNLU KAYIT: Operasyonel netlik logu
            logger.info("✅ sistem çalıştı — Paper trading kontrolü ve bildirimi başarıyla tamamlandı.")
            return True

        except Exception as e:
            logger.error(f"❌ Paper trading servisinde hata oluştu: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Servis döngüsü başlatıcı."""
    print("=" * 80)
    print("BIST V3 KANTİTATİF MODEL: PAPER TRADING SERVİSİ (ZAMANLANMIŞ)")
    print("KRİTİK SINIR: Bu servis SADECE bildirim gönderir, otomatik al-sat yapmaz.")
    print("=" * 80)

    # Parametre kontrolleri
    if len(sys.argv) > 1 and "--v4" in sys.argv:
        from run_paper_trader_v4 import periyodik_gorev_calistir_v4
        logger.info("V4 tetikleme bayrağı algılandı, V4 çalıştırılıyor...")
        periyodik_gorev_calistir_v4(force=True)
        return

    if len(sys.argv) > 1 and "--all" in sys.argv:
        from run_paper_trader_v4 import periyodik_gorev_calistir_v4
        logger.info("Çift model bayrağı algılandı, V3 ve V4 paralel çalıştırılıyor...")
        periyodik_gorev_calistir(force=True)
        periyodik_gorev_calistir_v4(force=True)
        return

    # Parametre olarak --run-once veya --now verilirse hemen tek seferlik çalıştır
    if len(sys.argv) > 1 and sys.argv[1] in ["--now", "--run-once", "-f"]:
        logger.info("Manuel tetikleme bayrağı algılandı, hemen çalıştırılıyor...")
        periyodik_gorev_calistir(force=True)
        return

    # Zamanlayıcı planı: Her gün saat 18:30'da (BIST seans kapanışı sonrası) kontrol et
    schedule.every().day.at("18:30").do(periyodik_gorev_calistir)
    logger.info("Servis zamanlayıcısı kuruldu: Her gün 18:30'da BIST seans kapanış kontrolü.")
    logger.info("Servis döngüsü başlatıldı (Durdurmak için Ctrl+C)...")

    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"Schedule döngüsünde beklenmeyen hata: {e}")
        time.sleep(30)


if __name__ == "__main__":
    main()
