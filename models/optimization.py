"""
models/optimization.py — FAZ B1: Multiclass Sniper Hiperparametre Optimizasyonu (Optuna)
==========================================================================================

SNIPER HEDEFİ:
  - Binary mod: PR-AUC + Precision@TopDecile (eski davranış)
  - Multiclass mod: macro-averaged PR-AUC ağırlıklı Sniper skoru
    P(label=2) → Hızlı TP sinyali; bu sınıfın precision'ı en kritik.
"""

import sys
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import numpy as np
import optuna
from optuna.samplers import TPESampler
import lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_score
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

# Optuna loglarını sessize al
optuna.logging.set_verbosity(optuna.logging.WARNING)

_MULTICLASS = getattr(cfg, "MULTICLASS_LABEL", True)


def _hesapla_sniper_skoru(y_true: np.ndarray, y_prob_pos: np.ndarray) -> float:
    """
    Binary Sniper optimizasyon metriği:
    PR-AUC (%50) + Top Decile Precision (%50)
    """
    # Binary: pozitif sınıf = 1 veya 2
    y_bin = (y_true >= 1).astype(int)
    pr_auc = average_precision_score(y_bin, y_prob_pos)

    top_thresh = np.percentile(y_prob_pos, 90)
    y_pred_top = (y_prob_pos >= top_thresh).astype(int)
    prec_top = precision_score(y_bin, y_pred_top, zero_division=0) if y_pred_top.sum() > 0 else 0.0

    return float((0.5 * pr_auc) + (0.5 * prec_top))


def _hesapla_multiclass_sniper_skoru(y_true: np.ndarray, y_prob_all: np.ndarray) -> float:
    """
    Multiclass Sniper optimizasyon metriği:
    - P(label=2): Hızlı TP olasılığı → bu sınıfın PR-AUC ağırlıklı
    - P(label>=1): Genel kazanma olasılığı → ikincil kriter

    Formül: 0.60 * PR-AUC(class2) + 0.40 * PR-AUC(class1_or_2)
    """
    y_class2 = (y_true == 2).astype(int)
    y_class12 = (y_true >= 1).astype(int)

    p_class2  = y_prob_all[:, 2] if y_prob_all.shape[1] > 2 else y_prob_all[:, 1]
    p_class12 = y_prob_all[:, 1:].sum(axis=1)

    pr_auc_2  = average_precision_score(y_class2,  p_class2)  if y_class2.sum()  > 0 else 0.0
    pr_auc_12 = average_precision_score(y_class12, p_class12) if y_class12.sum() > 0 else 0.0

    return float(0.60 * pr_auc_2 + 0.40 * pr_auc_12)


def optimize_lightgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    n_trials: int = 30,
) -> Dict[str, Any]:
    """LightGBM için Sniper optimizasyonu (Binary veya Multiclass)."""
    is_multi = _MULTICLASS and y_train.nunique() > 2

    if is_multi:
        base_params = {
            "objective":        "multiclass",
            "num_class":        3,
            "random_state":     42,
            "verbosity":        -1,
            "n_jobs":           -1,
        }
    else:
        neg_count = (y_train == 0).sum()
        pos_count = (y_train >= 1).sum()
        scale_w   = neg_count / max(1, pos_count)
        base_params = {
            "objective":        "binary",
            "scale_pos_weight": scale_w,
            "random_state":     42,
            "verbosity":        -1,
            "n_jobs":           -1,
        }

    def objective(trial: optuna.Trial) -> float:
        params = {
            **base_params,
            "n_estimators":      trial.suggest_int("n_estimators", 80, 400),
            "max_depth":         trial.suggest_int("max_depth", 3, 6),
            "num_leaves":        trial.suggest_int("num_leaves", 15, 63),
            "min_child_samples": trial.suggest_int("min_child_samples", 20, 100),
            "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.08, log=True),
            "subsample":         trial.suggest_float("subsample", 0.6, 0.95),
            "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.6, 0.95),
            "reg_alpha":         trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
            "reg_lambda":        trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
        model = lgb.LGBMClassifier(**params)
        model.fit(X_train, y_train)
        if is_multi:
            y_prob_all = model.predict_proba(X_val)
            return _hesapla_multiclass_sniper_skoru(y_val.values, y_prob_all)
        else:
            y_prob = model.predict_proba(X_val)[:, 1]
            return _hesapla_sniper_skoru(y_val.values, y_prob)

    study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials)

    best = study.best_params
    best.update(base_params)
    return best


def optimize_random_forest(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    n_trials: int = 20,
) -> Dict[str, Any]:
    """Random Forest için Sniper optimizasyonu."""
    is_multi = _MULTICLASS and y_train.nunique() > 2

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators":    trial.suggest_int("n_estimators", 80, 250),
            "max_depth":       trial.suggest_int("max_depth", 4, 10),
            "min_samples_split": trial.suggest_int("min_samples_split", 10, 50),
            "min_samples_leaf":  trial.suggest_int("min_samples_leaf", 10, 40),
            "max_features":    trial.suggest_float("max_features", 0.4, 0.9),
            "class_weight":    "balanced",
            "random_state":    42,
            "n_jobs":          -1,
        }
        model = RandomForestClassifier(**params)
        model.fit(X_train, y_train)
        if is_multi:
            y_prob_all = model.predict_proba(X_val)
            return _hesapla_multiclass_sniper_skoru(y_val.values, y_prob_all)
        else:
            y_prob = model.predict_proba(X_val)[:, 1]
            return _hesapla_sniper_skoru(y_val.values, y_prob)

    study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials)

    best = study.best_params
    best.update({"class_weight": "balanced", "random_state": 42, "n_jobs": -1})
    return best


def optimize_logistic_regression(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    n_trials: int = 15,
) -> Dict[str, Any]:
    """Logistic Regression için C parametresi optimizasyonu."""
    is_multi = _MULTICLASS and y_train.nunique() > 2

    def objective(trial: optuna.Trial) -> float:
        c_val = trial.suggest_float("C", 1e-4, 10.0, log=True)
        model = LogisticRegression(
            C=c_val,
            max_iter=1000,
            class_weight="balanced",
            random_state=42,
        )
        model.fit(X_train, y_train)
        if is_multi:
            y_prob_all = model.predict_proba(X_val)
            return _hesapla_multiclass_sniper_skoru(y_val.values, y_prob_all)
        else:
            y_prob = model.predict_proba(X_val)[:, 1]
            return _hesapla_sniper_skoru(y_val.values, y_prob)

    study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials)

    base = {
        "C":            study.best_params["C"],
        "max_iter":     1000,
        "class_weight": "balanced",
        "random_state": 42,
    }
    # NOT: scikit-learn >= 1.5'te multi_class parametresi kaldırıldı.
    # Çok sınıflı mod otomatik aktif olur.
    return base

