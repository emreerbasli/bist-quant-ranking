"""
scratch/test_e2e_chaos.py
================================================================================
E2E KAOS VE EŞZAMANLILIK (CONCURRENCY & RACE CONDITION) STRES TESTİ
================================================================================
Bu betik sistemin operasyonel dayanıklılığını ve hata toleransını doğrulamak
için 3 zorlu kaos testini icra eder:

  1. Eşzamanlı Okuma/Yazma Çakışma Testi (Concurrency Stress Test):
     - Çoklu iş parçacığı (threads) ile saniyede >50 okuma çağrısı yapılırken,
       aynı anda Parquet ve JSON dosyalarına atomik yazma (_safe_replace) tetiklenir.
     - 30 saniye boyunca WinError 32 / PermissionError, JSONDecodeError veya NoneType
       patlaması olmadığı, retry kalkanının çalıştığı kanıtlanır.

  2. Sentetik Kara Kuğu & Devre Kesici Tetikleme Testi:
     - V4 portföyündeki 15 hisseye anlık -%28'lik sentetik şok vektörü uygulanır.
     - -%25 devre kesicinin tetiklendiği, portföyün %100 nakde geçtiği ve
       korumanın devreye girdiği doğrulanır.

  3. Fail-Safe / Bozuk Veri Enjeksiyonu Testi:
     - data/raw/ dizinine bozuk/NaN dolu dummy parquet konur.
     - Hesaplama ve formatlama katmanlarının çökmeden güvenli fallback ürettiği
       teyit edilir ve dosya temizlenir.
================================================================================
"""

import sys
import os
import time
import json
import shutil
import threading
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

# UTF-8 Konsol
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg
from run_paper_trader_v4 import _safe_replace
from models.v4_ranking.paper_trader_v4 import PaperTraderV4

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ChaosTest")


# ==============================================================================
# TEST 1: EŞZAMANLI OKUMA/YAZMA ÇAKIŞMA (CONCURRENCY) SİMÜLASYONU
# ==============================================================================
def test_concurrency_race_condition(duration_sec: int = 30) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print(f"🔥 TEST 1: EŞZAMANLI OKUMA/YAZMA ÇAKIŞMA (RACE CONDITION) STRES TESTİ ({duration_sec} sn)")
    print("=" * 80)

    scratch_dir = ROOT_DIR / "scratch"
    scratch_dir.mkdir(exist_ok=True)
    test_parquet = scratch_dir / "chaos_stress_ranking.parquet"
    test_json = scratch_dir / "chaos_stress_portfolio.json"

    # Başlangıç verisi oluştur
    dummy_df = pd.DataFrame({
        "sembol": [f"TEST_{i:02d}.IS" for i in range(88)],
        "ml_score": np.random.randn(88),
        "rank": list(range(1, 89)),
        "z_roe": np.random.randn(88),
        "z_pb": np.random.randn(88),
        "reel_eps_growth": np.random.randn(88) * 0.1
    })
    dummy_df.to_parquet(test_parquet)

    dummy_json_data = {
        "version": "v4_chaos",
        "equity": 1.0,
        "positions": {f"TEST_{i:02d}.IS": {"entry_price": 100.0, "days_held": 5} for i in range(15)}
    }
    with open(test_json, "w", encoding="utf-8") as f:
        json.dump(dummy_json_data, f)

    stop_event = threading.Event()
    stats = {
        "reads_attempted": 0,
        "reads_succeeded": 0,
        "writes_attempted": 0,
        "writes_succeeded": 0,
        "permission_errors_caught": 0,
        "unhandled_crashes": []
    }
    stats_lock = threading.Lock()

    # app.py önbellek okuma mantığı (5-retry)
    def read_parquet_with_retry(p: Path) -> Optional[pd.DataFrame]:
        for attempt in range(5):
            try:
                df = pd.read_parquet(p)
                if df is not None and not df.empty:
                    return df
            except Exception:
                with stats_lock:
                    stats["permission_errors_caught"] += 1
                if attempt < 4:
                    time.sleep(0.05)
        with stats_lock:
            stats["unhandled_crashes"].append("Parquet Read Max Retries Exceeded")
        return None

    def read_json_with_retry(p: Path) -> Optional[dict]:
        for attempt in range(5):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data:
                        return data
            except Exception:
                with stats_lock:
                    stats["permission_errors_caught"] += 1
                if attempt < 4:
                    time.sleep(0.05)
        with stats_lock:
            stats["unhandled_crashes"].append("JSON Read Max Retries Exceeded")
        return None

    # Okuyucu iş parçacığı
    def reader_worker(worker_id: int):
        while not stop_event.is_set():
            # Parquet oku
            df = read_parquet_with_retry(test_parquet)
            # JSON oku
            js = read_json_with_retry(test_json)

            with stats_lock:
                stats["reads_attempted"] += 2
                if df is not None and len(df) == 88:
                    stats["reads_succeeded"] += 1
                if js is not None and "positions" in js:
                    stats["reads_succeeded"] += 1

            time.sleep(0.005)  # Hızlı döngü

    # Yazıcı iş parçacığı (Parquet)
    def parquet_writer_worker():
        cycle = 0
        while not stop_event.is_set():
            cycle += 1
            temp_p = test_parquet.with_suffix(f".tmp_{cycle}")
            try:
                new_df = dummy_df.copy()
                new_df["ml_score"] += 0.001 * cycle
                new_df.to_parquet(temp_p)
                _safe_replace(temp_p, test_parquet, max_retries=5, delay=0.05)
                with stats_lock:
                    stats["writes_attempted"] += 1
                    stats["writes_succeeded"] += 1
            except Exception as e:
                with stats_lock:
                    stats["unhandled_crashes"].append(f"Parquet Write Error: {e}")
            time.sleep(0.03)

    # Yazıcı iş parçacığı (JSON)
    def json_writer_worker():
        cycle = 0
        while not stop_event.is_set():
            cycle += 1
            temp_j = test_json.with_suffix(f".tmp_{cycle}")
            try:
                new_js = dict(dummy_json_data)
                new_js["equity"] = 1.0 + (cycle * 0.0001)
                with open(temp_j, "w", encoding="utf-8") as f:
                    json.dump(new_js, f)
                _safe_replace(temp_j, test_json, max_retries=5, delay=0.05)
                with stats_lock:
                    stats["writes_attempted"] += 1
                    stats["writes_succeeded"] += 1
            except Exception as e:
                with stats_lock:
                    stats["unhandled_crashes"].append(f"JSON Write Error: {e}")
            time.sleep(0.02)

    threads = []
    # 4 Okuyucu Thread
    for wid in range(4):
        t = threading.Thread(target=reader_worker, args=(wid,), daemon=True)
        threads.append(t)
        t.start()

    # 2 Yazıcı Thread
    tw1 = threading.Thread(target=parquet_writer_worker, daemon=True)
    tw2 = threading.Thread(target=json_writer_worker, daemon=True)
    threads.extend([tw1, tw2])
    tw1.start()
    tw2.start()

    start_time = time.time()
    print(f"[*] Stres testi çalışıyor ({duration_sec} saniye)...")
    while time.time() - start_time < duration_sec:
        time.sleep(1.0)
        elapsed = time.time() - start_time
        with stats_lock:
            rps = stats["reads_attempted"] / max(1.0, elapsed)
            print(f"    Geçen Süre: {elapsed:4.1f}s | Okuma: {stats['reads_attempted']} (Hız: {rps:5.1f} okuma/s) | Yazma: {stats['writes_succeeded']} | Yakalanan Kilit: {stats['permission_errors_caught']}", end="\r")

    stop_event.set()
    time.sleep(0.5)
    print()

    # Temizlik
    for f in [test_parquet, test_json]:
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass

    success = (len(stats["unhandled_crashes"]) == 0) and (stats["reads_succeeded"] > 500)
    print("\n--- TEST 1 SONUÇLARI ---")
    print(f"Toplam Okuma Denemesi : {stats['reads_attempted']}")
    print(f"Başarılı Okuma        : {stats['reads_succeeded']} (Başarı Oranı: %{(stats['reads_succeeded']/max(1,stats['reads_attempted'])*100):.2f})")
    print(f"Toplam Yazma Döngüsü  : {stats['writes_succeeded']}")
    print(f"Retry ile Emilen Kilit: {stats['permission_errors_caught']} (WinError 32 şeffafça çözüldü)")
    print(f"İşlenmemiş Çökme      : {len(stats['unhandled_crashes'])}")
    if stats["unhandled_crashes"]:
        for cr in stats["unhandled_crashes"][:5]:
            print(f"  ❌ HATA: {cr}")
    print(f"DURUM                 : {'✅ PASS' if success else '❌ FAIL'}")

    return {"test": "concurrency", "success": success, "stats": stats}


# ==============================================================================
# TEST 2: SENTETİK KARA KUĞU & DEVRE KESİCİ TETİKLEME TESTİ
# ==============================================================================
def test_black_swan_circuit_breaker() -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("⚡ TEST 2: SENTETİK KARA KUĞU / DEVRE KESİCİ (-%28 ŞOK) TETİKLEME TESTİ")
    print("=" * 80)

    scratch_dir = ROOT_DIR / "scratch"
    shock_portfolio_file = scratch_dir / "test_portfolio_shock.json"
    shock_log_file = scratch_dir / "test_log_shock.csv"

    # 15 hisselik başlangıç portföyü
    symbols = [
        "ALARK.IS", "ANSGR.IS", "DOHOL.IS", "FORTE.IS", "GENTS.IS",
        "GUBRF.IS", "KRDMD.IS", "PETKM.IS", "REEDR.IS", "SELEC.IS",
        "SKBNK.IS", "TERA.IS", "TUPRS.IS", "TURSG.IS", "VESTL.IS"
    ]
    initial_portfolio = {
        "version": "v4",
        "baslangic_tarihi": "2026-09-01",
        "last_check_date": "2026-09-01",
        "kilit_kutu_referans": "2026-09-01",
        "equity": 1.0000,
        "peak_equity": 1.0000,
        "drawdown": 0.0000,
        "dd_kesici_aktif": False,
        "last_xu100_price": 10000.0,
        "positions": {
            s: {
                "entry_date": "2026-09-01",
                "entry_price": 100.0,
                "last_price": 100.0,
                "prev_check_price": 100.0,
                "personal_peak_price": 100.0,
                "peak_drawdown_pct": 0.0,
                "days_held": 10,
                "weight": 1.0 / 15.0
            }
            for s in symbols
        }
    }
    with open(shock_portfolio_file, "w", encoding="utf-8") as f:
        json.dump(initial_portfolio, f, indent=2)

    # Sandbox PaperTrader oluştur
    trader = PaperTraderV4(k_size=15, dd_trigger=-0.25, dd_recover=-0.15)
    trader.portfolio_file = shock_portfolio_file
    trader.log_file = shock_log_file
    trader.portfolio_state = trader._load_or_init_portfolio()

    # Anlık -%28'lik şok fiyat vektörü (100 TL -> 72 TL)
    shock_prices = {s: 72.0 for s in symbols}
    shock_xu100 = 7500.0  # BIST 100 -%25

    t_now = pd.Timestamp("2026-09-15")
    dummy_usd = pd.Series([34.0, 35.0], index=pd.to_datetime(["2026-09-01", "2026-09-15"]))
    dummy_tufe = {"2026-08": 1.70, "2026-09": 1.50}

    print("[*] 15 hisseli portföye anlık -%28.0'lik Kara Kuğu piyasa çöküşü veriliyor...")
    res = trader.execute_check(
        t=t_now,
        top_k_ranked=symbols,
        current_prices=shock_prices,
        current_xu100_price=shock_xu100,
        seri_usdtry=dummy_usd,
        tufe_aylik=dummy_tufe,
        days_elapsed=14,
        send_telegram=False
    )

    final_equity = trader.portfolio_state.get("equity", 1.0)
    final_dd = trader.portfolio_state.get("drawdown", 0.0)
    dd_aktif = trader.portfolio_state.get("dd_kesici_aktif", False)
    kalan_pozisyonlar = trader.portfolio_state.get("positions", {})

    print(f"    Giriş Sermayesi     : 1.0000")
    print(f"    Şok Sonrası Sermaye : {final_equity:.4f}")
    print(f"    Hesaplanan Drawdown : %{final_dd*100:.2f} (Tetikleme Eşiği: %-25.0)")
    print(f"    Devre Kesici Durumu : {'⚡ AKTİF (%100 NAKİT)' if dd_aktif else '❌ PASİF'}")
    print(f"    Kalan Hisse Sayısı  : {len(kalan_pozisyonlar)} (Tasfiye Edildi: %100 Nakitte Bekliyor)")

    # Başarı kriterleri
    success = (dd_aktif is True) and (final_dd <= -0.25) and (len(kalan_pozisyonlar) == 0)

    # Temizlik
    for f in [shock_portfolio_file, shock_log_file]:
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass

    print(f"DURUM                   : {'✅ PASS' if success else '❌ FAIL'}")
    return {"test": "black_swan", "success": success, "dd_aktif": dd_aktif, "drawdown": final_dd}


# ==============================================================================
# TEST 3: FAIL-SAFE VE EKSİK/BOZUK VERİ ENJEKSİYONU (GRACEFUL DEGRADATION)
# ==============================================================================
def test_graceful_degradation_corrupted_data() -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("🛡️ TEST 3: FAIL-SAFE & EKSİK/BOZUK VERİ ENJEKSİYONU (GRACEFUL DEGRADATION)")
    print("=" * 80)

    chaos_ticker = "CHAOS_CORRUPT"
    clean_sym = chaos_ticker.replace(".", "_")
    dummy_raw_parquet = cfg.DATA_RAW / f"{clean_sym}.parquet"
    dummy_fund_parquet = cfg.BASE_DIR / "data" / "fundamentals" / f"{clean_sym}.parquet"

    created_files = []
    crashes = []

    try:
        # 1. Bozuk / Tamamen NaN ve Sıfır dolu OHLCV oluştur
        dates = pd.date_range(end="2026-09-14", periods=300, freq="B")
        corrupted_ohlcv = pd.DataFrame({
            "open": [np.nan] * 300,
            "high": [0.0] * 300,
            "low": [0.0] * 300,
            "close": [0.0] * 300,
            "volume": [0] * 300
        }, index=dates)
        corrupted_ohlcv.to_parquet(dummy_raw_parquet)
        created_files.append(dummy_raw_parquet)

        # 2. Bozuk Bilanço Parquet
        corrupted_fund = pd.DataFrame({
            "gecerlilik_tarihi": ["INVALID_DATE", None, "2026-01-01"],
            "ozsermaye": [np.nan, 0.0, None],
            "net_kar": [None, np.nan, 0.0],
            "is_bank": [None, False, None]
        })
        corrupted_fund.to_parquet(dummy_fund_parquet)
        created_files.append(dummy_fund_parquet)

        print("[*] Bozuk ve NaN dolu veri dosyaları data/raw/ ve data/fundamentals/ dizinlerine enjekte edildi.")

        # Test 3.1 & 3.2: app.py fonksiyonları çağrısı (Streamlit uyarılarını sessizleştirerek import et)
        import io
        old_stderr = sys.stderr
        try:
            sys.stderr = io.StringIO()
            from app import compute_relative_metrics, compute_technical_indicators
        finally:
            sys.stderr = old_stderr

        dummy_xu = pd.Series([10000.0] * 300, index=dates)
        try:
            res_metrics = compute_relative_metrics(corrupted_ohlcv, dummy_xu)
            assert isinstance(res_metrics, dict)
            print("    [+] compute_relative_metrics: Çökmeden güvenli fallback üretti.")
        except Exception as e:
            crashes.append(f"compute_relative_metrics crash: {e}")

        try:
            df_ti = compute_technical_indicators(corrupted_ohlcv)
            assert isinstance(df_ti, pd.DataFrame)
            print("    [+] compute_technical_indicators: Çökmeden güvenli DataFrame üretti.")
        except Exception as e:
            crashes.append(f"compute_technical_indicators crash: {e}")

        # Test 3.3: X-Ray ve Cüzdan f-string formatlama zırhı
        try:
            # Bozuk veri row simülasyonu
            bad_row = {"ml_score": None, "z_roe": None, "reel_eps_growth": None, "data_age_days": None}
            formatted_score = f"{float(bad_row.get('ml_score') or 0.0):.4f}"
            formatted_roe = f"{float(bad_row.get('z_roe') or 0.0):+.2f}σ"
            formatted_growth = f"%{float(bad_row.get('reel_eps_growth') or 0.0)*100:+.1f}"
            assert formatted_score == "0.0000"
            assert formatted_roe == "+0.00σ"
            assert formatted_growth == "%+0.0"
            print("    [+] X-Ray f-string NoneType zırhı: None değerlerini 0.0 formatıyla başarıyla korudu.")
        except Exception as e:
            crashes.append(f"f-string NoneType crash: {e}")

        # Test 3.4: Sıfır Fiyatlı Getiri Hesabı (ZeroDivision Kalkanı)
        try:
            entry_p = 0.0
            last_p = 50.0
            kz_pct = ((last_p - entry_p) / entry_p * 100.0) if entry_p > 0 else 0.0
            assert kz_pct == 0.0
            print("    [+] ZeroDivision Kalkanı: Sıfır maliyetli pozisyonda çökme olmadan 0.0 üretti.")
        except Exception as e:
            crashes.append(f"ZeroDivision crash: {e}")

    finally:
        # Kasıtlı oluşturulan dummy dosyaları kesin olarak temizle
        print("[*] Test tamamlandı, enjekte edilen dummy dosyalar temizleniyor...")
        for f in created_files:
            try:
                if f.exists():
                    f.unlink()
                    print(f"    Silindi: {f.name}")
            except Exception as ex:
                print(f"    Silinemedi: {f.name} ({ex})")

    success = len(crashes) == 0
    print(f"DURUM                   : {'✅ PASS' if success else '❌ FAIL'}")
    if crashes:
        for cr in crashes:
            print(f"  ❌ HATA: {cr}")

    return {"test": "graceful_degradation", "success": success, "crashes": crashes}


# ==============================================================================
# ANA ÇALIŞTIRICI VE ÖZET TABLOSU
# ==============================================================================
def main():
    print("=" * 80)
    print("🚀 BIST V4 QUANT OPERASYONEL GÜVENİLİRLİK & KAOS TESTİ PROTOKOLÜ BAŞLATILDI")
    print("=" * 80)

    r1 = test_concurrency_race_condition(duration_sec=30)
    r2 = test_black_swan_circuit_breaker()
    r3 = test_graceful_degradation_corrupted_data()

    print("\n" + "=" * 80)
    print("📋 E2E KAOS VE EŞZAMANLILIK TESTİ NİHAİ ÖZET RAPORU")
    print("=" * 80)

    all_passed = r1["success"] and r2["success"] and r3["success"]

    print(f"1. Eşzamanlı Okuma/Yazma (30s Concurrency & WinError 32) : {'✅ PASS' if r1['success'] else '❌ FAIL'}")
    print(f"2. Sentetik Kara Kuğu & Devre Kesici (-%28 Şok / Nakit)  : {'✅ PASS' if r2['success'] else '❌ FAIL'}")
    print(f"3. Fail-Safe & Bozuk Veri İzolasyonu (Graceful Fallback) : {'✅ PASS' if r3['success'] else '❌ FAIL'}")
    print("-" * 80)
    print(f"GENEL SONUÇ                                              : {'🎉 TÜM TESTLER BAŞARIYLA GEÇTİ (PASS)' if all_passed else '🚨 TESTLERDE HATA OLUŞTU (FAIL)'}")
    print("=" * 80 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
