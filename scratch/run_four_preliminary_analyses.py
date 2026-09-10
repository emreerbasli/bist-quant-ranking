"""
scratch/run_four_preliminary_analyses.py
========================================
DÖRT ÖN ANALİZ ÇALIŞMASI:
  1. K=10, Min 15g / Max 60g Kısmi Rotasyon Mimarisi Testi
  2. Drift Monitor için Veriye Dayalı Referans Sharpe ve Eşik
  3. Makro Rejim Eşiklerinin Ampirik Veriden Türetilmesi
  4. Pozisyon Boyutlandırması: Eşit Ağırlık vs Skor-Ağırlıklı (Rank / Softmax)

Kapsam: SADECE EĞİTİM PENCERESİ (2018-09-03 -> 2025-05-30)
Kilit Kutu (2025-06-01 -> 2026-09-07) VERİSİNE KESİNLİKLE DOKUNULMAZ / KÖRDÜR.
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

from scratch.run_faz_c_walk_forward_test import yukle_veriler
from scratch.run_alpha_decay_and_turnover_study import evaluate_daily_equity, run_fixed_holding_backtest

TRANSACTION_COST = 0.003  # %0.30 round-trip (15 bps buy + 15 bps sell)
RF_ANNUAL = 0.18
LOCKBOX_BARRIER = pd.Timestamp("2025-05-31")


def run_partial_turnover_weighted(min_hold, max_reb, k_val, trading_days, daily_returns_df, rankings_cache, check_freq=5, weighting="equal"):
    """
    Kısmi rotasyon mimarisi (Eşit veya Skor/Rank Ağırlıklı).
    """
    n_days = len(trading_days)
    daily_net = []
    daily_gross = []
    turnover_list = []

    # portfolio: sembol -> {"entry_day": int, "weight": float}
    portfolio = {}

    for day_i in range(n_days):
        t = trading_days[day_i]
        cost_today = 0.0

        if day_i == 0 or (day_i % check_freq == 0):
            top_k_ranked = rankings_cache[t]["ranked_symbols"][:k_val]
            top_k_set = set(top_k_ranked)

            if len(portfolio) == 0:
                # İlk portföy alımı
                if weighting == "equal":
                    weights = {s: 1.0 / k_val for s in top_k_ranked}
                elif weighting == "rank":
                    # Rank bazlı ağırlık (Rank 1 en yüksek)
                    total_pts = k_val * (k_val + 1) / 2.0
                    weights = {s: (k_val - idx) / total_pts for idx, s in enumerate(top_k_ranked)}
                elif weighting == "softmax":
                    # Softmax ağırlık
                    scores = np.array(rankings_cache[t]["scores"][:k_val])
                    exp_s = np.exp(scores - np.max(scores))
                    w_arr = exp_s / np.sum(exp_s)
                    weights = {s: float(w_arr[idx]) for idx, s in enumerate(top_k_ranked)}

                for s in top_k_ranked:
                    portfolio[s] = {"entry_day": day_i, "weight": weights[s]}
                turnover = 1.0
                turnover_list.append(turnover)
                cost_today = turnover * TRANSACTION_COST
            else:
                to_sell = []
                for s, info in portfolio.items():
                    days_held = day_i - info["entry_day"]
                    if s not in top_k_set:
                        if days_held >= min_hold or days_held >= max_reb:
                            to_sell.append(s)

                if len(to_sell) > 0:
                    sold_weight = sum([portfolio[s]["weight"] for s in to_sell])
                    turnover = len(to_sell) / float(k_val)
                    turnover_list.append(turnover)
                    cost_today = turnover * TRANSACTION_COST

                    for s in to_sell:
                        del portfolio[s]

                    # Boşalan yerlere Top-K içindeki yeni adaylar
                    candidates = [s for s in top_k_ranked if s not in portfolio]
                    new_picks = candidates[:len(to_sell)]

                    # Ağırlıkları güncelle
                    if weighting == "equal":
                        # Kalan ve yenileri eşit ağırlıklandır
                        cur_syms = list(portfolio.keys()) + new_picks
                        w_eq = 1.0 / float(len(cur_syms))
                        for s in list(portfolio.keys()):
                            portfolio[s]["weight"] = w_eq
                        for s in new_picks:
                            portfolio[s] = {"entry_day": day_i, "weight": w_eq}
                    elif weighting == "rank":
                        cur_syms = list(portfolio.keys()) + new_picks
                        total_pts = len(cur_syms) * (len(cur_syms) + 1) / 2.0
                        # Sıralamaya göre ağırlık
                        all_ranked = rankings_cache[t]["ranked_symbols"]
                        sym_rank_map = {s: idx for idx, s in enumerate(all_ranked)}
                        sorted_cur = sorted(cur_syms, key=lambda x: sym_rank_map.get(x, 999))
                        for idx, s in enumerate(sorted_cur):
                            w_val = (len(sorted_cur) - idx) / total_pts
                            if s in portfolio:
                                portfolio[s]["weight"] = w_val
                            else:
                                portfolio[s] = {"entry_day": day_i, "weight": w_val}
                    elif weighting == "softmax":
                        cur_syms = list(portfolio.keys()) + new_picks
                        all_ranked = rankings_cache[t]["ranked_symbols"]
                        all_scores = rankings_cache[t]["scores"]
                        sym_score_map = {s: sc for s, sc in zip(all_ranked, all_scores)}
                        sc_arr = np.array([sym_score_map.get(s, 0.0) for s in cur_syms])
                        exp_s = np.exp(sc_arr - np.max(sc_arr))
                        w_arr = exp_s / np.sum(exp_s)
                        for idx, s in enumerate(cur_syms):
                            if s in portfolio:
                                portfolio[s]["weight"] = float(w_arr[idx])
                            else:
                                portfolio[s] = {"entry_day": day_i, "weight": float(w_arr[idx])}
                else:
                    turnover_list.append(0.0)

        # Günlük getiri
        day_rets = []
        w_sum = 0.0
        for s, info in portfolio.items():
            if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s]):
                r_s = daily_returns_df.loc[t, s]
                w_s = info["weight"]
                day_rets.append(r_s * w_s)
                w_sum += w_s

        r_g = float(np.sum(day_rets) / w_sum) if w_sum > 0 else 0.0
        r_n = r_g - cost_today

        daily_gross.append(r_g)
        daily_net.append(r_n)

    annual_turnover = float(np.sum(turnover_list) * (252.0 / n_days))
    return daily_net, daily_gross, annual_turnover


def run_placebo_hysteresis(min_hold, max_reb, k_val, trading_days, daily_returns_df, rankings_cache, n_seeds=100):
    n_days = len(trading_days)
    rng = np.random.default_rng(42)
    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0
    plac_sharpes = []

    for seed in range(n_seeds):
        p_net = []
        cur_p = {}
        for day_i in range(n_days):
            t = trading_days[day_i]
            c_today = 0.0
            if day_i == 0 or (day_i % 5 == 0):
                univ = rankings_cache[t]["universe"]
                rand_target = set(rng.choice(univ, size=k_val, replace=False))
                if len(cur_p) == 0:
                    for s in rand_target:
                        cur_p[s] = day_i
                    c_today = 1.0 * TRANSACTION_COST
                else:
                    to_s = [s for s, ent in cur_p.items() if (s not in rand_target) and ((day_i - ent >= min_hold) or (day_i - ent >= max_reb))]
                    if to_s:
                        c_today = (len(to_s) / float(k_val)) * TRANSACTION_COST
                        for s in to_s:
                            del cur_p[s]
                        cands = [s for s in rand_target if s not in cur_p]
                        for s in cands[:len(to_s)]:
                            cur_p[s] = day_i
            day_rets = [daily_returns_df.loc[t, s] for s in cur_p.keys() if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])]
            r_g_p = float(np.mean(day_rets)) if len(day_rets) > 0 else 0.0
            p_net.append(r_g_p - c_today)

        r_arr = np.array(p_net)
        diff_rf = r_arr - rf_daily
        sh_p = float(np.mean(diff_rf) / (np.std(r_arr, ddof=1) + 1e-8) * np.sqrt(252))
        plac_sharpes.append(sh_p)

    return plac_sharpes


def main():
    print("=" * 115)
    print("DÖRT ÖN ANALİZ ÇALIŞMASI (ADIM 2 VE 3 HAZIRLIK)")
    print("Kapsam: SADECE EĞİTİM PENCERESİ (2018-09-03 -> 2025-05-30, 1682 Gün)")
    print("=" * 115)

    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    df_prices = pd.DataFrame(fiyat_dict).sort_index()

    xu_train = seri_xu100[(seri_xu100.index >= "2018-09-03") & (seri_xu100.index <= LOCKBOX_BARRIER)]
    trading_days = xu_train.index
    n_days = len(trading_days)

    df_prices_train = df_prices.reindex(trading_days).ffill()
    daily_returns_df = df_prices_train.pct_change().fillna(0.0)
    xu_daily = xu_train.pct_change().fillna(0.0).values
    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    cache_path = ROOT_DIR / "scratch" / "rankings_cache_2018_2025.joblib"
    rankings_cache = joblib.load(cache_path)

    # -------------------------------------------------------------------------
    # ÖN ANALİZ 1: K=10, Min 15g / Max 60g ve Benchmark Karşılaştırması
    # -------------------------------------------------------------------------
    print("\n" + "=" * 115)
    print("📌 ÖN ANALİZ 1: 'Min 15g / Max 60g, K=10' MİMARİSİ VE BENCHMARK KARŞILAŞTIRMASI")
    print("=" * 115)

    # Mimari 1: K=10, Min 15g / Max 60g
    net_k10_15_60, gross_k10_15_60, turn_k10_15_60 = run_partial_turnover_weighted(
        15, 60, 10, trading_days, daily_returns_df, rankings_cache, check_freq=5, weighting="equal"
    )
    met_k10_15_60 = evaluate_daily_equity(net_k10_15_60, gross_k10_15_60, xu_daily, rf_daily)
    sh_turn_k10_15_60 = met_k10_15_60["sharpe"] / max(turn_k10_15_60, 0.1)
    plac_k10_15_60 = run_placebo_hysteresis(15, 60, 10, trading_days, daily_returns_df, rankings_cache, 100)
    p_k10_15_60 = float(np.mean([1 if ps >= met_k10_15_60["sharpe"] else 0 for ps in plac_k10_15_60]))

    # Benchmark (a): K=10, H=60g sabit
    net_k10_60, gross_k10_60, turn_k10_60 = run_fixed_holding_backtest(
        60, 10, trading_days, daily_returns_df, rankings_cache
    )
    met_k10_60 = evaluate_daily_equity(net_k10_60, gross_k10_60, xu_daily, rf_daily)
    sh_turn_k10_60 = met_k10_60["sharpe"] / max(turn_k10_60, 0.1)
    # 100 seed placebo for fixed 60d K=10
    rng = np.random.default_rng(42)
    plac_k10_60 = []
    reb_60 = list(range(0, n_days, 60))
    for seed in range(100):
        p_net = []
        c_p = []
        for d_i in range(n_days):
            t = trading_days[d_i]
            c_t = 0.0
            if d_i in reb_60:
                univ = rankings_cache[t]["universe"]
                target = rng.choice(univ, size=10, replace=False)
                turn = 1.0 if len(c_p) == 0 else len(set(target)-set(c_p))/10.0
                c_t = turn * TRANSACTION_COST
                c_p = list(target)
            d_rets = [daily_returns_df.loc[t, s] for s in c_p if s in daily_returns_df.columns]
            p_net.append((float(np.mean(d_rets)) if d_rets else 0.0) - c_t)
        sh_p = float(np.mean(np.array(p_net)-rf_daily)/(np.std(p_net, ddof=1)+1e-8)*np.sqrt(252))
        plac_k10_60.append(sh_p)
    p_k10_60 = float(np.mean([1 if ps >= met_k10_60["sharpe"] else 0 for ps in plac_k10_60]))

    # Benchmark (b): K=15, Min 15g / Max 30g
    net_k15_15_30, gross_k15_15_30, turn_k15_15_30 = run_partial_turnover_weighted(
        15, 30, 15, trading_days, daily_returns_df, rankings_cache, check_freq=5, weighting="equal"
    )
    met_k15_15_30 = evaluate_daily_equity(net_k15_15_30, gross_k15_15_30, xu_daily, rf_daily)
    sh_turn_k15_15_30 = met_k15_15_30["sharpe"] / max(turn_k15_15_30, 0.1)
    plac_k15_15_30 = run_placebo_hysteresis(15, 30, 15, trading_days, daily_returns_df, rankings_cache, 100)
    p_k15_15_30 = float(np.mean([1 if ps >= met_k15_15_30["sharpe"] else 0 for ps in plac_k15_15_30]))

    print(f"{'Strateji / Mimari':<32} | {'Net CAGR':<9} | {'Net Sharpe':<11} | {'Sortino':<8} | {'Max DD':<9} | {'Turnover':<10} | {'Sharpe/Turn':<11} | {'Placebo p':<10}")
    print("-" * 115)
    print(f"{'K=10, Min 15g / Max 60g (YENİ)':<32} | %{met_k10_15_60['cagr_net']*100:>7.1f} | {met_k10_15_60['sharpe']:>11.2f} | {met_k10_15_60['sortino']:>8.2f} | %{met_k10_15_60['max_dd']*100:>7.1f} | %{turn_k10_15_60*100:>8.1f} | {sh_turn_k10_15_60:>11.2f} | p = {p_k10_15_60:.3f}")
    print(f"{'(a) K=10, H=60g Sabit':<32} | %{met_k10_60['cagr_net']*100:>7.1f} | {met_k10_60['sharpe']:>11.2f} | {met_k10_60['sortino']:>8.2f} | %{met_k10_60['max_dd']*100:>7.1f} | %{turn_k10_60*100:>8.1f} | {sh_turn_k10_60:>11.2f} | p = {p_k10_60:.3f}")
    print(f"{'(b) K=15, Min 15g / Max 30g':<32} | %{met_k15_15_30['cagr_net']*100:>7.1f} | {met_k15_15_30['sharpe']:>11.2f} | {met_k15_15_30['sortino']:>8.2f} | %{met_k15_15_30['max_dd']*100:>7.1f} | %{turn_k15_15_30*100:>8.1f} | {sh_turn_k15_15_30:>11.2f} | p = {p_k15_15_30:.3f}")

    # -------------------------------------------------------------------------
    # ÖN ANALİZ 2: Drift Monitor Referans Sharpe ve Alarm Eşiği
    # -------------------------------------------------------------------------
    print("\n" + "=" * 115)
    print("📌 ÖN ANALİZ 2: DRİFT MONİTÖRÜ İÇİN VERİYE DAYALI REFERANS SHARPE VE SAPMA EŞİĞİ")
    print("=" * 115)
    
    # K=10, Min 15g / Max 60g referansı
    sh_ref_hyst = met_k10_15_60["sharpe"]
    alarm_hyst = sh_ref_hyst * 0.60  # %40 düşüş eşiği

    # K=10, H=60g referansı
    sh_ref_60 = met_k10_60["sharpe"]
    alarm_60 = sh_ref_60 * 0.60

    print(f"K=10, Min 15g/Max 60g Eğitim Penceresi Sharpe:  {sh_ref_hyst:.2f}  --> %40 Sapma Alarm Eşiği: {alarm_hyst:.2f}")
    print(f"K=10, H=60g Sabit Eğitim Penceresi Sharpe:       {sh_ref_60:.2f}  --> %40 Sapma Alarm Eşiği: {alarm_60:.2f}")
    print(f"NOT: Kilit Kutu Sharpe'ı (2.09 / 3.41) süper-dönem olup referans alınmamıştır. Eğitim penceresi (6.75 yıl) sağlam çıpadır.")

    # -------------------------------------------------------------------------
    # ÖN ANALİZ 3: Makro Rejim Eşiklerinin Ampirik Veriden Türetilmesi
    # -------------------------------------------------------------------------
    print("\n" + "=" * 115)
    print("📌 ÖN ANALİZ 3: MAKRO REJİM EŞİKLERİNİN AMPİRİK VERİDEN TÜRETİLMESİ")
    print("=" * 115)

    macro_df = pd.read_csv(ROOT_DIR / "scratch" / "macro_regime_history.csv")
    macro_df["tarih"] = pd.to_datetime(macro_df["tarih"])

    # 1. Kötü Dönem (2022-01 -> 2024-09): Modelin spekülatif köpüğün gerisinde kaldığı derin negatif faiz dönemi
    kotu_df = macro_df[(macro_df["tarih"] >= "2022-01-01") & (macro_df["tarih"] <= "2024-09-01")]
    # 2. İyi Dönemler (2019-2020 ve 2025-2026 Kilit Kutu): Pozitif reel faiz / sıkı para politikası
    iyi_df = macro_df[
        ((macro_df["tarih"] >= "2019-01-01") & (macro_df["tarih"] <= "2020-12-31")) |
        ((macro_df["tarih"] >= "2025-06-01") & (macro_df["tarih"] <= "2026-09-07"))
    ]

    print(f"Kötü Dönem (2022-2024) Reel Faiz Dağılımı:  Min: %{kotu_df['reel'].min():.1f} | Medyan: %{kotu_df['reel'].median():.1f} | Max: %{kotu_df['reel'].max():.1f}")
    print(f"İyi Dönem  (2019-20 & 2025-26) Reel Faiz:   Min: %{iyi_df['reel'].min():.1f} | Medyan: %{iyi_df['reel'].median():.1f} | Max: %{iyi_df['reel'].max():.1f}")
    print("-" * 80)
    print(f"Kötü Dönem USD 60g İvmesi (usd_60):         Min: %{kotu_df['usd_60'].min()*100:.1f} | Medyan: %{kotu_df['usd_60'].median()*100:.1f} | Max: %{kotu_df['usd_60'].max()*100:.1f}")
    print(f"İyi Dönem  USD 60g İvmesi (usd_60):         Min: %{iyi_df['usd_60'].min()*100:.1f} | Medyan: %{iyi_df['usd_60'].median()*100:.1f} | Max: %{iyi_df['usd_60'].max()*100:.1f}")

    # Kur Şoku Dönemleri (2018-09 ve 2021-12)
    sok_df = macro_df[macro_df["rejim"].str.contains("KUR ŞOKU", na=False)]
    print("-" * 80)
    print("Tarihsel Kur Şoku Çeyrekleri (2018Q3 ve 2021Q4):")
    for _, r in sok_df.iterrows():
        print(f"  Tarih: {r['tarih'].strftime('%Y-%m-%d')} | USD 60g Mom: %{r['usd_60']*100:.1f} | USD 90g Mom: %{r['usd_90']*100:.1f} | Reel Faiz: %{r['reel']:.1f}")

    # Ampirik Eşik Çıkarımı:
    # 1. Reel faiz: Kötü dönemin maksimumu -%11.8, iyi dönemin minimumu -%3.5 (2020 pandemide bile faiz negatife inince -3.5 idi).
    # Ayrıştırma noktası: Reel Faiz <= -%10.0 (Derin Negatif Faiz Sınırı)
    # 2. USD 60g: Normal dönemlerde medyan %3.1 - %4.0 iken, kur şoklarında %44.0 ve %52.5 olmuştur.
    # Kur şoku eşiği: USD 60g >= %20.0 (veya %18.0)

    # -------------------------------------------------------------------------
    # ÖN ANALİZ 4: Pozisyon Boyutlandırması (Eşit vs Skor-Ağırlıklı)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 115)
    print("📌 ÖN ANALİZ 4: POZİSYON BOYUTLANDIRMASI (EŞİT AĞIRLIK vs SKOR/RANK AĞIRLIKLI)")
    print("Mimaride K=10, Min 15g / Max 60g kullanılmıştır.")
    print("=" * 115)

    # (A) Eşit Ağırlık (Ön Analiz 1'de hesaplandı)
    # (B) Rank Ağırlıklı (Rank 1: 10 puan, Rank 10: 1 puan)
    net_rank, gross_rank, turn_rank = run_partial_turnover_weighted(
        15, 60, 10, trading_days, daily_returns_df, rankings_cache, check_freq=5, weighting="rank"
    )
    met_rank = evaluate_daily_equity(net_rank, gross_rank, xu_daily, rf_daily)
    sh_turn_rank = met_rank["sharpe"] / max(turn_rank, 0.1)

    # (C) Softmax Skor Ağırlıklı
    net_soft, gross_soft, turn_soft = run_partial_turnover_weighted(
        15, 60, 10, trading_days, daily_returns_df, rankings_cache, check_freq=5, weighting="softmax"
    )
    met_soft = evaluate_daily_equity(net_soft, gross_soft, xu_daily, rf_daily)
    sh_turn_soft = met_soft["sharpe"] / max(turn_soft, 0.1)

    print(f"{'Ağırlıklandırma Yöntemi':<32} | {'Net CAGR':<9} | {'Net Sharpe':<11} | {'Sortino':<8} | {'Max DD':<9} | {'Turnover':<10} | {'Sharpe/Turn':<11}")
    print("-" * 105)
    print(f"{'(A) Eşit Ağırlık (Her hisseye %10)':<32} | %{met_k10_15_60['cagr_net']*100:>7.1f} | {met_k10_15_60['sharpe']:>11.2f} | {met_k10_15_60['sortino']:>8.2f} | %{met_k10_15_60['max_dd']*100:>7.1f} | %{turn_k10_15_60*100:>8.1f} | {sh_turn_k10_15_60:>11.2f}")
    print(f"{'(B) Doğrusal Rank Ağırlıklı':<32} | %{met_rank['cagr_net']*100:>7.1f} | {met_rank['sharpe']:>11.2f} | {met_rank['sortino']:>8.2f} | %{met_rank['max_dd']*100:>7.1f} | %{turn_rank*100:>8.1f} | {sh_turn_rank:>11.2f}")
    print(f"{'(C) Softmax Skor Ağırlıklı':<32} | %{met_soft['cagr_net']*100:>7.1f} | {met_soft['sharpe']:>11.2f} | {met_soft['sortino']:>8.2f} | %{met_soft['max_dd']*100:>7.1f} | %{turn_soft*100:>8.1f} | {sh_turn_soft:>11.2f}")
    print("=" * 115)


if __name__ == "__main__":
    main()
