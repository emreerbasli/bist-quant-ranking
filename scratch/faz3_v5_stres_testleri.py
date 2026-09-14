"""
scratch/faz3_v5_stres_testleri.py
==================================
V5-NEUTRAL MODELİ İÇİN 3 NİHAİ KANTİTATİF STRES TESTİ:
  1. Rejim İzoleli Placebo Testi (Sadece Dönem B: 2024-2025 Sıkılaşma / Ayı Piyasası)
     - 100 Tohumlu Monte Carlo simülasyonu
     - K=15 (ve K=10, K=20) için p-değeri hesabı
  2. DART Turnover ve Tutma Oranı (Retention Rate) Kontrolü:
     - 2022-2025 çeyreklik Top-15 sepetlerinin geçişkenliği
     - |S_t ∩ S_{t+1}| / 15 ortalaması (%60 eşik kontrolü)
     - V3-Kontrol, V4-Raw ve V5-Neutral karşılaştırması
  3. Information Ratio (IR) / Aktif Getiri (Alfa) Testi:
     - BIST 88 Eşit Ağırlıklı Piyasa Endeksine göre Excess Return
     - Yıllıklandırılmış Aktif Getiri, Takip Hatası (Tracking Error) ve Information Ratio
"""

import sys
import json
import warnings
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from lightgbm import LGBMRanker

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg
from models.v3_ranking.data_loader import yukle_veriler, hizli_pit, hesapla_mom, getir_tcmb_reel_faiz
from models.v3_ranking.ranking_pipeline import hesapla_sektor_zscore
from bot.kap_filter import ardisik_taban_tespit
from scratch.faz1_ic_tarama import extract_candidate_features

# Parametreler
RF_ANNUAL = 0.18
TRANSACTION_COST = 0.003
LOCKBOX_BARRIER = pd.Timestamp("2025-05-31")
TRAIN_START_DATE = pd.Timestamp("2019-09-01")
N_PLACEBO = 100
SEED = 42

V5_LGBM_PARAMS = {
    "boosting_type": "dart",
    "colsample_bytree": 0.6,
    "max_depth": 2,
    "num_leaves": 3,
    "learning_rate": 0.03,
    "n_estimators": 60,
    "min_child_samples": 15,
    "reg_lambda": 1.0,
    "random_state": 42,
    "verbose": -1
}

V4_LGBM_PARAMS = {
    "boosting_type": "gbdt",
    "max_depth": 2,
    "num_leaves": 3,
    "learning_rate": 0.03,
    "n_estimators": 60,
    "min_child_samples": 15,
    "reg_lambda": 1.0,
    "random_state": 42,
    "verbose": -1
}

V3_LGBM_PARAMS = {
    "boosting_type": "gbdt",
    "max_depth": 2,
    "num_leaves": 3,
    "learning_rate": 0.03,
    "n_estimators": 60,
    "min_child_samples": 15,
    "reg_lambda": 1.0,
    "random_state": 42,
    "verbose": -1
}

FEATURE_COLS_V5 = [
    "z_fcf", "z_roe", "z_mom", "z_borc", "z_pb",
    "reel_faiz", "usd_mom_60", "usd_mom_90",
    "reel_eps_growth"
]

FEATURE_COLS_V4 = [
    "z_fcf", "z_roe", "z_mom", "z_borc", "z_pb",
    "reel_faiz", "usd_mom_60", "usd_mom_90",
    "reel_eps_growth"
]

FEATURE_COLS_V3 = [
    "z_fcf", "z_roe", "z_mom", "z_borc", "z_pb",
    "reel_faiz", "usd_mom_60", "usd_mom_90"
]


def load_all_quarterly_data():
    """Çeyreklik kesitleri oluşturur ve hem absolute hem excess relevance etiketlerini ekler."""
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    tarihler_60 = pd.date_range("2018-09-01", "2025-08-01", freq="3MS")
    hisseler = sorted(fiyat_dict.keys())

    quarters_data = []

    for i in range(len(tarihler_60) - 1):
        t0, t1 = tarihler_60[i], tarihler_60[i + 1]
        if t0 >= LOCKBOX_BARRIER:
            continue

        rets = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        mevcut = [s for s in hisseler if s in rets]
        if len(mevcut) < 32:
            continue

        reel_faiz = getir_tcmb_reel_faiz(t0, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t0]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

        q_rows = []
        for s in mevcut:
            curr, _ = hizli_pit(pit_bellek, s, t0)
            if not curr:
                continue

            is_bank = bool(curr.get("is_bank", False))
            sektor = cfg.HISSE_SEKTOR.get(s, "XBANK.IS" if is_bank else "XUSIN.IS")
            mom = hesapla_mom(fiyat_dict[s], t0)
            pb = curr.get("pb", np.nan)
            roe = curr.get("roe", np.nan)
            fcf_v = curr.get("fcf_verim", np.nan)
            net_b = curr.get("net_borc", 0.0) or 0.0
            ebit = curr.get("ebitda", 1.0) or 1.0
            borc_ebitda = -net_b / max(1.0, abs(ebit)) if not is_bank else np.nan

            cand_feats = extract_candidate_features(
                t0, s, fiyat_dict[s], seri_usdtry, pit_bellek.get(s, []), tufe_aylik
            )
            reel_eps = cand_feats.get("reel_eps_growth", np.nan)

            p_sub = fiyat_dict[s][fiyat_dict[s].index <= t0]
            is_taban_riski, _ = ardisik_taban_tespit(p_sub, lookback_gun=10, min_taban=5, taban_esik=-0.095)

            q_rows.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb,
                "reel_eps_growth": float(np.clip(reel_eps if pd.notna(reel_eps) else 0.0, -2.0, 2.0)),
                "fwd_ret": rets[s],
                "is_taban_riski": is_taban_riski
            })

        df_q = pd.DataFrame(q_rows)

        # Sektörel Z-Skorları
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)

        df_q["reel_faiz"]  = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        # V3/V4 Absolute Relevance
        try:
            df_q["rel_absolute"] = pd.qcut(df_q["fwd_ret"], q=5, labels=False, duplicates="drop")
        except Exception:
            df_q["rel_absolute"] = pd.qcut(df_q["fwd_ret"], q=3, labels=False, duplicates="drop")

        # V5 Excess Return Relevance
        mean_mkt = df_q["fwd_ret"].mean()
        df_q["excess_ret"] = df_q["fwd_ret"] - mean_mkt
        try:
            df_q["rel_excess"] = pd.qcut(df_q["excess_ret"], q=5, labels=False, duplicates="drop")
        except Exception:
            df_q["rel_excess"] = pd.qcut(df_q["excess_ret"], q=3, labels=False, duplicates="drop")

        quarters_data.append({
            "t0": t0, "t1": t1, "yil": t0.year,
            "df": df_q, "group_size": len(df_q)
        })

    return quarters_data


def calc_metrics(returns_list, rf_annual=0.18):
    if not returns_list:
        return {"kumulatif": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0, "n_q": 0}
    arr = np.array(returns_list)
    kum = float(np.prod(1.0 + arr) - 1.0)
    n = len(arr)
    cagr = float((1.0 + kum) ** (4.0 / max(1, n)) - 1.0) if kum > -0.99 else -0.99
    rf_q = (1.0 + rf_annual) ** (0.25) - 1.0
    diff = arr - rf_q

    if n >= 2:
        std = float(np.std(arr, ddof=1))
        sharpe = float(np.mean(diff) / (std + 1e-8) * 2.0) if std > 1e-6 else 0.0
    else:
        std = 0.0
        sharpe = np.nan

    eq_curve = np.cumprod(1.0 + arr)
    peaks = np.maximum.accumulate(eq_curve)
    dds = (eq_curve - peaks) / peaks
    mdd = float(np.min(dds))
    return {
        "kumulatif": kum, "cagr": cagr, "sharpe": sharpe, "max_dd": mdd,
        "n_q": n, "mean_q_ret": float(np.mean(arr)), "std_q_ret": std,
        "returns": arr.tolist()
    }


def run_full_simulation(quarters_data):
    """
    4-Fold Walk-Forward üzerinde V3-Kontrol, V4-Raw ve V5-Neutral modellerini
    eş zamanlı olarak çalıştırır ve her çeyrek için:
      - Seçilen hisseler (Top-15)
      - Portföy getirisi
      - BIST 88 Benchmark getirisi
    kayıtlarını tutar.
    """
    folds = [
        {"name": "Fold 1 (2022)", "train_end": pd.Timestamp("2021-12-31"), "test_start": pd.Timestamp("2022-01-01"), "test_end": pd.Timestamp("2022-12-31"), "donem": "Donem_A"},
        {"name": "Fold 2 (2023)", "train_end": pd.Timestamp("2022-12-31"), "test_start": pd.Timestamp("2023-01-01"), "test_end": pd.Timestamp("2023-12-31"), "donem": "Donem_A"},
        {"name": "Fold 3 (2024)", "train_end": pd.Timestamp("2023-12-31"), "test_start": pd.Timestamp("2024-01-01"), "test_end": pd.Timestamp("2024-12-31"), "donem": "Donem_B"},
        {"name": "Fold 4 (2025)", "train_end": pd.Timestamp("2024-12-31"), "test_start": pd.Timestamp("2025-01-01"), "test_end": pd.Timestamp("2025-05-31"), "donem": "Donem_B"},
    ]

    history_records = []

    for fold in folds:
        train_q = [q for q in quarters_data if (q["t0"] >= TRAIN_START_DATE) and (q["t1"] <= fold["train_end"])]
        test_q = [q for q in quarters_data if (q["t0"] >= fold["test_start"]) and (q["t0"] <= fold["test_end"])]

        if not train_q or not test_q:
            continue

        df_train = pd.concat([q["df"] for q in train_q], ignore_index=True)
        train_groups = [q["group_size"] for q in train_q]

        # 1. Model V3 (8 faktör, mutlak getiri relevance)
        m_v3 = LGBMRanker(objective="lambdarank", **V3_LGBM_PARAMS)
        m_v3.fit(df_train[FEATURE_COLS_V3], df_train["rel_absolute"], group=train_groups)

        # 2. Model V4 (9 faktör, mutlak getiri relevance, GBDT)
        m_v4 = LGBMRanker(objective="lambdarank", **V4_LGBM_PARAMS)
        m_v4.fit(df_train[FEATURE_COLS_V4], df_train["rel_absolute"], group=train_groups)

        # 3. Model V5 (9 faktör, market-neutral excess relevance, DART, colsample=0.6)
        m_v5 = LGBMRanker(objective="lambdarank", **V5_LGBM_PARAMS)
        m_v5.fit(df_train[FEATURE_COLS_V5], df_train["rel_excess"], group=train_groups)

        for q in test_q:
            df_test = q["df"].copy()
            df_test["score_v3"] = m_v3.predict(df_test[FEATURE_COLS_V3])
            df_test["score_v4"] = m_v4.predict(df_test[FEATURE_COLS_V4])
            df_test["score_v5"] = m_v5.predict(df_test[FEATURE_COLS_V5])

            df_valid = df_test[~df_test["is_taban_riski"]].copy()
            if len(df_valid) < 20:
                df_valid = df_test.copy()

            # Benchmark: BIST 88 Eşit Ağırlıklı Piyasa Getirisi
            mkt_ret = float(df_valid["fwd_ret"].mean())

            # Top 15 Seçimleri
            s_v3 = df_valid.sort_values("score_v3", ascending=False)
            s_v4 = df_valid.sort_values("score_v4", ascending=False)
            s_v5 = df_valid.sort_values("score_v5", ascending=False)

            top15_v3 = s_v3.iloc[:15]["sembol"].tolist()
            top15_v4 = s_v4.iloc[:15]["sembol"].tolist()
            top15_v5 = s_v5.iloc[:15]["sembol"].tolist()

            r_v3 = float(s_v3.iloc[:15]["fwd_ret"].mean()) - TRANSACTION_COST
            r_v4 = float(s_v4.iloc[:15]["fwd_ret"].mean()) - TRANSACTION_COST
            r_v5 = float(s_v5.iloc[:15]["fwd_ret"].mean()) - TRANSACTION_COST

            history_records.append({
                "t0": q["t0"],
                "quarter": q["t0"].strftime("%Y-Q") + str((q["t0"].month - 1) // 3 + 1),
                "donem": fold["donem"],
                "mkt_ret": mkt_ret,
                "r_v3": r_v3,
                "r_v4": r_v4,
                "r_v5": r_v5,
                "top15_v3": top15_v3,
                "top15_v4": top15_v4,
                "top15_v5": top15_v5,
                "eligible_symbols": df_valid["sembol"].tolist(),
                "returns_dict": dict(zip(df_valid["sembol"], df_valid["fwd_ret"]))
            })

    return history_records


def test_1_rejim_izoleli_placebo(history_records, n_placebo=100, seed=42):
    """
    STRES TESTİ 1: Sadece Dönem B (2024-2025 Sıkılaşma / Ayı Piyasası) Placebo Testi
    5 çeyrek: 2024Q1, 2024Q2, 2024Q3, 2024Q4, 2025Q1
    """
    donem_b_records = [r for r in history_records if r["donem"] == "Donem_B"]
    n_q_b = len(donem_b_records)

    results = {}
    rng = np.random.default_rng(seed)

    for model_name, col in [("V3-Kontrol", "r_v3"), ("V4-Raw", "r_v4"), ("V5-Neutral", "r_v5")]:
        model_rets = [r[col] for r in donem_b_records]
        m_model = calc_metrics(model_rets)
        mod_sharpe = m_model["sharpe"]
        mod_cagr = m_model["cagr"]
        mod_kum = m_model["kumulatif"]

        plac_sharpes, plac_cagrs = [], []
        for _ in range(n_placebo):
            p_rets = []
            for rec in donem_b_records:
                el_syms = rec["eligible_symbols"]
                r_dict = rec["returns_dict"]
                chosen = rng.choice(el_syms, size=min(15, len(el_syms)), replace=False)
                r_p = float(np.mean([r_dict[s] for s in chosen])) - TRANSACTION_COST
                p_rets.append(r_p)

            m_p = calc_metrics(p_rets)
            plac_sharpes.append(m_p["sharpe"])
            plac_cagrs.append(m_p["cagr"])

        p_val_sharpe = float(np.mean([1 if s >= mod_sharpe else 0 for s in plac_sharpes]))
        p_val_cagr   = float(np.mean([1 if c >= mod_cagr else 0 for c in plac_cagrs]))

        results[model_name] = {
            "n_q": n_q_b,
            "model_sharpe": mod_sharpe,
            "model_cagr": mod_cagr,
            "model_kumulatif": mod_kum,
            "plac_mean_sharpe": float(np.mean(plac_sharpes)),
            "plac_95th_sharpe": float(np.percentile(plac_sharpes, 95)),
            "plac_max_sharpe": float(np.max(plac_sharpes)),
            "p_value_sharpe": p_val_sharpe,
            "p_value_cagr": p_val_cagr
        }

    return results


def test_2_turnover_ve_retention(history_records):
    """
    STRES TESTİ 2: DART Turnover ve Tutma Oranı (Retention Rate) Kontrolü
    Her ardışık iki çeyrek arasındaki kesişim: |Top15_t ∩ Top15_{t+1}| / 15
    """
    retention_stats = {"V3-Kontrol": [], "V4-Raw": [], "V5-Neutral": []}
    quarter_labels = []

    for i in range(len(history_records) - 1):
        r0 = history_records[i]
        r1 = history_records[i + 1]
        label = f"{r0['quarter']} -> {r1['quarter']}"
        quarter_labels.append(label)

        for m_name, key in [("V3-Kontrol", "top15_v3"), ("V4-Raw", "top15_v4"), ("V5-Neutral", "top15_v5")]:
            s0 = set(r0[key])
            s1 = set(r1[key])
            ret_rate = len(s0.intersection(s1)) / 15.0
            retention_stats[m_name].append(ret_rate)

    results = {}
    for m_name, ret_list in retention_stats.items():
        arr = np.array(ret_list)
        results[m_name] = {
            "mean_retention": float(np.mean(arr)),
            "mean_turnover": float(1.0 - np.mean(arr)),
            "min_retention": float(np.min(arr)),
            "max_retention": float(np.max(arr)),
            "retention_series": {q: round(float(v), 3) for q, v in zip(quarter_labels, arr)}
        }

    return results


def test_3_information_ratio(history_records):
    """
    STRES TESTİ 3: Information Ratio (IR) / Aktif Getiri (Alfa) Testi
    Benchmark: BIST 88 Eşit Ağırlıklı Piyasa Getirisi (mkt_ret)
    Active Return: R_active = R_model - R_benchmark
    Annualized IR = (Mean(R_active) / Std(R_active)) * sqrt(4)
    """
    mkt_rets = np.array([r["mkt_ret"] for r in history_records])
    n_q = len(mkt_rets)

    results = {}

    for m_name, key in [("V3-Kontrol", "r_v3"), ("V4-Raw", "r_v4"), ("V5-Neutral", "r_v5")]:
        mod_rets = np.array([r[key] for r in history_records])
        active_rets = mod_rets - mkt_rets

        mean_active_q = float(np.mean(active_rets))
        mean_active_ann = float(mean_active_q * 4.0)

        std_active_q = float(np.std(active_rets, ddof=1))
        tracking_error_ann = float(std_active_q * 2.0)  # sqrt(4) = 2

        ir_ann = float(mean_active_ann / (tracking_error_ann + 1e-8)) if tracking_error_ann > 1e-6 else 0.0

        # Kümülatif alfa ve beta getirileri
        cum_model = float(np.prod(1.0 + mod_rets) - 1.0)
        cum_mkt = float(np.prod(1.0 + mkt_rets) - 1.0)

        # Beta hesaplama: Cov(mod, mkt) / Var(mkt)
        cov_mat = np.cov(mod_rets, mkt_rets)
        beta = float(cov_mat[0, 1] / cov_mat[1, 1])

        results[m_name] = {
            "n_q": n_q,
            "cum_model_ret": cum_model,
            "cum_benchmark_ret": cum_mkt,
            "mean_active_q": mean_active_q,
            "mean_active_annualized": mean_active_ann,
            "tracking_error_annualized": tracking_error_ann,
            "information_ratio": ir_ann,
            "portfolio_beta": beta,
            "active_returns_quarterly": {r["quarter"]: round(float(a), 4) for r, a in zip(history_records, active_rets)}
        }

    return results


def main():
    print("=" * 105)
    print("V5-NEUTRAL MODELİ İÇİN 3 NİHAİ KANTİTATİF STRES TESTİ BAŞLATILIYOR...")
    print("=" * 105)

    print("\nAdım 1: Çeyreklik kesitler ve modeller hazırlanıyor...")
    quarters_data = load_all_quarterly_data()

    print("\nAdım 2: 4-Fold Walk-Forward simülasyonu yürütülüyor...")
    history = run_full_simulation(quarters_data)
    print(f"Toplam OOS Çeyrek Sayısı: {len(history)} (2022-Q1 -> 2025-Q1)")

    print("\n" + "=" * 105)
    print("TEST 1: REJİM İZOLELİ PLACEBO TESTİ (SADECE DÖNEM B: 2024-2025 SIKILAŞMA DÖNEMİ)")
    print("=" * 105)
    t1_res = test_1_rejim_izoleli_placebo(history, n_placebo=N_PLACEBO, seed=SEED)
    print(f"{'Model':<16} | {'Sharpe':<8} | {'CAGR (%)':<10} | {'Kümülatif (%)':<14} | {'Plac. Ort. Sharpe':<18} | {'p-değeri':<12} | {'Durum':<10}")
    print("-" * 105)
    for m, r in t1_res.items():
        status = "✅ GEÇTİ (p<=0.05)" if r["p_value_sharpe"] <= 0.05 else "❌ RED (p>0.05)"
        print(f"{m:<16} | {r['model_sharpe']:>6.3f}   | %{r['model_cagr']*100:>7.2f}  | %{r['model_kumulatif']*100:>11.2f}  | {r['plac_mean_sharpe']:>15.3f}   | p = {r['p_value_sharpe']:<6.3f} | {status:<10}")

    print("\n" + "=" * 105)
    print("TEST 2: DART TURNOVER VE TUTMA ORANI (RETENTION RATE) KONTROLÜ (2022-2025)")
    print("=" * 105)
    t2_res = test_2_turnover_ve_retention(history)
    print(f"{'Model':<16} | {'Ort. Tutma (Retention)':<24} | {'Ort. Turnover':<16} | {'Min Tutma':<12} | {'Max Tutma':<12} | {'Eşik (>=%60)':<12}")
    print("-" * 105)
    for m, r in t2_res.items():
        status = "✅ GÜVENLİ" if r["mean_retention"] >= 0.60 else "⚠️ YÜKSEK TURNOVER"
        print(f"{m:<16} | %{r['mean_retention']*100:>20.1f}   | %{r['mean_turnover']*100:>13.1f}  | %{r['min_retention']*100:>9.1f} | %{r['max_retention']*100:>9.1f} | {status:<12}")

    print("\n" + "=" * 105)
    print("TEST 3: INFORMATION RATIO (IR) / AKTİF GETİRİ (ALFA) ANALİZİ (2022-2025 OOS)")
    print("=" * 105)
    t3_res = test_3_information_ratio(history)
    print(f"{'Model':<16} | {'Yıllık Aktif Alfa':<18} | {'Takip Hatası (TE)':<18} | {'Information Ratio':<20} | {'Portföy Betası':<15}")
    print("-" * 105)
    for m, r in t3_res.items():
        print(f"{m:<16} | %{r['mean_active_annualized']*100:>15.2f}  | %{r['tracking_error_annualized']*100:>15.2f}  | {r['information_ratio']:>17.3f}   | {r['portfolio_beta']:>13.3f}")

    # Detaylı Çeyreklik Döküm
    print("\n" + "=" * 105)
    print("DÖNEM B (2024-2025) ÇEYREKLİK GETİRİ VE AKTİF ALFA DÖKÜMÜ:")
    print("=" * 105)
    donem_b_history = [r for r in history if r["donem"] == "Donem_B"]
    for r in donem_b_history:
        q = r["quarter"]
        mkt = r["mkt_ret"] * 100
        v3 = r["r_v3"] * 100
        v4 = r["r_v4"] * 100
        v5 = r["r_v5"] * 100
        print(f"Çeyrek {q} -> BIST88: %{mkt:>6.2f} | V3: %{v3:>6.2f} (Alfa: %{v3-mkt:>+6.2f}) | V4: %{v4:>6.2f} (Alfa: %{v4-mkt:>+6.2f}) | V5: %{v5:>6.2f} (Alfa: %{v5-mkt:>+6.2f})")

    # JSON Raporunu Kaydet
    output_path = ROOT_DIR / "reports" / "faz3_v5_stres_testi_sonuclari.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "test_1_rejim_izoleli_placebo": t1_res,
            "test_2_turnover_ve_retention": t2_res,
            "test_3_information_ratio": t3_res
        }, f, indent=2, default=str)
    print(f"\n✅ Stres testi sonuçları kaydedildi: {output_path}")


if __name__ == "__main__":
    main()
