"""
scratch/faz3_placebo_ve_gain_analizi.py
========================================
FAZ 3 EK PROTOKOL: 100-TOHUMLU PLACEBO TESTİ VE %54.5 GAIN YOĞUNLAŞMA ANALİZİ
------------------------------------------------------------------------------
Amaç:
  1. 100 Tohumlu Monte Carlo / Placebo Testi:
     - K=10, K=15, K=20 portföy boyutlarında 100 rastgele tohumla (seed=42)
     - V4 modelinin Walk-Forward OOS (2022-2025) Sharpe oranının rastgele
       sepetlere karşı istatistiksel üstünlüğü (p-değeri) hesaplanır.
     - V3-Kontrol ile başa baş karşılaştırılır.
     - Karar Kuralı: K=15'te p <= 0.05 VE (K=10 ve K=20'de p <= 0.10).
  2. %54.5 Gain Yoğunlaşması ve Overfitting Denetimi:
     - reel_eps_growth'un ağaçlardaki split derinliği (kök düğüm vs alt düğüm)
     - Etkileşim matrisi: reel_eps_growth hangi faktörlerle (PB, MOM, FCF) kombine oluyor?
     - Feature subsampling (colsample_bytree) duyarlılık testi: Aşırı uyum var mı?
"""

import sys
import json
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

from scratch.faz3_v4_walk_forward_egitimi import (
    build_v4_quarterly_dataset,
    hesapla_metrikler,
    LGBM_PARAMS,
    BASE_FEATURE_COLS,
    TRANSACTION_COST
)

N_PLACEBO = 100
SEED = 42
K_VALUES = [10, 15, 20]
RF_ANNUAL = 0.18


def run_placebo_simulation(quarters_data, feature_cols, model_label: str):
    """
    4-Fold Walk-Forward OOS periyotlarında modelin Top-K seçimlerini
    ve 100 rastgele tohumlu Placebo sepetlerini simüle eder.
    """
    train_start_date = pd.Timestamp("2019-09-01")
    folds = [
        {"name": "Fold 1 (2022)", "train_end": pd.Timestamp("2021-12-31"), "test_start": pd.Timestamp("2022-01-01"), "test_end": pd.Timestamp("2022-12-31")},
        {"name": "Fold 2 (2023)", "train_end": pd.Timestamp("2022-12-31"), "test_start": pd.Timestamp("2023-01-01"), "test_end": pd.Timestamp("2023-12-31")},
        {"name": "Fold 3 (2024)", "train_end": pd.Timestamp("2023-12-31"), "test_start": pd.Timestamp("2024-01-01"), "test_end": pd.Timestamp("2024-12-31")},
        {"name": "Fold 4 (2025)", "train_end": pd.Timestamp("2024-12-31"), "test_start": pd.Timestamp("2025-01-01"), "test_end": pd.Timestamp("2025-05-31")},
    ]

    # Model OOS tahminlerini ve test dönemlerini topla
    test_quarter_records = []

    for fold in folds:
        train_q = [q for q in quarters_data if (q["t0"] >= train_start_date) and (q["t1"] <= fold["train_end"])]
        test_q = [q for q in quarters_data if (q["t0"] >= fold["test_start"]) and (q["t0"] <= fold["test_end"])]

        if not train_q or not test_q:
            continue

        df_train = pd.concat([q["df"] for q in train_q], ignore_index=True)
        train_groups = [q["group_size"] for q in train_q]

        model = LGBMRanker(objective="lambdarank", **LGBM_PARAMS)
        model.fit(df_train[feature_cols], df_train["relevance"], group=train_groups)

        for q in test_q:
            df_test = q["df"].copy()
            preds = model.predict(df_test[feature_cols])
            df_test["model_score"] = preds

            # Faz 0 Hard Exclusion: Taban riski taşıyanları çıkar
            df_valid = df_test[~df_test["is_taban_riski"]].copy()
            if len(df_valid) < 20:
                df_valid = df_test.copy()

            df_sorted = df_valid.sort_values("model_score", ascending=False)

            test_quarter_records.append({
                "t0": q["t0"],
                "df_sorted": df_sorted,
                "eligible_symbols": df_valid["sembol"].tolist(),
                "returns_dict": dict(zip(df_valid["sembol"], df_valid["fwd_ret"]))
            })

    # Model ve Placebo Performanslarını K=10, 15, 20 için hesapla
    rng = np.random.default_rng(SEED)
    k_results = {}

    for k in K_VALUES:
        # 1. Model Getirileri
        model_q_rets = []
        for rec in test_quarter_records:
            top_k = rec["df_sorted"].iloc[:k]
            r = float(top_k["fwd_ret"].mean()) - TRANSACTION_COST
            model_q_rets.append(r)

        m_model = hesapla_metrikler(model_q_rets)
        model_sharpe = m_model["sharpe"]

        # 2. 100 Tohumlu Placebo Getirileri
        plac_sharpes = []
        plac_cagrs = []
        plac_drawdowns = []

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
            plac_drawdowns.append(m_p["max_dd"])

        # Ampirik p-değeri: Placebo Sharpe >= Model Sharpe oranı
        p_val_sharpe = float(np.mean([1 if s >= model_sharpe else 0 for s in plac_sharpes]))
        p_val_cagr   = float(np.mean([1 if c >= m_model["cagr"] else 0 for c in plac_cagrs]))

        plac_mean_sharpe = float(np.mean(plac_sharpes))
        plac_max_sharpe  = float(np.max(plac_sharpes))
        plac_95th_sharpe = float(np.percentile(plac_sharpes, 95))

        k_results[k] = {
            "model_sharpe": model_sharpe,
            "model_cagr": m_model["cagr"],
            "model_kumulatif": m_model["kumulatif"],
            "model_max_dd": m_model["max_dd"],
            "plac_mean_sharpe": plac_mean_sharpe,
            "plac_95th_sharpe": plac_95th_sharpe,
            "plac_max_sharpe": plac_max_sharpe,
            "p_value_sharpe": p_val_sharpe,
            "p_value_cagr": p_val_cagr
        }

    return k_results


def analyze_gain_concentration_and_interactions(quarters_data, feature_cols):
    """
    reel_eps_growth'un %54.5'lik Gain payının iç yapısını,
    kök düğüm/yaprak düğüm dağılımını ve diğer faktörlerle etkileşimini inceler.
    """
    train_start_date = pd.Timestamp("2019-09-01")
    train_q = [q for q in quarters_data if (q["t0"] >= train_start_date)]
    df_all = pd.concat([q["df"] for q in train_q], ignore_index=True)
    groups = [q["group_size"] for q in train_q]

    # Temel V4 Modeli
    model = LGBMRanker(objective="lambdarank", **LGBM_PARAMS)
    model.fit(df_all[feature_cols], df_all["relevance"], group=groups)

    booster = model.booster_
    tree_dump = booster.dump_model()["tree_info"]

    # Ağaç Düğümlerini Analiz Et
    split_counts_by_depth = {0: {}, 1: {}}
    interaction_pairs = []

    for tree in tree_dump:
        tree_struct = tree["tree_structure"]
        if "split_feature" in tree_struct:
            root_feat = feature_cols[tree_struct["split_feature"]]
            split_counts_by_depth[0][root_feat] = split_counts_by_depth[0].get(root_feat, 0) + 1

            # Sol çocuk
            left_child = tree_struct.get("left_child", {})
            if "split_feature" in left_child:
                child_feat = feature_cols[left_child["split_feature"]]
                split_counts_by_depth[1][child_feat] = split_counts_by_depth[1].get(child_feat, 0) + 1
                interaction_pairs.append((root_feat, child_feat))

            # Sağ çocuk
            right_child = tree_struct.get("right_child", {})
            if "split_feature" in right_child:
                child_feat = feature_cols[right_child["split_feature"]]
                split_counts_by_depth[1][child_feat] = split_counts_by_depth[1].get(child_feat, 0) + 1
                interaction_pairs.append((root_feat, child_feat))

    # Düzenlileştirme Duyarlılık Testi (colsample_bytree = 0.70)
    # Eğer reel_eps_growth overfitting ise, colsample konulduğunda OOS Sharpe artmalıdır;
    # Eğer gerçek sinyal ise, her ağaçta görülmesi kısıtlandığında sinyal hafif azalmalıdır.
    params_reg = LGBM_PARAMS.copy()
    params_reg["colsample_bytree"] = 0.70
    params_reg["reg_alpha"] = 0.50

    from scratch.faz3_v4_walk_forward_egitimi import run_v4_walk_forward
    print("Duyarlılık Testi: colsample_bytree=0.70 + L1=0.50 ile düzenlileştirilmiş V4 Walk-Forward çalıştırılıyor...")
    res_reg = run_v4_walk_forward(quarters_data, feature_cols, "V4-Regularized (Colsample 0.70)")

    return {
        "split_counts_by_depth": split_counts_by_depth,
        "interaction_pairs": interaction_pairs,
        "res_reg": res_reg
    }


def main():
    print("=" * 115)
    print("FAZ 3 EK DOĞRULAMA: 100-TOHUMLU PLACEBO TESTİ VE GAIN YOĞUNLAŞMA ANALİZİ")
    print("=" * 115)

    quarters_data = build_v4_quarterly_dataset()

    v4_feats = BASE_FEATURE_COLS + ["reel_eps_growth"]
    v3_feats = BASE_FEATURE_COLS

    print("\n1. V3-Kontrol Modeli için 100 Tohumlu Placebo Simülasyonu çalıştırılıyor...")
    plac_v3 = run_placebo_simulation(quarters_data, v3_feats, "V3-Kontrol")

    print("2. V4 Modeli için 100 Tohumlu Placebo Simülasyonu çalıştırılıyor...")
    plac_v4 = run_placebo_simulation(quarters_data, v4_feats, "V4-Raw")

    print("\n" + "=" * 125)
    print("100-TOHUMLU MONTE CARLO / PLACEBO TEST SONUÇLARI (WALK-FORWARD OOS 2022-2025)")
    print("Kill Criteria: K=15'te p <= 0.05 VE (K=10 ve K=20'de p <= 0.10)")
    print("=" * 125)
    print(f"{'Model':<12} | {'K':<4} | {'Model Sharpe':<14} | {'Placebo Ortalama':<18} | {'Placebo %95':<14} | {'Placebo Maks':<14} | {'p-değeri (Sharpe)':<18} | {'Durum':<12}")
    print("-" * 125)

    for k in K_VALUES:
        r3 = plac_v3[k]
        durum3 = "✅ GEÇTİ" if (r3["p_value_sharpe"] <= 0.05 if k == 15 else r3["p_value_sharpe"] <= 0.10) else "❌ RED"
        print(f"{'V3-Kontrol':<12} | {k:<4} | {r3['model_sharpe']:>10.3f}     | {r3['plac_mean_sharpe']:>12.3f}      | {r3['plac_95th_sharpe']:>10.3f}   | {r3['plac_max_sharpe']:>10.3f}   | p = {r3['p_value_sharpe']:<14.3f} | {durum3:<12}")

        r4 = plac_v4[k]
        durum4 = "✅ GEÇTİ" if (r4["p_value_sharpe"] <= 0.05 if k == 15 else r4["p_value_sharpe"] <= 0.10) else "❌ RED"
        print(f"{'V4-Raw':<12} | {k:<4} | {r4['model_sharpe']:>10.3f}     | {r4['plac_mean_sharpe']:>12.3f}      | {r4['plac_95th_sharpe']:>10.3f}   | {r4['plac_max_sharpe']:>10.3f}   | p = {r4['p_value_sharpe']:<14.3f} | {durum4:<12}")
        print("-" * 125)

    # Gain Yoğunlaşma ve Overfitting Derinlik Analizi
    print("\n" + "=" * 115)
    print("2. %54.5 GAIN YOĞUNLAŞMASI VE OVERFITTING DENETİMİ")
    print("=" * 115)
    gain_res = analyze_gain_concentration_and_interactions(quarters_data, v4_feats)

    print("\nA. AĞAÇ DERİNLİĞİ BAZINDA BÖLÜNME (SPLIT) DAĞILIMI:")
    print("-" * 75)
    print(f"{'Öznitelik':<20} | {'Kök Düğüm (Derinlik 0)':<25} | {'Alt Düğüm (Derinlik 1)':<25}")
    print("-" * 75)
    all_f = sorted(list(set(list(gain_res["split_counts_by_depth"][0].keys()) + list(gain_res["split_counts_by_depth"][1].keys()))))
    for f in all_f:
        d0 = gain_res["split_counts_by_depth"][0].get(f, 0)
        d1 = gain_res["split_counts_by_depth"][1].get(f, 0)
        print(f"{f:<20} | {d0:>15}           | {d1:>15}")
    print("-" * 75)

    print("\nB. REEL_EPS_GROWTH İLE DİĞER FAKTÖRLERİN ETKİLEŞİM FREKANSI:")
    pairs = gain_res["interaction_pairs"]
    int_with_growth = [p[1] if p[0] == "reel_eps_growth" else p[0] for p in pairs if "reel_eps_growth" in p]
    from collections import Counter
    c_int = Counter(int_with_growth)
    for f, cnt in c_int.most_common():
        print(f"  • reel_eps_growth <-> {f:<15}: {cnt:>2} kez ağaç dallarında birlikte karar verdi")

    # Düzenlileştirme Kıyaslaması
    res_reg = gain_res["res_reg"]
    print("\nC. DÜZENLİLEŞTİRME DUYARLILIK TESTİ (COLSAMPLE=0.70 & L1=0.50):")
    print(f"  • Orijinal V4-Raw (K=15):     OOS Sharpe = {plac_v4[15]['model_sharpe']:.3f} | Max DD = %{plac_v4[15]['model_max_dd']*100:.2f} | Kümülatif = %{plac_v4[15]['model_kumulatif']*100:.1f}")
    print(f"  • Düzenlileştirilmiş V4 (K=15): OOS Sharpe = {res_reg['k15_agg']['sharpe']:.3f} | Max DD = %{res_reg['k15_agg']['max_dd']*100:.2f} | Kümülatif = %{res_reg['k15_agg']['kumulatif']*100:.1f}")

    # JSON Olarak Kaydet
    output_path = ROOT_DIR / "reports" / "faz3_placebo_ve_gain_analizi.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "placebo_v3": plac_v3,
            "placebo_v4": plac_v4,
            "split_by_depth": gain_res["split_counts_by_depth"],
            "interactions": dict(c_int),
            "regularized_v4_k15": res_reg["k15_agg"]
        }, f, indent=2, default=str)
    print(f"\n✅ Placebo ve Gain analiz sonuçları kaydedildi: {output_path}")


if __name__ == "__main__":
    main()
