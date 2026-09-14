"""
scratch/faz3_v6_evaluation.py
==============================
FAZ 3 V6: REEL PEG SENTEZİ VE MONOTONİK YÖN KISITLARI (MONOTONIC CONSTRAINTS)
-----------------------------------------------------------------------------
Kullanıcı Direktifleri:
  1. Feature Synthesis (reel_peg):
     - pb / reel_eps_growth (Zarar eden veya büyümesi negatif şirketlere cezalandırıcı tavan değer)
     - Sektörel z-skoru ile normalize edilir (z_reel_peg)
     - reel_eps_growth ve z_pb yerine sadece bu sentezlenmiş faktör verilir.
  2. Monotonic Constraints (Yön Kısıtları - GBDT):
     - z_roe: +1 (ROE artışı)
     - z_fcf: +1 (Nakit akım artışı)
     - z_mom: +1 (Momentum artışı)
     - z_net_borc: -1 (Borç azalışı - yüksek borç cezalandırılır)
     - z_reel_peg: -1 (Değerleme ucuzluğu - yüksek PEG cezalandırılır)
     - reel_faiz: 0 (Makro kısıtsız)
     - usd_mom_60: 0 (Makro kısıtsız)
     - usd_mom_90: 0 (Makro kısıtsız)
  3. Hedef:
     - Orijinal hedef değişken (fwd_ret relevance) ile 2019-2025 eğitimi
     - 4-Fold Purged Walk-Forward (2022-2025) OOS metrikleri
     - 1) Yeni Faktör Gain Dağılımı
     - 2) Information Ratio (IR) ve Aktif Alfa vs BIST 88
     - 3) Max Drawdown ve Beta analizi
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
K_TOP = 15

# V6 Feature Listesi ve Monotonic Kısıtlar
FEATURE_COLS_V6 = [
    "z_roe",        # +1
    "z_fcf",        # +1
    "z_mom",        # +1
    "z_net_borc",   # -1 (Borç arttıkça getiri beklentisi azalmalı)
    "z_reel_peg",   # -1 (PEG arttıkça / pahalılaştıkça getiri beklentisi azalmalı)
    "reel_faiz",    #  0 (Makro)
    "usd_mom_60",   #  0 (Makro)
    "usd_mom_90"    #  0 (Makro)
]

MONOTONE_CONSTRAINTS_V6 = [1, 1, 1, -1, -1, 0, 0, 0]

V6_LGBM_PARAMS = {
    "boosting_type": "gbdt",
    "monotone_constraints": MONOTONE_CONSTRAINTS_V6,
    "max_depth": 2,
    "num_leaves": 3,
    "learning_rate": 0.03,
    "n_estimators": 60,
    "min_child_samples": 15,
    "reg_lambda": 1.0,
    "random_state": 42,
    "verbose": -1
}


def build_v6_dataset():
    """V6 veri setini oluşturur."""
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
            net_kar = curr.get("net_kar", 0.0) or 0.0

            # Borç / EBITDA (Pozitif = Borçlu, Negatif = Net Nakitte)
            net_borc_ebitda = net_b / max(1.0, abs(ebit)) if not is_bank else np.nan

            cand_feats = extract_candidate_features(
                t0, s, fiyat_dict[s], seri_usdtry, pit_bellek.get(s, []), tufe_aylik
            )
            reel_eps = cand_feats.get("reel_eps_growth", np.nan)

            # ─── 1. REEL PEG HESAPLAMASI (FEATURE SYNTHESIS) ───
            # Eğer şirket zarar ediyorsa, büyümesi negatifse veya veri eksikse: Cezalandırıcı Tavan (100.0)
            # Eğer büyüme pozitifse: pb / reel_eps (Daha düşük değer = daha ucuz büyüme)
            p_ceiling = 100.0
            if pd.notna(reel_eps) and reel_eps > 0.005 and net_kar > 0 and pd.notna(pb) and pb > 0:
                peg_val = float(pb / np.clip(reel_eps, 0.005, 2.0))
                peg_val = min(peg_val, p_ceiling)
            else:
                peg_val = p_ceiling

            p_sub = fiyat_dict[s][fiyat_dict[s].index <= t0]
            is_taban_riski, _ = ardisik_taban_tespit(p_sub, lookback_gun=10, min_taban=5, taban_esik=-0.095)

            q_rows.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "net_borc_ebitda": net_borc_ebitda,
                "reel_peg_raw": peg_val,
                "fwd_ret": rets[s],
                "is_taban_riski": is_taban_riski
            })

        df_q = pd.DataFrame(q_rows)

        # Sektörel Z-Skorları
        df_q["z_roe"]      = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_fcf"]      = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_mom"]      = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_net_borc"] = hesapla_sektor_zscore(df_q, "net_borc_ebitda", min_grup=4).fillna(0.0) # Yüksek = Çok Borçlu
        df_q["z_reel_peg"] = hesapla_sektor_zscore(df_q, "reel_peg_raw", min_grup=4).fillna(0.0)     # Yüksek = Pahalı PEG / Cezalı

        df_q["reel_faiz"]  = reel_faiz
        df_q["usd_mom_60"] = mom_60_usd
        df_q["usd_mom_90"] = mom_90_usd

        # Orijinal Hedef Değişken (fwd_ret relevance quintiles 0-4)
        try:
            df_q["relevance"] = pd.qcut(df_q["fwd_ret"], q=5, labels=False, duplicates="drop")
        except Exception:
            df_q["relevance"] = pd.qcut(df_q["fwd_ret"], q=3, labels=False, duplicates="drop")

        quarters_data.append({
            "t0": t0, "t1": t1, "yil": t0.year,
            "df": df_q, "group_size": len(df_q)
        })

    print(f"V6 Veri Seti Üretildi: {len(quarters_data)} Çeyrek ({quarters_data[0]['t0'].strftime('%Y-%m')} -> {quarters_data[-1]['t1'].strftime('%Y-%m')})")
    return quarters_data


def run_v6_walk_forward(quarters_data):
    """4-Fold Purged Walk-Forward ile V6'yı değerlendirir."""
    folds = [
        {"name": "Fold 1 (2022)", "train_end": pd.Timestamp("2021-12-31"), "test_start": pd.Timestamp("2022-01-01"), "test_end": pd.Timestamp("2022-12-31"), "donem": "Donem_A"},
        {"name": "Fold 2 (2023)", "train_end": pd.Timestamp("2022-12-31"), "test_start": pd.Timestamp("2023-01-01"), "test_end": pd.Timestamp("2023-12-31"), "donem": "Donem_A"},
        {"name": "Fold 3 (2024)", "train_end": pd.Timestamp("2023-12-31"), "test_start": pd.Timestamp("2024-01-01"), "test_end": pd.Timestamp("2024-12-31"), "donem": "Donem_B"},
        {"name": "Fold 4 (2025)", "train_end": pd.Timestamp("2024-12-31"), "test_start": pd.Timestamp("2025-01-01"), "test_end": pd.Timestamp("2025-05-31"), "donem": "Donem_B"},
    ]

    history = []

    for fold in folds:
        train_q = [q for q in quarters_data if (q["t0"] >= TRAIN_START_DATE) and (q["t1"] <= fold["train_end"])]
        test_q = [q for q in quarters_data if (q["t0"] >= fold["test_start"]) and (q["t0"] <= fold["test_end"])]

        if not train_q or not test_q:
            continue

        df_train = pd.concat([q["df"] for q in train_q], ignore_index=True)
        train_groups = [q["group_size"] for q in train_q]

        model = LGBMRanker(objective="lambdarank", **V6_LGBM_PARAMS)
        model.fit(df_train[FEATURE_COLS_V6], df_train["relevance"], group=train_groups)

        for q in test_q:
            df_test = q["df"].copy()
            df_test["model_score"] = model.predict(df_test[FEATURE_COLS_V6])

            df_valid = df_test[~df_test["is_taban_riski"]].copy()
            if len(df_valid) < 20:
                df_valid = df_test.copy()

            mkt_ret = float(df_valid["fwd_ret"].mean())
            df_sorted = df_valid.sort_values("model_score", ascending=False)
            top_k = df_sorted.iloc[:K_TOP]
            r_k = float(top_k["fwd_ret"].mean()) - TRANSACTION_COST

            history.append({
                "t0": q["t0"],
                "quarter": q["t0"].strftime("%Y-Q") + str((q["t0"].month - 1) // 3 + 1),
                "donem": fold["donem"],
                "mkt_ret": mkt_ret,
                "r_model": r_k,
                "top15": top_k["sembol"].tolist()
            })

    return history


def train_v6_full_model(quarters_data):
    """Tüm 2019-09 -> 2025-05 kümesinde V6'yı eğitir ve Gain analizi yapar."""
    train_q = [q for q in quarters_data if (q["t0"] >= TRAIN_START_DATE) and (q["t1"] <= LOCKBOX_BARRIER)]
    df_all = pd.concat([q["df"] for q in train_q], ignore_index=True)
    groups = [q["group_size"] for q in train_q]

    model = LGBMRanker(objective="lambdarank", **V6_LGBM_PARAMS)
    model.fit(df_all[FEATURE_COLS_V6], df_all["relevance"], group=groups)

    imp_split = model.feature_importances_
    imp_gain = model.booster_.feature_importance(importance_type="gain")
    df_imp = pd.DataFrame({
        "feature": FEATURE_COLS_V6,
        "constraint": MONOTONE_CONSTRAINTS_V6,
        "split": imp_split,
        "gain": imp_gain
    }).sort_values("gain", ascending=False)
    df_imp["gain_pct"] = df_imp["gain"] / df_imp["gain"].sum() * 100.0

    tree_dump = model.booster_.dump_model()["tree_info"]
    root_splits = {}
    for tree in tree_dump:
        struct = tree["tree_structure"]
        if "split_feature" in struct:
            f = FEATURE_COLS_V6[struct["split_feature"]]
            root_splits[f] = root_splits.get(f, 0) + 1

    return model, df_imp, root_splits


def compute_comprehensive_metrics(history):
    """Model metriklerini ve BIST 88 benchmark kıyaslamasını hesaplar."""
    r_arr = np.array([h["r_model"] for h in history])
    m_arr = np.array([h["mkt_ret"] for h in history])
    n = len(r_arr)

    # 1. Getiri & Sharpe
    kum = float(np.prod(1.0 + r_arr) - 1.0)
    cagr = float((1.0 + kum) ** (4.0 / max(1, n)) - 1.0) if kum > -0.99 else -0.99
    rf_q = (1.0 + RF_ANNUAL) ** (0.25) - 1.0
    diff = r_arr - rf_q
    std = float(np.std(r_arr, ddof=1))
    sharpe = float(np.mean(diff) / (std + 1e-8) * 2.0)

    # 2. Max Drawdown
    eq = np.cumprod(1.0 + r_arr)
    peaks = np.maximum.accumulate(eq)
    dds = (eq - peaks) / peaks
    mdd = float(np.min(dds))

    # 3. Active Return, Tracking Error & Information Ratio vs BIST 88
    active_arr = r_arr - m_arr
    mean_active_q = float(np.mean(active_arr))
    mean_active_ann = float(mean_active_q * 4.0)
    std_active_q = float(np.std(active_arr, ddof=1))
    tracking_error_ann = float(std_active_q * 2.0)
    ir_ann = float(mean_active_ann / (tracking_error_ann + 1e-8)) if tracking_error_ann > 1e-6 else 0.0

    # 4. Portföy Betası
    cov_mat = np.cov(r_arr, m_arr)
    beta = float(cov_mat[0, 1] / cov_mat[1, 1])

    # 5. Dönem B Metrikleri
    b_records = [h for h in history if h["donem"] == "Donem_B"]
    b_r = np.array([h["r_model"] for h in b_records])
    b_kum = float(np.prod(1.0 + b_r) - 1.0)
    b_cagr = float((1.0 + b_kum) ** (4.0 / max(1, len(b_r))) - 1.0) if b_kum > -0.99 else -0.99
    b_diff = b_r - rf_q
    b_std = float(np.std(b_r, ddof=1))
    b_sharpe = float(np.mean(b_diff) / (b_std + 1e-8) * 2.0)

    return {
        "kumulatif": kum,
        "cagr": cagr,
        "sharpe": sharpe,
        "max_dd": mdd,
        "mean_active_ann": mean_active_ann,
        "tracking_error_ann": tracking_error_ann,
        "information_ratio": ir_ann,
        "beta": beta,
        "donem_b_kumulatif": b_kum,
        "donem_b_cagr": b_cagr,
        "donem_b_sharpe": b_sharpe
    }


def main():
    print("=" * 115)
    print("FAZ 3 V6 MODELİ TESTİ: REEL PEG SENTEZİ + MONOTONIC CONSTRAINTS GBDT")
    print("=" * 115)

    quarters_data = build_v6_dataset()

    print("\n1. 4-Fold Purged Walk-Forward Simülasyonu yürütülüyor...")
    history = run_v6_walk_forward(quarters_data)

    print("\n2. V6 Modeli 2019-2025 eğitim setinde eğitiliyor (Gain & Kök Düğüm Dağılımı)...")
    model_v6, df_imp, root_splits = train_v6_full_model(quarters_data)

    m6 = compute_comprehensive_metrics(history)

    # Karşılaştırma İçin Önceki Rapor Verileri
    stres_path = ROOT_DIR / "reports" / "faz3_v5_stres_testi_sonuclari.json"
    with open(stres_path, "r", encoding="utf-8") as f:
        stres_data = json.load(f)
    t3 = stres_data["test_3_information_ratio"]

    print("\n" + "=" * 115)
    print("SONUÇ 1: YENİ FAKTÖR AĞIRLIKLARI (GAIN) DAĞILIMI — TEKEL DURUMU")
    print("=" * 115)
    print(f"{'Faktör':<16} | {'Yön Kısıtı':<12} | {'Split Sayısı':<14} | {'Toplam Gain':<14} | {'Gain Payı (%)':<14}")
    print("-" * 115)
    for _, r in df_imp.iterrows():
        c_str = f"+1 (Artış)" if r["constraint"] == 1 else (f"-1 (Azalış)" if r["constraint"] == -1 else "0 (Serbest)")
        print(f"{r['feature']:<16} | {c_str:<12} | {r['split']:>10.0f}     | {r['gain']:>12.2f}  | %{r['gain_pct']:>11.2f}")
    print("-" * 115)

    print("\nKÖK DÜĞÜM (DERİNLİK 0) DAĞILIMI (60 AĞAÇ):")
    for f, cnt in sorted(root_splits.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {f:<16}: {cnt:>2} ağacın kök düğümü (%{cnt/60*100:>4.1f})")

    print("\n" + "=" * 125)
    print("SONUÇ 2 & 3: DÖRT KUŞAK KARŞILAŞTIRMASI (V3-KONTROL vs V4-RAW vs V5-NEUTRAL vs V6-MONOTONIC)")
    print("=" * 125)
    print(f"{'Model':<16} | {'Aktif Alfa (Yıllık)':<20} | {'Tracking Error':<16} | {'Information Ratio':<18} | {'Portföy Betası':<15} | {'Max Drawdown':<14} | {'Donem B Küm.':<14}")
    print("-" * 125)

    v3_ir = t3["V3-Kontrol"]
    v4_ir = t3["V4-Raw"]
    v5_ir = t3["V5-Neutral"]

    print(f"{'V3-Kontrol':<16} | %{v3_ir['mean_active_annualized']*100:>17.2f} | %{v3_ir['tracking_error_annualized']*100:>13.2f} | {v3_ir['information_ratio']:>16.3f} | {v3_ir['portfolio_beta']:>13.3f} | %-13.39        | % -6.76")
    print(f"{'V4-Raw':<16} | %{v4_ir['mean_active_annualized']*100:>17.2f} | %{v4_ir['tracking_error_annualized']*100:>13.2f} | {v4_ir['information_ratio']:>16.3f} | {v4_ir['portfolio_beta']:>13.3f} | % -9.73        | % +8.15")
    print(f"{'V5-Neutral':<16} | %{v5_ir['mean_active_annualized']*100:>17.2f} | %{v5_ir['tracking_error_annualized']*100:>13.2f} | {v5_ir['information_ratio']:>16.3f} | {v5_ir['portfolio_beta']:>13.3f} | %-11.50        | % +4.15")
    print(f"{'V6-Monotonic':<16} | %{m6['mean_active_ann']*100:>17.2f} | %{m6['tracking_error_ann']*100:>13.2f} | {m6['information_ratio']:>16.3f} | {m6['beta']:>13.3f} | %{m6['max_dd']*100:>10.2f}    | %{m6['donem_b_kumulatif']*100:>+6.2f}")
    print("-" * 125)

    # Detaylı Çeyreklik Çıktı
    print("\nV6 ÇEYREKLİK GETİRİ PERFORMANSI (2022-2025):")
    for h in history:
        mkt = h["mkt_ret"] * 100
        mod = h["r_model"] * 100
        alfa = mod - mkt
        print(f"  • {h['quarter']} ({h['donem']}): BIST88 = %{mkt:>6.2f} | V6 = %{mod:>6.2f} | Aktif Alfa = %{alfa:>+6.2f}")

    # JSON Olarak Kaydet
    output_path = ROOT_DIR / "reports" / "faz3_v6_evaluation_sonuclari.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "v6_metrics": m6,
            "v6_feature_importance": df_imp.to_dict("records"),
            "v6_root_splits": root_splits,
            "v6_history": history
        }, f, indent=2, default=str)
    print(f"\n✅ V6 sonuçları kaydedildi: {output_path}")


if __name__ == "__main__":
    main()
