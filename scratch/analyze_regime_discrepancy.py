"""
scratch/analyze_regime_discrepancy.py
=====================================
ALT DÖNEM REJİM KIRILIMI VE PLACEBO P-DEĞERİ PARADOKSU ANALİZİ
-------------------------------------------------------------
Kapsam: SADECE EĞİTİM PENCERESİ (2018-09-03 -> 2025-05-30)
Kilit Kutu (2025-06-01 -> 2026-09-07) VERİSİNE DOKUNULMAZ.

İki Alt Dönem:
  1. Dönem 1 (Erken Dönem: 2018-09-03 -> 2021-12-31) - Pozitif/Nötr Reel Faiz, Yüksek Sermaye Maliyeti
  2. Dönem 2 (Geç Dönem: 2022-01-01 -> 2025-05-30) - Derin Negatif Reel Faiz, Hiperenflasyonist Ralli
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
from scratch.run_alpha_decay_and_turnover_study import evaluate_daily_equity, run_fixed_holding_backtest

TRANSACTION_COST = 0.003
RF_ANNUAL = 0.18
LOCKBOX_BARRIER = pd.Timestamp("2025-05-31")


def run_subperiod_analysis():
    print("=" * 115)
    print("ALT DÖNEM REJİM KIRILIMI VE PLACEBO P-DEĞERİ PARADOKSU")
    print("Eğitim Penceresi: 2018-09-03 -> 2025-05-30 (Kilit Kutu KESİNLİKLE KÖRDÜR)")
    print("=" * 115)

    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    df_prices = pd.DataFrame(fiyat_dict).sort_index()

    xu_train = seri_xu100[(seri_xu100.index >= "2018-09-03") & (seri_xu100.index <= LOCKBOX_BARRIER)]
    trading_days = xu_train.index
    df_prices_train = df_prices.reindex(trading_days).ffill()
    daily_returns_df = df_prices_train.pct_change().fillna(0.0)
    xu_daily = xu_train.pct_change().fillna(0.0).values
    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    # Sıralama önbelleğini yükle
    cache_path = ROOT_DIR / "scratch" / "rankings_cache_2018_2025.joblib"
    rankings_cache = joblib.load(cache_path)

    # İki Alt Dönem Tanımı
    sub_periods = [
        ("TÜM EĞİTİM DÖNEMİ (2018.09 - 2025.05)", "2018-09-03", "2025-05-30"),
        ("DÖNEM 1: Erken / Pozitif Reel Faiz (2018.09 - 2021.12)", "2018-09-03", "2021-12-31"),
        ("DÖNEM 2: Hiperenflasyon / Negatif Reel Faiz (2022.01 - 2025.05)", "2022-01-01", "2025-05-30"),
    ]

    holding_test_list = [5, 21, 60]

    for sub_name, start_d, end_d in sub_periods:
        sub_mask = (trading_days >= start_d) & (trading_days <= end_d)
        sub_days = trading_days[sub_mask]
        sub_xu_daily = xu_daily[sub_mask]
        n_sub = len(sub_days)

        print("\n" + "=" * 115)
        print(f"📊 {sub_name} (İşlem Günü: {n_sub} gün)")
        print("=" * 115)
        print(f"{'Tutma Süresi (H)':<16} | {'Net Getiri':<11} | {'CAGR':<8} | {'Net Sharpe':<11} | {'Max DD':<9} | {'Turnover':<10} | {'Sharpe/Turn':<11} | {'Placebo p (Günlük)':<18} | {'Placebo p (Periyot)':<19}")
        print("-" * 115)

        for h in holding_test_list:
            # 1. Model Simülasyonu
            reb_indices = list(range(0, n_sub, h))
            daily_net = []
            daily_gross = []
            turnover_list = []
            current_portfolio = []
            period_returns = []

            for day_i in range(n_sub):
                t = sub_days[day_i]
                cost_today = 0.0

                if day_i in reb_indices:
                    target_stocks = rankings_cache[t]["ranked_symbols"][:15]
                    if len(current_portfolio) == 0:
                        turnover = 1.0
                    else:
                        degisen = len(set(target_stocks) - set(current_portfolio))
                        turnover = degisen / 15.0

                    turnover_list.append(turnover)
                    cost_today = turnover * TRANSACTION_COST
                    current_portfolio = list(target_stocks)

                day_rets = [daily_returns_df.loc[t, s] for s in current_portfolio if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])]
                r_g = float(np.mean(day_rets)) if len(day_rets) > 0 else 0.0
                r_n = r_g - cost_today

                daily_gross.append(r_g)
                daily_net.append(r_n)

            # Periyot bazlı getiriler (Discrete rebalancing horizon)
            for reb_idx in range(len(reb_indices)):
                i_start = reb_indices[reb_idx]
                i_end = reb_indices[reb_idx + 1] if reb_idx + 1 < len(reb_indices) else n_sub
                p_gross = np.prod([1.0 + daily_gross[d] for d in range(i_start, i_end)]) - 1.0
                cost = turnover_list[reb_idx] * TRANSACTION_COST
                period_returns.append(p_gross - cost)

            met = evaluate_daily_equity(daily_net, daily_gross, sub_xu_daily, rf_daily)
            ann_turnover = float(np.sum(turnover_list) * (252.0 / n_sub))
            sh_turn = met["sharpe"] / max(ann_turnover, 0.1)

            # 2. Placebo Testi (100 Tohum)
            rng = np.random.default_rng(42)
            plac_daily_sharpes = []
            plac_period_sharpes = []

            rf_period = (1.0 + RF_ANNUAL) ** (h / 252.0) - 1.0

            for seed in range(100):
                p_daily_net = []
                p_cur = []
                p_turn_list = []
                p_per_rets = []

                for day_i in range(n_sub):
                    t = sub_days[day_i]
                    c_today = 0.0
                    if day_i in reb_indices:
                        univ = rankings_cache[t]["universe"]
                        target_stocks = rng.choice(univ, size=15, replace=False)
                        if len(p_cur) == 0:
                            turn = 1.0
                        else:
                            turn = len(set(target_stocks) - set(p_cur)) / 15.0
                        p_turn_list.append(turn)
                        c_today = turn * TRANSACTION_COST
                        p_cur = list(target_stocks)

                    d_rets = [daily_returns_df.loc[t, s] for s in p_cur if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])]
                    r_g_p = float(np.mean(d_rets)) if len(d_rets) > 0 else 0.0
                    p_daily_net.append(r_g_p - c_today)

                # Günlük Sharpe
                r_arr = np.array(p_daily_net)
                std_v = float(np.std(r_arr, ddof=1)) if len(r_arr) > 1 else 1e-6
                sh_d = float(np.mean(r_arr - rf_daily) / (std_v + 1e-8) * np.sqrt(252))
                plac_daily_sharpes.append(sh_d)

                # Periyot Sharpe (Lockbox stili discrete returns)
                for reb_idx in range(len(reb_indices)):
                    i_start = reb_indices[reb_idx]
                    i_end = reb_indices[reb_idx + 1] if reb_idx + 1 < len(reb_indices) else n_sub
                    p_per = float(np.prod([1.0 + p_daily_net[d] for d in range(i_start, i_end)]) - 1.0)
                    p_per_rets.append(p_per)
                
                # Periyot bazlı Sharpe
                p_per_arr = np.array(p_per_rets)
                rf_per = (1.0 + RF_ANNUAL) ** (h / 252.0) - 1.0
                std_per = float(np.std(p_per_arr, ddof=1)) if len(p_per_arr) > 1 else 1e-6
                sh_p_per = float(np.mean(p_per_arr - rf_per) / (std_per + 1e-8) * np.sqrt(252.0 / h))
                plac_period_sharpes.append(sh_p_per)

            p_val_daily = float(np.mean([1 if ps >= met["sharpe"] else 0 for ps in plac_daily_sharpes]))
            mean_plac_sh_daily = float(np.mean(plac_daily_sharpes))

            # Model periyot Sharpe
            model_per_arr = np.array(period_returns)
            rf_per = (1.0 + RF_ANNUAL) ** (h / 252.0) - 1.0
            std_model_per = float(np.std(model_per_arr, ddof=1)) if len(model_per_arr) > 1 else 1e-6
            model_sh_per = float(np.mean(model_per_arr - rf_per) / (std_model_per + 1e-8) * np.sqrt(252.0 / h))
            p_val_per = float(np.mean([1 if ps >= model_sh_per else 0 for ps in plac_period_sharpes]))
            mean_plac_sh_per = float(np.mean(plac_period_sharpes))

            print(f"H = {h:<3} gün       | %{met['cum_net']*100:>9.1f} | %{met['cagr_net']*100:>6.1f} | {met['sharpe']:>9.2f} (pl:{mean_plac_sh_daily:.2f}) | %{met['max_dd']*100:>7.1f} | %{ann_turnover*100:>8.1f} | {sh_turn:>11.2f} | p = {p_val_daily:<8.3f} (ΔSh:{met['sharpe']-mean_plac_sh_daily:+.2f}) | p = {p_val_per:<8.3f} (ΔSh:{model_sh_per-mean_plac_sh_per:+.2f})")


if __name__ == "__main__":
    run_subperiod_analysis()
