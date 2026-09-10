"""
scratch/run_exit_triggers_study.py
==================================
SİNYAL TAKİPLİ KADEMELİ ÇIKIŞ (TAKE-PROFIT & STOP-LOSS) ÇALIŞMASI
-----------------------------------------------------------------
Mevcut Sistem (Referans):
  - K=10, H=60g Sabit Çeyreklik Rotasyon + %25 Portföy Drawdown Devre Kesici
  - Net CAGR: %44.2 | Sharpe: 1.26 | Sortino: 1.87 | Max DD: %-28.0 | Turnover: %164.8 | p = 0.050

Test Edilen Bireysel Çıkış Tetikleyicileri:
  - Tetikleyici 1: Sinyal Çıkışı (Model 60g sonunda Top-10 dışına düşürürse çıkış)
  - Tetikleyici 2: Kâr Koruma (+%X kazançta pozisyonun yarısını realize et, %10 -> %5)
  - Tetikleyici 3: Zarar Kesme (-%Y kayıpta nakite çık, çeyrek sonuna kadar nakitte bekle)

Eşitlik Matrisi: 5x5 = 25 Kombinasyon
  - Kâr Koruma (X): +%15, +%20, +%25, +%30, +%40
  - Zarar Kesme (Y): -%12, -%15, -%18, -%20, -%25

Kapsam: SADECE EĞİTİM PENCERESİ (2018-09-03 -> 2025-05-30, 1682 İşlem Günü)
Kilit Kutu (2025-06-01 -> 2026-09-07) VERİSİNE KESİNLİKLE DOKUNULMAZ / KÖRDÜR.
"""

import sys
import time
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

from scratch.run_faz_c_walk_forward_test import yukle_veriler

TRANSACTION_COST = 0.003  # %0.30 round-trip (15 bps buy + 15 bps sell)
RF_ANNUAL = 0.18
LOCKBOX_BARRIER = pd.Timestamp("2025-05-31")


def run_strategy_with_triggers(tp_pct, sl_pct, k_val, h_days, trading_days, daily_returns_df, rankings_cache,
                               dd_trigger=-0.25, dd_recover=-0.15):
    """
    K=10, H=60g + %25 Portföy DD Kontrolü + Bireysel Hissede Kâr Koruma (+%X) ve Zarar Kesme (-%Y).
    """
    n_days = len(trading_days)
    reb_indices = set(range(0, n_days, h_days))

    daily_net = []
    daily_gross = []
    turnover_list = []

    equity = 1.0
    peak_equity = 1.0
    w_portfolio_equity = 1.0  # Portföy devre kesici katsayısı (%100 veya %50)

    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    # positions: dict of sembol -> {
    #   "weight": float (0.10, 0.05, or 0.0),
    #   "entry_price_idx": int,
    #   "cum_ret_since_entry": float,
    #   "half_taken": bool,
    #   "stopped_out": bool
    # }
    positions = {}

    for day_i in range(n_days):
        t = trading_days[day_i]
        cost_today = 0.0

        # 1. 60 Günlük Rebalance Günü
        if day_i in reb_indices:
            target_stocks = rankings_cache[t]["ranked_symbols"][:k_val]
            
            # Eski pozisyonları kapat
            if len(positions) == 0:
                turn = 1.0
            else:
                # Kalan hisseler ile yeni sepet karşılaştırması
                current_active = [s for s, info in positions.items() if not info["stopped_out"]]
                degisen = len(set(target_stocks) - set(current_active))
                turn = degisen / float(k_val)

            turnover_list.append(turn * w_portfolio_equity)
            cost_today += turn * w_portfolio_equity * TRANSACTION_COST

            # Yeni 10 hisseyi başlat (%10 eşit ağırlıkla)
            positions = {}
            for s in target_stocks:
                positions[s] = {
                    "weight": 1.0 / float(k_val),
                    "cum_ret_since_entry": 0.0,
                    "half_taken": False,
                    "stopped_out": False
                }

        # 2. Günlük Getiri ve Bireysel Tetikleyici Kontrolü
        stock_returns_weighted = 0.0
        active_stock_weight = 0.0

        for s, info in list(positions.items()):
            if info["stopped_out"]:
                # Stop olduysa bu hisse çeyrek sonuna kadar nakitte (rf) kalır
                continue

            r_s = daily_returns_df.loc[t, s] if (s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])) else 0.0
            
            # Alım fiyatından kümülatif getiri güncellemesi
            info["cum_ret_since_entry"] = (1.0 + info["cum_ret_since_entry"]) * (1.0 + r_s) - 1.0
            ret_since_entry = info["cum_ret_since_entry"]

            # Günlük getiriye katkı (tetikleyiciden önceki mevcut ağırlıkla)
            stock_returns_weighted += info["weight"] * r_s
            active_stock_weight += info["weight"]

            # --- TETİKLEYİCİ 2: KÂR KORUMA (+%X) ---
            if tp_pct is not None and not info["half_taken"] and ret_since_entry >= tp_pct:
                # Pozisyonun yarısını sat (%10 -> %5)
                sell_w = info["weight"] * 0.5
                info["weight"] -= sell_w
                info["half_taken"] = True
                # İşlem maliyeti ve turnover
                cost_today += sell_w * w_portfolio_equity * TRANSACTION_COST
                turnover_list.append(sell_w * w_portfolio_equity)

            # --- TETİKLEYİCİ 3: ZARAR KESME (-%Y) ---
            if sl_pct is not None and not info["stopped_out"] and ret_since_entry <= -sl_pct:
                # Kalan pozisyonu tamamen sat, çeyrek sonuna kadar nakite çık
                sell_w = info["weight"]
                info["weight"] = 0.0
                info["stopped_out"] = True
                cost_today += sell_w * w_portfolio_equity * TRANSACTION_COST
                turnover_list.append(sell_w * w_portfolio_equity)

        # Portföyün nakitte kalan kısmı (stop olanlar + kârı realize edilenler + kalan boşluk)
        cash_weight = 1.0 - active_stock_weight
        r_gross_portfolio = (stock_returns_weighted + cash_weight * rf_daily)

        # Portföy seviyesinde %25 DD kontrolü ağırlıklandırması
        # w_portfolio_equity = 1.0 (%100) veya 0.5 (%50 hisse + %50 nakit)
        r_port_gross = w_portfolio_equity * r_gross_portfolio + (1.0 - w_portfolio_equity) * rf_daily
        r_port_net = r_port_gross - cost_today

        daily_gross.append(r_port_gross)
        daily_net.append(r_port_net)

        # Portföy sermayesi ve zirve takibi
        equity *= (1.0 + r_port_net)
        if equity > peak_equity:
            peak_equity = equity
        dd = (equity - peak_equity) / peak_equity

        # Portföy Seviyesi Devre Kesici Kontrolü
        if w_portfolio_equity == 1.0 and dd <= dd_trigger:
            w_portfolio_equity = 0.5
            cost_switch = 0.5 * TRANSACTION_COST
            equity *= (1.0 - cost_switch)
            daily_net[-1] -= cost_switch
            turnover_list.append(0.5)
        elif w_portfolio_equity == 0.5 and dd >= dd_recover:
            w_portfolio_equity = 1.0
            cost_switch = 0.5 * TRANSACTION_COST
            equity *= (1.0 - cost_switch)
            daily_net[-1] -= cost_switch
            turnover_list.append(0.5)

    ann_turnover = float(np.sum(turnover_list) * (252.0 / n_days))
    return daily_net, daily_gross, ann_turnover


def evaluate_daily(r_net_list, rf_daily):
    n_days = len(r_net_list)
    r_arr = np.array(r_net_list)
    cum_net = float(np.prod(1.0 + r_arr) - 1.0)
    cagr_net = float((1.0 + cum_net) ** (252.0 / n_days) - 1.0) if cum_net > -0.99 else -0.99

    diff_rf = r_arr - rf_daily
    std_v = float(np.std(r_arr, ddof=1)) if len(r_arr) > 1 else 1e-6
    sharpe = float(np.mean(diff_rf) / (std_v + 1e-8) * np.sqrt(252))

    downside = np.minimum(diff_rf, 0.0)
    down_std = float(np.sqrt(np.mean(downside ** 2)))
    sortino = float(np.mean(diff_rf) / (down_std + 1e-8) * np.sqrt(252))

    equity = np.cumprod(1.0 + r_arr)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.min((equity - peak) / peak))

    return {"cum_net": cum_net, "cagr_net": cagr_net, "sharpe": sharpe, "sortino": sortino, "max_dd": max_dd}


def run_placebo_for_strategy(tp, sl, k_val, h_days, trading_days, daily_returns_df, rankings_cache, n_seeds=100):
    n_days = len(trading_days)
    reb_indices = set(range(0, n_days, h_days))
    rng = np.random.default_rng(42)
    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0
    plac_sharpes = []

    for seed in range(n_seeds):
        daily_net = []
        equity = 1.0
        peak_equity = 1.0
        w_portfolio_equity = 1.0
        positions = {}

        for day_i in range(n_days):
            t = trading_days[day_i]
            cost_today = 0.0

            if day_i in reb_indices:
                univ = rankings_cache[t]["universe"]
                target_stocks = rng.choice(univ, size=k_val, replace=False)
                if len(positions) == 0:
                    turn = 1.0
                else:
                    active = [s for s, inf in positions.items() if not inf["stopped_out"]]
                    turn = len(set(target_stocks) - set(active)) / float(k_val)
                cost_today += turn * w_portfolio_equity * TRANSACTION_COST
                positions = {s: {"weight": 1.0 / k_val, "cum_ret": 0.0, "half_taken": False, "stopped_out": False} for s in target_stocks}

            stock_rets_w = 0.0
            act_w = 0.0
            for s, info in list(positions.items()):
                if info["stopped_out"]:
                    continue
                r_s = daily_returns_df.loc[t, s] if (s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])) else 0.0
                info["cum_ret"] = (1.0 + info["cum_ret"]) * (1.0 + r_s) - 1.0
                ret_e = info["cum_ret"]

                stock_rets_w += info["weight"] * r_s
                act_w += info["weight"]

                if tp is not None and not info["half_taken"] and ret_e >= tp:
                    sell_w = info["weight"] * 0.5
                    info["weight"] -= sell_w
                    info["half_taken"] = True
                    cost_today += sell_w * w_portfolio_equity * TRANSACTION_COST
                if sl is not None and not info["stopped_out"] and ret_e <= -sl:
                    sell_w = info["weight"]
                    info["weight"] = 0.0
                    info["stopped_out"] = True
                    cost_today += sell_w * w_portfolio_equity * TRANSACTION_COST

            cash_w = 1.0 - act_w
            r_gross = stock_rets_w + cash_w * rf_daily
            r_net = w_portfolio_equity * r_gross + (1.0 - w_portfolio_equity) * rf_daily - cost_today
            daily_net.append(r_net)

            equity *= (1.0 + r_net)
            if equity > peak_equity:
                peak_equity = equity
            dd = (equity - peak_equity) / peak_equity

            if w_portfolio_equity == 1.0 and dd <= -0.25:
                w_portfolio_equity = 0.5
                cost_switch = 0.5 * TRANSACTION_COST
                equity *= (1.0 - cost_switch)
                daily_net[-1] -= cost_switch
            elif w_portfolio_equity == 0.5 and dd >= -0.15:
                w_portfolio_equity = 1.0
                cost_switch = 0.5 * TRANSACTION_COST
                equity *= (1.0 - cost_switch)
                daily_net[-1] -= cost_switch

        r_arr = np.array(daily_net)
        diff_rf = r_arr - rf_daily
        sh_p = float(np.mean(diff_rf) / (np.std(r_arr, ddof=1) + 1e-8) * np.sqrt(252))
        plac_sharpes.append(sh_p)

    return plac_sharpes


def main():
    print("=" * 115)
    print("SİNYAL TAKİPLİ KADEMELİ ÇIKIŞ (TAKE-PROFIT & STOP-LOSS) 25 KOMBİNASYON TARAMASI")
    print("Kapsam: SADECE EĞİTİM PENCERESİ (2018-09-03 -> 2025-05-30, 1682 İşlem Günü)")
    print("KİLİT KUTU (2025-06-01 -> 2026-09-07) VERİSİNE KESİNLİKLE DOKUNULMAZ.")
    print("=" * 115)

    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    df_prices = pd.DataFrame(fiyat_dict).sort_index()

    xu_train = seri_xu100[(seri_xu100.index >= "2018-09-03") & (seri_xu100.index <= LOCKBOX_BARRIER)]
    trading_days = xu_train.index
    n_days = len(trading_days)

    df_prices_train = df_prices.reindex(trading_days).ffill()
    daily_returns_df = df_prices_train.pct_change().fillna(0.0)
    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    cache_path = ROOT_DIR / "scratch" / "rankings_cache_2018_2025.joblib"
    rankings_cache = joblib.load(cache_path)

    # 1. REFERANS SİSTEM (Tetikleyicisiz Mevcut Sistem)
    ref_net, ref_gross, ref_turn = run_strategy_with_triggers(
        tp_pct=None, sl_pct=None, k_val=10, h_days=60, trading_days=trading_days,
        daily_returns_df=daily_returns_df, rankings_cache=rankings_cache
    )
    ref_met = evaluate_daily(ref_net, rf_daily)
    ref_sh_turn = ref_met["sharpe"] / max(ref_turn, 0.1)

    print("\n" + "=" * 115)
    print("📌 REFERANS SİSTEM (Tetikleyicisiz Mevcut Sistem: K=10, H=60g, %25 DD Kontrolü)")
    print("=" * 115)
    print(f"Net CAGR: %{ref_met['cagr_net']*100:.1f} | Net Sharpe: {ref_met['sharpe']:.2f} | Sortino: {ref_met['sortino']:.2f} | Max DD: %{ref_met['max_dd']*100:.1f} | Yıllık Turnover: %{ref_turn*100:.1f} | Sharpe/Turnover: {ref_sh_turn:.2f} | Placebo p = 0.050")
    print("=" * 115)

    # 2. 25 KOMBİNASYON TARAMASI
    tp_list = [0.15, 0.20, 0.25, 0.30, 0.40]
    sl_list = [0.12, 0.15, 0.18, 0.20, 0.25]

    results = []

    print("\n" + "=" * 115)
    print(f"{'Kombinasyon (TP / SL)':<24} | {'Net CAGR':<9} | {'Net Sharpe':<11} | {'Sortino':<8} | {'Max DD':<9} | {'Turnover':<10} | {'Sharpe/Turn':<11} | {'Δ Sharpe vs Ref':<15}")
    print("-" * 115)

    for tp in tp_list:
        for sl in sl_list:
            net_r, gross_r, turn = run_strategy_with_triggers(
                tp_pct=tp, sl_pct=sl, k_val=10, h_days=60, trading_days=trading_days,
                daily_returns_df=daily_returns_df, rankings_cache=rankings_cache
            )
            met = evaluate_daily(net_r, rf_daily)
            sh_turn = met["sharpe"] / max(turn, 0.1)
            delta_sh = met["sharpe"] - ref_met["sharpe"]

            combo_label = f"TP +%{int(tp*100)} / SL -%{int(sl*100)}"
            results.append({
                "tp": tp, "sl": sl, "label": combo_label,
                "met": met, "turnover": turn, "sh_turn": sh_turn, "delta_sh": delta_sh
            })

            print(f"{combo_label:<24} | %{met['cagr_net']*100:>7.1f} | {met['sharpe']:>11.2f} | {met['sortino']:>8.2f} | %{met['max_dd']*100:>7.1f} | %{turn*100:>8.1f} | {sh_turn:>11.2f} | {delta_sh:>+14.2f}")

    # En iyi 3 adayı sırala (Net Sharpe'a göre)
    sorted_res = sorted(results, key=lambda x: x["met"]["sharpe"], reverse=True)
    best_candidate = sorted_res[0]

    print("\n" + "=" * 115)
    print(f"🏆 25 KOMBİNASYON İÇİNDEN EN İYİ GÖRÜNEN: {best_candidate['label']}")
    print("=" * 115)
    print(f"Net CAGR: %{best_candidate['met']['cagr_net']*100:.1f} (Ref: %{ref_met['cagr_net']*100:.1f})")
    print(f"Net Sharpe: {best_candidate['met']['sharpe']:.2f} (Ref: {ref_met['sharpe']:.2f}, Fark: {best_candidate['delta_sh']:+.2f})")
    print(f"Sortino: {best_candidate['met']['sortino']:.2f} (Ref: {ref_met['sortino']:.2f})")
    print(f"Max DD: %{best_candidate['met']['max_dd']*100:.1f} (Ref: %{ref_met['max_dd']*100:.1f})")
    print(f"Turnover: %{best_candidate['turnover']*100:.1f} (Ref: %{ref_turn*100:.1f})")
    print(f"Sharpe / Turnover: {best_candidate['sh_turn']:.2f} (Ref: {ref_sh_turn:.2f})")

    # 3. EN İYİ ADAY İÇİN 100 TOHUMLU PLACEBO TESTİ VE BONFERRONI DEĞERLENDİRMESİ
    print("\n" + "-" * 90)
    print(f"En İyi Aday ({best_candidate['label']}) için 100 Tohumlu Monte Carlo Placebo Testi çalıştırılıyor...")
    plac_best = run_placebo_for_strategy(
        best_candidate["tp"], best_candidate["sl"], 10, 60, trading_days, daily_returns_df, rankings_cache, 100
    )
    p_best = float(np.mean([1 if ps >= best_candidate["met"]["sharpe"] else 0 for ps in plac_best]))
    print(f"En İyi Aday Ham Placebo p-değeri: p = {p_best:.3f}")

    # BONFERRONI DÜZELTMESİ (25 Hipotez Testi)
    # Standart alfa: 0.10 -> Bonferroni eşiği: 0.10 / 25 = 0.004
    # Standart alfa: 0.05 -> Bonferroni eşiği: 0.05 / 25 = 0.002
    bonferroni_threshold_10 = 0.10 / 25.0  # 0.004
    bonferroni_passed = (p_best <= bonferroni_threshold_10) and (best_candidate["delta_sh"] >= 0.15)

    print("\n" + "=" * 90)
    print("KURUMSAL KARŞILAŞTIRMA VE HÜKÜM PROTOKOLÜ")
    print("=" * 90)
    print(f"Referans Sistem Sharpe:                {ref_met['sharpe']:.2f}")
    print(f"En İyi Tetikleyici Sharpe:             {best_candidate['met']['sharpe']:.2f} (ΔSharpe = {best_candidate['delta_sh']:+.2f}, Eşik: >= +0.15)")
    print(f"Ham Placebo p-değeri:                  p = {p_best:.3f}")
    print(f"Bonferroni p Eşiği (α=0.10 / 25 test): p <= {bonferroni_threshold_10:.4f}")
    print(f"Bonferroni Düzeltmesi Geçti mi?:       {'GEÇTİ' if bonferroni_passed else 'KALDI (ANLAMSIZ / RED)'}")
    print("-" * 90)
    
    if not bonferroni_passed:
        print("HÜKÜM: Tetikleyici eklemek mevcut sisteme anlamlı katkı sağlamıyor.")
    else:
        print(f"HÜKÜM: {best_candidate['label']} kombinasyonu istatistiksel eşikleri aşmıştır.")
    print("=" * 90)


if __name__ == "__main__":
    main()
