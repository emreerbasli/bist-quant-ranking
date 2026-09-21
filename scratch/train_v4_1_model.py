"""
scratch/train_v4_1_model.py
===========================
RESMİ V4.1 LGBMRanker MODELİ EĞİTİM, DONDURMA VE ÖNBELLEK GÜNCELLEME BETİĞİ
--------------------------------------------------------------------------
Faktörler (9 Adet):
  ['z_fcf', 'z_roe', 'z_mom', 'z_borc', 'z_pb', 'reel_faiz', 'usd_mom_60', 'usd_mom_90', 'z_reel_eps']
Optimum Hiperparametreler:
  num_leaves=15, max_depth=4, learning_rate=0.03, min_child_samples=15,
  n_estimators=60, reg_lambda=1.0, random_state=42, objective="lambdarank"
"""

import sys
import shutil
import warnings
from pathlib import Path
from datetime import datetime

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

LOCKBOX_BARRIER = pd.Timestamp("2025-06-01")
FEATURE_COLS_V4_1 = [
    "z_fcf", "z_roe", "z_mom", "z_borc", "z_pb",
    "reel_faiz", "usd_mom_60", "usd_mom_90", "z_reel_eps"
]

V4_1_PARAMS = {
    "objective": "lambdarank",
    "num_leaves": 15,
    "max_depth": 4,
    "learning_rate": 0.03,
    "min_child_samples": 15,
    "n_estimators": 60,
    "reg_lambda": 1.0,
    "random_state": 42,
    "verbose": -1,
    "n_jobs": -1
}


def build_train_data(fiyat_dict, seri_usdtry, pit_bellek, tufe_aylik):
    print("--- 1. Eğitim Veri Seti (2019-09 -> 2025-05) Üretiliyor ---")
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
        df_q["z_fcf"]  = hesapla_sektor_zscore(df_q, "fcf_v", min_grup=4).fillna(0.0)
        df_q["z_roe"]  = hesapla_sektor_zscore(df_q, "roe", min_grup=4).fillna(0.0)
        df_q["z_mom"]  = hesapla_sektor_zscore(df_q, "mom", min_grup=4).fillna(0.0)
        df_q["z_borc"] = hesapla_sektor_zscore(df_q, "borc_ebitda", min_grup=4).fillna(0.0)
        df_q["z_pb"]   = -hesapla_sektor_zscore(df_q, "pb", min_grup=4).fillna(0.0)

        # 9. Faktör: z_reel_eps ([-1.5, 1.5] Winsorize)
        df_q["z_reel_eps"] = hesapla_sektor_zscore(df_q, "reel_eps_raw", min_grup=4).fillna(0.0).clip(-1.5, 1.5)

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

    print(f"[TAMAM] {len(train_quarters)} çeyrek hazırlandı.")
    return train_quarters


def main():
    print("=" * 90)
    print("RESMİ V4.1 ŞAMPİYON MODELİ EĞİTİM & SİSTEM ENTEGRASYONU")
    print("=" * 90)

    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    train_quarters = build_train_data(fiyat_dict, seri_usdtry, pit_bellek, tufe_aylik)

    df_train = pd.concat([q["df"] for q in train_quarters], ignore_index=True)
    train_groups = [q["group_size"] for q in train_quarters]

    print(f"\n--- 2. V4.1 LGBMRanker Eğitiliyor (Satır sayısı: {len(df_train)}, Çeyrek: {len(train_groups)}) ---")
    print(f"Özellikler (9 Adet): {FEATURE_COLS_V4_1}")
    print(f"Hiperparametreler: num_leaves={V4_1_PARAMS['num_leaves']}, lr={V4_1_PARAMS['learning_rate']}, min_child={V4_1_PARAMS['min_child_samples']}")

    model = LGBMRanker(**V4_1_PARAMS)
    model.fit(df_train[FEATURE_COLS_V4_1], df_train["relevance"], group=train_groups)

    # Feature Importance
    gains = model.booster_.feature_importance(importance_type="gain")
    splits = model.booster_.feature_importance(importance_type="split")
    tot_gain = gains.sum()
    gain_pcts = (gains / tot_gain) * 100.0

    df_imp = pd.DataFrame({
        "feature": FEATURE_COLS_V4_1,
        "split": splits,
        "gain": gains,
        "gain_pct": gain_pcts
    }).sort_values("gain", ascending=False).reset_index(drop=True)

    print("\n--- 3. Faktör Önem (Gain) Dağılımı ---")
    for _, r in df_imp.iterrows():
        print(f"  • {r['feature']:<15}: Split={r['split']:>3.0f} | Gain={r['gain']:>10.2f} (%{r['gain_pct']:>5.1f})")

    # Skor İstatistiği (Drift Monitörü Çıpaları)
    all_scores = model.predict(df_train[FEATURE_COLS_V4_1])
    # Çeyrek bazlı ortalama ve std dağılımı
    q_means = []
    q_stds = []
    idx_start = 0
    for g in train_groups:
        sub_scores = all_scores[idx_start:idx_start + g]
        q_means.append(float(np.mean(sub_scores)))
        q_stds.append(float(np.std(sub_scores, ddof=1)))
        idx_start += g

    drift_mu_mean = float(np.mean(q_means))
    drift_sigma_mean = float(np.std(q_means, ddof=1)) if len(q_means) > 1 else 0.04
    drift_mu_std = float(np.mean(q_stds))
    drift_sigma_std = float(np.std(q_stds, ddof=1)) if len(q_stds) > 1 else 0.04

    print(f"\n--- 4. V4.1 Tarihsel Skor Dağılım Çıpaları (Drift Monitörü İçin) ---")
    print(f"  • HISTORICAL_V4_BATCH_MEAN_MU    = {drift_mu_mean:+.4f}")
    print(f"  • HISTORICAL_V4_BATCH_MEAN_SIGMA = {drift_sigma_mean:+.4f}")
    print(f"  • HISTORICAL_V4_BATCH_STD_MU     = {drift_mu_std:+.4f}")
    print(f"  • HISTORICAL_V4_BATCH_STD_SIGMA  = {drift_sigma_std:+.4f}")

    # Model Paketleme ve Kaydetme
    v4_dir = ROOT_DIR / "models" / "v4_ranking"
    raw_v4_path = v4_dir / "winning_lgbm_ranker_v4.joblib"
    raw_backup_path = v4_dir / "winning_lgbm_ranker_v4_raw_deprecated.joblib"
    v4_1_save_path = v4_dir / "winning_lgbm_ranker_v4_1.joblib"

    if raw_v4_path.exists() and not raw_backup_path.exists():
        shutil.copy2(raw_v4_path, raw_backup_path)
        print(f"\n[YEDEK] Eski ham V4 modeli yedeklendi: {raw_backup_path}")

    model_payload = {
        "model": model,
        "model_name": "V4.1 LGBMRanker (9 Feature: z_reel_eps win[-1.5, 1.5])",
        "train_window": "2019-09-01 -> 2025-05-30",
        "feature_cols": FEATURE_COLS_V4_1,
        "params": V4_1_PARAMS,
        "df_imp": df_imp,
        "drift_anchors": {
            "mean_mu": drift_mu_mean,
            "mean_sigma": drift_sigma_mean,
            "std_mu": drift_mu_std,
            "std_sigma": drift_sigma_std
        },
        "updated_at": datetime.now().isoformat(),
        "status": "OFFICIAL_V4_1_PRODUCTION_CANDIDATE"
    }

    # Hem winning_lgbm_ranker_v4_1.joblib hem winning_lgbm_ranker_v4.joblib olarak kaydet
    joblib.dump(model_payload, v4_1_save_path)
    joblib.dump(model_payload, raw_v4_path)
    print(f"[KAYDEDİLDİ] V4.1 Modeli: {v4_1_save_path}")
    print(f"[KAYDEDİLDİ] Resmi V4 Bağı: {raw_v4_path}")

    # Güncel Sıralama Önbelleğini (latest_ranking_cache_v4.parquet) Üret
    print("\n--- 5. Güncel Sıralama Önbelleği Üretiliyor ---")
    from models.v4_ranking.ranking_pipeline_v4 import LGBMRankingPipelineV4
    pipeline = LGBMRankingPipelineV4(v4_1_save_path)

    t_now = seri_xu100.index[-1]
    df_feat_cur = pipeline.compute_features(t_now, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
    df_ranked_cur = pipeline.rank_stocks(df_feat_cur)
    df_selected_cur = pipeline.select_top_k_v2(df_feat_cur, k=15, fiyat_dict=fiyat_dict, check_vbts=True)

    cache_rank = v4_dir / "latest_ranking_cache_v4.parquet"
    cache_sel = v4_dir / "latest_selection_cache_v4.parquet"

    df_ranked_cur.to_parquet(cache_rank, index=False)
    df_selected_cur.to_parquet(cache_sel, index=False)
    print(f"[ÖNBELLEK] {cache_rank} yazıldı (Hisse sayısı: {len(df_ranked_cur)}, Sütunlar: {list(df_ranked_cur.columns)})")
    print(f"[ÖNBELLEK] {cache_sel} yazıldı (Top-15 Seçilen: {df_selected_cur['sembol'].tolist()[:5]}...)")

    print("\n" + "=" * 90)
    print("✅ V4.1 MODELİ VE ÖNBELLEK DOSYALARI BAŞARIYLA TAMAMLANDI!")
    print("=" * 90)


if __name__ == "__main__":
    main()
