"""
models/dataset_loader.py — FAZ 4: Veri Seti Yükleyici & Purged Walk-Forward Bölücü
=================================================================================
Plan referansı: FAZ 4.1 (bist_sinyal_botu_proje_plani_v2.md)

Özellikler:
  - data/labeled/ altındaki tüm etiketli hisseleri birleştirir veya hisse bazlı filtreler.
  - Sızıntısız Zaman Bölme (Purged Walk-Forward + 5 Gün Embargo).
  - Feature matrisi (X) ve Etiket vektörünü (y) temizleyip hazırlar.
"""

import sys
from pathlib import Path
from typing import List, Tuple, Dict, Optional

import pandas as pd
import numpy as np
from loguru import logger

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

# Model eğitimine GİRMEYECEK meta ve ham fiyat kolonları
HARIC_KOLONLAR = [
    "open", "high", "low", "close", "volume", "dividends", "stock_splits",
    "label", "entry_date", "entry_price", "upper_barrier", "lower_barrier",
    "exit_date", "exit_price", "exit_reason", "holding_days", "trade_return"
]


def yukle_tum_etiketli_veri(
    hisseler: Optional[List[str]] = None,
    sirala_tarih: bool = True,
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    Tüm etiketli parquet dosyalarını yükler.
    
    Returns:
        X (DataFrame): Model feature matrisi (kategorikler sayısal kodlanmış)
        y (Series): 0/1 Etiket vektörü
        meta_df (DataFrame): İşlem detayları (entry_price, exit_reason, holding_days vb.)
    """
    labeled_dir = cfg.DATA_LABEL
    files = list(labeled_dir.glob("*.parquet"))
    
    if hisseler is not None:
        sembol_dosyalar = [f"{s.replace('.', '_')}.parquet" for s in hisseler]
        files = [f for f in files if f.name in sembol_dosyalar]
        
    if not files:
        raise FileNotFoundError(f"{labeled_dir} altında etiketli parquet dosyası bulunamadı!")
        
    df_list = []
    for f in sorted(files):
        df_tmp = pd.read_parquet(f)
        df_tmp["ticker"] = f.stem.replace("_IS", "")
        df_list.append(df_tmp)
        
    combined_df = pd.concat(df_list, axis=0)
    if sirala_tarih:
        combined_df = combined_df.sort_index()

    # Meta bilgiler
    meta_cols = [c for c in combined_df.columns if c in HARIC_KOLONLAR or c == "ticker"]
    meta_df = combined_df[meta_cols].copy()

    # Etiket
    y = combined_df["label"].astype(int)

    # Feature matrisi
    feature_cols = [c for c in combined_df.columns if c not in HARIC_KOLONLAR and c != "ticker"]
    X = combined_df[feature_cols].copy()

    # Kategorik sütunları sayısal kodla (One-Hot veya Category Code)
    for col in X.select_dtypes(include=["object", "category"]).columns:
        X[col] = X[col].astype("category").cat.codes

    return X, y, meta_df


def olustur_purged_walk_forward_splits(
    X: pd.DataFrame,
    y: pd.Series,
    embargo_days: int = 5,
) -> List[Dict[str, pd.DataFrame]]:
    """
    Zaman sıralı Purged Walk-Forward pencereleri oluşturur.
    Her pencere arasında etiket çakışmalarını önlemek için 'embargo_days' kadar boşluk bırakılır.
    
    Pencere 1: Train [2018-2021] -> Test [2022]
    Pencere 2: Train [2018-2022] -> Test [2023]
    Pencere 3: Train [2018-2023] -> Test [2024]
    Kör Test (Holdout): Train [2018-2024] -> Test [2025-2026]
    """
    years = X.index.year
    splits = []

    # Walk-Forward Pencereleri
    test_years = [2022, 2023, 2024, 2025]

    for test_yr in test_years:
        train_mask = years < test_yr
        
        if test_yr == 2025:
            # 2025 ve 2026 birlikte holdout
            test_mask = years >= test_yr
            test_name = "Holdout [2025-2026]"
        else:
            test_mask = years == test_yr
            test_name = f"Test [{test_yr}]"

        X_train_full = X[train_mask]
        y_train_full = y[train_mask]

        X_test_raw = X[test_mask]
        y_test_raw = y[test_mask]

        if len(X_train_full) == 0 or len(X_test_raw) == 0:
            continue

        # Embargo Uygulaması:
        # Train setinin son embargo günlerini at (overlap sızıntısını önle).
        # 21 günlük residual getiri ufkunda minimum 30 takvim günü embargo şart;
        # 5 iş günü * 2 = 10 gün eskiden yetersiz kalıyordu.
        train_end_date = X_train_full.index.max()
        embargo_takvim_gun = max(embargo_days * 6, 30)  # min 30 takvim günü garantisi
        embargo_cutoff = train_end_date - pd.Timedelta(days=embargo_takvim_gun)
        
        purged_train_mask = X_train_full.index <= embargo_cutoff
        X_train = X_train_full[purged_train_mask]
        y_train = y_train_full[purged_train_mask]

        # Train içinden zaman sıralı Kalibrasyon seti ayır (son %20)
        n_tr = len(X_train)
        split_point = int(n_tr * 0.80)
        
        X_calib = X_train.iloc[split_point:].copy()
        y_calib = y_train.iloc[split_point:].copy()
        
        # Train ile Kalibrasyon arasına da embargo (aynı minimum garanti)
        calib_start_date = X_calib.index.min()
        train_cutoff = calib_start_date - pd.Timedelta(days=max(embargo_days * 6, 30))
        
        tr_mask = (X_train.index <= train_cutoff)
        X_tr = X_train[tr_mask].copy()
        y_tr = y_train[tr_mask].copy()

        splits.append({
            "name": test_name,
            "train_range": f"{X_tr.index.min().date()} → {X_tr.index.max().date()}",
            "calib_range": f"{X_calib.index.min().date()} → {X_calib.index.max().date()}",
            "test_range": f"{X_test_raw.index.min().date()} → {X_test_raw.index.max().date()}",
            "X_train": X_tr,
            "y_train": y_tr,
            "X_calib": X_calib,
            "y_calib": y_calib,
            "X_test": X_test_raw,
            "y_test": y_test_raw,
        })

    return splits
