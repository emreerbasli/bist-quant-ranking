"""
scratch/faz0_taban_backtest.py
==============================
FAZ 0: ARDIŞIK TABAN FİLTRESİ GEÇMİŞ VERİ TESTİ (2018-09 -> 2025-05)
---------------------------------------------------------------------
Amaç:
  "Son 10 işlem gününde >= 5 kez <= -%9.5 kapanış" kuralının model
  performansına etkisini ampirik olarak test etmek.

Senaryolar:
  (a) "Giriş Engelleme": Aday, taban kuralına takılıyorsa Top-K sepetine hiç alınmaz.
  (b) "Acil Çıkış": Portföyde bulunan bir hisse, 60 gün tutma kuralına bakılmaksızın
      taban kuralına takıldığı an portföyden çıkarılır (PASEU tipi çöküş koruması).
  (a+b) "Kombine": Hem giriş engelleme hem de portföydeyken acil çıkış birlikte uygulanır.

Değerlendirme:
  - K=10 ve K=15 için ayrı ayrı Sharpe, CAGR, Max DD ve vaka sayısı
  - Karar kuralı: Filtreli Sharpe < Filtresiz - 0.05 ise filtre zararlı (soft warning),
                  fark <= 0.05 ise hard exclusion onaylanır.
  - Sadece Eğitim Penceresi: 2018-09-03 -> 2025-05-30 (1682 İşlem Günü).
"""

import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import joblib

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

from scratch.run_faz_c_walk_forward_test import yukle_veriler
from scratch.run_institutional_filters_study import evaluate_daily

RF_ANNUAL = 0.18
TRANSACTION_COST = 0.003  # %0.30 round-trip (15 bps alım + 15 bps satım)
LOCKBOX_BARRIER = pd.Timestamp("2025-05-31")
TABAN_RETURN_THRESHOLD = -0.095  # Günlük yüzde değişim <= -%9.5 (BIST taban barı)
TABAN_ROLLING_WINDOW = 10        # Son 10 işlem günü
TABAN_MIN_COUNT = 5             # En az 5 kez taban kapanış


def main():
    print("=" * 115)
    print("FAZ 0: ARDIŞIK TABAN KURALLI PORTFÖY BACKTESTİ (2018-09-03 -> 2025-05-30)")
    print("Kural: Son 10 işlem gününde >= 5 kez <= -%9.5 kapanış")
    print("=" * 115)

    # 1. Verileri Yükle
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    df_prices = pd.DataFrame(fiyat_dict).sort_index()

    xu_train = seri_xu100[(seri_xu100.index >= "2018-09-03") & (seri_xu100.index <= LOCKBOX_BARRIER)]
    trading_days = xu_train.index
    n_days = len(trading_days)

    df_prices_train = df_prices.reindex(trading_days).ffill()
    daily_returns_df = df_prices_train.pct_change().fillna(0.0)
    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    cache_path = ROOT_DIR / "scratch" / "rankings_cache_2018_2025.joblib"
    if not cache_path.exists():
        raise FileNotFoundError(f"Sıralama önbelleği bulunamadı: {cache_path}")
    rankings_cache = joblib.load(cache_path)

    # 2. Taban Göstergesi Matrisi (BIST Tüm Evren)
    is_taban = (daily_returns_df <= TABAN_RETURN_THRESHOLD)
    taban_count_10d = is_taban.rolling(TABAN_ROLLING_WINDOW, min_periods=1).sum()
    taban_triggered = (taban_count_10d >= TABAN_MIN_COUNT)

    # Evren geneli vaka analizi
    total_trigger_events = int(taban_triggered.sum().sum())
    trigger_stocks_all = taban_triggered.columns[taban_triggered.any()].tolist()
    yearly_counts = taban_triggered.groupby(taban_triggered.index.year).sum().sum(axis=1)

    print("\n" + "-" * 80)
    print("EVREN GENELİ (88 HİSSE) TABAN KURALI VAKA ANALİZİ (2018 - 2025):")
    print(f"  Toplam hisse-gün kural tetiklenme sayısı: {total_trigger_events}")
    print(f"  Kurala takılan tekil hisse sayısı: {len(trigger_stocks_all)} -> {trigger_stocks_all}")
    print("  Yıl yıl dağılım:")
    for yr, cnt in yearly_counts.items():
        print(f"    {yr}: {int(cnt)} hisse-gün tetiklenmesi")
    print("-" * 80)

    # 3. Simülasyon Motoru
    def run_simulation(k_val: int, h_days: int = 60,
                       filter_entry: bool = False,
                       filter_exit: bool = False):
        reb_indices = set(range(0, n_days, h_days))
        daily_net = []
        turnover_list = []
        equity = 1.0
        peak_equity = 1.0
        w_portfolio_equity = 1.0

        positions = {}
        # Log tutma
        entry_exclusions = []
        emergency_exits = []

        for day_i in range(n_days):
            t = trading_days[day_i]
            cost_today = 0.0

            # --- A. 60 Günlük Rebalance Günü ---
            if day_i in reb_indices:
                ranked_symbols = rankings_cache[t]["ranked_symbols"]
                selected = []
                for s in ranked_symbols:
                    if filter_entry and taban_count_10d.loc[t, s] >= TABAN_MIN_COUNT:
                        entry_exclusions.append((t.strftime("%Y-%m-%d"), s, int(taban_count_10d.loc[t, s])))
                        continue  # Giriş engellendi
                    selected.append(s)
                    if len(selected) >= k_val:
                        break

                # Eğer filtre yüzünden tamamlanamadıysa kalanlardan doldur
                if len(selected) < k_val:
                    for s in ranked_symbols:
                        if s not in selected:
                            selected.append(s)
                            if len(selected) >= k_val:
                                break

                # Turnover hesabı
                if len(positions) == 0:
                    turn = 1.0
                else:
                    active_prev = [s for s, inf in positions.items() if not inf["stopped"]]
                    degisen = len(set(selected) - set(active_prev))
                    turn = degisen / float(k_val)

                turnover_list.append(turn * w_portfolio_equity)
                cost_today += turn * w_portfolio_equity * TRANSACTION_COST

                positions = {s: {"weight": 1.0 / float(k_val), "stopped": False, "entry_date": t} for s in selected}

            # --- B. Günlük Getiri ve Acil Çıkış Takibi ---
            stock_ret_weighted = 0.0
            active_stock_weight = 0.0

            for s, inf in list(positions.items()):
                if inf["stopped"]:
                    continue

                r_s = daily_returns_df.loc[t, s] if s in daily_returns_df.columns else 0.0
                stock_ret_weighted += inf["weight"] * r_s
                active_stock_weight += inf["weight"]

                # Acil Çıkış Tetikleyicisi
                if filter_exit and taban_count_10d.loc[t, s] >= TABAN_MIN_COUNT:
                    emergency_exits.append((t.strftime("%Y-%m-%d"), s, int(taban_count_10d.loc[t, s])))
                    sell_w = inf["weight"]
                    inf["weight"] = 0.0
                    inf["stopped"] = True
                    # Çıkış işlem maliyeti
                    cost_today += sell_w * w_portfolio_equity * TRANSACTION_COST
                    turnover_list.append(sell_w * w_portfolio_equity)

            cash_weight = max(0.0, 1.0 - active_stock_weight)
            r_gross = w_portfolio_equity * (stock_ret_weighted + cash_weight * rf_daily) + (1.0 - w_portfolio_equity) * rf_daily
            r_net = r_gross - cost_today
            daily_net.append(r_net)

            # Sermaye ve DD Devre Kesici
            equity *= (1.0 + r_net)
            if equity > peak_equity:
                peak_equity = equity
            dd = (equity - peak_equity) / peak_equity

            if w_portfolio_equity == 1.0 and dd <= -0.25:
                w_portfolio_equity = 0.5
                cost_switch = 0.5 * TRANSACTION_COST
                equity *= (1.0 - cost_switch)
                daily_net[-1] -= cost_switch
                turnover_list.append(0.5)
            elif w_portfolio_equity == 0.5 and dd >= -0.15:
                w_portfolio_equity = 1.0
                cost_switch = 0.5 * TRANSACTION_COST
                equity *= (1.0 - cost_switch)
                daily_net[-1] -= cost_switch
                turnover_list.append(0.5)

        met = evaluate_daily(daily_net, rf_daily)
        ann_turn = float(np.sum(turnover_list) * (252.0 / n_days))
        met["turnover"] = ann_turn
        return met, entry_exclusions, emergency_exits

    # 4. K=10 ve K=15 Testlerinin İcrası
    results = {}
    for k in [10, 15]:
        base_met, _, _ = run_simulation(k, 60, filter_entry=False, filter_exit=False)
        a_met, a_entries, _ = run_simulation(k, 60, filter_entry=True, filter_exit=False)
        b_met, _, b_exits = run_simulation(k, 60, filter_entry=False, filter_exit=True)
        ab_met, ab_entries, ab_exits = run_simulation(k, 60, filter_entry=True, filter_exit=True)

        results[k] = {
            "base": base_met,
            "senaryo_a": (a_met, a_entries),
            "senaryo_b": (b_met, b_exits),
            "senaryo_ab": (ab_met, ab_entries, ab_exits)
        }

    # 5. Raporlama
    print("\n" + "=" * 125)
    print(f"{'K':<5} | {'Senaryo':<30} | {'CAGR (%)':<10} | {'Sharpe':<10} | {'ΔSharpe':<10} | {'Max DD (%)':<12} | {'Turnover (%)':<14} | {'Vaka':<6} | {'Karar'}")
    print("-" * 125)

    for k in [10, 15]:
        b = results[k]["base"]
        print(f"K={k:<3} | {'V3-Kontrol (Filtresiz)':<30} | %{b['cagr_net']*100:>7.2f} | {b['sharpe']:>8.4f} | {'REF':>8} | %{b['max_dd']*100:>10.2f} | %{b['turnover']*100:>12.1f} | {'-':>4} | REFERANS")

        # Senaryo a
        a, a_ent = results[k]["senaryo_a"]
        diff_a = a["sharpe"] - b["sharpe"]
        dec_a = "✅ Hard Exclusion" if diff_a >= -0.05 else "⚠️ Soft Warning"
        print(f"K={k:<3} | {'(a) Giriş Engelleme':<30} | %{a['cagr_net']*100:>7.2f} | {a['sharpe']:>8.4f} | {diff_a:>+8.4f} | %{a['max_dd']*100:>10.2f} | %{a['turnover']*100:>12.1f} | {len(a_ent):>4} | {dec_a}")

        # Senaryo b
        b_res, b_ex = results[k]["senaryo_b"]
        diff_b = b_res["sharpe"] - b["sharpe"]
        dec_b = "✅ Hard Exclusion" if diff_b >= -0.05 else "⚠️ Soft Warning"
        print(f"K={k:<3} | {'(b) Acil Çıkış':<30} | %{b_res['cagr_net']*100:>7.2f} | {b_res['sharpe']:>8.4f} | {diff_b:>+8.4f} | %{b_res['max_dd']*100:>10.2f} | %{b_res['turnover']*100:>12.1f} | {len(b_ex):>4} | {dec_b}")

        # Senaryo ab
        ab, ab_ent, ab_ex = results[k]["senaryo_ab"]
        diff_ab = ab["sharpe"] - b["sharpe"]
        dec_ab = "✅ Hard Exclusion" if diff_ab >= -0.05 else "⚠️ Soft Warning"
        print(f"K={k:<3} | {'(a+b) Giriş + Acil Çıkış':<30} | %{ab['cagr_net']*100:>7.2f} | {ab['sharpe']:>8.4f} | {diff_ab:>+8.4f} | %{ab['max_dd']*100:>10.2f} | %{ab['turnover']*100:>12.1f} | {len(ab_ent)+len(ab_ex):>4} | {dec_ab}")
        print("-" * 125)

    # Detaylı vaka listeleri
    print("\nDETAYLI PORTFÖY VAKA KAYITLARI:")
    for k in [10, 15]:
        print(f"\n--- K={k} Vakaları ---")
        _, a_ent = results[k]["senaryo_a"]
        _, b_ex = results[k]["senaryo_b"]
        print(f"  Senaryo (a) Giriş Engelleme Vakaları ({len(a_ent)} adet):")
        if a_ent:
            for item in a_ent:
                print(f"    Tarih: {item[0]}, Hisse: {item[1]}, Taban Sayısı: {item[2]}")
        else:
            print("    Hiçbir aday Top-K sepetine girerken bu kurala takılmadı (0 vaka).")

        print(f"  Senaryo (b) Acil Çıkış Vakaları ({len(b_ex)} adet):")
        if b_ex:
            # Tekilleştirilmiş çıkış işlemleri
            exited_stocks = set()
            for item in b_ex:
                if item[1] not in exited_stocks:
                    print(f"    Tarih: {item[0]}, Hisse: {item[1]}, Taban Sayısı: {item[2]} (Portföyden acil tasfiye edildi)")
                    exited_stocks.add(item[1])
                else:
                    print(f"    Tarih: {item[0]}, Hisse: {item[1]} (Zaten tasfiye edilmişti, sinyal devam etti)")
        else:
            print("    Portföydeki hiçbir hisse elde tutma süresinde bu kurala takılmadı (0 vaka).")


if __name__ == "__main__":
    main()
