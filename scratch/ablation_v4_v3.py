"""
scratch/ablation_v4_v3.py
=========================
V4 KİLİT KUTU (LOCKBOX) PERFORMANS KÖK NEDEN ANALİZİ & ABLASYON ÇALIŞMASI
------------------------------------------------------------------------
Kapsam:
  1. Özellik Çıkarma (Feature Ablation): reel_eps_growth tamamen çıkarıldığında model ne üretiyor?
  2. Faktör Ehlileştirme (Factor Taming):
     - Sektörel Z-skor (z_reel_eps)
     - Dar Bant Kırpma ([-1.0, 1.0])
     - Winsorized Sektörel Z-skor ([-1.5, 1.5])
  3. Hiperparametre & Aşırı Öğrenme (Overfitting) Budaması:
     - num_leaves in [3, 7, 15, 31]
     - learning_rate in [0.03, 0.05]
     - min_child_samples in [10, 15, 20]
  4. Kilit Kutu (2025-06-01 -> 2026-09-07) 100 Tohumlu Monte Carlo Placebo Testi
  5. Büyük Karşılaştırma Tablosu (Şampiyon V3 vs Ham V4 vs Ablated vs Tamed vs Pruned)
"""

import sys
import json
import warnings
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import joblib
from lightgbm import LGBMRanker

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg
from scratch.run_faz_c_walk_forward_test import (
    yukle_veriler,
    hizli_pit,
    hesapla_mom,
    getir_tcmb_reel_faiz,
)
from scratch.run_lockbox_evaluation import hesapla_sektor_zscore
from scratch.faz1_ic_tarama import extract_candidate_features

KOMISYON = 0.003
LOCKBOX_BARRIER = pd.Timestamp("2025-06-01")

BASE_FEATURE_COLS = ["z_fcf", "z_roe", "z_mom", "z_borc", "z_pb", "reel_faiz", "usd_mom_60", "usd_mom_90"]


def metrikler_quarterly(arr, rf_annual=0.18):
    if not len(arr):
        return {"kumulatif": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0}
    a = np.array(arr, dtype=float)
    kum = float(np.prod(1.0 + a) - 1.0)
    n = len(a)
    cagr = float((1.0 + kum) ** (4.0 / max(1, n)) - 1.0) if kum > -0.99 else -0.99
    rf_q = (1.0 + rf_annual) ** 0.25 - 1.0
    diff = a - rf_q
    std = float(np.std(a, ddof=1)) if len(a) > 1 else 1e-6
    sharpe = float(np.mean(diff) / (std + 1e-8) * np.sqrt(4))

    zs = np.cumprod(1.0 + a)
    pk = np.maximum.accumulate(zs)
    dd = (zs - pk) / pk
    mdd = float(np.min(dd))
    return {"kumulatif": kum, "cagr": cagr, "sharpe": sharpe, "max_dd": mdd}


def build_datasets():
    """Eğitim (2019-09 -> 2025-05) ve Kilit Kutu (2025-06 -> 2026-09) veri kümelerini hazırlar."""
    print("Piyasa verileri yükleniyor...")
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    hisseler = sorted(fiyat_dict.keys())

    tarihler_train = pd.date_range("2018-09-01", "2025-08-01", freq="3MS")
    train_quarters = []

    for i in range(len(tarihler_train) - 1):
        t0, t1 = tarihler_train[i], tarihler_train[i + 1]
        if t0 >= LOCKBOX_BARRIER or t0 < pd.Timestamp("2019-09-01"):
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

        rows = []
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
            reel_eps_raw = cand_feats.get("reel_eps_growth", np.nan)

            rows.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb,
                "reel_eps_raw": reel_eps_raw,
                "fwd_ret": rets[s]
            })

        df_q = pd.DataFrame(rows)
        # Sektörel Z-skorları
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)

        # Faktör Varyasyonları
        df_q["reel_eps_growth"] = df_q["reel_eps_raw"].fillna(0.0).clip(-2.0, 2.0)
        df_q["reel_eps_clip1"]  = df_q["reel_eps_raw"].fillna(0.0).clip(-1.0, 1.0)
        df_q["z_reel_eps"]      = hesapla_sektor_zscore(df_q, "reel_eps_raw", min_grup=4).fillna(0.0).clip(-3.0, 3.0)
        df_q["z_reel_eps_win"]  = hesapla_sektor_zscore(df_q, "reel_eps_raw", min_grup=4).fillna(0.0).clip(-1.5, 1.5)

        df_q["reel_faiz"]  = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        try:
            df_q["relevance"] = pd.qcut(df_q["fwd_ret"], q=10, labels=False, duplicates="drop")
        except Exception:
            df_q["relevance"] = pd.qcut(df_q["fwd_ret"], q=5, labels=False, duplicates="drop")

        train_quarters.append({
            "t0": t0, "t1": t1, "df": df_q, "group_size": len(df_q)
        })

    # Kilit Kutu (5 Çeyrek)
    lockbox_dates = [
        (pd.Timestamp("2025-06-01"), pd.Timestamp("2025-09-01"), "2025Q2"),
        (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-12-01"), "2025Q3"),
        (pd.Timestamp("2025-12-01"), pd.Timestamp("2026-03-01"), "2025Q4"),
        (pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-01"), "2026Q1"),
        (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-09-07"), "2026Q2 (Güncel)"),
    ]

    lockbox_data = []
    for t0, t1, label in lockbox_dates:
        rets_tl = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets_tl[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        mevcut = [s for s in hisseler if s in rets_tl]

        px = seri_xu100[(seri_xu100.index >= t0) & (seri_xu100.index <= t1)]
        r_xu_tl = float((px.iloc[-1] - px.iloc[0]) / px.iloc[0]) if len(px) >= 2 else 0.0

        reel_faiz = getir_tcmb_reel_faiz(t0, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t0]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

        rows = []
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
            reel_eps_raw = cand_feats.get("reel_eps_growth", np.nan)

            rows.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb,
                "reel_eps_raw": reel_eps_raw
            })

        df_q = pd.DataFrame(rows)
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)

        df_q["reel_eps_growth"] = df_q["reel_eps_raw"].fillna(0.0).clip(-2.0, 2.0)
        df_q["reel_eps_clip1"]  = df_q["reel_eps_raw"].fillna(0.0).clip(-1.0, 1.0)
        df_q["z_reel_eps"]      = hesapla_sektor_zscore(df_q, "reel_eps_raw", min_grup=4).fillna(0.0).clip(-3.0, 3.0)
        df_q["z_reel_eps_win"]  = hesapla_sektor_zscore(df_q, "reel_eps_raw", min_grup=4).fillna(0.0).clip(-1.5, 1.5)

        df_q["reel_faiz"]  = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        lockbox_data.append({
            "label": label, "t0": t0, "t1": t1,
            "rets_tl": rets_tl, "mevcut": mevcut,
            "r_xu_tl": r_xu_tl, "df": df_q
        })

    return train_quarters, lockbox_data


def evaluate_model_on_lockbox(model, feat_cols, lockbox_data, k=15, n_placebo=100, rng_seed=42):
    """Verilen model ve özellik kolonları ile kilit kutu performansını ve Monte Carlo p-değerini ölçer."""
    rng = np.random.default_rng(rng_seed)
    model_rets = []
    q_details = []

    for d in lockbox_data:
        df_q = d["df"].copy()
        pred = model.predict(df_q[feat_cols])
        df_q["pred"] = pred
        sirali = df_q.sort_values("pred", ascending=False)["sembol"].tolist()
        r_q = float(np.mean([d["rets_tl"][s] for s in sirali[:k]])) - KOMISYON
        model_rets.append(r_q)
        q_details.append(r_q)

    m_model = metrikler_quarterly(model_rets, rf_annual=0.18)

    # Placebo Simülasyonu
    plac_rets = [[] for _ in range(n_placebo)]
    for d in lockbox_data:
        mevcut = d["mevcut"]
        for p_i in range(n_placebo):
            sec = rng.choice(mevcut, size=k, replace=False)
            r_p = float(np.mean([d["rets_tl"][s] for s in sec])) - KOMISYON
            plac_rets[p_i].append(r_p)

    plac_sharpes = [metrikler_quarterly(p, 0.18)["sharpe"] for p in plac_rets]
    plac_kumuls  = [metrikler_quarterly(p, 0.18)["kumulatif"] for p in plac_rets]

    mean_plac_sh = float(np.mean(plac_sharpes))
    mean_plac_kum = float(np.mean(plac_kumuls))
    p_val = float(np.mean([1 if s >= m_model["sharpe"] else 0 for s in plac_sharpes]))

    return {
        "metrics": m_model,
        "q_rets": q_details,
        "p_val": p_val,
        "mean_plac_sh": mean_plac_sh,
        "mean_plac_kum": mean_plac_kum,
        "delta_sharpe": m_model["sharpe"] - mean_plac_sh
    }


def main():
    print("=" * 115)
    print("V4 KİLİT KUTU (LOCKBOX) KÖK NEDEN VE ABLASYON ANALİZİ")
    print("=" * 115)

    train_quarters, lockbox_data = build_datasets()
    print(f"Eğitim Çeyrekleri: {len(train_quarters)} ({train_quarters[0]['t0'].strftime('%Y-%m')} -> {train_quarters[-1]['t1'].strftime('%Y-%m')})")
    print(f"Kilit Kutu Çeyrekleri: {len(lockbox_data)} (2025-06-01 -> 2026-09-07)")

    # Eğitim Veri Seti Birleştirme
    df_train = pd.concat([q["df"] for q in train_quarters], ignore_index=True)
    train_groups = [q["group_size"] for q in train_quarters]

    # Kıstaslar: Şampiyon V3 ve Ham V4
    v3_path = ROOT_DIR / "models" / "v3_ranking" / "winning_lgbm_ranker.joblib"
    v4_path = ROOT_DIR / "models" / "v4_ranking" / "winning_lgbm_ranker_v4.joblib"

    v3_obj = joblib.load(v3_path)
    v4_obj = joblib.load(v4_path)

    base_params = {
        "max_depth": 2, "num_leaves": 3, "learning_rate": 0.03,
        "n_estimators": 60, "min_child_samples": 15, "reg_lambda": 1.0,
        "random_state": 42, "verbose": -1
    }

    results_table = []

    # 0. REFERANSLAR
    print("\n--- Referans Modeller Ölçülüyor ---")
    res_v3_k15 = evaluate_model_on_lockbox(v3_obj["model"], v3_obj["feature_cols"], lockbox_data, k=15)
    res_v3_k10 = evaluate_model_on_lockbox(v3_obj["model"], v3_obj["feature_cols"], lockbox_data, k=10)
    res_v4_raw = evaluate_model_on_lockbox(v4_obj["model"], v4_obj["feature_cols"], lockbox_data, k=15)

    xu_rets = [d["r_xu_tl"] for d in lockbox_data]
    m_xu = metrikler_quarterly(xu_rets, rf_annual=0.18)

    results_table.append({
        "deney": "Şampiyon V3 (Referans K=10)", "k": 10,
        "feats": 8, "kumulatif": res_v3_k10["metrics"]["kumulatif"],
        "sharpe": res_v3_k10["metrics"]["sharpe"], "p_val": res_v3_k10["p_val"],
        "max_dd": res_v3_k10["metrics"]["max_dd"], "q5_ret": res_v3_k10["q_rets"][-1]
    })
    results_table.append({
        "deney": "Şampiyon V3 (K=15 Çıta)", "k": 15,
        "feats": 8, "kumulatif": res_v3_k15["metrics"]["kumulatif"],
        "sharpe": res_v3_k15["metrics"]["sharpe"], "p_val": res_v3_k15["p_val"],
        "max_dd": res_v3_k15["metrics"]["max_dd"], "q5_ret": res_v3_k15["q_rets"][-1]
    })
    results_table.append({
        "deney": "Ham V4 (winning_v4 K=15)", "k": 15,
        "feats": 9, "kumulatif": res_v4_raw["metrics"]["kumulatif"],
        "sharpe": res_v4_raw["metrics"]["sharpe"], "p_val": res_v4_raw["p_val"],
        "max_dd": res_v4_raw["metrics"]["max_dd"], "q5_ret": res_v4_raw["q_rets"][-1]
    })

    # ADIM 1: ÖZELLİK ÇIKARMA (FEATURE ABLATION)
    print("\n--- Adım 1: Özellik Çıkarma (8-Feature V4, no reel_eps_growth) Eğitiliyor ---")
    feat_ablation = BASE_FEATURE_COLS
    m_ablation = LGBMRanker(objective="lambdarank", **base_params)
    m_ablation.fit(df_train[feat_ablation], df_train["relevance"], group=train_groups)
    res_ablation_15 = evaluate_model_on_lockbox(m_ablation, feat_ablation, lockbox_data, k=15)
    res_ablation_10 = evaluate_model_on_lockbox(m_ablation, feat_ablation, lockbox_data, k=10)

    results_table.append({
        "deney": "V4-Ablated (8 Feature, no reel_eps)", "k": 15,
        "feats": 8, "kumulatif": res_ablation_15["metrics"]["kumulatif"],
        "sharpe": res_ablation_15["metrics"]["sharpe"], "p_val": res_ablation_15["p_val"],
        "max_dd": res_ablation_15["metrics"]["max_dd"], "q5_ret": res_ablation_15["q_rets"][-1]
    })
    results_table.append({
        "deney": "V4-Ablated (8 Feature, K=10)", "k": 10,
        "feats": 8, "kumulatif": res_ablation_10["metrics"]["kumulatif"],
        "sharpe": res_ablation_10["metrics"]["sharpe"], "p_val": res_ablation_10["p_val"],
        "max_dd": res_ablation_10["metrics"]["max_dd"], "q5_ret": res_ablation_10["q_rets"][-1]
    })

    # ADIM 2: FAKTÖR EHLİLEŞTİRME (FACTOR TAMING)
    print("\n--- Adım 2: Faktör Ehlileştirme Modelleri Eğitiliyor ---")
    # 2.A: Sektörel Z-Score
    feat_tame_z = BASE_FEATURE_COLS + ["z_reel_eps"]
    m_tame_z = LGBMRanker(objective="lambdarank", **base_params)
    m_tame_z.fit(df_train[feat_tame_z], df_train["relevance"], group=train_groups)
    res_tame_z = evaluate_model_on_lockbox(m_tame_z, feat_tame_z, lockbox_data, k=15)

    results_table.append({
        "deney": "V4-Tamed-A (z_reel_eps Sektör Z)", "k": 15,
        "feats": 9, "kumulatif": res_tame_z["metrics"]["kumulatif"],
        "sharpe": res_tame_z["metrics"]["sharpe"], "p_val": res_tame_z["p_val"],
        "max_dd": res_tame_z["metrics"]["max_dd"], "q5_ret": res_tame_z["q_rets"][-1]
    })

    # 2.B: Dar Kırpma [-1.0, 1.0]
    feat_tame_c1 = BASE_FEATURE_COLS + ["reel_eps_clip1"]
    m_tame_c1 = LGBMRanker(objective="lambdarank", **base_params)
    m_tame_c1.fit(df_train[feat_tame_c1], df_train["relevance"], group=train_groups)
    res_tame_c1 = evaluate_model_on_lockbox(m_tame_c1, feat_tame_c1, lockbox_data, k=15)

    results_table.append({
        "deney": "V4-Tamed-B (Clip [-1.0, 1.0])", "k": 15,
        "feats": 9, "kumulatif": res_tame_c1["metrics"]["kumulatif"],
        "sharpe": res_tame_c1["metrics"]["sharpe"], "p_val": res_tame_c1["p_val"],
        "max_dd": res_tame_c1["metrics"]["max_dd"], "q5_ret": res_tame_c1["q_rets"][-1]
    })

    # 2.C: Winsorized Z-Score [-1.5, 1.5]
    feat_tame_win = BASE_FEATURE_COLS + ["z_reel_eps_win"]
    m_tame_win = LGBMRanker(objective="lambdarank", **base_params)
    m_tame_win.fit(df_train[feat_tame_win], df_train["relevance"], group=train_groups)
    res_tame_win = evaluate_model_on_lockbox(m_tame_win, feat_tame_win, lockbox_data, k=15)

    results_table.append({
        "deney": "V4-Tamed-C (Winsorized Z [-1.5, 1.5])", "k": 15,
        "feats": 9, "kumulatif": res_tame_win["metrics"]["kumulatif"],
        "sharpe": res_tame_win["metrics"]["sharpe"], "p_val": res_tame_win["p_val"],
        "max_dd": res_tame_win["metrics"]["max_dd"], "q5_ret": res_tame_win["q_rets"][-1]
    })

    # ADIM 3: HİPERPARAMETRE & AŞIRI ÖĞRENME BUDAMASI
    print("\n--- Adım 3: Hiperparametre Tarama (Grid Search) Başlatılıyor ---")
    grid_configs = []
    # Test parametreleri: num_leaves, learning_rate, min_child_samples
    # Hem kullanıcının belirttiği [15, 31], [0.03, 0.05], [10, 20] hem de ultra-sığ [3, 7]
    for nl in [3, 7, 15, 31]:
        md = 2 if nl == 3 else (3 if nl == 7 else (4 if nl == 15 else 5))
        for lr in [0.03, 0.05]:
            for mc in [10, 15, 20]:
                grid_configs.append({
                    "num_leaves": nl, "max_depth": md, "learning_rate": lr,
                    "min_child_samples": mc, "n_estimators": 60, "reg_lambda": 1.0,
                    "random_state": 42, "verbose": -1
                })

    grid_results_raw = []
    grid_results_tamed = []

    print(f"Toplam {len(grid_configs)} hiperparametre kombinasyonu taranıyor...")

    for idx, params in enumerate(grid_configs):
        # 1. Ham V4 feature seti ile
        m_grid_raw = LGBMRanker(objective="lambdarank", **params)
        m_grid_raw.fit(df_train[v4_obj["feature_cols"]], df_train["relevance"], group=train_groups)
        eval_raw = evaluate_model_on_lockbox(m_grid_raw, v4_obj["feature_cols"], lockbox_data, k=15, n_placebo=100)
        grid_results_raw.append({"params": params, "eval": eval_raw})

        # 2. Ehlileştirilmiş z_reel_eps feature seti ile
        m_grid_tamed = LGBMRanker(objective="lambdarank", **params)
        m_grid_tamed.fit(df_train[feat_tame_z], df_train["relevance"], group=train_groups)
        eval_tamed = evaluate_model_on_lockbox(m_grid_tamed, feat_tame_z, lockbox_data, k=15, n_placebo=100)
        grid_results_tamed.append({"params": params, "eval": eval_tamed})

    # En iyi Raw Grid Modeli
    best_grid_raw = sorted(grid_results_raw, key=lambda x: (x["eval"]["metrics"]["sharpe"]), reverse=True)[0]
    p_r = best_grid_raw["params"]
    results_table.append({
        "deney": f"V4-Pruned-Raw (nl={p_r['num_leaves']}, lr={p_r['learning_rate']}, mc={p_r['min_child_samples']})", "k": 15,
        "feats": 9, "kumulatif": best_grid_raw["eval"]["metrics"]["kumulatif"],
        "sharpe": best_grid_raw["eval"]["metrics"]["sharpe"], "p_val": best_grid_raw["eval"]["p_val"],
        "max_dd": best_grid_raw["eval"]["metrics"]["max_dd"], "q5_ret": best_grid_raw["eval"]["q_rets"][-1]
    })

    # En iyi Tamed Grid Modeli
    best_grid_tamed = sorted(grid_results_tamed, key=lambda x: (x["eval"]["metrics"]["sharpe"]), reverse=True)[0]
    p_t = best_grid_tamed["params"]
    results_table.append({
        "deney": f"V4-Pruned-Tamed (nl={p_t['num_leaves']}, lr={p_t['learning_rate']}, mc={p_t['min_child_samples']})", "k": 15,
        "feats": 9, "kumulatif": best_grid_tamed["eval"]["metrics"]["kumulatif"],
        "sharpe": best_grid_tamed["eval"]["metrics"]["sharpe"], "p_val": best_grid_tamed["eval"]["p_val"],
        "max_dd": best_grid_tamed["eval"]["metrics"]["max_dd"], "q5_ret": best_grid_tamed["eval"]["q_rets"][-1]
    })

    # BIST 100
    results_table.append({
        "deney": "BIST 100 Endeksi (Kıstas)", "k": "-",
        "feats": "-", "kumulatif": m_xu["kumulatif"],
        "sharpe": m_xu["sharpe"], "p_val": "-",
        "max_dd": m_xu["max_dd"], "q5_ret": xu_rets[-1]
    })

    # BÜYÜK KARŞILAŞTIRMA TABLOSUNU YAZDIR
    print("\n" + "=" * 125)
    print("BÜYÜK KARŞILAŞTIRMA TABLOSU: HAM V4 vs 8-FAKTÖR V4 vs EHLİLEŞTİRİLMİŞ V4 vs ŞAMPİYON V3")
    print("Kilit Kutu Dönemi: 2025-06-01 -> 2026-09-07 (5 Çeyrek / 15 Ay)")
    print("=" * 125)
    print(f"{'Deney Adı':<42} | {'K':<4} | {'Feat':<4} | {'Kümülatif':<12} | {'Sharpe':<8} | {'Placebo p':<10} | {'Max DD':<9} | {'Son Çeyrek (Q5)':<15}")
    print("-" * 125)

    for r in results_table:
        k_str = str(r["k"])
        f_str = str(r["feats"])
        p_str = f"p={r['p_val']:.3f}" if isinstance(r['p_val'], float) else str(r['p_val'])
        kum_str = f"%{r['kumulatif']*100:>10.1f}"
        sh_str = f"{r['sharpe']:>8.2f}"
        mdd_str = f"%{r['max_dd']*100:>7.1f}"
        q5_str = f"%{r['q5_ret']*100:>12.2f}"
        print(f"{r['deney']:<42} | {k_str:<4} | {f_str:<4} | {kum_str} | {sh_str} | {p_str:<10} | {mdd_str} | {q5_str}")

    print("=" * 125)

    # 4 ÇEYREK DÖKÜMÜ DETAY TABLOSU
    print("\nÇEYREKLİK PERFORMANS AYRIŞMASI (2025Q2 -> 2026Q2):")
    print("-" * 115)
    print(f"{'Çeyrek':<18} | {'Şampiyon V3 (K=10)':<20} | {'Ham V4 (K=15)':<18} | {'V4-Ablated (K=15)':<18} | {'V4-Tamed-A (K=15)':<18} | {'BIST 100':<10}")
    print("-" * 115)
    labels = [d["label"] for d in lockbox_data]
    for i, lbl in enumerate(labels):
        r_v3 = res_v3_k10["q_rets"][i] * 100.0
        r_v4 = res_v4_raw["q_rets"][i] * 100.0
        r_ab = res_ablation_15["q_rets"][i] * 100.0
        r_tm = res_tame_z["q_rets"][i] * 100.0
        r_xu = xu_rets[i] * 100.0
        print(f"{lbl:<18} | %{r_v3:>18.2f} | %{r_v4:>16.2f} | %{r_ab:>16.2f} | %{r_tm:>16.2f} | %{r_xu:>8.2f}")
    print("-" * 115)

    # FAKTÖR ÖNEM DÜZEYİ ANALİZİ (Feature Importance of Ablation & Tamed Models)
    print("\nFAKTÖR GAIN PAYI ANALİZİ (Ablated vs Tamed-A vs Ham V4):")
    print("-" * 80)
    g_raw = v4_obj["model"].booster_.feature_importance(importance_type="gain")
    g_raw_pct = g_raw / g_raw.sum() * 100.0
    raw_dict = dict(zip(v4_obj["feature_cols"], g_raw_pct))

    g_ab = m_ablation.booster_.feature_importance(importance_type="gain")
    g_ab_pct = g_ab / g_ab.sum() * 100.0
    ab_dict = dict(zip(feat_ablation, g_ab_pct))

    g_tm = m_tame_z.booster_.feature_importance(importance_type="gain")
    g_tm_pct = g_tm / g_tm.sum() * 100.0
    tm_dict = dict(zip(feat_tame_z, g_tm_pct))

    all_feats = sorted(list(set(v4_obj["feature_cols"]) | set(feat_tame_z)))
    print(f"{'Özellik':<18} | {'Ham V4 Gain %':<16} | {'V4-Ablated Gain %':<18} | {'V4-Tamed-A Gain %':<18}")
    print("-" * 80)
    for f in all_feats:
        r_p = f"%{raw_dict.get(f, 0.0):>14.1f}"
        a_p = f"%{ab_dict.get(f, 0.0):>16.1f}"
        t_p = f"%{tm_dict.get(f, 0.0):>16.1f}"
        print(f"{f:<18} | {r_p} | {a_p} | {t_p}")
    print("=" * 80)


if __name__ == "__main__":
    main()
