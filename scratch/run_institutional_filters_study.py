"""
scratch/run_institutional_filters_study.py
==========================================
ÜÇ KURUMSAL PORTFÖY FİLTRESİ VE KOMBİNASYONU TESTİ
--------------------------------------------------
Referans Sistem (Baseline):
  - K=10, H=60g Sabit Çeyreklik Rotasyon + %25 Portföy Drawdown Devre Kesici
  - Eşit Ağırlık (%10 her hisse)
  - Net CAGR: %44.2 | Sharpe: 1.26 | Sortino: 1.87 | Max DD: %-28.0 | Turnover: %164.8 | p = 0.050

Test Edilen Kurumsal Filtreler:
  1. Sektörel Tavan (Sector Cap = 3): Top-10'da aynı sektörden en fazla 3 hisse
  2. Değer Tuzağı Filtresi: Price > SMA_200 (Düşen bıçak engelleme)
  3. Ters Volatilite Ağırlıklandırması: w_i proportional to 1 / sigma_60
  4. Kombine Sistem: Üç filtrenin aynı anda uygulanması

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
import config as cfg

from scratch.run_faz_c_walk_forward_test import yukle_veriler

TRANSACTION_COST = 0.003  # %0.30 round-trip (15 bps alım + 15 bps satım)
RF_ANNUAL = 0.18
LOCKBOX_BARRIER = pd.Timestamp("2025-05-31")


def select_portfolio_basket(t, ranked_symbols, df_prices_train, daily_returns_df,
                            use_sector_cap=False, max_sector_count=3,
                            use_value_trap=False,
                            use_inv_vol=False, k_val=10):
    """
    Belirli bir rebalance tarihinde kurumsal filtreleri uygulayarak Top-K sepetini
    ve hisse ağırlıklarını belirler.
    """
    selected_symbols = []
    sector_counts = {}

    for s in ranked_symbols:
        if len(selected_symbols) >= k_val:
            break

        # 1. Değer Tuzağı Filtresi (Price > SMA_200)
        if use_value_trap:
            p_series = df_prices_train.loc[:t, s].dropna()
            if len(p_series) >= 200:
                sma_200 = p_series.iloc[-200:].mean()
                if p_series.iloc[-1] <= sma_200:
                    continue  # 200 günlük ortalamasının altında, pas geç
            elif len(p_series) >= 50:
                # 200 günden az geçmişi varsa eldeki ortalamayı kullan
                if p_series.iloc[-1] <= p_series.mean():
                    continue

        # 2. Sektörel Tavan Kısıtı (Max 3 hisse / sektör)
        if use_sector_cap:
            sektor = cfg.HISSE_SEKTOR.get(s, "XUSIN.IS")
            if sector_counts.get(sektor, 0) >= max_sector_count:
                continue  # Sektör kotası dolu, pas geç
            sector_counts[sektor] = sector_counts.get(sektor, 0) + 1

        selected_symbols.append(s)

    # Eğer filtreler yüzünden 10 hisse tamamlanamadıysa, eksikleri sıralamadaki kalanlardan doldur
    if len(selected_symbols) < k_val:
        for s in ranked_symbols:
            if s not in selected_symbols:
                selected_symbols.append(s)
                if len(selected_symbols) >= k_val:
                    break

    # 3. Ağırlıklandırma: Ters Volatilite vs Eşit Ağırlık
    if use_inv_vol:
        vols = []
        for s in selected_symbols:
            r_series = daily_returns_df.loc[:t, s].iloc[-60:].dropna()
            vol = float(r_series.std(ddof=1)) if len(r_series) >= 20 else 0.02
            vols.append(max(vol, 0.005))
        vols = np.array(vols)
        inv_v = 1.0 / vols
        weights = inv_v / np.sum(inv_v)
        weights_dict = {s: float(w) for s, w in zip(selected_symbols, weights)}
    else:
        eq_w = 1.0 / float(len(selected_symbols))
        weights_dict = {s: eq_w for s in selected_symbols}

    return selected_symbols, weights_dict


def run_filter_simulation(use_sector_cap, use_value_trap, use_inv_vol,
                          k_val, h_days, trading_days, df_prices_train, daily_returns_df, rankings_cache,
                          dd_trigger=-0.25, dd_recover=-0.15):
    """
    Belirli filtre kombinasyonu ile 60 günlük sabit tutma + %25 portföy devre kesici simülasyonu.
    """
    n_days = len(trading_days)
    reb_indices = set(range(0, n_days, h_days))

    daily_net = []
    daily_gross = []
    turnover_list = []

    equity = 1.0
    peak_equity = 1.0
    w_portfolio_equity = 1.0  # %100 veya %50
    current_weights = {}

    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    for day_i in range(n_days):
        t = trading_days[day_i]
        cost_today = 0.0

        # Rebalance Günü (Her 60 günde bir)
        if day_i in reb_indices:
            ranked_list = rankings_cache[t]["ranked_symbols"]
            new_symbols, new_weights = select_portfolio_basket(
                t, ranked_list, df_prices_train, daily_returns_df,
                use_sector_cap=use_sector_cap, use_value_trap=use_value_trap,
                use_inv_vol=use_inv_vol, k_val=k_val
            )

            # Turnover hesabı (Ağırlık farklarının mutlak toplamının yarısı)
            if len(current_weights) == 0:
                turnover = 1.0
            else:
                all_keys = set(current_weights.keys()).union(set(new_weights.keys()))
                diff_sum = sum([abs(new_weights.get(k, 0.0) - current_weights.get(k, 0.0)) for k in all_keys])
                turnover = diff_sum / 2.0

            turnover_list.append(turnover * w_portfolio_equity)
            cost_today += turnover * w_portfolio_equity * TRANSACTION_COST
            current_weights = new_weights

        # Günlük Getiri Hesabı (Hisse ağırlıklı ortalama + Nakit faizi)
        stock_ret_weighted = 0.0
        for s, w in current_weights.items():
            r_s = daily_returns_df.loc[t, s] if (s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])) else 0.0
            stock_ret_weighted += w * r_s

        r_gross = w_portfolio_equity * stock_ret_weighted + (1.0 - w_portfolio_equity) * rf_daily
        r_net = r_gross - cost_today

        daily_gross.append(r_gross)
        daily_net.append(r_net)

        # Sermaye ve Drawdown Takibi
        equity *= (1.0 + r_net)
        if equity > peak_equity:
            peak_equity = equity
        dd = (equity - peak_equity) / peak_equity

        # %25 Portföy Drawdown Devre Kesici
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


def run_placebo_for_filter(use_sector_cap, use_value_trap, use_inv_vol,
                           k_val, h_days, trading_days, df_prices_train, daily_returns_df, rankings_cache, n_seeds=100):
    """
    100 Tohumlu Monte Carlo Placebo Testi (İlgili filtre kuralları altında).
    """
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
        current_weights = {}

        for day_i in range(n_days):
            t = trading_days[day_i]
            cost_today = 0.0

            if day_i in reb_indices:
                univ = list(rankings_cache[t]["universe"])
                # Rastgele sıralanmış evren
                shuffled_univ = rng.permutation(univ).tolist()
                new_symbols, new_weights = select_portfolio_basket(
                    t, shuffled_univ, df_prices_train, daily_returns_df,
                    use_sector_cap=use_sector_cap, use_value_trap=use_value_trap,
                    use_inv_vol=use_inv_vol, k_val=k_val
                )
                if len(current_weights) == 0:
                    turn = 1.0
                else:
                    all_keys = set(current_weights.keys()).union(set(new_weights.keys()))
                    turn = sum([abs(new_weights.get(k, 0.0) - current_weights.get(k, 0.0)) for k in all_keys]) / 2.0

                cost_today += turn * w_portfolio_equity * TRANSACTION_COST
                current_weights = new_weights

            stock_ret_weighted = 0.0
            for s, w in current_weights.items():
                r_s = daily_returns_df.loc[t, s] if (s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])) else 0.0
                stock_ret_weighted += w * r_s

            r_gross = w_portfolio_equity * stock_ret_weighted + (1.0 - w_portfolio_equity) * rf_daily
            r_net = r_gross - cost_today
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
    print("ÜÇ KURUMSAL PORTFÖY FİLTRESİ VE KOMBİNASYONU ANALİZİ")
    print("Kapsam: SADECE EĞİTİM PENCERESİ (2018-09-03 -> 2025-05-30, 1682 İşlem Günü)")
    print("KİLİT KUTU (2025-06-01 -> 2026-09-07) VERİSİNE KESİNLİKLE DOKUNULMAZ / KÖRDÜR.")
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

    # 1. REFERANS SİSTEM (Baseline)
    ref_net, ref_gross, ref_turn = run_filter_simulation(
        use_sector_cap=False, use_value_trap=False, use_inv_vol=False,
        k_val=10, h_days=60, trading_days=trading_days,
        df_prices_train=df_prices_train, daily_returns_df=daily_returns_df, rankings_cache=rankings_cache
    )
    ref_met = evaluate_daily(ref_net, rf_daily)
    ref_sh_turn = ref_met["sharpe"] / max(ref_turn, 0.1)

    scenarios = [
        ("REFERANS (Mevcut Sistem: Eşit Ağırlık, Filtresiz)", False, False, False),
        ("Filtre 1: Sektörel Tavan (Sector Cap = 3)", True, False, False),
        ("Filtre 2: Değer Tuzağı (Price > SMA_200)", False, True, False),
        ("Filtre 3: Ters Volatilite (w proportional to 1/sigma)", False, False, True),
        ("Kombine: 3 Filtre Birlikte (Sektör + SMA200 + TersVol)", True, True, True),
    ]

    results = []

    print("\n" + "=" * 125)
    print(f"{'Senaryo / Portföy Mimarisi':<42} | {'Net CAGR':<9} | {'Net Sharpe':<11} | {'Sortino':<8} | {'Max DD':<9} | {'Turnover':<10} | {'Sharpe/Turn':<11} | {'Placebo p':<10}")
    print("-" * 125)

    for label, sec_cap, val_trap, inv_vol in scenarios:
        t0 = time.perf_counter()
        net_d, gross_d, turn = run_filter_simulation(
            use_sector_cap=sec_cap, use_value_trap=val_trap, use_inv_vol=inv_vol,
            k_val=10, h_days=60, trading_days=trading_days,
            df_prices_train=df_prices_train, daily_returns_df=daily_returns_df, rankings_cache=rankings_cache
        )
        met = evaluate_daily(net_d, rf_daily)
        sh_turn = met["sharpe"] / max(turn, 0.1)

        # 100 tohumlu placebo testi
        plac_sharpes = run_placebo_for_filter(
            sec_cap, val_trap, inv_vol, 10, 60, trading_days, df_prices_train, daily_returns_df, rankings_cache, 100
        )
        p_val = float(np.mean([1 if ps >= met["sharpe"] else 0 for ps in plac_sharpes]))

        results.append({
            "label": label, "met": met, "turnover": turn, "sh_turn": sh_turn, "p_val": p_val
        })

        print(f"{label:<42} | %{met['cagr_net']*100:>7.1f} | {met['sharpe']:>11.2f} | {met['sortino']:>8.2f} | %{met['max_dd']*100:>7.1f} | %{turn*100:>8.1f} | {sh_turn:>11.2f} | p = {p_val:.3f}")

    print("=" * 125)

    # İstatistiksel Anlamlılık ve Kurumsal Karşılaştırma
    print("\n" + "=" * 105)
    print("KURUMSAL PORTFÖY FİLTRELERİ DEĞERLENDİRME ÖZETİ (REFERANS = SHARPE 1.26, MAX DD -%28.0)")
    print("=" * 105)
    for r in results[1:]:
        delta_sh = r["met"]["sharpe"] - ref_met["sharpe"]
        delta_dd = r["met"]["max_dd"] - ref_met["max_dd"]
        delta_cagr = r["met"]["cagr_net"] - ref_met["cagr_net"]
        print(f"👉 {r['label']}:")
        print(f"   ΔSharpe: {delta_sh:+.2f} | ΔMax DD: {delta_dd*100:+.1f} puan | ΔCAGR: {delta_cagr*100:+.1f} puan | Placebo p = {r['p_val']:.3f}")
        
        if delta_sh >= 0.15 and delta_dd >= 0:
            print("   --> HÜKÜM: GÜÇLÜ KATKI SAĞLADI.")
        elif delta_sh > 0:
            print("   --> HÜKÜM: HAFİF MARJİNAL İYİLEŞME (İstatistiksel anlamlılık sınırı altında).")
        else:
            print("   --> HÜKÜM: PERFORMANSI AŞINDIRDI VEYA KATKI SAĞLAMADI.")
        print("-" * 80)


if __name__ == "__main__":
    main()
