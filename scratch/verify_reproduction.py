"""
scratch/verify_reproduction.py
==============================
Doğrulama Scripti:
LGBMRankingPipeline (models/v3_ranking/ranking_pipeline.py) ile
run_lockbox_evaluation.py arasındaki birebir eşitlik (reproduction) denetimi.
"""

import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np
import joblib

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config as cfg
from scratch.run_faz_c_walk_forward_test import yukle_veriler, hizli_pit, hesapla_mom, getir_tcmb_reel_faiz
from scratch.run_lockbox_evaluation import hesapla_sektor_zscore as lockbox_zscore
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline

def main():
    print("=" * 90)
    print("REPRODUCTION DENETİMİ: ranking_pipeline.py vs run_lockbox_evaluation.py")
    print("=" * 90)

    # 1. Verileri yükle
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    hisseler = sorted(fiyat_dict.keys())

    # 2. Modelleri yükle
    orig_obj = joblib.load(ROOT_DIR / "scratch" / "winning_lgbm_ranker.joblib")
    orig_model = orig_obj["model"]
    orig_features = orig_obj["feature_cols"]

    prod_pipeline = LGBMRankingPipeline()
    prod_model = prod_pipeline.model
    prod_features = prod_pipeline.feature_cols

    # Model ağırlıkları/objesi kontrolü
    print(f"Orijinal Model Tipi: {type(orig_model)} | Features: {orig_features}")
    print(f"Production Model Tipi: {type(prod_model)} | Features: {prod_features}")
    assert orig_features == prod_features, "Feature sütunları uyuşmuyor!"

    lockbox_dates = [
        (pd.Timestamp("2025-06-01"), pd.Timestamp("2025-09-01"), "2025Q2"),
        (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-12-01"), "2025Q3"),
        (pd.Timestamp("2025-12-01"), pd.Timestamp("2026-03-01"), "2025Q4"),
        (pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-01"), "2026Q1"),
        (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-09-07"), "2026Q2 (Güncel)"),
    ]

    tum_ceyrekler_tam_eslesme = True

    for t0, t1, label in lockbox_dates:
        print(f"\n>>> ÇEYREK İNCELEMESİ: {label} ({t0.strftime('%Y-%m-%d')} -> {t1.strftime('%Y-%m-%d')})")

        # --- YÖNTEM 1: run_lockbox_evaluation.py Orijinal Mantığı ---
        rets = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        mevcut = [s for s in hisseler if s in rets]
        reel_faiz = getir_tcmb_reel_faiz(t0, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t0]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

        satirlar_orig = []
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

            satirlar_orig.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb
            })

        df_orig = pd.DataFrame(satirlar_orig)
        df_orig["z_fcf"]  = lockbox_zscore(df_orig, "fcf_v", min_grup=4).fillna(0.0)
        df_orig["z_roe"]  = lockbox_zscore(df_orig, "roe", min_grup=4).fillna(0.0)
        df_orig["z_mom"]  = lockbox_zscore(df_orig, "mom", min_grup=4).fillna(0.0)
        df_orig["z_borc"] = lockbox_zscore(df_orig, "borc_ebitda", min_grup=4).fillna(0.0)
        df_orig["z_pb"]   = -lockbox_zscore(df_orig, "pb", min_grup=4).fillna(0.0)
        df_orig["reel_faiz"]  = reel_faiz
        df_orig["usd_mom_60"] = mom_60_usd
        df_orig["usd_mom_90"] = mom_90_usd

        X_orig = df_orig[orig_features]
        df_orig["ml_pred"] = orig_model.predict(X_orig)
        df_orig = df_orig.sort_values("ml_pred", ascending=False).reset_index(drop=True)
        df_orig["rank"] = df_orig.index + 1

        # --- YÖNTEM 2: ranking_pipeline.py Mantığı ---
        df_prod_features = prod_pipeline.compute_features(
            t0, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik
        )
        df_prod_ranked = prod_pipeline.rank_stocks(df_prod_features)

        # Karşılaştırma
        n_orig = len(df_orig)
        n_prod = len(df_prod_ranked)
        print(f"  Hisse Sayısı: Orijinal={n_orig}, Production={n_prod}")

        semboller_orig = set(df_orig["sembol"])
        semboller_prod = set(df_prod_ranked["sembol"])
        fark_semboller = semboller_orig.symmetric_difference(semboller_prod)

        if fark_semboller:
            print(f"  [UYARI] Hisse evreni farklılığı var! Farklı semboller: {fark_semboller}")
            tum_ceyrekler_tam_eslesme = False

        # Ortak semboller üzerinden skor ve sıra kıyaslaması
        ortak = sorted(list(semboller_orig.intersection(semboller_prod)))
        df_orig_ortak = df_orig.set_index("sembol").loc[ortak]
        df_prod_ortak = df_prod_ranked.set_index("sembol").loc[ortak]

        score_diff = np.abs(df_orig_ortak["ml_pred"] - df_prod_ortak["ml_score"])
        max_score_diff = score_diff.max()
        mean_score_diff = score_diff.mean()

        print(f"  Maksimum Skor Farkı: {max_score_diff:.10e}")
        print(f"  Ortalama Skor Farkı: {mean_score_diff:.10e}")

        # Top 15 karşılaştırması
        top15_orig = df_orig.head(15)["sembol"].tolist()
        top15_prod = df_prod_ranked.head(15)["sembol"].tolist()

        top15_ayni = (top15_orig == top15_prod)
        print(f"  Top-15 Sıralaması Birebir Aynı mı?: {'EVET' if top15_ayni else 'HAYIR'}")
        if not top15_ayni:
            print(f"    Orijinal Top-15:   {top15_orig}")
            print(f"    Production Top-15: {top15_prod}")
            tum_ceyrekler_tam_eslesme = False

        # Detaylı feature fark kontrolü
        for feat in ["z_pb", "z_borc", "z_mom", "z_roe", "z_fcf"]:
            f_diff = np.abs(df_orig_ortak[feat] - df_prod_ortak[feat]).max()
            if f_diff > 1e-6:
                print(f"    [FARK] Feature '{feat}' max diff: {f_diff:.6e}")
                tum_ceyrekler_tam_eslesme = False

    print("\n" + "=" * 90)
    print(f"NİHAİ SONUÇ: {'BİREBİR TAM EŞLEŞME' if tum_ceyrekler_tam_eslesme else 'FARKLILIK TESPİT EDİLDİ'}")
    print("=" * 90)

if __name__ == "__main__":
    main()
