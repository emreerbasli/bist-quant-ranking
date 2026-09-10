"""
scratch/run_faz_d_candidate_race.py
===================================
ADIM 3: 4 ADAYLI LGBMRANKER CV YARIŞI (SADECE EĞİTİM PENCERESİ: 2018-09 -> 2025-05)
----------------------------------------------------------------------------------
KİLİT KUTU (2025-06-01 -> 2026-09-07) VERİSİNE KESİNLİKLE BAKILMAZ / KÖRDÜR.

4 Aday Model:
  Aday 1 (Aşırı Muhafazakâr): max_depth=2, num_leaves=3,  lr=0.03,  n_est=60,  min_child=15, L2=1.0
  Aday 2 (Endüstri Standardı): max_depth=3, num_leaves=7,  lr=0.03,  n_est=80,  min_child=12, L2=1.0
  Aday 3 (Yavaş Öğrenen):      max_depth=3, num_leaves=6,  lr=0.015, n_est=120, min_child=15, L1=0.5, L2=2.0
  Aday 4 (Rejim Etkileşimli):  max_depth=4, num_leaves=11, lr=0.02,  n_est=80,  min_child=10, L2=1.0, colsample=0.7

Doğrulama:
  - Purged TimeSeries Walk-Forward CV (1 Çeyrek Embargo ile).
  - 11 Out-of-Fold Çeyreklik Test (2022Q3 -> 2025Q1).
  - NDCG@15 Değerlendirmesi.
  - Tie-Breaker Kuralı: En iyi aday ile Aday 1 farkı <%2.5 ise Aday 1 seçilir.
"""

import sys
import joblib
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from lightgbm import LGBMRanker
from sklearn.metrics import ndcg_score

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

from scratch.run_faz_c_walk_forward_test import yukle_veriler, hizli_pit, hesapla_mom, getir_tcmb_reel_faiz


def hesapla_sektor_zscore(df, col, min_grup=4):
    zscores = pd.Series(np.nan, index=df.index)
    for sektor, grup in df.groupby("sektor"):
        gecerli = grup[col].dropna()
        if len(gecerli) >= min_grup:
            mu  = gecerli.mean()
            std = gecerli.std()
        else:
            gecerli = df[col].dropna()
            mu  = gecerli.mean()
            std = gecerli.std()
        if std > 1e-8:
            zscores.loc[grup.index] = (grup[col] - mu) / std
        else:
            zscores.loc[grup.index] = 0.0
    return zscores.clip(-3.0, 3.0)


def hazirla_egitim_veriseti():
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    tarihler_60 = pd.date_range("2018-09-01", "2026-08-01", freq="3MS")
    hisseler = sorted(fiyat_dict.keys())

    # KİLİT KUTU SINIRI: t1 <= 2025-06-01 (Kilit kutu 2025-06-01'de başlar)
    LOCKBOX_START = pd.Timestamp("2025-06-01")

    quarters_data = []

    for i in range(len(tarihler_60) - 1):
        t0, t1 = tarihler_60[i], tarihler_60[i + 1]

        # Kilit kutuya ve sonrasına ait dönemleri KESİNLİKLE EĞİTİME ALMA
        if t0 >= LOCKBOX_START:
            continue

        rets = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        mevcut = [s for s in hisseler if s in rets]
        if len(mevcut) < 32:
            continue

        # Makro Rejim Göstergeleri (t0 anında point-in-time)
        reel_faiz = getir_tcmb_reel_faiz(t0, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t0]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

        satirlar = []
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

            satirlar.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb,
                "fwd_ret": rets[s]
            })

        df_q = pd.DataFrame(satirlar)

        # Sektör z-skorları (kesitsel)
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)  # Ters PB

        # Makro Değişkenler (Tüm hisseler için aynı)
        df_q["reel_faiz"]   = reel_faiz
        df_q["usd_mom_60"]  = mom_60_usd
        df_q["usd_mom_90"]  = mom_90_usd

        # Ground Truth Sıralama Hedefi (Relevance Score 0 - 9 deciles)
        try:
            df_q["relevance"] = pd.qcut(df_q["fwd_ret"], q=10, labels=False, duplicates="drop")
        except Exception:
            df_q["relevance"] = pd.qcut(df_q["fwd_ret"], q=5, labels=False, duplicates="drop")

        quarters_data.append({
            "period_idx": len(quarters_data),
            "t0": t0, "t1": t1, "yil": t0.year,
            "df": df_q,
            "group_size": len(df_q)
        })

    print(f"Eğitim Penceresi Çeyrek Sayısı: {len(quarters_data)} (Son çeyrek: {quarters_data[-1]['t0'].strftime('%Y-%m-%d')} -> {quarters_data[-1]['t1'].strftime('%Y-%m-%d')})")
    return quarters_data


FEATURE_COLS = ["z_fcf", "z_roe", "z_mom", "z_borc", "z_pb", "reel_faiz", "usd_mom_60", "usd_mom_90"]

CANDIDATES = {
    "Aday 1 (Aşırı Muhafazakâr)": {
        "max_depth": 2, "num_leaves": 3, "learning_rate": 0.03,
        "n_estimators": 60, "min_child_samples": 15, "reg_lambda": 1.0,
        "random_state": 42, "verbose": -1
    },
    "Aday 2 (Endüstri Standardı)": {
        "max_depth": 3, "num_leaves": 7, "learning_rate": 0.03,
        "n_estimators": 80, "min_child_samples": 12, "reg_lambda": 1.0,
        "random_state": 42, "verbose": -1
    },
    "Aday 3 (Yavaş Öğrenen)": {
        "max_depth": 3, "num_leaves": 6, "learning_rate": 0.015,
        "n_estimators": 120, "min_child_samples": 15, "reg_alpha": 0.5, "reg_lambda": 2.0,
        "random_state": 42, "verbose": -1
    },
    "Aday 4 (Rejim Etkileşimli)": {
        "max_depth": 4, "num_leaves": 11, "learning_rate": 0.02,
        "n_estimators": 80, "min_child_samples": 10, "reg_lambda": 1.0, "colsample_bytree": 0.7,
        "random_state": 42, "verbose": -1
    }
}


def run_candidate_race(quarters_data):
    # Purged TimeSeries Walk-Forward:
    # 15. çeyrekten başla (2022 ortası), 1 çeyrek embargo uygula, 27. çeyreğe kadar test et (toplam 11 test fold)
    min_train_quarters = 15
    embargo = 1

    test_folds = range(min_train_quarters + embargo, len(quarters_data))
    print(f"Toplam Değerlendirilecek Walk-Forward Test Katı (Fold): {len(test_folds)}")

    results = {name: [] for name in CANDIDATES.keys()}
    fold_details = []

    for test_idx in test_folds:
        test_q = quarters_data[test_idx]
        train_end = test_idx - embargo
        train_qs = quarters_data[:train_end]

        # Eğitim Verisini Birleştir
        df_train = pd.concat([q["df"] for q in train_qs], ignore_index=True)
        train_groups = [q["group_size"] for q in train_qs]
        X_train = df_train[FEATURE_COLS]
        y_train = df_train["relevance"]

        # Test Verisi
        df_test = test_q["df"]
        X_test = df_test[FEATURE_COLS]
        y_test = df_test["relevance"]
        y_true_ret = df_test["fwd_ret"].values

        fold_name = f"{test_q['t0'].strftime('%Y-%m')} ({test_q['yil']}Q{(test_q['t0'].month-1)//3 + 1})"

        fold_row = {"fold": fold_name}

        for name, params in CANDIDATES.items():
            model = LGBMRanker(objective="lambdarank", **params)
            model.fit(X_train, y_train, group=train_groups)

            preds = model.predict(X_test)

            # NDCG@15 Hesapla
            # scikit-learn ndcg_score 2D array bekler: [n_samples, n_items]
            try:
                ndcg15 = ndcg_score([y_test.values], [preds], k=15)
            except Exception:
                ndcg15 = np.nan

            results[name].append(ndcg15)
            fold_row[name] = ndcg15

        fold_details.append(fold_row)

    # Fold Bazında Sonuç Tablosu
    df_folds = pd.DataFrame(fold_details)
    print("\n" + "=" * 115)
    print("PURGED WALK-FORWARD CV FOLD BAZINDA NDCG@15 SONUÇLARI (2022 - 2025Q1)")
    print("=" * 115)
    print(f"{'Test Çeyreği':<20} | {'Aday 1 (Muhafazakâr)':<22} | {'Aday 2 (Standart)':<20} | {'Aday 3 (Yavaş)':<18} | {'Aday 4 (Rejim)':<18}")
    print("-" * 115)
    for _, r in df_folds.iterrows():
        print(f"{r['fold']:<20} | {r['Aday 1 (Aşırı Muhafazakâr)']:>20.4f} | {r['Aday 2 (Endüstri Standardı)']:>18.4f} | {r['Aday 3 (Yavaş Öğrenen)']:>16.4f} | {r['Aday 4 (Rejim Etkileşimli)']:>16.4f}")

    # Özet Metrikler
    summary = []
    for name in CANDIDATES.keys():
        arr = np.array(results[name])
        mean_s = np.nanmean(arr)
        std_s = np.nanstd(arr)
        min_s = np.nanmin(arr)
        max_s = np.nanmax(arr)
        summary.append({
            "name": name, "mean_ndcg": mean_s, "std_ndcg": std_s,
            "min_ndcg": min_s, "max_ndcg": max_s
        })

    df_sum = pd.DataFrame(summary).sort_values("mean_ndcg", ascending=False)
    print("\n" + "=" * 115)
    print("4 ADAY MODELİN NİHAİ KARŞILAŞTIRMA VE TİE-BREAKER TABLOSU")
    print("=" * 115)
    print(f"{'Aday Model Adı':<30} | {'Ortalama NDCG@15':<18} | {'Std (Volatilite)':<18} | {'Min NDCG':<12} | {'Max NDCG':<12}")
    print("-" * 115)
    for _, r in df_sum.iterrows():
        print(f"{r['name']:<30} | {r['mean_ndcg']:>16.4f} | {r['std_ndcg']:>16.4f} | {r['min_ndcg']:>10.4f} | {r['max_ndcg']:>10.4f}")

    # TIE-BREAKER KURALI UYGULAMASI:
    top_candidate = df_sum.iloc[0]
    aday_1 = df_sum[df_sum["name"] == "Aday 1 (Aşırı Muhafazakâr)"].iloc[0]

    rel_diff = (top_candidate["mean_ndcg"] - aday_1["mean_ndcg"]) / aday_1["mean_ndcg"] * 100.0

    print("\n" + "-" * 85)
    print("TIE-BREAKER DEĞERLENDİRMESİ:")
    print(f"En Yüksek Skorlu Model: {top_candidate['name']} (NDCG: {top_candidate['mean_ndcg']:.4f})")
    print(f"Aday 1 (Aşırı Muhafazakâr): NDCG: {aday_1['mean_ndcg']:.4f}")
    print(f"Göreceli Fark (Relative Delta): %{rel_diff:+.2f}")

    if rel_diff <= 2.5:
        chosen_candidate = aday_1
        reason = f"Fark (%{rel_diff:+.2f} <= %2.5) eşiğin altında kaldı. Sadeliği ve sıfır overfitting riskini ödüllendiren kural gereği Aday 1 seçildi."
    else:
        chosen_candidate = top_candidate
        reason = f"En yüksek skorlu aday ({top_candidate['name']}), Aday 1'den %{rel_diff:.2f} (> %2.5) belirgin biçimde üstün olduğu için seçildi."

    print(f"\n🏆 KAZANAN MODEL: {chosen_candidate['name']}")
    print(f"Seçim Gerekçesi: {reason}")
    print("-" * 85)

    # Kazanan Modeli Tüm Eğitim Setinde (2018-01 -> 2025-05) Eğit ve Dondur
    print("\nKazanan model tüm eğitim penceresinde (2018-09 -> 2025-05) eğitiliyor ve donduruluyor...")
    df_all_train = pd.concat([q["df"] for q in quarters_data], ignore_index=True)
    train_all_groups = [q["group_size"] for q in quarters_data]

    final_model = LGBMRanker(objective="lambdarank", **CANDIDATES[chosen_candidate["name"]])
    final_model.fit(df_all_train[FEATURE_COLS], df_all_train["relevance"], group=train_all_groups)

    # Feature Importance (Gain ve Split)
    imp_split = final_model.feature_importances_
    imp_gain = final_model.booster_.feature_importance(importance_type="gain")

    df_imp = pd.DataFrame({
        "feature": FEATURE_COLS,
        "split_count": imp_split,
        "gain": imp_gain
    }).sort_values("gain", ascending=False)
    df_imp["gain_pct"] = df_imp["gain"] / df_imp["gain"].sum() * 100.0

    print("\n" + "=" * 85)
    print(f"KAZANAN MODEL ({chosen_candidate['name']}) FAKTÖR ÖNEM DÜZEYLERİ (FEATURE IMPORTANCE)")
    print("=" * 85)
    print(f"{'Öznitelik (Feature)':<20} | {'Bölünme (Split)':<16} | {'Toplam Gain':<18} | {'Gain Payı (%)':<15}")
    print("-" * 85)
    for _, r in df_imp.iterrows():
        print(f"{r['feature']:<20} | {r['split_count']:>14.0f} | {r['gain']:>16.2f} | %{r['gain_pct']:>12.1f}")

    # Modeli dondur ve kaydet
    model_save_path = ROOT_DIR / "scratch" / "winning_lgbm_ranker.joblib"
    joblib.dump({
        "model": final_model,
        "candidate_name": chosen_candidate["name"],
        "params": CANDIDATES[chosen_candidate["name"]],
        "feature_cols": FEATURE_COLS,
        "df_imp": df_imp,
        "cv_summary": df_sum,
        "fold_details": df_folds
    }, model_save_path)
    print(f"\nModel başarıyla donduruldu ve kaydedildi: {model_save_path}")
    print("KİLİT KUTU KASASINA KESİNLİKLE DOKUNULMAMIŞTIR.")


if __name__ == "__main__":
    quarters_data = hazirla_egitim_veriseti()
    run_candidate_race(quarters_data)
