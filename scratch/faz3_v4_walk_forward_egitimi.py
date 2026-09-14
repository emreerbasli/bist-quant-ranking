"""
scratch/faz3_v4_walk_forward_egitimi.py
========================================
FAZ 3: V4 FEATURE MOTORU VE 4-FOLD WALK-FORWARD MODEL EĞİTİMİ
--------------------------------------------------------------
9 Faktörlü V4 Mimarisi:
  - 8 Orijinal V3 Feature: z_pb, z_roe, z_fcf, z_mom, z_borc, reel_faiz, usd_mom_60, usd_mom_90
  - 1 Yeni PIT Alfa Feature: reel_eps_growth (ve sektörel z-skoru z_reel_eps)

Eğitim Penceresi: 2019-09-01 -> 2025-05-30
Kilit Kutu (2025-06 -> 2026-09) KESİNLİKLE DOKUNULMAZDIR.

Doğrulama Protokolü:
  - 4-Fold Purged Walk-Forward (2022 - 2025)
  - K=10 ve K=15 Top-K Eşit Ağırlıklı Portföyler
  - Faz 0 Ardışık Taban Hard-Exclusion Filtresi Uygulanır
  - Karşılaştırma: V3-Kontrol Çıtası (Sharpe >= 0.994, Max DD <= -%13.39)
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

LGBM_PARAMS = {
    "max_depth": 2,
    "num_leaves": 3,
    "learning_rate": 0.03,
    "n_estimators": 60,
    "min_child_samples": 15,
    "reg_lambda": 1.0,
    "random_state": 42,
    "verbose": -1
}

# 8 Orijinal Feature
BASE_FEATURE_COLS = ["z_fcf", "z_roe", "z_mom", "z_borc", "z_pb", "reel_faiz", "usd_mom_60", "usd_mom_90"]


def build_v4_quarterly_dataset():
    """
    2018-09 -> 2025-05 arasındaki tüm çeyreklik verileri 9 faktörlü V4 yapısında üretir.
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

        # Makro
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

            # Faz 1'de Kabul Edilen reel_eps_growth
            cand_feats = extract_candidate_features(
                t0, s, fiyat_dict[s], seri_usdtry, pit_bellek.get(s, []), tufe_aylik
            )
            reel_eps = cand_feats.get("reel_eps_growth", np.nan)

            # Faz 0 Taban Riski Kontrolü
            p_sub = fiyat_dict[s][fiyat_dict[s].index <= t0]
            is_taban_riski, _ = ardisik_taban_tespit(p_sub, lookback_gun=10, min_taban=5, taban_esik=-0.095)

            q_rows.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb,
                "reel_eps_raw": reel_eps,
                "fwd_ret": rets[s],
                "is_taban_riski": is_taban_riski
            })

        df_q = pd.DataFrame(q_rows)

        # Sektörel z-skorları (V3 standartları)
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)

        # 9. Faktör: Sektörel z-skor ve normalize edilmiş form
        df_q["z_reel_eps"] = hesapla_sektor_zscore(df_q, "reel_eps_raw", min_grup=4).fillna(0.0)
        df_q["reel_eps_growth"] = df_q["reel_eps_raw"].fillna(0.0).clip(-2.0, 2.0)

        df_q["reel_faiz"]  = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        # Relevance hedefi (deciles 0-9)
        try:
            df_q["relevance"] = pd.qcut(df_q["fwd_ret"], q=10, labels=False, duplicates="drop")
        except Exception:
            df_q["relevance"] = pd.qcut(df_q["fwd_ret"], q=5, labels=False, duplicates="drop")

        quarters_data.append({
            "t0": t0, "t1": t1, "yil": t0.year,
            "df": df_q, "group_size": len(df_q)
        })

    print(f"V4 Çeyreklik Veri Seti Üretildi: {len(quarters_data)} Çeyrek ({quarters_data[0]['t0'].strftime('%Y-%m')} -> {quarters_data[-1]['t1'].strftime('%Y-%m')})")
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


def run_v4_walk_forward(quarters_data, feature_cols, model_label: str):
    """
    4-Fold Walk-Forward OOS simülasyonunu icra eder (2019-09 başlangıçlı).
    """
    train_start_date = pd.Timestamp("2019-09-01")
    folds = [
        {"name": "Fold 1 (2022)", "train_end": pd.Timestamp("2021-12-31"), "test_start": pd.Timestamp("2022-01-01"), "test_end": pd.Timestamp("2022-12-31"), "donem": "Donem_A"},
        {"name": "Fold 2 (2023)", "train_end": pd.Timestamp("2022-12-31"), "test_start": pd.Timestamp("2023-01-01"), "test_end": pd.Timestamp("2023-12-31"), "donem": "Donem_A"},
        {"name": "Fold 3 (2024)", "train_end": pd.Timestamp("2023-12-31"), "test_start": pd.Timestamp("2024-01-01"), "test_end": pd.Timestamp("2024-12-31"), "donem": "Donem_B"},
        {"name": "Fold 4 (2025)", "train_end": pd.Timestamp("2024-12-31"), "test_start": pd.Timestamp("2025-01-01"), "test_end": pd.Timestamp("2025-05-31"), "donem": "Donem_B"},
    ]

    oos_k10_returns, oos_k15_returns = [], []
    donem_a_k10, donem_a_k15 = [], []
    donem_b_k10, donem_b_k15 = [], []
    yearly_results = {}

    for fold in folds:
        train_q = [q for q in quarters_data if (q["t0"] >= train_start_date) and (q["t1"] <= fold["train_end"])]
        test_q = [q for q in quarters_data if (q["t0"] >= fold["test_start"]) and (q["t0"] <= fold["test_end"])]

        if not train_q or not test_q:
            continue

        df_train = pd.concat([q["df"] for q in train_q], ignore_index=True)
        train_groups = [q["group_size"] for q in train_q]

        model = LGBMRanker(objective="lambdarank", **LGBM_PARAMS)
        model.fit(df_train[feature_cols], df_train["relevance"], group=train_groups)

        fold_k10, fold_k15 = [], []

        for q in test_q:
            df_test = q["df"].copy()
            preds = model.predict(df_test[feature_cols])
            df_test["model_score"] = preds

            # Faz 0 Hard Exclusion
            df_valid = df_test[~df_test["is_taban_riski"]].copy()
            if len(df_valid) < 15:
                df_valid = df_test.copy()

            df_sorted = df_valid.sort_values("model_score", ascending=False)
            top10 = df_sorted.iloc[:10]
            top15 = df_sorted.iloc[:15]

            r10 = float(top10["fwd_ret"].mean()) - TRANSACTION_COST
            r15 = float(top15["fwd_ret"].mean()) - TRANSACTION_COST

            fold_k10.append(r10)
            fold_k15.append(r15)
            oos_k10_returns.append(r10)
            oos_k15_returns.append(r15)

            if fold["donem"] == "Donem_A":
                donem_a_k10.append(r10)
                donem_a_k15.append(r15)
            else:
                donem_b_k10.append(r10)
                donem_b_k15.append(r15)

        m_f_10 = hesapla_metrikler(fold_k10)
        m_f_15 = hesapla_metrikler(fold_k15)
        yearly_results[fold["name"]] = {"k10": m_f_10, "k15": m_f_15}

    m_agg_10 = hesapla_metrikler(oos_k10_returns)
    m_agg_15 = hesapla_metrikler(oos_k15_returns)
    m_dna_10 = hesapla_metrikler(donem_a_k10)
    m_dna_15 = hesapla_metrikler(donem_a_k15)
    m_dnb_10 = hesapla_metrikler(donem_b_k10)
    m_dnb_15 = hesapla_metrikler(donem_b_k15)

    return {
        "model_label": model_label,
        "feature_cols": feature_cols,
        "k10_agg": m_agg_10,
        "k15_agg": m_agg_15,
        "k10_donem_a": m_dna_10,
        "k15_donem_a": m_dna_15,
        "k10_donem_b": m_dnb_10,
        "k15_donem_b": m_dnb_15,
        "yearly_results": yearly_results
    }


def main():
    print("=" * 115)
    print("FAZ 3: V4 MODELİ WALK-FORWARD EĞİTİMİ VE V3-KONTROL KIYASLAMASI")
    print("Eğitim Penceresi: 2019-09-01 -> 2025-05-30 (Aday 1 Hiperparametreleri)")
    print("Hedef Çıta: V3-Kontrol (OOS Sharpe >= 0.994, Max DD <= -%13.39)")
    print("=" * 115)

    quarters_data = build_v4_quarterly_dataset()

    # V3-Kontrol Sonuçlarını Yükle
    ctrl_path = ROOT_DIR / "reports" / "faz2_v3_kontrol_sonuclari.json"
    if not ctrl_path.exists():
        raise FileNotFoundError(f"V3-Kontrol sonuçları bulunamadı: {ctrl_path}. Önce Faz 2 tamamlanmalı.")
    with open(ctrl_path, "r", encoding="utf-8") as f:
        ctrl_json = json.load(f)
    res_ctrl = ctrl_json["v3_kontrol"]
    res_orig = ctrl_json["v3_orijinal"]

    # V4 Modellerini Test Et:
    # 1. Konfigürasyon: V4-Z (Sektörel Z-skor z_reel_eps ile)
    feat_v4_z = BASE_FEATURE_COLS + ["z_reel_eps"]
    print("\n1. V4-Z (9 Feature - Sektörel z_reel_eps) Walk-Forward çalıştırılıyor...")
    res_v4_z = run_v4_walk_forward(quarters_data, feat_v4_z, "V4-Z (Sektör z_reel_eps)")

    # 2. Konfigürasyon: V4-Raw (Ham reel_eps_growth ile)
    feat_v4_raw = BASE_FEATURE_COLS + ["reel_eps_growth"]
    print("2. V4-Raw (9 Feature - Ham reel_eps_growth) Walk-Forward çalıştırılıyor...")
    res_v4_raw = run_v4_walk_forward(quarters_data, feat_v4_raw, "V4-Raw (Ham reel_eps_growth)")

    # En İyi V4 Konfigürasyonunu Seç
    if res_v4_z["k15_agg"]["sharpe"] >= res_v4_raw["k15_agg"]["sharpe"]:
        chosen_v4 = res_v4_z
        chosen_variant = "z_reel_eps"
    else:
        chosen_v4 = res_v4_raw
        chosen_variant = "reel_eps_growth"

    print("\n" + "=" * 125)
    print("BÜYÜK KARŞILAŞTIRMA TABLOSU: V3-ORİJİNAL vs V3-KONTROL vs V4 (WALK-FORWARD OOS 2022-2025)")
    print("=" * 125)
    print(f"{'Model / Portföy':<32} | {'OOS Sharpe':<12} | {'CAGR (%)':<10} | {'Kümülatif':<12} | {'Max DD':<10} | {'Dönem A Sharpe':<16} | {'Dönem B Küm (%)':<16}")
    print("-" * 125)

    def format_row(name, m_agg, m_a, m_b):
        return f"{name:<32} | {m_agg['sharpe']:>10.3f}   | %{m_agg['cagr']*100:>7.2f}  | %{m_agg['kumulatif']*100:>9.1f}  | %{m_agg['max_dd']*100:>7.2f} | {m_a['sharpe']:>14.3f}   | %{m_b['kumulatif']*100:>12.2f}"

    print(format_row("V3-Orijinal (K=10)", res_orig["k10_agg"], res_orig["k10_donem_a"], res_orig["k10_donem_b"]))
    print(format_row("V3-Kontrol  (K=10)", res_ctrl["k10_agg"], res_ctrl["k10_donem_a"], res_ctrl["k10_donem_b"]))
    print(format_row("V4-Z        (K=10)", res_v4_z["k10_agg"], res_v4_z["k10_donem_a"], res_v4_z["k10_donem_b"]))
    print(format_row("V4-Raw      (K=10)", res_v4_raw["k10_agg"], res_v4_raw["k10_donem_a"], res_v4_raw["k10_donem_b"]))
    print("-" * 125)
    print(format_row("V3-Orijinal (K=15)", res_orig["k15_agg"], res_orig["k15_donem_a"], res_orig["k15_donem_b"]))
    print(format_row("V3-Kontrol  (K=15) [ÇITA]", res_ctrl["k15_agg"], res_ctrl["k15_donem_a"], res_ctrl["k15_donem_b"]))
    print(format_row("V4-Z        (K=15)", res_v4_z["k15_agg"], res_v4_z["k15_donem_a"], res_v4_z["k15_donem_b"]))
    print(format_row("V4-Raw      (K=15)", res_v4_raw["k15_agg"], res_v4_raw["k15_donem_a"], res_v4_raw["k15_donem_b"]))
    print("=" * 125)

    # Yıllık OOS Kıyaslama Tablosu (K=15)
    print("\nYILLIK OOS GETİRİ VE SHARPE DAĞILIMI (K=15):")
    print("-" * 105)
    print(f"{'Fold / Yıl':<18} | {'V3-Kontrol Getiri':<20} | {'V4 Getiri':<16} | {'V3-Kontrol Sharpe':<20} | {'V4 Sharpe':<15}")
    print("-" * 105)
    for fold_name in res_ctrl["yearly_results"].keys():
        r_ctrl = res_ctrl["yearly_results"][fold_name]["k15"]["kumulatif"] * 100.0
        r_v4 = chosen_v4["yearly_results"][fold_name]["k15"]["kumulatif"] * 100.0
        s_ctrl = res_ctrl["yearly_results"][fold_name]["k15"]["sharpe"]
        s_v4 = chosen_v4["yearly_results"][fold_name]["k15"]["sharpe"]
        s_c_str = f"{s_ctrl:.3f}" if pd.notna(s_ctrl) else "N/A"
        s_v_str = f"{s_v4:.3f}" if pd.notna(s_v4) else "N/A"
        print(f"{fold_name:<18} | %{r_ctrl:>18.2f} | %{r_v4:>14.2f} | {s_c_str:>18} | {s_v_str:>13}")
    print("=" * 105)

    # Kazanan V4 Modelini Tüm 2019-09 -> 2025-05 Kümesinde Eğit ve Dondur
    print(f"\n3. Kazanan V4 Modeli ({chosen_v4['model_label']}) tüm eğitim kümesinde eğitiliyor...")
    final_feats = chosen_v4["feature_cols"]

    train_v4_q = [q for q in quarters_data if (q["t0"] >= pd.Timestamp("2019-09-01")) and (q["t1"] <= LOCKBOX_BARRIER)]
    df_all_v4 = pd.concat([q["df"] for q in train_v4_q], ignore_index=True)
    all_v4_groups = [q["group_size"] for q in train_v4_q]

    final_v4_model = LGBMRanker(objective="lambdarank", **LGBM_PARAMS)
    final_v4_model.fit(df_all_v4[final_feats], df_all_v4["relevance"], group=all_v4_groups)

    imp_split = final_v4_model.feature_importances_
    imp_gain = final_v4_model.booster_.feature_importance(importance_type="gain")
    df_imp = pd.DataFrame({
        "feature": final_feats,
        "split": imp_split,
        "gain": imp_gain
    }).sort_values("gain", ascending=False)
    df_imp["gain_pct"] = df_imp["gain"] / df_imp["gain"].sum() * 100.0

    print("\nV4 MODELİ FAKTÖR ÖNEM DÜZEYLERİ (FEATURE IMPORTANCE):")
    print("-" * 80)
    for _, r in df_imp.iterrows():
        print(f"  • {r['feature']:<18}: Split={r['split']:>3.0f} | Gain={r['gain']:>10.2f} (%{r['gain_pct']:>5.1f})")
    print("-" * 80)

    # Modeli models/v4_ranking dizinine kaydet
    v4_dir = ROOT_DIR / "models" / "v4_ranking"
    v4_dir.mkdir(parents=True, exist_ok=True)
    v4_save_path = v4_dir / "winning_lgbm_ranker_v4.joblib"

    v4_save_obj = {
        "model": final_v4_model,
        "model_name": "V4 LGBMRanker (9 Feature)",
        "train_window": "2019-09-01 -> 2025-05-30",
        "feature_cols": final_feats,
        "params": LGBM_PARAMS,
        "df_imp": df_imp,
        "wf_results": chosen_v4,
        "wf_baseline_ctrl": res_ctrl,
        "variant": chosen_variant
    }
    joblib.dump(v4_save_obj, v4_save_path)
    print(f"\n✅ V4 modeli başarıyla donduruldu ve kaydedildi: {v4_save_path}")

    # JSON Raporu
    rep_path = ROOT_DIR / "reports" / "faz3_v4_walk_forward_sonuclari.json"
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump({
            "v4_secilen": chosen_v4,
            "v4_z": res_v4_z,
            "v4_raw": res_v4_raw,
            "v3_kontrol": res_ctrl,
            "df_imp": df_imp.to_dict("records")
        }, f, indent=2, default=str)
    print(f"✅ Rapor kaydedildi: {rep_path}")


if __name__ == "__main__":
    main()
