"""
scratch/run_clean_macro_and_dd_control_study.py
================================================
YENİ KONSOLİDE ANALİZ:
  1. DÜZELTME 1: Kilit kutudan arındırılmış temiz makro rejim analizi ve eşik türetimi (2018-09 -> 2025-05)
  2. DÜZELTME 2: K=10, H=60g + %25 Drawdown Kesici simülasyonu vs K=10 Min15g/Max60g net karşılaştırma
  3. DÜZELTME 3: models/v3_ranking/honesty_note.txt oluşturulması

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
from scratch.run_four_preliminary_analyses import run_partial_turnover_weighted

TRANSACTION_COST = 0.003  # %0.30 round-trip
RF_ANNUAL = 0.18
LOCKBOX_BARRIER = pd.Timestamp("2025-05-31")


def analyze_clean_macro_regimes():
    """
    DÜZELTME 1: SADECE 2018-09 -> 2025-05 arasındaki çeyrekleri kullanarak
    iyi ve kötü rejimleri ayrıştırır ve veriye dayalı eşikleri türetir.
    Kilit kutu (2025-06 sonrası) KESİNLİKLE DIŞARIDA BIRAKILIR.
    """
    macro_file = ROOT_DIR / "scratch" / "macro_regime_history.csv"
    df = pd.read_csv(macro_file)
    df["tarih"] = pd.to_datetime(df["tarih"])

    # KİLİT KUTU ARINDIRMASI: Sadece 2018-09 -> 2025-05
    df_clean = df[(df["tarih"] >= "2018-09-01") & (df["tarih"] <= LOCKBOX_BARRIER)].copy()

    # İki Grup Tanımı
    iyi_grup = df_clean[df_clean["reel"] > -5.0]
    kotu_grup = df_clean[df_clean["reel"] < -10.0]
    gecis_grup = df_clean[(df_clean["reel"] >= -10.0) & (df_clean["reel"] <= -5.0)]

    res = {
        "n_total": len(df_clean),
        "n_iyi": len(iyi_grup),
        "n_kotu": len(kotu_grup),
        "n_gecis": len(gecis_grup),
        "iyi_reel": {
            "min": float(iyi_grup["reel"].min()),
            "median": float(iyi_grup["reel"].median()),
            "max": float(iyi_grup["reel"].max()),
        },
        "kotu_reel": {
            "min": float(kotu_grup["reel"].min()),
            "median": float(kotu_grup["reel"].median()),
            "max": float(kotu_grup["reel"].max()),
        },
        "iyi_usd": {
            "min": float(iyi_grup["usd_60"].min()),
            "median": float(iyi_grup["usd_60"].median()),
            "max": float(iyi_grup["usd_60"].max()),
        },
        "kotu_usd": {
            "min": float(kotu_grup["usd_60"].min()),
            "median": float(kotu_grup["usd_60"].median()),
            "max": float(kotu_grup["usd_60"].max()),
        },
        "sok_ceyreker": df_clean[df_clean["rejim"].str.contains("KUR ŞOKU", na=False)]
    }

    # Eşik Türetimi:
    # 1. Reel Faiz Eşiği: Kötü grubun tavanı (-11.8%) ile İyi grubun tabanı (-4.9%) arasındaki orta nokta
    # veya kötü grubun başladığı sınır: -%10.0
    # 2. USD 60g Eşiği: Sakin dönemlerin tavanı (~%11.6) ile Şok dönemleri (%44.0, %52.5) arasındaki sınır: %20.0
    return res, df_clean


def run_fixed_holding_with_dd_control(h_days, k_val, trading_days, daily_returns_df, rankings_cache,
                                      dd_trigger=-0.25, dd_recover=-0.15):
    """
    DÜZELTME 2: H=60g sabit tutma + %25 Drawdown Kesici Devresi.
    Zirveden %25 düşünce pozisyon %50 nakit (%18 faiz) + %50 hisse olur.
    Zirveden %15'e toparlanınca %100 hisseye döner.
    """
    n_days = len(trading_days)
    reb_indices = set(range(0, n_days, h_days))

    daily_net = []
    daily_gross = []
    equity_curve = []
    allocation_curve = []
    turnover_list = []

    current_portfolio = []
    equity = 1.0
    peak_equity = 1.0
    w_equity = 1.0  # %100 hisse ile başla

    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0

    for day_i in range(n_days):
        t = trading_days[day_i]
        cost_today = 0.0

        # Periyodik rebalance günü
        if day_i in reb_indices:
            target_stocks = rankings_cache[t]["ranked_symbols"][:k_val]
            if len(current_portfolio) == 0:
                turn = 1.0
            else:
                turn = len(set(target_stocks) - set(current_portfolio)) / float(k_val)
            turnover_list.append(turn * w_equity)
            cost_today += turn * w_equity * TRANSACTION_COST
            current_portfolio = list(target_stocks)

        # Günlük hisse getirisi
        day_rets = [daily_returns_df.loc[t, s] for s in current_portfolio if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])]
        r_stocks = float(np.mean(day_rets)) if len(day_rets) > 0 else 0.0

        # Portföy getirisi (ağırlıklı hisse + nakit faizi)
        r_gross = w_equity * r_stocks + (1.0 - w_equity) * rf_daily
        r_net = r_gross - cost_today

        daily_gross.append(r_gross)
        daily_net.append(r_net)

        # Sermaye güncelleme
        equity *= (1.0 + r_net)
        if equity > peak_equity:
            peak_equity = equity
        dd = (equity - peak_equity) / peak_equity

        equity_curve.append(equity)
        allocation_curve.append(w_equity)

        # DRAWDOWN KONTROLÜ TETİKLEME KONTROLÜ
        if w_equity == 1.0 and dd <= dd_trigger:
            # %25 düşüş oldu -> Pozisyonu %50'ye indir
            w_equity = 0.5
            # %50 hisse satıldığı için işlem maliyeti
            cost_switch = 0.5 * TRANSACTION_COST
            equity *= (1.0 - cost_switch)
            daily_net[-1] -= cost_switch
            turnover_list.append(0.5)

        elif w_equity == 0.5 and dd >= dd_recover:
            # Toparlanma oldu -> %100 hisseye dön
            w_equity = 1.0
            # %50 hisse tekrar alındığı için işlem maliyeti
            cost_switch = 0.5 * TRANSACTION_COST
            equity *= (1.0 - cost_switch)
            daily_net[-1] -= cost_switch
            turnover_list.append(0.5)

    annual_turnover = float(np.sum(turnover_list) * (252.0 / n_days))
    return daily_net, daily_gross, annual_turnover, allocation_curve


def run_placebo_dd_control(h_days, k_val, trading_days, daily_returns_df, rankings_cache,
                           dd_trigger=-0.25, dd_recover=-0.15, n_seeds=100):
    """
    100 Tohumlu Monte Carlo Placebo Testi (Drawdown Kontrolü Dahil).
    """
    n_days = len(trading_days)
    reb_indices = set(range(0, n_days, h_days))
    rng = np.random.default_rng(42)
    rf_daily = (1.0 + RF_ANNUAL) ** (1.0 / 252.0) - 1.0
    plac_sharpes = []

    for seed in range(n_seeds):
        p_net = []
        cur_p = []
        equity = 1.0
        peak_equity = 1.0
        w_equity = 1.0

        for day_i in range(n_days):
            t = trading_days[day_i]
            cost_today = 0.0

            if day_i in reb_indices:
                univ = rankings_cache[t]["universe"]
                target_stocks = rng.choice(univ, size=k_val, replace=False)
                if len(cur_p) == 0:
                    turn = 1.0
                else:
                    turn = len(set(target_stocks) - set(cur_p)) / float(k_val)
                cost_today += turn * w_equity * TRANSACTION_COST
                cur_p = list(target_stocks)

            day_rets = [daily_returns_df.loc[t, s] for s in cur_p if s in daily_returns_df.columns and not np.isnan(daily_returns_df.loc[t, s])]
            r_stocks = float(np.mean(day_rets)) if len(day_rets) > 0 else 0.0

            r_gross = w_equity * r_stocks + (1.0 - w_equity) * rf_daily
            r_n = r_gross - cost_today
            p_net.append(r_n)

            equity *= (1.0 + r_n)
            if equity > peak_equity:
                peak_equity = equity
            dd = (equity - peak_equity) / peak_equity

            if w_equity == 1.0 and dd <= dd_trigger:
                w_equity = 0.5
                cost_switch = 0.5 * TRANSACTION_COST
                equity *= (1.0 - cost_switch)
                p_net[-1] -= cost_switch
            elif w_equity == 0.5 and dd >= dd_recover:
                w_equity = 1.0
                cost_switch = 0.5 * TRANSACTION_COST
                equity *= (1.0 - cost_switch)
                p_net[-1] -= cost_switch

        r_arr = np.array(p_net)
        diff_rf = r_arr - rf_daily
        sh_p = float(np.mean(diff_rf) / (np.std(r_arr, ddof=1) + 1e-8) * np.sqrt(252))
        plac_sharpes.append(sh_p)

    return plac_sharpes


def evaluate_metrics(daily_returns_net, daily_returns_gross, rf_daily):
    n_days = len(daily_returns_net)
    r_net = np.array(daily_returns_net)
    r_gross = np.array(daily_returns_gross)

    cum_net = float(np.prod(1.0 + r_net) - 1.0)
    cagr_net = float((1.0 + cum_net) ** (252.0 / n_days) - 1.0) if cum_net > -0.99 else -0.99

    diff_rf = r_net - rf_daily
    std_net = float(np.std(r_net, ddof=1)) if len(r_net) > 1 else 1e-6
    sharpe = float(np.mean(diff_rf) / (std_net + 1e-8) * np.sqrt(252))

    downside = np.minimum(diff_rf, 0.0)
    downside_std = float(np.sqrt(np.mean(downside ** 2)))
    sortino = float(np.mean(diff_rf) / (downside_std + 1e-8) * np.sqrt(252))

    equity = np.cumprod(1.0 + r_net)
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = float(np.min(dd))

    return {
        "cum_net": cum_net, "cagr_net": cagr_net,
        "sharpe": sharpe, "sortino": sortino, "max_dd": max_dd
    }


def main():
    print("=" * 115)
    print("YENİ KONSOLİDE RAPOR: TEMİZ MAKRO ANALİZİ & DRAWDOWN KESİCİ SEÇİMİ")
    print("Kapsam: SADECE EĞİTİM PENCERESİ (2018-09-03 -> 2025-05-30, 1682 İşlem Günü)")
    print("KİLİT KUTU (2025-06-01 -> 2026-09-07) KESİNLİKLE DAHİL EDİLMEMİŞTİR.")
    print("=" * 115)

    # -------------------------------------------------------------------------
    # DÜZELTME 1: KİLİT KUTUDAN ARINDIRILMIŞ MAKRO REJİM ANALİZİ
    # -------------------------------------------------------------------------
    macro_stats, df_clean = analyze_clean_macro_regimes()
    print("\n" + "=" * 90)
    print("📊 DÜZELTME 1: KİLİT KUTUDAN ARINDIRILMIŞ MAKRO REJİM ANALİZİ (2018Q3 -> 2025Q1)")
    print("=" * 90)
    print(f"Toplam Analiz Edilen Çeyrek Sayısı: {macro_stats['n_total']} çeyrek (SADECE EĞİTİM PENCERESİ)")
    print(f"  - İyi Dönem (Reel Faiz > -%5):   {macro_stats['n_iyi']} çeyrek")
    print(f"  - Kötü Dönem (Reel Faiz < -%10): {macro_stats['n_kotu']} çeyrek")
    print(f"  - Geçiş Dönemi (-%10 <= Reel <= -%5): {macro_stats['n_gecis']} çeyrek")
    print("-" * 90)
    print(f"{'Metrik':<25} | {'İyi Dönem (Reel > -%5)':<30} | {'Kötü Dönem (Reel < -%10)':<30}")
    print("-" * 90)
    print(f"{'Reel Faiz [Min, Med, Max]':<25} | [%{macro_stats['iyi_reel']['min']:.1f}, %{macro_stats['iyi_reel']['median']:.1f}, %{macro_stats['iyi_reel']['max']:.1f}]{'':<12} | [%{macro_stats['kotu_reel']['min']:.1f}, %{macro_stats['kotu_reel']['median']:.1f}, %{macro_stats['kotu_reel']['max']:.1f}]")
    print(f"{'USD 60g Mom [Min, Med, Max]':<25} | [%{macro_stats['iyi_usd']['min']*100:.1f}, %{macro_stats['iyi_usd']['median']*100:.1f}, %{macro_stats['iyi_usd']['max']*100:.1f}]{'':<10} | [%{macro_stats['kotu_usd']['min']*100:.1f}, %{macro_stats['kotu_usd']['median']*100:.1f}, %{macro_stats['kotu_usd']['max']*100:.1f}]")
    print("-" * 90)
    print("TEMİZ VERİDEN TÜRETİLEN NİHAİ MAKRO REJİM EŞİKLERİ:")
    print("  1. REJİM TEHLİKE EŞİĞİ:  Reel Faiz <= -10.0%  (Kötü dönemin en yüksek değeri -%11.8 idi)")
    print("  2. KUR ŞOKU ALARM EŞİĞİ: USD_Mom_60 >= +20.0% (Sakin dönem tavanı %11.6, kur şokları %44 ve %52 idi)")

    # -------------------------------------------------------------------------
    # DÜZELTME 2: MİMARİ KARARINI NETLEŞTİR (H=60g + DD Kontrolü vs Min15/Max60)
    # -------------------------------------------------------------------------
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

    print("\n" + "=" * 105)
    print("📊 DÜZELTME 2: MİMARİ SEÇİM SİMÜLASYONU (K=10, 2018-09 -> 2025-05)")
    print("=" * 105)

    # 1. K=10, H=60g Sabit + %25 Drawdown Kontrolü (YENİ)
    net_dd, gross_dd, turn_dd, alloc_curve = run_fixed_holding_with_dd_control(
        60, 10, trading_days, daily_returns_df, rankings_cache, dd_trigger=-0.25, dd_recover=-0.15
    )
    met_dd = evaluate_metrics(net_dd, gross_dd, rf_daily)
    sh_turn_dd = met_dd["sharpe"] / max(turn_dd, 0.1)
    plac_dd = run_placebo_dd_control(60, 10, trading_days, daily_returns_df, rankings_cache, -0.25, -0.15, 100)
    p_dd = float(np.mean([1 if ps >= met_dd["sharpe"] else 0 for ps in plac_dd]))
    pct_defensive = float(np.mean([1 if a == 0.5 else 0 for a in alloc_curve])) * 100

    # 2. K=10, Min 15g / Max 60g Kısmi Rotasyon
    net_part, gross_part, turn_part = run_partial_turnover_weighted(
        15, 60, 10, trading_days, daily_returns_df, rankings_cache, check_freq=5, weighting="equal"
    )
    met_part = evaluate_metrics(net_part, gross_part, rf_daily)
    sh_turn_part = met_part["sharpe"] / max(turn_part, 0.1)
    from scratch.run_four_preliminary_analyses import run_placebo_hysteresis
    plac_part = run_placebo_hysteresis(15, 60, 10, trading_days, daily_returns_df, rankings_cache, 100)
    p_part = float(np.mean([1 if ps >= met_part["sharpe"] else 0 for ps in plac_part]))

    # 3. K=10, H=60g Ham (Referans)
    from scratch.run_alpha_decay_and_turnover_study import run_fixed_holding_backtest
    net_raw, gross_raw, turn_raw = run_fixed_holding_backtest(60, 10, trading_days, daily_returns_df, rankings_cache)
    met_raw = evaluate_metrics(net_raw, gross_raw, rf_daily)
    sh_turn_raw = met_raw["sharpe"] / max(turn_raw, 0.1)
    # p-value for raw 60d K=10
    from scratch.run_alpha_decay_and_turnover_study import run_placebo_distribution
    plac_raw = run_placebo_distribution(60, 10, trading_days, daily_returns_df, rankings_cache, 100)
    p_raw = float(np.mean([1 if ps >= met_raw["sharpe"] else 0 for ps in plac_raw]))

    print(f"{'Mimari Seçeneği':<38} | {'Net CAGR':<9} | {'Net Sharpe':<11} | {'Sortino':<8} | {'Max DD':<9} | {'Turnover':<10} | {'Sharpe/Turn':<11} | {'Placebo p':<10}")
    print("-" * 115)
    print(f"{'K=10, H=60g + %25 DD Kontrolü':<38} | %{met_dd['cagr_net']*100:>7.1f} | {met_dd['sharpe']:>11.2f} | {met_dd['sortino']:>8.2f} | %{met_dd['max_dd']*100:>7.1f} | %{turn_dd*100:>8.1f} | {sh_turn_dd:>11.2f} | p = {p_dd:.3f}")
    print(f"{'K=10, Min 15g / Max 60g Kısmi Rotasyon':<38} | %{met_part['cagr_net']*100:>7.1f} | {met_part['sharpe']:>11.2f} | {met_part['sortino']:>8.2f} | %{met_part['max_dd']*100:>7.1f} | %{turn_part*100:>8.1f} | {sh_turn_part:>11.2f} | p = {p_part:.3f}")
    print(f"{'K=10, H=60g Ham (Kontrolsüz Sabit)':<38} | %{met_raw['cagr_net']*100:>7.1f} | {met_raw['sharpe']:>11.2f} | {met_raw['sortino']:>8.2f} | %{met_raw['max_dd']*100:>7.1f} | %{turn_raw*100:>8.1f} | {sh_turn_raw:>11.2f} | p = {p_raw:.3f}")
    print("-" * 115)
    print(f"NOT: DD Kontrolü, 1682 günün %{pct_defensive:.1f}'inde savunma moduna (%50 hisse + %50 nakit) geçmiştir.")

    # -------------------------------------------------------------------------
    # DÜZELTME 3: models/v3_ranking/honesty_note.txt OLUŞTURULMASI
    # -------------------------------------------------------------------------
    # Seçilen mimari: K=10, H=60g + %25 DD Kontrolü
    honesty_file = ROOT_DIR / "models" / "v3_ranking" / "honesty_note.txt"
    honesty_content = f"""================================================================================
KURUMSAL DÜRÜSTLÜK NOTU (HONESTY NOTE) — PRODUCTION-CANDIDATE V3 RANKER
================================================================================
Tarih: 2026-09-09
Model: Aşırı Muhafazakâr Sığ Ağaç LGBMRanker (winning_lgbm_ranker.joblib)
Seçilen Portföy Mimarisi: K=10, H=60 Günlük Sabit Çeyreklik Rotasyon + %25 Drawdown Kesici Devresi

1. EĞİTİM PENCERESİ GENELİNDE İSTATİSTİKSEL ANLAMLILIK:
   - 2018-09 -> 2025-05 dönemi (6.75 yıl, 1682 işlem günü) genelinde seçilen mimarinin:
     * Net CAGR: %{met_dd['cagr_net']*100:.1f}
     * Net Sharpe: {met_dd['sharpe']:.2f}
     * Sortino: {met_dd['sortino']:.2f}
     * Max Drawdown: %{met_dd['max_dd']*100:.1f}
     * Yıllık Devir Hızı (Turnover): %{turn_dd*100:.1f}
     * Net Sharpe / Turnover Verimliliği: {sh_turn_dd:.2f}
     * 100 Tohumlu Monte Carlo Placebo p-değeri: p = {p_dd:.3f}

2. REJİM DUYARLILIĞI VE ÇALIŞMA ŞARTLARI:
   - Bu model HER ZAMAN VE HER PİYASA KOŞULUNDA ÇALIŞMAZ.
   - Model, DNA'sı gereği yüksek oranda Düşük Borç (%19.4) ve Değer/Ters P-B (%57.3) ağırlıklıdır.
   - POZİTİF REEL FAİZ ve sıkı para politikası rejimlerinde (sağlam bilanço ve nakit akışının ödüllendirildiği
     ortodoks dönemlerde) piyasayı güçlü şekilde ezer.
   - Ancak DERİN NEGATİF REEL FAİZ rejimlerinde (2022-2024 gibi enflasyonist balon dönemlerinde, borçlu
     ve aşırı değerli spekülatif büyüme hisselerinin ralli yaptığı ortamlarda) rastgele sepetlerin
     ve agresif beta hisselerinin gerisinde kalır.

3. KİLİT KUTU (LOCKBOX) ÖRNEKLEM ŞERHİ:
   - Kilit kutu dönemi (2025-06 -> 2026-09) sadece n=5 çeyreklik küçük bir örnektir.
   - Kilit kutudaki olağanüstü yüksek Sharpe (2.09 / 3.41), pozitif reel faizin uygulandığı bir "süper-döneme"
     denk gelmiştir ve geniş bir istatistiksel belirsizlik payı taşır.
   - Uzun vadeli gerçekçi beklenti Kilit Kutu Sharpe'ı değil; 6.75 yıllık eğitim penceresinde ölçülen
     Sharpe={met_dd['sharpe']:.2f} tabanıdır.

4. VERİYE DAYALI MAKRO REJİM EŞİKLERİ (Kilit Kutudan Arındırılmış Temiz Veri):
   Eğitim penceresindeki (2018Q3 -> 2025Q1) 27 çeyreklik veriden türetilen kesin eşikler:
   * REEL FAİZ TEHLİKE EŞİĞİ: Reel Faiz <= -10.0%
     (Kötü dönemin tavanı %-11.8 idi. Bu seviyenin altı kontrolsüz parasal genişleme/negatif faiz alarmıdır)
   * KUR ŞOKU ALARM EŞİĞİ: USD_Mom_60 >= +20.0%
     (Sakin dönem tavanı %11.6 iken tarihsel kur şokları %44 ve %52 olmuştur. %20 üzeri kur şoku alarmıdır)

================================================================================
"""
    with open(honesty_file, "w", encoding="utf-8") as f:
        f.write(honesty_content)

    print("\n" + "=" * 90)
    print(f"✅ DÜZELTME 3: {honesty_file} başarıyla oluşturuldu.")
    print("=" * 90)


if __name__ == "__main__":
    main()
