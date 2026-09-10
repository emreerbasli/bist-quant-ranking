"""
scratch/run_alpha_decay_and_turnover_study.py
=============================================
ALFA ÇÜRÜME EĞRİSİ (ALPHA DECAY CURVE) VE KISMİ TURNOVER MİMARİSİ ANALİZİ
------------------------------------------------------------------------
KESİNLİKLE VE SADECE EĞİTİM PENCERESİ: 2018-09-03 -> 2025-05-30
KİLİT KUTU (2025-06-01 -> 2026-09-07) VERİSİNE KESİNLİKLE DOKUNULMAZ / KÖRDÜR.

Dondurulmuş Model: scratch/winning_lgbm_ranker.joblib (Aday 1: Aşırı Muhafazakâr)
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

from scratch.run_faz_c_walk_forward_test import yukle_veriler, hizli_pit, hesapla_mom, getir_tcmb_reel_faiz
from scratch.run_lockbox_evaluation import hesapla_sektor_zscore

TRANSACTION_COST = 0.003  # %0.30 round-trip (15 bps alım + 15 bps satım)
RF_ANNUAL = 0.18          # %18 yıllık risksiz faiz
LOCKBOX_BARRIER = pd.Timestamp("2025-05-31")  # KİLİT KUTU YASAĞI SINIRI


def precompute_all_rankings(trading_days, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik, model, feature_cols):
    """
    Tüm işlem günlerinde veya haftalık günlerde model sıralamalarını önceden hesaplar.
    Sadece 2018-09-03 -> 2025-05-30 arası çalışır.
    """
    print(f"Sıralama matrisi hesaplanıyor (Tarihler: {trading_days[0].strftime('%Y-%m-%d')} -> {trading_days[-1].strftime('%Y-%m-%d')})...")
    hisseler = sorted(fiyat_dict.keys())
    daily_rankings = {}
    
    t_start = time.perf_counter()
    for idx, t in enumerate(trading_days):
        if t > LOCKBOX_BARRIER:
            continue
            
        reel_faiz = getir_tcmb_reel_faiz(t, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

        satirlar = []
        for s in hisseler:
            curr, _ = hizli_pit(pit_bellek, s, t)
            if not curr:
                continue
            is_bank = bool(curr.get("is_bank", False))
            sektor = cfg.HISSE_SEKTOR.get(s, "XBANK.IS" if is_bank else "XUSIN.IS")
            mom = hesapla_mom(fiyat_dict[s], t)
            pb = curr.get("pb", np.nan)
            roe = curr.get("roe", np.nan)
            fcf_v = curr.get("fcf_verim", np.nan)
            net_b = curr.get("net_borc", 0.0) or 0.0
            ebit = curr.get("ebitda", 1.0) or 1.0
            borc_ebitda = -net_b / max(1.0, abs(ebit)) if not is_bank else np.nan

            satirlar.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb
            })

        df = pd.DataFrame(satirlar)
        if len(df) < 20:
            continue

        df["z_fcf"]  = hesapla_sektor_zscore(df, "fcf_v", min_grup=4).fillna(0.0)
        df["z_roe"]  = hesapla_sektor_zscore(df, "roe", min_grup=4).fillna(0.0)
        df["z_mom"]  = hesapla_sektor_zscore(df, "mom", min_grup=4).fillna(0.0)
        df["z_borc"] = hesapla_sektor_zscore(df, "borc_ebitda", min_grup=4).fillna(0.0)
        df["z_pb"]   = -hesapla_sektor_zscore(df, "pb", min_grup=4).fillna(0.0)

        df["reel_faiz"]  = reel_faiz
        df["usd_mom_60"] = mom_60_usd
        df["usd_mom_90"] = mom_90_usd

        X = df[feature_cols]
        df["score"] = model.predict(X)
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
        daily_rankings[t] = {
            "ranked_symbols": df["sembol"].tolist(),
            "scores": df["score"].tolist(),
            "universe": df["sembol"].tolist()
        }

    t_elapsed = time.perf_counter() - t_start
    print(f"Toplam {len(daily_rankings)} rebalance günü için sıralamalar {t_elapsed:.2f} saniyede hesaplandı.")
    return daily_rankings


def evaluate_daily_equity(daily_returns_net, daily_returns_gross, benchmark_daily, rf_daily):
    """
    Günlük getiri serilerinden standart kurumsal metrikleri hesaplar.
    """
    n_days = len(daily_returns_net)
    if n_days < 20:
        return {}

    r_net = np.array(daily_returns_net)
    r_gross = np.array(daily_returns_gross)
    r_bm = np.array(benchmark_daily)

    cum_net = float(np.prod(1.0 + r_net) - 1.0)
    cum_gross = float(np.prod(1.0 + r_gross) - 1.0)
    
    cagr_net = float((1.0 + cum_net) ** (252.0 / n_days) - 1.0) if cum_net > -0.99 else -0.99
    cagr_gross = float((1.0 + cum_gross) ** (252.0 / n_days) - 1.0) if cum_gross > -0.99 else -0.99

    # Sharpe
    diff_rf = r_net - rf_daily
    std_net = float(np.std(r_net, ddof=1)) if len(r_net) > 1 else 1e-6
    sharpe = float(np.mean(diff_rf) / (std_net + 1e-8) * np.sqrt(252))

    # Sortino
    downside = np.minimum(diff_rf, 0.0)
    downside_std = float(np.sqrt(np.mean(downside ** 2)))
    sortino = float(np.mean(diff_rf) / (downside_std + 1e-8) * np.sqrt(252))

    # Max Drawdown
    equity = np.cumprod(1.0 + r_net)
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = float(np.min(dd))

    # Residual Alpha & Beta (CAPM vs XU100)
    var_bm = float(np.var(r_bm, ddof=1))
    cov_bm = float(np.cov(r_net, r_bm)[0, 1]) if var_bm > 1e-8 else 0.0
    beta = cov_bm / var_bm if var_bm > 1e-8 else 1.0
    
    cagr_bm = float((1.0 + np.prod(1.0 + r_bm) - 1.0) ** (252.0 / n_days) - 1.0)
    residual_alpha = cagr_net - (RF_ANNUAL + beta * (cagr_bm - RF_ANNUAL))

    return {
        "cum_net": cum_net, "cum_gross": cum_gross,
        "cagr_net": cagr_net, "cagr_gross": cagr_gross,
        "sharpe": sharpe, "sortino": sortino,
        "max_dd": max_dd, "beta": beta,
        "residual_alpha": residual_alpha
    }


def run_fixed_holding_backtest(holding_days, k_val, trading_days, daily_returns_df, rankings_cache):
    """
    Belirli bir sabit tutma süresi H için periyodik rebalance backtesti.
    """
    n_days = len(trading_days)
    reb_indices = list(range(0, n_days, holding_days))

    daily_net = []
    daily_gross = []
    turnover_list = []

    current_portfolio = []
    current_reb_idx = 0

    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    for day_i in range(n_days):
        t = trading_days[day_i]

        # Rebalance günü mü?
        is_reb = (day_i in reb_indices)
        cost_today = 0.0

        if is_reb:
            target_stocks = rankings_cache[t]["ranked_symbols"][:k_val]
            if len(current_portfolio) == 0:
                turnover = 1.0
            else:
                degisen = len(set(target_stocks) - set(current_portfolio))
                turnover = degisen / k_val

            turnover_list.append(turnover)
            cost_today = turnover * TRANSACTION_COST
            current_portfolio = list(target_stocks)

        # Günlük getiri hesapla
        day_rets = [daily_returns_df.loc[t, s] for s in current_portfolio if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])]
        r_g = float(np.mean(day_rets)) if len(day_rets) > 0 else 0.0
        r_n = r_g - cost_today

        daily_gross.append(r_g)
        daily_net.append(r_n)

    annual_turnover = float(np.sum(turnover_list) * (252.0 / n_days))
    return daily_net, daily_gross, annual_turnover


def run_partial_turnover_backtest(min_hold, max_reb, k_val, trading_days, daily_returns_df, rankings_cache, check_freq=5):
    """
    'Ranking Sıklığı != Tam Turnover' Hysteresis / Kısmi Rotasyon Mimarisi.
    Her check_freq (5 gün, haftalık) sıralama kontrol edilir.
    Sadece Top-K'dan düşen VE (elde tutma >= min_hold VEYA >= max_reb) olan hisseler satılır.
    """
    n_days = len(trading_days)
    daily_net = []
    daily_gross = []
    turnover_list = []

    # portfolio dict: sembol -> {"entry_day": int}
    portfolio = {}

    for day_i in range(n_days):
        t = trading_days[day_i]
        cost_today = 0.0

        # Haftalık kontrol günü (veya ilk gün)
        if day_i == 0 or (day_i % check_freq == 0):
            top_k_target = set(rankings_cache[t]["ranked_symbols"][:k_val])

            if len(portfolio) == 0:
                # İlk portföy alımı
                for s in list(top_k_target)[:k_val]:
                    portfolio[s] = {"entry_day": day_i}
                turnover = 1.0
                turnover_list.append(turnover)
                cost_today = turnover * TRANSACTION_COST
            else:
                to_sell = []
                for s, info in portfolio.items():
                    days_held = day_i - info["entry_day"]
                    is_in_top = (s in top_k_target)

                    if not is_in_top:
                        if days_held >= min_hold or days_held >= max_reb:
                            to_sell.append(s)

                if len(to_sell) > 0:
                    turnover = len(to_sell) / k_val
                    turnover_list.append(turnover)
                    cost_today = turnover * TRANSACTION_COST

                    for s in to_sell:
                        del portfolio[s]

                    # Boşalan yerleri Top-K içindeki en yüksek puanlı henüz elde tutulmayanlarla doldur
                    ranked_list = rankings_cache[t]["ranked_symbols"]
                    available_candidates = [s for s in ranked_list if s not in portfolio]
                    for s in available_candidates[:len(to_sell)]:
                        portfolio[s] = {"entry_day": day_i}
                else:
                    turnover_list.append(0.0)

        # Günlük getiri hesapla
        current_stocks = list(portfolio.keys())
        day_rets = [daily_returns_df.loc[t, s] for s in current_stocks if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])]
        r_g = float(np.mean(day_rets)) if len(day_rets) > 0 else 0.0
        r_n = r_g - cost_today

        daily_gross.append(r_g)
        daily_net.append(r_n)

    annual_turnover = float(np.sum(turnover_list) * (252.0 / n_days))
    return daily_net, daily_gross, annual_turnover


def run_placebo_distribution(holding_days, k_val, trading_days, daily_returns_df, rankings_cache, n_seeds=100):
    """
    100 Tohumlu Monte Carlo Placebo Testi.
    """
    n_days = len(trading_days)
    reb_indices = list(range(0, n_days, holding_days))
    rng = np.random.default_rng(42)

    placebo_sharpes = []
    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    for seed in range(n_seeds):
        daily_net = []
        current_portfolio = []
        for day_i in range(n_days):
            t = trading_days[day_i]
            cost_today = 0.0
            if day_i in reb_indices:
                univ = rankings_cache[t]["universe"]
                target_stocks = rng.choice(univ, size=k_val, replace=False)
                if len(current_portfolio) == 0:
                    turnover = 1.0
                else:
                    degisen = len(set(target_stocks) - set(current_portfolio))
                    turnover = degisen / k_val
                cost_today = turnover * TRANSACTION_COST
                current_portfolio = list(target_stocks)

            day_rets = [daily_returns_df.loc[t, s] for s in current_portfolio if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])]
            r_g = float(np.mean(day_rets)) if len(day_rets) > 0 else 0.0
            daily_net.append(r_g - cost_today)

        r_arr = np.array(daily_net)
        diff_rf = r_arr - rf_daily
        std_val = float(np.std(r_arr, ddof=1)) if len(r_arr) > 1 else 1e-6
        sh = float(np.mean(diff_rf) / (std_val + 1e-8) * np.sqrt(252))
        placebo_sharpes.append(sh)

    return placebo_sharpes


def main():
    print("=" * 115)
    print("BİST KANTİTATİF MODEL: ALFA ÇÜRÜME EĞRİSİ VE KISMİ TURNOVER ANALİZİ")
    print("Dönem: 2018-09-03 -> 2025-05-30 (SADECE EĞİTİM PENCERESİ, KİLİT KUTU KESİNLİKLE KÖRDÜR)")
    print("=" * 115)

    # 1. Model ve verileri yükle
    saved_obj = joblib.load(ROOT_DIR / "scratch" / "winning_lgbm_ranker.joblib")
    model = saved_obj["model"]
    feature_cols = saved_obj["feature_cols"]

    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    df_prices = pd.DataFrame(fiyat_dict).sort_index()
    
    xu_train = seri_xu100[(seri_xu100.index >= "2018-09-03") & (seri_xu100.index <= LOCKBOX_BARRIER)]
    trading_days = xu_train.index
    n_days = len(trading_days)
    print(f"Eğitim Penceresi XU100 İşlem Günü Sayısı: {n_days} gün")

    # Günlük fiyat ve getiri matrisini tam XU100 takvimine hizala
    df_prices_train = df_prices.reindex(trading_days).ffill()
    daily_returns_df = df_prices_train.pct_change().fillna(0.0)
    xu_daily = xu_train.pct_change().fillna(0.0).values
    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    # 2. Önceden Sıralamaları Hesapla (Disk Cache ile)
    cache_path = ROOT_DIR / "scratch" / "rankings_cache_2018_2025.joblib"
    if cache_path.exists():
        print(f"Önceden hesaplanmış sıralama önbelleği diskten yükleniyor: {cache_path}...")
        rankings_cache = joblib.load(cache_path)
    else:
        rankings_cache = precompute_all_rankings(
            trading_days, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik, model, feature_cols
        )
        joblib.dump(rankings_cache, cache_path)

    # =========================================================================
    # BÖLÜM 1: SABİT TUTMA SÜRELERİ (ALPHA DECAY CURVE)
    # =========================================================================
    holding_periods = [5, 10, 15, 21, 30, 45, 60]
    
    print("\n" + "=" * 115)
    print("BÖLÜM 1: SABİT TUTMA SÜRELERİ (ALPHA DECAY CURVE) PERFORMANS TABLOSU (K=15)")
    print("=" * 115)
    header = f"{'Tutma (H)':<10} | {'Brüt Get':<9} | {'Net Get':<9} | {'CAGR':<7} | {'Sharpe':<7} | {'Sortino':<7} | {'Max DD':<8} | {'Turnover':<9} | {'Sharpe/Turn':<11} | {'Resid.Alpha':<11} | {'Placebo p':<9}"
    print(header)
    print("-" * 115)

    decay_results = []

    for h in holding_periods:
        daily_net, daily_gross, turnover = run_fixed_holding_backtest(
            h, 15, trading_days, daily_returns_df, rankings_cache
        )
        met = evaluate_daily_equity(daily_net, daily_gross, xu_daily, rf_daily)
        
        # Net Sharpe / Turnover Oranı
        sh_turn_ratio = met["sharpe"] / max(turnover, 0.1)

        # Placebo Testi
        plac_sharpes = run_placebo_distribution(h, 15, trading_days, daily_returns_df, rankings_cache, n_seeds=100)
        p_val = float(np.mean([1 if ps >= met["sharpe"] else 0 for ps in plac_sharpes]))

        decay_results.append({
            "h": h, "met": met, "turnover": turnover,
            "sh_turn_ratio": sh_turn_ratio, "p_val": p_val
        })

        print(f"{h:<3} gün     | %{met['cum_gross']*100:>7.0f} | %{met['cum_net']*100:>7.0f} | %{met['cagr_net']*100:>5.1f} | {met['sharpe']:>7.2f} | {met['sortino']:>7.2f} | %{met['max_dd']*100:>6.1f} | %{turnover*100:>7.1f} | {sh_turn_ratio:>11.2f} | %{met['residual_alpha']*100:>9.1f} | p = {p_val:.3f}")

    # K=10 ve K=20 için Placebo p-değeri özeti
    print("\n" + "-" * 85)
    print("PORTFÖY BOYUTU DUYARLILIĞI (K=10, K=15, K=20 için Placebo p-değerleri)")
    print("-" * 85)
    print(f"{'Tutma (H)':<10} | {'p-değeri (K=10)':<18} | {'p-değeri (K=15)':<18} | {'p-değeri (K=20)':<18}")
    print("-" * 85)

    for h in [10, 21, 45, 60]:
        # K=10
        d_net_10, _, _ = run_fixed_holding_backtest(h, 10, trading_days, daily_returns_df, rankings_cache)
        sh_10 = evaluate_daily_equity(d_net_10, d_net_10, xu_daily, rf_daily)["sharpe"]
        pl_10 = run_placebo_distribution(h, 10, trading_days, daily_returns_df, rankings_cache, 100)
        p_10 = float(np.mean([1 if ps >= sh_10 else 0 for ps in pl_10]))

        # K=20
        d_net_20, _, _ = run_fixed_holding_backtest(h, 20, trading_days, daily_returns_df, rankings_cache)
        sh_20 = evaluate_daily_equity(d_net_20, d_net_20, xu_daily, rf_daily)["sharpe"]
        pl_20 = run_placebo_distribution(h, 20, trading_days, daily_returns_df, rankings_cache, 100)
        p_20 = float(np.mean([1 if ps >= sh_20 else 0 for ps in pl_20]))

        p_15 = [d["p_val"] for d in decay_results if d["h"] == h][0]
        print(f"{h:<3} gün     | p = {p_10:<14.3f} | p = {p_15:<14.3f} | p = {p_20:<14.3f}")

    # =========================================================================
    # BÖLÜM 2: 'RANKING SIKLIĞI != TAM TURNOVER' MİMARİSİ (HYSTERESIS)
    # =========================================================================
    print("\n" + "=" * 115)
    print("BÖLÜM 2: 'RANKING SIKLIĞI ≠ TAM TURNOVER' KISMİ ROTASYON MİMARİSİ (K=15, Haftalık Kontrol)")
    print("=" * 115)
    print(f"{'Mimari (MinHold / MaxReb)':<25} | {'Brüt Get':<9} | {'Net Get':<9} | {'CAGR':<7} | {'Sharpe':<7} | {'Sortino':<7} | {'Max DD':<8} | {'Turnover':<9} | {'Sharpe/Turn':<11} | {'Resid.Alpha':<11} | {'Placebo p':<9}")
    print("-" * 115)

    hysteresis_combos = [
        (10, 21, "Min 10g / Max 21g"),
        (15, 30, "Min 15g / Max 30g"),
        (21, 60, "Min 21g / Max 60g")
    ]

    for min_h, max_r, label in hysteresis_combos:
        daily_net, daily_gross, turnover = run_partial_turnover_backtest(
            min_h, max_r, 15, trading_days, daily_returns_df, rankings_cache, check_freq=5
        )
        met = evaluate_daily_equity(daily_net, daily_gross, xu_daily, rf_daily)
        sh_turn = met["sharpe"] / max(turnover, 0.1)

        # Placebo test for hysteresis
        # Generate placebo with random picks under same frequency
        plac_sharpes = []
        rng = np.random.default_rng(42)
        for seed in range(100):
            p_net = []
            cur_p = {}
            for day_i in range(n_days):
                t = trading_days[day_i]
                c_today = 0.0
                if day_i == 0 or (day_i % 5 == 0):
                    univ = rankings_cache[t]["universe"]
                    # Random target
                    rand_target = set(rng.choice(univ, size=15, replace=False))
                    if len(cur_p) == 0:
                        for s in rand_target:
                            cur_p[s] = day_i
                        c_today = 1.0 * TRANSACTION_COST
                    else:
                        to_s = [s for s, ent in cur_p.items() if (s not in rand_target) and (day_i - ent >= min_h)]
                        if to_s:
                            c_today = (len(to_s) / 15.0) * TRANSACTION_COST
                            for s in to_s:
                                del cur_p[s]
                            cands = [s for s in rand_target if s not in cur_p]
                            for s in cands[:len(to_s)]:
                                cur_p[s] = day_i
                day_rets = [daily_returns_df.loc[t, s] for s in cur_p.keys() if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])]
                p_net.append((float(np.mean(day_rets)) if day_rets else 0.0) - c_today)
            r_arr = np.array(p_net)
            sh_p = float(np.mean(r_arr - rf_daily) / (np.std(r_arr, ddof=1) + 1e-8) * np.sqrt(252))
            plac_sharpes.append(sh_p)

        p_val = float(np.mean([1 if ps >= met["sharpe"] else 0 for ps in plac_sharpes]))

        print(f"{label:<25} | %{met['cum_gross']*100:>7.0f} | %{met['cum_net']*100:>7.0f} | %{met['cagr_net']*100:>5.1f} | {met['sharpe']:>7.2f} | {met['sortino']:>7.2f} | %{met['max_dd']*100:>6.1f} | %{turnover*100:>7.1f} | {sh_turn:>11.2f} | %{met['residual_alpha']*100:>9.1f} | p = {p_val:.3f}")

    print("=" * 115)


if __name__ == "__main__":
    main()
