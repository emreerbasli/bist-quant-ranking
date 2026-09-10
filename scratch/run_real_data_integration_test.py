"""
scratch/run_real_data_integration_test.py
=========================================
GERÇEK VERİYLE UÇTAN UCA ENTEGRASYON TESTİ (TEK SEFERLİK)
---------------------------------------------------------
Adım A: Ranking Pipeline Gerçek Veri Testi (2026-09-07)
Adım B: Drift Monitor Gerçek Veri Testi
Adım C: Paper Trader İlk Gerçek Çalışma (paper_portfolio.json ve log.csv)
"""

import sys
import json
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scratch.run_faz_c_walk_forward_test import yukle_veriler
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline
from models.v3_ranking.drift_monitor import DriftMonitor
from models.v3_ranking.paper_trader import PaperTrader


def main():
    print("=" * 115)
    print("GERÇEK VERİYLE UÇTAN UCA ENTEGRASYON VE BAŞLATMA TESTİ")
    print("Hedef Tarih: 2026-09-07 (Mevcut Veri Tabanındaki En Güncel Tarih)")
    print("=" * 115)

    # 1. Gerçek Verileri Yükle
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    t_now = pd.Timestamp("2026-09-07")
    total_universe_count = len(fiyat_dict)

    # =========================================================================
    # ADIM A — RANKING PIPELINE GERÇEK VERİ TESTİ
    # =========================================================================
    print("\n" + "=" * 90)
    print(">>> ADIM A: RANKING PIPELINE GERÇEK VERİ TESTİ")
    print("=" * 90)

    try:
        pipeline = LGBMRankingPipeline()
        print(f"Model Yüklendi: {pipeline.candidate_name}")
        print(f"Kullanılan Özellikler: {pipeline.feature_cols}")

        df_features = pipeline.compute_features(t_now, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
        stocks_with_fundamentals = len(df_features)
        stocks_missing = total_universe_count - stocks_with_fundamentals

        print(f"Bugünkü Tarih: {t_now.strftime('%Y-%m-%d')}")
        print(f"Kullanılan Son Bilanço Çeyreği: 2026Q2 (Geçerlilik: 2026-08-15 Point-in-Time)")
        print(f"Toplam BIST Evreni: {total_universe_count} hisse")
        print(f"Fundamental Verisi Mevcut: {stocks_with_fundamentals} hisse")
        print(f"Fundamental Verisi Eksik/Filtrelenen: {stocks_missing} hisse")

        if stocks_with_fundamentals < 50:
            raise ValueError(f"Yetersiz hisse sayısı ({stocks_with_fundamentals})! Veri akışında problem var.")

        df_ranked = pipeline.rank_stocks(df_features)
        df_top10 = pipeline.select_top_k(df_features, k=10)

        print("\n🏆 MODELİN ÜRETTİĞİ GÜNCEL K=10 LİSTESİ:")
        print("-" * 80)
        print(f"{'Sıra':<5} | {'Hisse':<10} | {'Sektör':<12} | {'Ham Skor':<10} | {'Z(P/B)':<8} | {'Z(Borç)':<8} | {'Z(Mom)':<8}")
        print("-" * 80)
        for _, row in df_top10.iterrows():
            print(f"{int(row['rank']):<5} | {row['sembol']:<10} | {row['sektor']:<12} | {row['ml_score']:>10.4f} | {row['z_pb']:>8.2f} | {row['z_borc']:>8.2f} | {row['z_mom']:>8.2f}")
        print("-" * 80)

        # Eksik / NaN kontrolü
        nan_count = df_features[pipeline.feature_cols].isna().sum().sum()
        print(f"Feature matrisinde NaN / Eksik Veri Sayısı: {nan_count}")
        assert nan_count == 0, "Feature matrisinde beklenmeyen NaN değerler var!"
        print("✅ ADIM A BAŞARIYLA GEÇTİ (Sıfır Hata).")

    except Exception as e:
        print(f"❌ ADIM A HATASI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # =========================================================================
    # ADIM B — DRIFT MONITOR GERÇEK VERİ TESTİ
    # =========================================================================
    print("\n" + "=" * 90)
    print(">>> ADIM B: DRIFT MONITOR GERÇEK VERİ TESTİ")
    print("=" * 90)

    try:
        monitor = DriftMonitor()
        scores_all = df_ranked["ml_score"].values

        # 1. Makro Kontrol
        macro_res = monitor.check_macro_regime(t_now, seri_usdtry, tufe_aylik)
        print(f"1. Bugünkü TCMB Politika Faizi:  %{macro_res.politika_faizi:.2f}")
        print(f"   Son 12 Aylık TÜFE:            %{macro_res.yillik_tufe:.2f}")
        print(f"   Hesaplanan Reel Faiz:         %{macro_res.reel_faiz:.2f}")
        print(f"2. Bugünkü USD_Mom_60 (60g):     %{macro_res.usd_mom_60*100:.2f}")
        print(f"3. Makro Durum:                  {macro_res.status}")
        print(f"   Detay:                        {macro_res.details}")

        # 2. Skor Drift Kontrolü
        score_res = monitor.check_score_drift(scores_all)
        print(f"\n4. Skor Dağılımı:                Ort: {score_res.current_mean:.4f}, Std: {score_res.current_std:.4f}")
        print(f"   Tarihsel Z-Score (Ortalama):  Z = {score_res.z_score_mean:+.2f} (Eşik: |Z| > 2.5)")
        print(f"   Skor Drift Durumu:            {score_res.status}")

        # 3. Konsolide Durum
        full_rep = monitor.generate_full_report(t_now, seri_usdtry, tufe_aylik, scores_all, realized_sharpe=None)
        print(f"\n5. GENEL SİSTEM DURUMU:          {full_rep.overall_status}")
        print(f"   Özet Mesaj:                   {full_rep.summary_message}")
        print("✅ ADIM B BAŞARIYLA GEÇTİ (Sıfır Hata).")

    except Exception as e:
        print(f"❌ ADIM B HATASI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # =========================================================================
    # ADIM C — PAPER TRADER İLK GERÇEK ÇALIŞMA
    # =========================================================================
    print("\n" + "=" * 90)
    print(">>> ADIM C: PAPER TRADER İLK GERÇEK ÇALIŞMA")
    print("=" * 90)

    try:
        trader = PaperTrader()
        top_10_tickers = df_top10["sembol"].tolist()

        # Güncel hisse kapanış fiyatları (2026-09-07)
        current_prices = {}
        for s in top_10_tickers:
            if s in fiyat_dict and len(fiyat_dict[s]) > 0:
                # 2026-09-07 veya en son geçerli kapanış
                sub_p = fiyat_dict[s][fiyat_dict[s].index <= t_now]
                current_prices[s] = float(sub_p.iloc[-1])
            else:
                raise ValueError(f"Hisse fiyatı bulunamadı: {s}")

        # Güncel XU100 kapanışı
        sub_xu = seri_xu100[seri_xu100.index <= t_now]
        current_xu = float(sub_xu.iloc[-1])

        print(f"Portföye Alınacak 10 Hisse ve Güncel Fiyatları ({t_now.strftime('%Y-%m-%d')}):")
        for s in top_10_tickers:
            print(f"  - {s:<10}: {current_prices[s]:>8.2f} TL (%10 ağırlık)")
        print(f"  - BIST 100:   {current_xu:>8.2f}")

        # İlk çalıştırmayı icra et
        run_res = trader.execute_check(
            t=t_now,
            top_k_ranked=top_10_tickers,
            current_prices=current_prices,
            current_xu100_price=current_xu,
            seri_usdtry=seri_usdtry,
            tufe_aylik=tufe_aylik,
            scores_universe=scores_all,
            days_elapsed=0
        )

        print("\n📁 OLUŞTURULAN PAPER TRADING DOSYALARI:")
        print(f"  1. Portföy Durumu: {trader.portfolio_file} (Boyut: {trader.portfolio_file.stat().st_size} bytes)")
        print(f"  2. İşlem Günlüğü:  {trader.log_file} (Boyut: {trader.log_file.stat().st_size} bytes)")

        # Dosya içeriklerini doğrula
        with open(trader.portfolio_file, "r", encoding="utf-8") as f:
            saved_portfolio = json.load(f)
        assert len(saved_portfolio["positions"]) == 10, "Portföyde 10 hisse yok!"

        df_log = pd.read_csv(trader.log_file)
        print(f"\n📄 {trader.log_file.name} DOSYASININ GÜNCEL SATIRI:")
        print("-" * 105)
        print(df_log.tail(1).to_string(index=False))
        print("-" * 105)

        print("\n✅ ADIM C BAŞARIYLA GEÇTİ (Sıfır Hata).")

    except Exception as e:
        print(f"❌ ADIM C HATASI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 115)
    print("🏆 UÇTAN UCA ENTEGRASYON TESTİ EKSİKSİZ VE HATASIZ TAMAMLANDI.")
    print("=" * 115)


if __name__ == "__main__":
    main()
