"""
models/calibration_ensemble.py — FAZ B1: Multiclass Kalibre Edilmiş 3'lü Ensemble
===================================================================================

Değişiklikler (FAZ B1):
  - Multiclass mod (3 sınıf: 0/1/2) desteklendi.
  - predict_proba_all: Multiclass'ta 3 sınıf olasılık matrisini döner.
  - Sniper sinyali: P(label=2) >= eşik → Hızlı TP beklentisi
  - Fikir birliği std: P(kazanma=1|2) üzerinden hesaplanır.
"""

import sys
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

import pandas as pd
import numpy as np
import joblib
import lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.isotonic import IsotonicRegression
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

_MULTICLASS = getattr(cfg, "MULTICLASS_LABEL", True)


class SingleModelCalibrator:
    """
    Tek bir sınıflandırıcı için Isotonic veya Sigmoid olasılık kalibratörü.
    Multiclass modda her sınıf için ayrı kalibratör kullanılmaz;
    bunun yerine P(kazanma) = P(label>=1) kalibre edilir.
    """
    def __init__(self, base_estimator: Any, method: str = "isotonic", multiclass: bool = False):
        self.base_estimator = base_estimator
        self.method = method
        self.multiclass = multiclass
        self.calibrator = None
        self._n_classes = 2

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series, X_calib: pd.DataFrame, y_calib: pd.Series):
        self.base_estimator.fit(X_train, y_train)
        self._n_classes = y_train.nunique()

        if self.multiclass and self._n_classes > 2:
            # Multiclass: P(label>=1) kalibre et
            raw_probs_all = self.base_estimator.predict_proba(X_calib)
            raw_pos_prob = raw_probs_all[:, 1:].sum(axis=1)   # P(1) + P(2)
            y_bin = (y_calib.values >= 1).astype(int)
        else:
            raw_pos_prob = self.base_estimator.predict_proba(X_calib)[:, 1]
            y_bin = y_calib.values

        if self.method == "isotonic" and len(X_calib) >= 500:
            self.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            self.calibrator.fit(raw_pos_prob, y_bin)
        else:
            self.calibrator = LogisticRegression(C=1.0, max_iter=500, random_state=42)
            self.calibrator.fit(raw_pos_prob.reshape(-1, 1), y_bin)

        return self

    def predict_proba(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns:
            cal_pos_prob: Kalibre edilmiş P(kazanma) = P(label>=1) — Ana sinyal skoru
            raw_probs_all: Ham tüm sınıf olasılıkları (multiclass için [n, 3])
        """
        raw_probs_all = self.base_estimator.predict_proba(X)

        if self.multiclass and self._n_classes > 2:
            raw_pos_prob = raw_probs_all[:, 1:].sum(axis=1)
        else:
            raw_pos_prob = raw_probs_all[:, 1]

        if isinstance(self.calibrator, IsotonicRegression):
            cal_pos_prob = self.calibrator.predict(raw_pos_prob)
        else:
            cal_pos_prob = self.calibrator.predict_proba(raw_pos_prob.reshape(-1, 1))[:, 1]

        return np.clip(cal_pos_prob, 0.0, 1.0), raw_probs_all


class SniperEnsemblePipeline:
    """
    3 Kalibre Modelden oluşan Multiclass-Ready Sniper Karar Motoru.
    """
    def __init__(
        self,
        lgbm_params:   Optional[Dict[str, Any]] = None,
        rf_params:     Optional[Dict[str, Any]] = None,
        logreg_params: Optional[Dict[str, Any]] = None,
        calib_method:  str = "isotonic",
    ):
        self.lgbm_params   = lgbm_params   or {"random_state": 42, "verbosity": -1, "n_jobs": -1}
        self.rf_params     = rf_params     or {"class_weight": "balanced", "random_state": 42, "n_jobs": -1}
        self.logreg_params = logreg_params or {"C": 0.1, "max_iter": 1000, "class_weight": "balanced", "random_state": 42}
        self.calib_method  = calib_method
        self.multiclass    = _MULTICLASS

        self.raw_lgbm = lgb.LGBMClassifier(**self.lgbm_params)
        self.raw_rf   = RandomForestClassifier(**self.rf_params)
        self.raw_logreg_pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf",    LogisticRegression(**self.logreg_params))
        ])

        self.cal_lgbm   = SingleModelCalibrator(self.raw_lgbm,              method=self.calib_method, multiclass=self.multiclass)
        self.cal_rf     = SingleModelCalibrator(self.raw_rf,                method=self.calib_method, multiclass=self.multiclass)
        self.cal_logreg = SingleModelCalibrator(self.raw_logreg_pipeline,   method="sigmoid",         multiclass=self.multiclass)

        self.feature_names = []
        self.is_fitted     = False

    def fit(self, X_train, y_train, X_calib, y_calib) -> "SniperEnsemblePipeline":
        self.feature_names = list(X_train.columns)
        logger.debug(f"3 model fit ve kalibre ediliyor ({len(X_train)} train, {len(X_calib)} calib)...")
        self.cal_lgbm.fit(X_train, y_train, X_calib, y_calib)
        self.cal_rf.fit(X_train, y_train, X_calib, y_calib)
        self.cal_logreg.fit(X_train, y_train, X_calib, y_calib)
        self.is_fitted = True
        return self

    def predict_proba_all(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
        """
        Tüm kalibre modellerin P(kazanma>=1) ortalamasını ve std'sini döner.

        Returns:
            final_prob:     Ortalama kalibre P(kazanma) — ana sinyal skoru
            consensus_std:  3 modelin fikir birliği sapması
            individual:     {p_lgbm, p_rf, p_logreg, raw_class_probs_lgbm}
        """
        if not self.is_fitted:
            raise ValueError("Model henüz eğitilmedi!")

        p_lgbm,   raw_lgbm   = self.cal_lgbm.predict_proba(X)
        p_rf,     raw_rf     = self.cal_rf.predict_proba(X)
        p_logreg, raw_logreg = self.cal_logreg.predict_proba(X)

        prob_matrix   = np.vstack([p_lgbm, p_rf, p_logreg])
        final_prob    = np.mean(prob_matrix, axis=0)
        consensus_std = np.std(prob_matrix, axis=0)

        individual = {
            "p_lgbm":   p_lgbm,
            "p_rf":     p_rf,
            "p_logreg": p_logreg,
            # Multiclass: ham sınıf dağılımı (label=2 ihtimali için)
            "raw_class_probs_lgbm": raw_lgbm,
        }
        return final_prob, consensus_std, individual

    def predict_sniper(
        self,
        X: pd.DataFrame,
        threshold: float = cfg.SINYAL_ESIGI_NORMAL,
        max_std: float = cfg.CONSENSUS_STD_MAX,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Sniper Karar Fonksiyonu: P(kazanma) >= eşik & std <= max_std"""
        final_prob, consensus_std, _ = self.predict_proba_all(X)
        sniper_signal = (final_prob >= threshold) & (consensus_std <= max_std)
        return sniper_signal, final_prob, consensus_std

    def save(self, filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, filepath, compress=3)
        logger.info(f"Model pipeline kaydedildi: {filepath}")

    @classmethod
    def load(cls, filepath: Path) -> "SniperEnsemblePipeline":
        if not filepath.exists():
            raise FileNotFoundError(f"Model dosyası bulunamadı: {filepath}")
        return joblib.load(filepath)
