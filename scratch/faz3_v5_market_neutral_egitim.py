"""
scratch/faz3_v5_market_neutral_egitim.py
=========================================
FAZ 3 V5: MARKET-NEUTRAL ALPHA MODELİ VE PLACEBO DOĞRULAMASI
-------------------------------------------------------------
Kullanıcı Direktifleri Uyarınca 3 Yapısal Mimari Değişikliği:
  1. Hedef Nötralizasyonu (Cross-Sectional Target):
     - Her çeyrek kesiti için: excess_ret = fwd_ret - fwd_ret.mean()
     - Relevance hedefi: pd.qcut(excess_ret, q=5, labels=False, duplicates="drop") (0-4 quintiles)
  2. Açgözlülük Engelleyici (DART & Feature Fraction):
     - boosting_type = "dart" (Dropout ile faktör tekelini kırma)
     - colsample_bytree = 0.6 (Her ağaçta rastgele %60 özellik seçimi)
     - Sığ ağaç (max_depth=2, num_leaves=3, min_child_samples=15)
  3. Yeni Eğitim ve 100-Tohumlu Placebo Testi:
     - 4-Fold Purged Walk-Forward (2022-2025)
     - K=10, K=15, K=20 için Sharpe ve ampirik p-değerleri
     - Feature Importance (Gain payları ve kök düğüm analizi)
"""

import sys
import json
import joblib
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import warnings
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
TRANSACTION_COST = 0.003  # %0.30 rebalance maliyeti
LOCKBOX_BARRIER = pd.Timestamp("2025-05-31")
N_PLACEBO = 100
SEED = 42
K_VALUES = [10, 15, 20]

# V5 Hiperparametreleri (DART + colsample=0.6)
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

FEATURE_COLS_V5 = [
    "z_fcf", "z_roe", "z_mom", "z_borc", "z_pb",
    "reel_faiz", "usd_mom_60", "usd_mom_90",
    "reel_eps_growth"
]


def build_v5_neutralized_dataset():
    """
    Hedef nötralizasyonu uygulanmış (excess_ret üzerinden 0-4 quintile relevance)
    çeyreklik veri setini inşa eder.
    """
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

        # ─── 1. HEDEF NÖTRALİZASYONU: MARKET-NEUTRAL EXCESS RETURN ───
        # Her çeyrekte pazar ortalaması (beta) çıkarılır:
        mean_market_ret = df_q["fwd_ret"].mean()
        df_q["excess_ret"] = df_q["fwd_ret"] - mean_market_ret

        # Relevance skorları (0 - 4 arası 5 quintile):
        try:
            df_q["relevance"] = pd.qcut(df_q["excess_ret"], q=5, labels=False, duplicates="drop")
        except Exception:
            df_q["relevance"] = pd.qcut(df_q["excess_ret"], q=3, labels=False, duplicates="drop")

        quarters_data.append({
            "t0": t0, "t1": t1, "yil": t0.year,
            "df": df_q, "group_size": len(df_q)
        })

    print(f"V5 Nötralize Veri Seti Üretildi: {len(quarters_data)} Çeyrek ({quarters_data[0]['t0'].strftime('%Y-%m')} -> {quarters_data[-1]['t1'].strftime('%Y-%m')})")
    return quarters_data


def hesapla_metrikler(returns_list, rf_annual=0.18):
    """Portföy quarterly metriklerini hesaplar."""
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
        "kumulatif": kum,
        "cagr": cagr,
        "sharpe": sharpe,
        "max_dd": mdd,
        "n_q": n,
        "mean_q_ret": float(np.mean(arr)),
        "std_q_ret": std,
        "returns": arr.tolist()
    }


def run_v5_evaluation_and_placebo(quarters_data):
    """
    V5 modelini 4-Fold Purged Walk-Forward ile eğitir, OOS getirilerini hesaplar
    ve 100-tohumlu Placebo testini çalıştırır.
    """
    train_start_date = pd.Timestamp("2019-09-01")
    folds = [
        {"name": "Fold 1 (2022)", "train_end": pd.Timestamp("2021-12-31"), "test_start": pd.Timestamp("2022-01-01"), "test_end": pd.Timestamp("2022-12-31"), "donem": "Donem_A"},
        {"name": "Fold 2 (2023)", "train_end": pd.Timestamp("2022-12-31"), "test_start": pd.Timestamp("2023-01-01"), "test_end": pd.Timestamp("2023-12-31"), "donem": "Donem_A"},
        {"name": "Fold 3 (2024)", "train_end": pd.Timestamp("2023-12-31"), "test_start": pd.Timestamp("2024-01-01"), "test_end": pd.Timestamp("2024-12-31"), "donem": "Donem_B"},
        {"name": "Fold 4 (2025)", "train_end": pd.Timestamp("2024-12-31"), "test_start": pd.Timestamp("2025-01-01"), "test_end": pd.Timestamp("2025-05-31"), "donem": "Donem_B"},
    ]

    test_quarter_records = []
    oos_k_returns = {10: [], 15: [], 20: []}
    yearly_results = {}

    for fold in folds:
        train_q = [q for q in quarters_data if (q["t0"] >= train_start_date) and (q["t1"] <= fold["train_end"])]
        test_q = [q for q in quarters_data if (q["t0"] >= fold["test_start"]) and (q["t0"] <= fold["test_end"])]

        if not train_q or not test_q:
            continue

        df_train = pd.concat([q["df"] for q in train_q], ignore_index=True)
        train_groups = [q["group_size"] for q in train_q]

        model = LGBMRanker(objective="lambdarank", **V5_LGBM_PARAMS)
        model.fit(df_train[FEATURE_COLS_V5], df_train["relevance"], group=train_groups)

        fold_rets_k15 = []

        for q in test_q:
            df_test = q["df"].copy()
            preds = model.predict(df_test[FEATURE_COLS_V5])
            df_test["model_score"] = preds

            # Faz 0 Hard Exclusion
            df_valid = df_test[~df_test["is_taban_riski"]].copy()
            if len(df_valid) < 20:
                df_valid = df_test.copy()

            df_sorted = df_valid.sort_values("model_score", ascending=False)

            for k in K_VALUES:
                top_k = df_sorted.iloc[:k]
                r_k = float(top_k["fwd_ret"].mean()) - TRANSACTION_COST
                oos_k_returns[k].append(r_k)
                if k == 15:
                    fold_rets_k15.append(r_k)

            test_quarter_records.append({
                "t0": q["t0"],
                "df_sorted": df_sorted,
                "eligible_symbols": df_valid["sembol"].tolist(),
                "returns_dict": dict(zip(df_valid["sembol"], df_valid["fwd_ret"]))
            })

        yearly_results[fold["name"]] = hesapla_metrikler(fold_rets_k15)

    # 100 Tohumlu Placebo Simülasyonu
    rng = np.random.default_rng(SEED)
    k_results = {}

    for k in K_VALUES:
        m_model = hesapla_metrikler(oos_k_returns[k])
        model_sharpe = m_model["sharpe"]

        plac_sharpes, plac_cagrs = [], []
        for p_i in range(N_PLACEBO):
            plac_rets = []
            for rec in test_quarter_records:
                el_syms = rec["eligible_symbols"]
                r_dict = rec["returns_dict"]
                chosen = rng.choice(el_syms, size=min(k, len(el_syms)), replace=False)
                r_p = float(np.mean([r_dict[s] for s in chosen])) - TRANSACTION_COST
                plac_rets.append(r_p)

            m_p = hesapla_metrikler(plac_rets)
            plac_sharpes.append(m_p["sharpe"])
            plac_cagrs.append(m_p["cagr"])

        p_val_sharpe = float(np.mean([1 if s >= model_sharpe else 0 for s in plac_sharpes]))
        p_val_cagr   = float(np.mean([1 if c >= m_model["cagr"] else 0 for c in plac_cagrs]))

        k_results[k] = {
            "model_sharpe": model_sharpe,
            "model_cagr": m_model["cagr"],
            "model_kumulatif": m_model["kumulatif"],
            "model_max_dd": m_model["max_dd"],
            "plac_mean_sharpe": float(np.mean(plac_sharpes)),
            "plac_95th_sharpe": float(np.percentile(plac_sharpes, 95)),
            "plac_max_sharpe": float(np.max(plac_sharpes)),
            "p_value_sharpe": p_val_sharpe,
            "p_value_cagr": p_val_cagr
        }

    return k_results, yearly_results


def analyze_v5_full_model(quarters_data):
    """
    V5 modelini tüm 2019-09 -> 2025-05 kümesinde eğitir,
    faktör Gain paylarını ve düğüm dağılımlarını çıkarır.
    """
    train_start_date = pd.Timestamp("2019-09-01")
    train_q = [q for q in quarters_data if (q["t0"] >= train_start_date) and (q["t1"] <= LOCKBOX_BARRIER)]
    df_all = pd.concat([q["df"] for q in train_q], ignore_index=True)
    groups = [q["group_size"] for q in train_q]

    model = LGBMRanker(objective="lambdarank", **V5_LGBM_PARAMS)
    model.fit(df_all[FEATURE_COLS_V5], df_all["relevance"], group=groups)

    imp_split = model.feature_importances_
    imp_gain = model.booster_.feature_importance(importance_type="gain")
    df_imp = pd.DataFrame({
        "feature": FEATURE_COLS_V5,
        "split": imp_split,
        "gain": imp_gain
    }).sort_values("gain", ascending=False)
    df_imp["gain_pct"] = df_imp["gain"] / df_imp["gain"].sum() * 100.0

    # Ağaç yapısı kök düğüm incelemesi
    tree_dump = model.booster_.dump_model()["tree_info"]
    root_splits = {}
    for tree in tree_dump:
        struct = tree["tree_structure"]
        if "split_feature" in struct:
            f = FEATURE_COLS_V5[struct["split_feature"]]
            root_splits[f] = root_splits.get(f, 0) + 1

    return model, df_imp, root_splits


def main():
    print("=" * 115)
    print("FAZ 3 V5: MARKET-NEUTRAL ALPHA MODELİ VE 100-TOHUMLU PLACEBO TESTİ")
    print("Mimarî Değişiklikler: 1) Excess Return Quintiles (0-4) | 2) DART Boosting | 3) Colsample=0.6")
    print("=" * 115)

    quarters_data = build_v5_neutralized_dataset()

    print("\n1. V5 Modeli Walk-Forward OOS (2022-2025) ve 100-Tohumlu Placebo Testi çalıştırılıyor...")
    k_res_v5, yearly_v5 = run_v5_evaluation_and_placebo(quarters_data)

    print("\n2. V5 Modeli tüm eğitim kümesinde (2019-09 -> 2025-05) eğitiliyor ve Gain dağılımı çıkarılıyor...")
    model_v5, df_imp_v5, root_splits_v5 = analyze_v5_full_model(quarters_data)

    # Önceki Sonuçları Yükle (Karşılaştırma İçin)
    old_res_path = ROOT_DIR / "reports" / "faz3_placebo_ve_gain_analizi.json"
    with open(old_res_path, "r", encoding="utf-8") as f:
        old_data = json.load(f)
    old_v4 = old_data["placebo_v4"]
    old_v3 = old_data["placebo_v3"]

    print("\n" + "=" * 125)
    print("ÜÇ KUŞAK KARŞILAŞTIRMASI: V3-KONTROL vs V4-RAW vs V5-NEUTRAL (100-TOHUMLU PLACEBO TESTİ)")
    print("=" * 125)
    print(f"{'Model':<16} | {'K':<4} | {'Sharpe':<10} | {'CAGR (%)':<10} | {'Max DD':<10} | {'Placebo Ort.':<14} | {'p-değeri (Sharpe)':<18} | {'Durum':<12}")
    print("-" * 125)

    for k in K_VALUES:
        r3 = old_v3[str(k)]
        r4 = old_v4[str(k)]
        r5 = k_res_v5[k]

        def get_stat(p, k_val):
            if k_val == 15:
                return "✅ GEÇTİ" if p <= 0.05 else "❌ RED"
            else:
                return "✅ GEÇTİ" if p <= 0.10 else "❌ RED"

        print(f"{'V3-Kontrol':<16} | {k:<4} | {r3['model_sharpe']:>8.3f}   | %{r3['model_cagr']*100:>7.2f}  | %{r3['model_max_dd']*100:>7.2f} | {r3['plac_mean_sharpe']:>12.3f}  | p = {r3['p_value_sharpe']:<14.3f} | {get_stat(r3['p_value_sharpe'], k):<12}")
        print(f"{'V4-Raw':<16} | {k:<4} | {r4['model_sharpe']:>8.3f}   | %{r4['model_cagr']*100:>7.2f}  | %{r4['model_max_dd']*100:>7.2f} | {r4['plac_mean_sharpe']:>12.3f}  | p = {r4['p_value_sharpe']:<14.3f} | {get_stat(r4['p_value_sharpe'], k):<12}")
        print(f"{'V5-Neutral (YENİ)':<16} | {k:<4} | {r5['model_sharpe']:>8.3f}   | %{r5['model_cagr']*100:>7.2f}  | %{r5['model_max_dd']*100:>7.2f} | {r5['plac_mean_sharpe']:>12.3f}  | p = {r5['p_value_sharpe']:<14.3f} | {get_stat(r5['p_value_sharpe'], k):<12}")
        print("-" * 125)

    print("\n" + "=" * 80)
    print("V5 MODELİ FAKTÖR ÖNEM DÜZEYLERİ (FEATURE IMPORTANCE — DART):")
    print("=" * 80)
    for _, r in df_imp_v5.iterrows():
        print(f"  • {r['feature']:<18}: Split={r['split']:>3.0f} | Gain={r['gain']:>10.2f} (%{r['gain_pct']:>5.1f})")
    print("-" * 80)

    print("\nV5 KÖK DÜĞÜM (DERİNLİK 0) BÖLÜNME DAĞILIMI (60 AĞAÇ):")
    for f, cnt in sorted(root_splits_v5.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {f:<18}: {cnt:>2} ağacın kök düğümü (%{cnt/60*100:>4.1f})")

    # JSON Olarak Kaydet
    output_path = ROOT_DIR / "reports" / "faz3_v5_market_neutral_sonuclari.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "v5_placebo": k_res_v5,
            "v5_yearly": yearly_v5,
            "v5_feature_importance": df_imp_v5.to_dict("records"),
            "v5_root_splits": root_splits_v5
        }, f, indent=2, default=str)
    print(f"\n✅ V5 sonuçları kaydedildi: {output_path}")


if __name__ == "__main__":
    main()
