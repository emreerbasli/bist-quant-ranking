"""
run_paper_trader_v4.py
======================
V4 PRODUCTION-CANDIDATE: PAPER TRADING OTOMASYON SERVİSİ (9-FEATURE RANKER)
----------------------------------------------------------------------------
KRİTİK KURUMSAL SINIR:
Bu servis SADECE bildirim gönderir — hiçbir şekilde otomatik emir vermez.
Canlı sermaye KESİNLİKLE kullanılmaz; sadece sanal portföy (paper trading) takibidir.

V4 ÖZELLİKLERİ:
  - 9 Faktörlü LGBMRanker (winning_lgbm_ranker_v4.joblib)
  - K=15 Portföy Boyutu
  - Faz 0 Ardışık Taban Hard-Exclusion ve Acil Çıkış
  - KAP / VBTS Tedbir Kalkanı
  - Layer 4 Veri Tazeliği (2 iş günü gecikmede operasyon kilitleme) ve Layer 5 Veri Sağlığı
  - V3 altyapısından %100 izole state ve kilit mekanizması.
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

from models.v4_ranking.data_loader_v4 import yukle_veriler, check_market_date_alignment
from models.v4_ranking.ranking_pipeline_v4 import LGBMRankingPipelineV4
from models.v4_ranking.paper_trader_v4 import PaperTraderV4
import config as cfg

# Log Yapılandırması (RotatingFileHandler: 5MB sınır, 5 yedek dosya koruması)
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SERVICE_LOG_FILE = LOGS_DIR / "paper_trading_service_v4.log"

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
logger = logging.getLogger("PaperTraderServiceV4")

# V4 Süreç Kilitleme Dosyası (Race Condition Önleme — V3'ten Tamamen İzole)
LOCK_FILE_V4 = ROOT_DIR / "models" / "v4_ranking" / "paper_trader_v4.lock"
SELECTION_CACHE_FILE_V4 = ROOT_DIR / "models" / "v4_ranking" / "latest_selection_cache_v4.parquet"
RANKING_CACHE_FILE_V4 = ROOT_DIR / "models" / "v4_ranking" / "latest_ranking_cache_v4.parquet"
DRIFT_REPORT_FILE_V4 = ROOT_DIR / "models" / "v4_ranking" / "latest_drift_report_v4.json"


def _safe_replace(src_path: Path, dst_path: Path, max_retries: int = 5, delay: float = 0.2) -> None:
    """Windows dosya kilitleme (WinError 32) korumalı atomik ve dayanıklı yer değiştirme."""
    import shutil
    for i in range(max_retries):
        try:
            os.replace(src_path, dst_path)
            return
        except (PermissionError, OSError):
            time.sleep(delay)
    # 5 deneme sonrası hala kilitliyse copy2 ile üzerine yaz
    try:
        shutil.copy2(src_path, dst_path)
        try:
            os.remove(src_path)
        except Exception:
            pass
    except Exception as ex:
        logger.warning(f"Dosya güvenli yer değiştirme uyarısı: {ex}")


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Atomik JSON yazıcı."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2, default=str)
        output.flush()
        os.fsync(output.fileno())
    _safe_replace(temporary, path)


class SingleExecutionLockV4:
    """V4 için bağımsız süreç kilidi."""
    def __init__(self, lock_file: Path, max_age_seconds: int = 600):
        self.lock_file = lock_file
        self.max_age_seconds = max_age_seconds
        self.acquired = False

    def __enter__(self):
        if self.lock_file.exists():
            try:
                mtime = self.lock_file.stat().st_mtime
                if (time.time() - mtime) < self.max_age_seconds:
                    logger.warning(f"V4 Kilidi aktif ({self.lock_file.name}). Başka bir kontrol çalışıyor.")
                    return False
                else:
                    logger.warning("Bayatlamış V4 kilidi tespit edildi, temizleniyor...")
            except Exception:
                pass

        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            self.lock_file.write_text(f"{os.getpid()}_{time.time()}", encoding="utf-8")
            self.acquired = True
            return True
        except Exception as e:
            logger.warning(f"V4 Kilit dosyası oluşturulamadı: {e}")
            return False

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            try:
                if self.lock_file.exists():
                    self.lock_file.unlink()
            except Exception:
                pass


def periyodik_gorev_calistir_v4(force: bool = False, send_telegram: bool = True) -> bool:
    """
    V4 Ranker 14 günlük periyodik rebalance ve sağlık denetimini icra eder.
    """
    simdi = datetime.now()
    logger.info("--------------------------------------------------")
    logger.info(f"V4 Paper Trading Servis Kontrolü Başladı: {simdi.strftime('%Y-%m-%d %H:%M:%S')}")

    if not force and not cfg.bist_is_gunu_mu(simdi):
        logger.info("BIST piyasası kapalı (Hafta sonu veya resmi/dini tatil). V4 görevi atlandı.")
        return False

    with SingleExecutionLockV4(LOCK_FILE_V4) as acquired:
        if not acquired:
            logger.warning("V4 Eşzamanlı işlem engellendi (Kilit dosyası meşgul).")
            return False

        try:
            trader = PaperTraderV4()
            last_check_str = trader.portfolio_state.get("last_check_date")

            # 14 gün kontrolü
            if not force and last_check_str:
                try:
                    last_date = datetime.strptime(last_check_str, "%Y-%m-%d").date()
                    fark_gun = (simdi.date() - last_date).days
                    if fark_gun < 14:
                        logger.info(f"V4 Son kontrol üzerinden {fark_gun} gün geçti. 14 günlük periyot dolmadı (Beklemede).")
                        return False
                except Exception as e:
                    logger.warning(f"V4 Tarih karşılaştırma hatası: {e}")

            # Verileri yükle
            logger.info("V4 Piyasa verileri ve 9-Faktörlü model yükleniyor...")
            fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
            pipeline = LGBMRankingPipelineV4()

            t_now = seri_xu100.index[-1]

            # Veri Hizalama Kontrolü
            alignment = check_market_date_alignment(fiyat_dict, seri_xu100)
            if not alignment["aligned"]:
                logger.error(f"VERİ HİZALAMA KAPISI: {alignment['reason']}. V4 portföy güncellenmedi.")
                return False

            # Katman 4: Veri Tazelik Kapısı (Faz -1.3 / 2 iş günü durdurma)
            freshness = trader.drift_monitor.check_data_freshness(pd.Timestamp.now(), fiyat_dict, max_lag_business_days=2)
            if freshness.should_halt:
                logger.error(f"🚨 V4 VERİ TAZELİK KAPISI DEVREDE: {freshness.details}")
                return False

            # 9-Faktörlü Model Sıralaması ve K=15 Seçimi
            df_features = pipeline.compute_features(t_now, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
            df_ranked = pipeline.rank_stocks(df_features)
            df_selected = pipeline.select_top_k_v2(df_features, k=15, fiyat_dict=fiyat_dict, check_vbts=True)
            top_15 = df_selected["sembol"].tolist()
            scores_all = df_ranked["ml_score"].values

            # Dashboard önbelleğini atomik kaydet
            temp_cache = RANKING_CACHE_FILE_V4.with_suffix(".tmp")
            df_ranked.to_parquet(temp_cache, index=False)
            _safe_replace(temp_cache, RANKING_CACHE_FILE_V4)

            temp_sel = SELECTION_CACHE_FILE_V4.with_suffix(".tmp")
            df_selected.to_parquet(temp_sel, index=False)
            _safe_replace(temp_sel, SELECTION_CACHE_FILE_V4)

            # Kapanış fiyatları
            tum_semboller = set(top_15) | set(trader.portfolio_state.get("positions", {}).keys())
            current_prices = {}
            for s in tum_semboller:
                if s in fiyat_dict:
                    sub_p = fiyat_dict[s][fiyat_dict[s].index <= t_now]
                    if len(sub_p) > 0:
                        current_prices[s] = float(sub_p.iloc[-1])

            current_xu = float(seri_xu100[seri_xu100.index <= t_now].iloc[-1])

            days_elapsed = 14
            if last_check_str:
                try:
                    days_elapsed = (t_now - pd.Timestamp(last_check_str)).days
                except Exception:
                    days_elapsed = 14

            # V4 Paper Trader İcrası
            logger.info(f"V4 Paper trading kontrolü icra ediliyor ({t_now.strftime('%Y-%m-%d')})...")
            execution = trader.execute_check(
                t=t_now,
                top_k_ranked=top_15,
                current_prices=current_prices,
                current_xu100_price=current_xu,
                seri_usdtry=seri_usdtry,
                tufe_aylik=tufe_aylik,
                scores_universe=scores_all,
                days_elapsed=max(0, days_elapsed),
                send_telegram=send_telegram,
                fiyat_dict=fiyat_dict,
                pit_bellek=pit_bellek
            )

            drift = execution["drift_report"]
            _atomic_write_json(
                DRIFT_REPORT_FILE_V4,
                {
                    "as_of": t_now.date().isoformat(),
                    "generated_at": datetime.now().isoformat(),
                    "overall_status": drift.overall_status,
                    "summary_message": drift.summary_message,
                    "macro": asdict(drift.macro_result),
                    "score": asdict(drift.score_result) if drift.score_result else None,
                    "performance": asdict(drift.performance_result) if drift.performance_result else None,
                    "freshness": asdict(drift.freshness_result) if drift.freshness_result else None,
                    "health": asdict(drift.health_result) if drift.health_result else None,
                },
            )

            # Çift model karşılaştırma raporunu güncelle ve konsola bas
            try:
                from models.v4_ranking.v3_v4_comparator import generate_v3_vs_v4_comparison, print_comparison_card
                comp_data = generate_v3_vs_v4_comparison(tarih=t_now.strftime("%Y-%m-%d"))
                print_comparison_card(comp_data)
            except Exception as e:
                logger.debug(f"Karşılaştırma raporu güncelleme uyarısı: {e}")

            logger.info("✅ sistem çalıştı — V4 Paper trading kontrolü başarıyla tamamlandı.")
            return True

        except Exception as e:
            logger.error(f"❌ V4 Paper trading servisinde hata: {e}", exc_info=True)
            return False


def seans_1335_kontrol_v4(force: bool = False) -> bool:
    """
    Arife / Yarım Gün V4 Paper Trading Tetikleyicisi (13:35).
    BIST yarım günlerde 12:40'ta kapanır. Veriler 13:15'te indikten sonra 13:35'te V4 kontrolü çalışır.
    KRİTİK GÜVENLİK KAPISI: Normal günlerde 13:35'te ASLA çalışmaz.
    """
    simdi = datetime.now()
    if not force:
        if not cfg.bist_is_gunu_mu(simdi):
            logger.info("BIST piyasası kapalı (Hafta sonu veya tatil). Saat 13:35 V4 kontrolü atlandı.")
            return False
        if not cfg.bist_yarim_gun_mu(simdi):
            logger.info("Bugün BIST normal tam seans günü. Saat 13:35 V4 kontrolü güvenlik kapısıyla engellendi; 18:35'te çalışacak.")
            return False
    logger.info("📢 Arife/Yarım gün seans kapanış tespiti — V4 kontrolü başlatılıyor...")
    return periyodik_gorev_calistir_v4(force=force)


def seans_1835_kontrol_v4(force: bool = False) -> bool:
    """
    Normal Gün V4 Paper Trading Tetikleyicisi (18:35).
    Eğer bugün yarım gün idiyse (13:35'te kontrol yapıldıysa) mükerrer çalışmayı engeller.
    """
    simdi = datetime.now()
    if not force:
        if not cfg.bist_is_gunu_mu(simdi):
            logger.info("BIST piyasası kapalı (Hafta sonu veya tatil). Saat 18:35 V4 kontrolü atlandı.")
            return False
        if cfg.bist_yarim_gun_mu(simdi):
            logger.info("Bugün BIST yarım gündü ve V4 kontrolü 13:35'te tamamlandı. Saat 18:35 mükerrer koşusu atlandı.")
            return False
    return periyodik_gorev_calistir_v4(force=force)


def main():
    print("=" * 80)
    print("BIST V4 KANTİTATİF MODEL (9 FAKTÖR): PAPER TRADING SERVİSİ")
    print("KRİTİK SINIR: Bu servis SADECE bildirim gönderir, otomatik al-sat yapmaz.")
    print("=" * 80)

    if len(sys.argv) > 1 and sys.argv[1] in ["--now", "--run-once", "-f"]:
        logger.info("Manuel tetikleme algılandı, V4 hemen çalıştırılıyor...")
        periyodik_gorev_calistir_v4(force=True)
        return

    if schedule:
        schedule.every().day.at("13:35").do(seans_1335_kontrol_v4)
        schedule.every().day.at("18:35").do(seans_1835_kontrol_v4)
        logger.info("V4 Servis zamanlayıcısı kuruldu:")
        logger.info("  • Normal Seans: Her gün saat 18:35'te BIST kapanış kontrolü (Yarım günlerde atlar).")
        logger.info("  • Yarım Seans:  Arife günlerinde saat 13:35'te erken kontrol (Normal günlerde atlar).")
        logger.info("V4 Servis döngüsü başlatıldı (Durdurmak için Ctrl+C)...")

        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                logger.error(f"V4 Schedule döngüsünde hata: {e}")
            time.sleep(30)
    else:
        logger.warning("Schedule modülü bulunamadı, tek seferlik çalıştırılıyor.")
        periyodik_gorev_calistir_v4(force=True)


if __name__ == "__main__":
    main()
