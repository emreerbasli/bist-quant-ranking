"""
models/train.py — FAZ B1: Multiclass Master Model Eğitimi & Sniper Doğrulama Pipeline
========================================================================================

Değişiklikler (FAZ B1):
  - Multiclass (0/1/2) etiket desteği: degerlendir_tahminler güncellendi
  - v2 model dizinine kaydediliyor: models/v2/
  - v1 (binary) ile karşılaştırma raporu üretiliyor
  - Sniper sinyal: P(kazanma>=1) eşik + özellikle P(label=2) izleniyor
"""

import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple

import pandas as pd
import numpy as np
from sklearn.metrics import (
    roc_auc_score, average_precision_score, brier_score_loss,
    precision_score, recall_score, f1_score, balanced_accuracy_score
)
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg
from models.dataset_loader import yukle_tum_etiketli_veri, olustur_purged_walk_forward_splits
from models.optimization import optimize_lightgbm, optimize_random_forest, optimize_logistic_regression
from models.calibration_ensemble import SniperEnsemblePipeline

_MULTICLASS = getattr(cfg, "MULTICLASS_LABEL", True)

# ─── Log ayarı ───────────────────────────────────────────────────────────────
logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add(cfg.LOGS_DIR / "train_{time:YYYY-MM-DD}.log",
           rotation="1 day", retention="30 days", level="DEBUG", encoding="utf-8")


def degerlendir_tahminler(
    y_true: pd.Series,
    y_prob: np.ndarray,
    consensus_std: np.ndarray,
    raw_class_probs: np.ndarray = None,
) -> Dict[str, Any]:
    """
    Kapsamlı Out-of-Sample performans ve Sniper metriklerini hesaplar.

    FAZ B1 Multiclass:
      - y_prob = P(kazanma) = P(label >= 1) — Ana sinyal skoru
      - raw_class_probs (optional): [n, 3] ham sınıf olasılıkları
      - Ek metrikler: P(label=2) için PR-AUC, Hızlı TP oranı
    """
    y_arr = y_true.values

    # Binary: 0=kayıp, 1=kazanç (her iki TP türü)
    y_bin = (y_arr >= 1).astype(int)

    # ─── Binary Metrikler ─────────────────────────────────────────────────────
    auc    = roc_auc_score(y_bin, y_prob)
    pr_auc = average_precision_score(y_bin, y_prob)
    brier  = brier_score_loss(y_bin, y_prob)
    taban_winrate = y_bin.mean() * 100.0

    # Kademeli eşikler
    esikler = [0.50, 0.60, 0.70, 0.75, 0.80]
    esik_raporu = {}
    for th in esikler:
        mask = (y_prob >= th) & (consensus_std <= cfg.CONSENSUS_STD_MAX)
        n_tr = int(mask.sum())
        if n_tr > 0:
            prec = precision_score(y_bin[mask], np.ones(n_tr, dtype=int), zero_division=0) * 100.0
        else:
            prec = 0.0
        esik_raporu[f"islem_sayisi_{int(th*100)}"] = n_tr
        esik_raporu[f"precision_{int(th*100)}_%"]  = round(prec, 1)

    # Top Decile
    p90       = np.percentile(y_prob, 90)
    top10_mask = y_prob >= p90
    n_top10    = int(top10_mask.sum())
    prec_top10 = precision_score(y_bin[top10_mask], np.ones(n_top10, dtype=int), zero_division=0) * 100.0 if n_top10 > 0 else 0.0

    sonuc = {
        "ornek_sayisi":          len(y_true),
        "taban_winrate_%":       round(taban_winrate, 1),
        "roc_auc":               round(auc, 3),
        "pr_auc":                round(pr_auc, 3),
        "brier_score":           round(brier, 4),
        "top_decile_precision_%": round(prec_top10, 1),
        "top_decile_islem":      n_top10,
        **esik_raporu,
    }

    # ─── FAZ B1 Multiclass Ek Metrikler ──────────────────────────────────────
    if _MULTICLASS and raw_class_probs is not None and raw_class_probs.shape[1] > 2:
        y_class2  = (y_arr == 2).astype(int)
        y_class12 = (y_arr >= 1).astype(int)
        p_class2  = raw_class_probs[:, 2]

        pr_auc_hizli = average_precision_score(y_class2, p_class2) if y_class2.sum() > 0 else 0.0
        hizli_tp_oran = y_class2.mean() * 100.0
        yavas_tp_oran = ((y_arr == 1).mean()) * 100.0

        sonuc.update({
            "pr_auc_hizli_tp":    round(pr_auc_hizli, 3),
            "hizli_tp_orani_%":   round(hizli_tp_oran, 1),
            "yavas_tp_orani_%":   round(yavas_tp_oran, 1),
            "kayip_orani_%":      round((y_arr == 0).mean() * 100.0, 1),
        })

    return sonuc


def calistir_walk_forward_egitimi(
    n_optuna_trials: int = 25,
    model_surumu: str = "v2",
) -> Tuple[List[Dict], SniperEnsemblePipeline]:
    """
    Purged Walk-Forward doğrulama döngüsünü çalıştırır.
    model_surumu: "v1" (binary) veya "v2" (multiclass)
    """
    logger.info(f"{'═'*70}")
    logger.info(f"FAZ B1: Purged Walk-Forward Eğitimi — Model {model_surumu.upper()}")
    logger.info(f"Mod: {'MULTICLASS (0/1/2)' if _MULTICLASS else 'BINARY (0/1)'}")
    logger.info(f"{'═'*70}")

    X, y, meta_df = yukle_tum_etiketli_veri()

    if _MULTICLASS:
        n0 = int((y == 0).sum())
        n1 = int((y == 1).sum())
        n2 = int((y == 2).sum())
        logger.info(
            f"Yüklenen Veri: {len(X):,} satır | {len(X.columns)} feature\n"
            f"  Etiket Dağılımı: Kayıp(0)={n0:,} (%{n0/len(y)*100:.1f}) | "
            f"Yavaş TP(1)={n1:,} (%{n1/len(y)*100:.1f}) | "
            f"Hızlı TP(2)={n2:,} (%{n2/len(y)*100:.1f})"
        )
    else:
        logger.info(f"Yüklenen Veri: {len(X):,} satır, {len(X.columns)} feature, {y.sum():,} pozitif (%{y.mean()*100:.1f})")

    splits = olustur_purged_walk_forward_splits(X, y, embargo_days=5)
    logger.info(f"Walk-Forward Pencere Sayısı: {len(splits)}")

    wf_sonuclari = []
    best_lgbm = best_rf = best_lr = None

    for i, split in enumerate(splits, 1):
        name = split["name"]
        logger.info(f"\n{'─'*60}")
        logger.info(f"[Pencere {i}/{len(splits)}] {name}")
        logger.info(f"  Train: {split['train_range']} ({len(split['X_train']):,})")
        logger.info(f"  Calib: {split['calib_range']} ({len(split['X_calib']):,})")
        logger.info(f"  Test : {split['test_range']} ({len(split['X_test']):,})")

        # 1. Sniper Hiperparametre Optimizasyonu
        logger.info("  → Optuna optimizasyonu çalıştırılıyor...")
        best_lgbm = optimize_lightgbm(split["X_train"], split["y_train"], split["X_calib"], split["y_calib"], n_trials=n_optuna_trials)
        best_rf   = optimize_random_forest(split["X_train"], split["y_train"], split["X_calib"], split["y_calib"], n_trials=max(10, n_optuna_trials // 2))
        best_lr   = optimize_logistic_regression(split["X_train"], split["y_train"], split["X_calib"], split["y_calib"], n_trials=10)

        # 2. Kalibre Edilmiş 3'lü Ensemble
        pipeline = SniperEnsemblePipeline(lgbm_params=best_lgbm, rf_params=best_rf, logreg_params=best_lr)
        pipeline.fit(split["X_train"], split["y_train"], split["X_calib"], split["y_calib"])

        # 3. Out-of-Sample Değerlendirme
        final_prob, consensus_std, individual = pipeline.predict_proba_all(split["X_test"])
        raw_class = individual.get("raw_class_probs_lgbm")
        metrics   = degerlendir_tahminler(split["y_test"], final_prob, consensus_std, raw_class)
        metrics["pencere"] = name
        wf_sonuclari.append(metrics)

        logger.info(
            f"  Sonuçlar: PR-AUC={metrics['pr_auc']:.3f} | ROC-AUC={metrics['roc_auc']:.3f} | Brier={metrics['brier_score']:.4f}\n"
            f"  Sniper %80 Precision: %{metrics['precision_80_%']:.1f} ({metrics['islem_sayisi_80']} işlem)\n"
            f"  Top Decile Precision: %{metrics['top_decile_precision_%']:.1f} | Taban WinRate: %{metrics['taban_winrate_%']:.1f}"
        )
        if _MULTICLASS and "pr_auc_hizli_tp" in metrics:
            logger.info(f"  Hızlı TP PR-AUC: {metrics['pr_auc_hizli_tp']:.3f} | Hızlı TP Oranı: %{metrics['hizli_tp_orani_%']:.1f}")

    # 4. Nihai Üretim Modeli
    logger.info(f"\n{'═'*70}")
    logger.info("Nihai Üretim Modeli (Production Pipeline) Eğitiliyor...")

    n_all         = len(X)
    train_cutoff  = int(n_all * 0.85)
    X_prod_tr     = X.iloc[:train_cutoff]
    y_prod_tr     = y.iloc[:train_cutoff]
    X_prod_cal    = X.iloc[train_cutoff:]
    y_prod_cal    = y.iloc[train_cutoff:]

    prod_pipeline = SniperEnsemblePipeline(lgbm_params=best_lgbm, rf_params=best_rf, logreg_params=best_lr)
    prod_pipeline.fit(X_prod_tr, y_prod_tr, X_prod_cal, y_prod_cal)

    # Kaydet
    model_path    = cfg.MODELS_DIR / model_surumu / f"ensemble_sniper_{model_surumu}.joblib"
    aktif_path    = cfg.MODELS_DIR / "aktif" / "ensemble_sniper.joblib"
    prod_pipeline.save(model_path)
    prod_pipeline.save(aktif_path)

    # Feature Importance
    feat_imp = pd.DataFrame({
        "feature":    prod_pipeline.feature_names,
        "importance": prod_pipeline.raw_lgbm.feature_importances_,
    }).sort_values("importance", ascending=False)
    feat_imp.to_csv(cfg.MODELS_DIR / model_surumu / "feature_importance.csv", index=False)

    logger.info(f"✅ Model {model_surumu.upper()} kaydedildi: {model_path}")
    return wf_sonuclari, prod_pipeline


master_train_pipeline = calistir_walk_forward_egitimi


def yazdir_sniper_raporu(wf_sonuclari: List[Dict], baslik: str = "FAZ 4") -> None:
    """Walk-Forward sonuçlarını özet tablo olarak ekrana basar."""
    df_res = pd.DataFrame(wf_sonuclari)
    print(f"\n{'='*90}")
    print(f"{baslik}: PURGED WALK-FORWARD & SNIPER ENSEMBLE EĞİTİM RAPORU")
    print(f"{'='*90}")
    kolonlar = [
        "pencere", "taban_winrate_%", "pr_auc", "roc_auc", "brier_score",
        "top_decile_precision_%", "precision_70_%", "islem_sayisi_70",
        "precision_80_%", "islem_sayisi_80",
    ]
    if _MULTICLASS:
        kolonlar += ["pr_auc_hizli_tp", "hizli_tp_orani_%", "yavas_tp_orani_%", "kayip_orani_%"]
    gosterge = df_res[[c for c in kolonlar if c in df_res.columns]]
    print(gosterge.to_string(index=False))
    print(f"{'='*90}")


def karsilastir_v1_v2(v1_sonuclari: List[Dict], v2_sonuclari: List[Dict]) -> pd.DataFrame:
    """V1 (binary) ile V2 (multiclass) Walk-Forward metriklerini karşılaştırır."""
    rows = []
    for s1, s2 in zip(v1_sonuclari, v2_sonuclari):
        rows.append({
            "Pencere":      s1["pencere"],
            "PR-AUC v1":   s1.get("pr_auc", 0),
            "PR-AUC v2":   s2.get("pr_auc", 0),
            "ΔPRX":        round(s2.get("pr_auc", 0) - s1.get("pr_auc", 0), 3),
            "Brier v1":    s1.get("brier_score", 0),
            "Brier v2":    s2.get("brier_score", 0),
            "Δ Brier":     round(s2.get("brier_score", 0) - s1.get("brier_score", 0), 4),
            "P@80 v1 %":   s1.get("precision_80_%", 0),
            "P@80 v2 %":   s2.get("precision_80_%", 0),
            "ΔP@80":       round(s2.get("precision_80_%", 0) - s1.get("precision_80_%", 0), 1),
            "Hızlı TP%":   s2.get("hizli_tp_orani_%", "-"),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    sonuclar, model = calistir_walk_forward_egitimi(n_optuna_trials=25, model_surumu="v2")
    yazdir_sniper_raporu(sonuclar, baslik="FAZ B1 — V2 Multiclass")
