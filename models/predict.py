"""
models/predict.py — FAZ B1: Multiclass Tahmin & Sinyal Üretim Modülü
======================================================================

Değişiklikler (FAZ B1):
  - Multiclass model (0/1/2) çıktısını doğru yorumlar
  - p_hizli_tp = P(label=2): Hızlı TP olasılığı — Telegram'da öncelik skoru
  - Sinyal eşiği: SINYAL_ESIGI_NORMAL = 0.45 (multiclass kalibre)
  - is_sniper: P(kazanma) >= 0.45 & std <= 0.10
  - is_hizli_tp: P(label=2) >= 0.30 & is_sniper → En yüksek öncelikli sinyal
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd
import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg
from models.calibration_ensemble import SniperEnsemblePipeline
from models.dataset_loader import HARIC_KOLONLAR

_MULTICLASS = getattr(cfg, "MULTICLASS_LABEL", True)
_HIZLI_TP_ESIGI = getattr(cfg, "SINYAL_ESIGI_HIZLI_TP", 0.30)


def yukle_aktif_model(model_yolu: Optional[Path] = None) -> SniperEnsemblePipeline:
    """Aktif modeli yükler."""
    if model_yolu is None:
        model_yolu = cfg.MODELS_DIR / "aktif" / "ensemble_sniper.joblib"
    return SniperEnsemblePipeline.load(model_yolu)


def tahmin_uret_tek_hisse(
    df_feat: pd.DataFrame,
    sembol: str,
    pipeline: Optional[SniperEnsemblePipeline] = None,
) -> Dict[str, Any]:
    """
    Tek bir hissenin en son güncel satırı için model tahmini üretir.

    FAZ B1 Multiclass çıktıları:
      kalibre_olasilik: P(kazanma) = P(label=1) + P(label=2)  — Ana sinyal skoru
      p_hizli_tp:       P(label=2)                             — Hızlı TP ihtimali
      is_sniper:        P(kazanma) >= 0.45 & std <= 0.10
      is_hizli_tp:      is_sniper & P(label=2) >= 0.30         — Öncelikli sinyal
    """
    if pipeline is None:
        pipeline = yukle_aktif_model()

    son_satir   = df_feat.iloc[[-1]].copy()
    feature_cols = [c for c in son_satir.columns if c not in HARIC_KOLONLAR and c != "ticker"]
    X_son       = son_satir[feature_cols].copy()

    for col in X_son.select_dtypes(include=["str", "category"]).columns:
        X_son[col] = X_son[col].astype("category").cat.codes

    # Pipeline feature sıralamasına hizala
    feat_names = [f for f in pipeline.feature_names if f in X_son.columns]
    X_son = X_son[feat_names]

    final_prob, consensus_std, individual = pipeline.predict_proba_all(X_son)
    p_kazanma = float(final_prob[0])
    std       = float(consensus_std[0])

    # Hızlı TP olasılığı: LightGBM ham çıktısından P(label=2) al
    p_hizli_tp = 0.0
    raw_class = individual.get("raw_class_probs_lgbm")
    if raw_class is not None and _MULTICLASS and raw_class.shape[1] > 2:
        p_hizli_tp = float(raw_class[0, 2])

    # Sniper kararı — multiclass kalibre eşikler
    is_sniper     = (p_kazanma >= cfg.SINYAL_ESIGI_NORMAL) and (std <= cfg.CONSENSUS_STD_MAX)
    is_hizli_tp   = is_sniper and (p_hizli_tp >= _HIZLI_TP_ESIGI)

    return {
        "sembol":             sembol,
        "tarih":              str(son_satir.index[-1].date()),
        "kapanis_fiyati":     float(son_satir["close"].iloc[0]),
        "atr_14":             float(son_satir["atr_14"].iloc[0]),
        "kalibre_olasilik":   round(p_kazanma, 4),   # P(kazanma)
        "p_hizli_tp":         round(p_hizli_tp, 4),  # P(label=2) — Hızlı TP
        "fikir_birligi_std":  round(std, 4),
        "lgbm_olasilik":      round(float(individual["p_lgbm"][0]), 4),
        "rf_olasilik":        round(float(individual["p_rf"][0]), 4),
        "logreg_olasilik":    round(float(individual["p_logreg"][0]), 4),
        "is_sniper":          is_sniper,
        "is_hizli_tp":        is_hizli_tp,  # En kaliteli sinyal türü
    }


import concurrent.futures

def _oku_tek_hisse_vektorel(sembol: str, pipeline: SniperEnsemblePipeline) -> Optional[Dict[str, Any]]:
    """Tek hissenin en güncel feature barını okur ve modele hazır hale getirir."""
    dosya_adi = f"{sembol.replace('.', '_')}.parquet"
    feat_path = cfg.DATA_FEAT / dosya_adi
    if not feat_path.exists():
        return None
    try:
        df_feat = pd.read_parquet(feat_path)
        if df_feat.empty:
            return None
        son_satir = df_feat.iloc[[-1]].copy()
        feature_cols = [c for c in son_satir.columns if c not in HARIC_KOLONLAR and c != "ticker"]
        X_son = son_satir[feature_cols].copy()
        for col in X_son.select_dtypes(include=["str", "category"]).columns:
            X_son[col] = X_son[col].astype("category").cat.codes
        feat_names = [f for f in pipeline.feature_names if f in X_son.columns]
        
        return {
            "sembol": sembol,
            "tarih": str(son_satir.index[-1].date()),
            "kapanis_fiyati": float(son_satir["close"].iloc[0]),
            "atr_14": float(son_satir["atr_14"].iloc[0]),
            "X_son": X_son[feat_names],
        }
    except Exception as e:
        logger.warning(f"{sembol} hızlı okuma hatası: {e}")
        return None


def tahmin_uret_tum_evren(
    hisseler: Optional[List[str]] = None,
    max_workers: int = 8,
) -> pd.DataFrame:
    """
    Tüm hisse evreni için en son günün model tahminlerini paralel IO & vektörize toplu çıkarımla üretir.
    Sıralama: Önce Hızlı TP sinyaller, sonra P(kazanma) büyükten küçüğe.
    """
    if hisseler is None:
        hisseler = cfg.HISSELER

    pipeline = yukle_aktif_model()

    # 1. Paralel IO ile en güncel barları topla
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(lambda s: _oku_tek_hisse_vektorel(s, pipeline), hisseler))

    valid_results = [r for r in results if r is not None]
    if not valid_results:
        return pd.DataFrame()

    # 2. Vektörize Toplu Çıkarım (Tek Matris Geçişi)
    X_batch = pd.concat([r["X_son"] for r in valid_results], ignore_index=True)
    final_prob, consensus_std, individual = pipeline.predict_proba_all(X_batch)

    raw_class = individual.get("raw_class_probs_lgbm")
    if raw_class is not None and _MULTICLASS and raw_class.shape[1] > 2:
        p_hizli_tp = raw_class[:, 2]
    else:
        p_hizli_tp = np.zeros(len(valid_results))

    # Sniper Kararları
    is_sniper = (final_prob >= cfg.SINYAL_ESIGI_NORMAL) & (consensus_std <= cfg.CONSENSUS_STD_MAX)
    is_hizli_tp_arr = is_sniper & (p_hizli_tp >= _HIZLI_TP_ESIGI)

    df_out = pd.DataFrame({
        "sembol": [r["sembol"] for r in valid_results],
        "tarih": [r["tarih"] for r in valid_results],
        "kapanis_fiyati": [r["kapanis_fiyati"] for r in valid_results],
        "atr_14": [r["atr_14"] for r in valid_results],
        "kalibre_olasilik": np.round(final_prob, 4),
        "p_hizli_tp": np.round(p_hizli_tp, 4),
        "fikir_birligi_std": np.round(consensus_std, 4),
        "lgbm_olasilik": np.round(individual["p_lgbm"], 4),
        "rf_olasilik": np.round(individual["p_rf"], 4),
        "logreg_olasilik": np.round(individual["p_logreg"], 4),
        "is_sniper": is_sniper,
        "is_hizli_tp": is_hizli_tp_arr,
    })

    # Önce Hızlı TP sinyaller, sonra P(kazanma)
    df_out = df_out.sort_values(
        ["is_hizli_tp", "kalibre_olasilik"],
        ascending=[False, False]
    ).reset_index(drop=True)

    return df_out


if __name__ == "__main__":
    df_res = tahmin_uret_tum_evren()
    goster_cols = ["sembol", "tarih", "kapanis_fiyati", "kalibre_olasilik",
                   "p_hizli_tp", "fikir_birligi_std", "is_sniper", "is_hizli_tp"]
    print("\n--- EN GÜNCEL GÜNÜN MODEL TAHMİNLERİ (SIRALI) ---")
    print(df_res[goster_cols].to_string(index=False))
