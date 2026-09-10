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

from models.v3_ranking.data_loader import yukle_veriler
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline
from models.v3_ranking.paper_trader import PaperTrader

# Log Yapılandırması
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SERVICE_LOG_FILE = LOGS_DIR / "paper_trading_service.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(SERVICE_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PaperTraderService")

# Süreç Kilitleme Dosyası (Race Condition Önleme)
LOCK_FILE = ROOT_DIR / "models" / "v3_ranking" / "paper_trader.lock"


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

            # Model sıralamasını üret (V3.1 Sektör Kısıtı + Likidite Filtresi ile select_top_k_v2)
            df_features = pipeline.compute_features(t_now, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
            df_ranked = pipeline.rank_stocks(df_features)
            top_10 = pipeline.select_top_k_v2(df_features, k=10)["sembol"].tolist()
            scores_all = df_ranked["ml_score"].values

            # Dashboard için sıralama önbelleğini atomik kaydet
            cache_path = ROOT_DIR / "models" / "v3_ranking" / "latest_ranking_cache.parquet"
            temp_cache = cache_path.with_suffix(".tmp")
            df_ranked.to_parquet(temp_cache, index=False)
            os.replace(temp_cache, cache_path)

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
            trader.execute_check(
                t=t_now,
                top_k_ranked=top_10,
                current_prices=current_prices,
                current_xu100_price=current_xu,
                seri_usdtry=seri_usdtry,
                tufe_aylik=tufe_aylik,
                scores_universe=scores_all,
                days_elapsed=max(0, days_elapsed)
            )

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
