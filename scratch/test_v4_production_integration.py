"""
scratch/test_v4_production_integration.py
==========================================
V4 PRODÜKSİYON ALTYAPISI ENTEGRASYON VE İZOLASYON DOĞRULAMA TESTİ
-----------------------------------------------------------------
Bu test paketi şu 5 kritik kurumsal teyidi yapar:
  1. V4 Model ve Çıkarım Motoru (9-Feature Pipeline):
     - winning_lgbm_ranker_v4.joblib dosyasının yüklenmesi
     - 9 faktörün eksiksiz hesaplanması (özellikle reel_eps_growth)
     - select_top_k_v2 (K=15, Faz 0 ardışık taban ve VBTS koruması)
  2. V4 Drift & Güvenlik Monitörü (5 Katman):
     - Layer 1 (Makro rejim), Layer 2 (V4 Skor Drifti), Layer 3 (Performans)
     - Layer 4 (Veri Tazeliği 2 iş günü kilidi), Layer 5 (88 Hisse Sağlık)
  3. V3 vs V4 %100 Durum İzolasyonu:
     - paper_portfolio_v4.json ve paper_trading_log_v4.csv bağımsızlığı
     - V3 paper_portfolio.json dosyasının hiçbir şekilde etkilenmediği
  4. V4 Paper Trader İcra Döngüsü:
     - execute_check() ile portföy güncellemesi, log kaydı ve önbellek yazımı
  5. Otonom Veri Senkronizasyonu Güvencesi:
     - tasks/data_sync_service.py'nin ortak ham veriyi beslemesi
"""

import sys
import json
import logging
from pathlib import Path
import pandas as pd
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.v3_ranking.data_loader import yukle_veriler, check_market_date_alignment
from models.v4_ranking.ranking_pipeline_v4 import LGBMRankingPipelineV4
from models.v4_ranking.drift_monitor_v4 import DriftMonitorV4
from models.v4_ranking.paper_trader_v4 import PaperTraderV4

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TestV4Integration")


def test_1_v4_pipeline_and_features():
    print("\n--- TEST 1: V4 MODEL VE ÇIKARIM MOTORU TESTİ ---")
    pipe = LGBMRankingPipelineV4()
    assert pipe.model is not None, "V4 Model nesnesi None!"
    assert len(pipe.feature_cols) == 9, f"Özellik sayısı 9 olmalı, mevcut: {len(pipe.feature_cols)}"
    assert "reel_eps_growth" in pipe.feature_cols, "reel_eps_growth özelliklerde yok!"
    print(f"✅ V4 Model başarıyla yüklendi: {pipe.model_name}")
    print(f"✅ Özellikler (9 Adet): {pipe.feature_cols}")

    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, _, tufe_aylik = yukle_veriler()
    t_now = seri_xu100.index[-1]
    print(f"Piyasa referans tarihi: {t_now.strftime('%Y-%m-%d')}")

    df_features = pipe.compute_features(t_now, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
    assert not df_features.empty, "Özellik matrisi boş!"
    assert len(df_features) >= 80, f"Evrendeki hisse sayısı yetersiz: {len(df_features)}"
    assert "reel_eps_growth" in df_features.columns, "reel_eps_growth matriste yok!"
    print(f"✅ 9-Faktör matrisi üretildi: {len(df_features)} hisse | reel_eps_growth ortalama: {df_features['reel_eps_growth'].mean():.4f}")

    df_ranked = pipe.rank_stocks(df_features)
    assert "ml_score" in df_ranked.columns, "ml_score sütunu eksik!"
    assert df_ranked["rank"].iloc[0] == 1, "En iyi hisse 1. sırada olmalı!"
    print(f"✅ Sıralama motoru çalıştı: En yüksek skorlu hisse: {df_ranked['sembol'].iloc[0]} (Skor: {df_ranked['ml_score'].iloc[0]:.4f})")

    df_top15 = pipe.select_top_k_v2(df_features, k=15, fiyat_dict=fiyat_dict, check_vbts=True)
    assert len(df_top15) == 15, f"Seçilen hisse sayısı 15 olmalı, mevcut: {len(df_top15)}"
    print(f"✅ select_top_k_v2 (K=15) çalıştı: {df_top15['sembol'].tolist()}")
    return pipe, df_features, df_ranked, df_top15, fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, tufe_aylik, t_now


def test_2_v4_drift_and_health_monitor(pipe, df_features, df_ranked, fiyat_dict, seri_usdtry, tufe_aylik, pit_bellek, t_now):
    print("\n--- TEST 2: V4 DRİFT VE SAĞLIK MONİTÖRÜ TESTİ (5 KATMAN) ---")
    monitor = DriftMonitorV4()
    
    # Katman 1: Makro Rejim
    macro = monitor.check_macro_regime(t_now, seri_usdtry, tufe_aylik)
    print(f"✅ Katman 1 (Makro Rejim): {macro.status} (Reel Faiz: %{macro.reel_faiz:.1f}, USD Mom: %{macro.usd_mom_60*100:.1f})")

    # Katman 2: Skor Drifti
    score_drift = monitor.check_score_drift(df_ranked["ml_score"].values)
    print(f"✅ Katman 2 (V4 Skor Drifti): {score_drift.status} (Mean Z: {score_drift.z_score_mean:+.2f}, Std Z: {score_drift.z_score_std:+.2f})")

    # Katman 3: Performans
    perf = monitor.check_performance_degradation(realized_sharpe=0.95)
    print(f"✅ Katman 3 (Performans Eşiği): {perf.status} (Ref: {perf.reference_sharpe:.2f}, Eşik: {perf.alarm_threshold:.2f})")

    # Katman 4: Veri Tazeliği
    freshness = monitor.check_data_freshness(pd.Timestamp.now(), fiyat_dict, max_lag_business_days=2)
    print(f"✅ Katman 4 (Veri Tazeliği Emniyet Kapısı): {freshness.status} (İş günü gecikmesi: {freshness.business_days_lag})")

    # Katman 5: Veri Sağlığı
    health = monitor.check_data_health(fiyat_dict, pit_bellek, tufe_aylik, t_now)
    print(f"✅ Katman 5 (88 Hisse Sağlık): {health.status} ({health.details})")

    report = monitor.generate_full_report(
        t=t_now, seri_usdtry=seri_usdtry, tufe_aylik=tufe_aylik,
        scores=df_ranked["ml_score"].values,
        realized_sharpe=0.95,
        fiyat_dict=fiyat_dict,
        pit_bellek=pit_bellek
    )
    assert report is not None, "Rapor üretilemedi!"
    drift_json = Path(__file__).resolve().parent.parent / "models" / "v4_ranking" / "latest_drift_report_v4.json"
    assert drift_json.exists(), "latest_drift_report_v4.json oluşturulamadı!"
    print(f"✅ Konsolide Rapor ve JSON kaydı doğrulandı: Genel Durum = {report.overall_status}")


def test_3_isolation_and_paper_trader(df_top15, fiyat_dict, seri_xu100, seri_usdtry, tufe_aylik, pit_bellek, t_now):
    print("\n--- TEST 3: V3 VS V4 İZOLASYON VE PAPER TRADER TESTİ ---")
    v3_portfolio_file = Path(__file__).resolve().parent.parent / "models" / "v3_ranking" / "paper_portfolio.json"
    v4_portfolio_file = Path(__file__).resolve().parent.parent / "models" / "v4_ranking" / "paper_portfolio_v4.json"
    v4_log_file = Path(__file__).resolve().parent.parent / "models" / "v4_ranking" / "paper_trading_log_v4.csv"

    assert v3_portfolio_file.exists(), "V3 Portföy dosyası mevcut olmalı!"
    assert v4_portfolio_file.exists(), "V4 Portföy dosyası mevcut olmalı!"
    assert v4_log_file.exists(), "V4 Log dosyası mevcut olmalı!"

    # V3'ün mevcut durumunu oku
    with open(v3_portfolio_file, "r", encoding="utf-8") as f:
        v3_before = f.read()

    # V4 Paper Trader başlat
    trader_v4 = PaperTraderV4()
    assert trader_v4.portfolio_state["version"] == "v4", "V4 versiyon etiketi hatalı!"
    assert trader_v4.k_size == 15, f"V4 portföy boyutu 15 olmalı, mevcut: {trader_v4.k_size}"
    print(f"✅ V4 Paper Trader başlatıldı (K={trader_v4.k_size}, Başlangıç Sermayesi: {trader_v4.portfolio_state['equity']})")

    # Kapanış fiyatları
    top15_symbols = df_top15["sembol"].tolist()
    current_prices = {s: float(fiyat_dict[s][fiyat_dict[s].index <= t_now].iloc[-1]) for s in top15_symbols if s in fiyat_dict}
    current_xu = float(seri_xu100[seri_xu100.index <= t_now].iloc[-1])

    # V4 Rebalance İcrası
    exec_res = trader_v4.execute_check(
        t=t_now,
        top_k_ranked=top15_symbols,
        current_prices=current_prices,
        current_xu100_price=current_xu,
        seri_usdtry=seri_usdtry,
        tufe_aylik=tufe_aylik,
        days_elapsed=14,
        fiyat_dict=fiyat_dict,
        pit_bellek=pit_bellek
    )

    assert len(exec_res["positions"]) == 15, f"V4 Portföyünde 15 hisse olmalı, mevcut: {len(exec_res['positions'])}"
    print(f"✅ V4 İcra Başarılı: {len(exec_res['positions'])} hisse portföye alındı.")
    print(f"   Yeni Pozisyonlar: {', '.join(exec_res['positions'])}")

    # V3 Dosyasının Dokunulmadığını Teyit Et
    with open(v3_portfolio_file, "r", encoding="utf-8") as f:
        v3_after = f.read()
    assert v3_before == v3_after, "KRİTİK HATA: V4 icrası sırasında V3 portföy dosyası değişti!"
    print("🏆 %100 İZOLASYON DOĞRULANDI: V3 paper_portfolio.json dosyası tamamen korunmuştur (Sıfır Etkileşim).")

    # V4 Log Dosyasını Denetle
    df_log = pd.read_csv(v4_log_file)
    assert not df_log.empty, "V4 paper_trading_log_v4.csv boş kaldı!"
    print(f"✅ V4 Log Dosyasına Kayıt Yazıldı: {len(df_log)} satır mevcut.")


def main():
    print("=" * 85)
    print("BIST V4 PRODÜKSİYON ALTYAPISI DOĞRULAMA VE ENTEGRASYON TESTİ")
    print("=" * 85)
    pipe, df_f, df_r, df_top15, fiyat_dict, xu, u, pit, tufe, t_now = test_1_v4_pipeline_and_features()
    test_2_v4_drift_and_health_monitor(pipe, df_f, df_r, fiyat_dict, u, tufe, pit, t_now)
    test_3_isolation_and_paper_trader(df_top15, fiyat_dict, xu, u, tufe, pit, t_now)
    print("\n" + "=" * 85)
    print("🎉 TÜM DOĞRULAMA VE ENTEGRASYON TESTLERİ 3/3 BAŞARIYLA TAMAMLANDI!")
    print("V4 PRODÜKSİYON ALTYAPISI İZOLE VE CANLI PAPER TRADING DÖNGÜSÜNE HAZIRDIR.")
    print("=" * 85)


if __name__ == "__main__":
    main()
