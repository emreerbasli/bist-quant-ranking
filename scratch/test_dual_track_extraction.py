"""
scratch/test_dual_track_extraction.py
=====================================
Sanayi ve Banka kulvarı rasyolarının İş Yatırım cache ve fundamental parquet'lerinden
tam olarak çekilip hesaplanabildiğini doğrulayan test betiği.
"""

import sys
import json
import glob
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

def test_extraction():
    cache_dir = cfg.DATA_RAW / "isyatirim_cache"
    fund_dir = cfg.BASE_DIR / "data" / "fundamentals"

    sample_industrials = ["AEFES", "FROTO", "THYAO", "EREGL", "TUPRS"]
    sample_banks = ["AKBNK", "GARAN", "ISCTR", "YKBNK", "VAKBN"]

    print("--- SANAYİ NUMUNELERİ TESTİ ---")
    for s in sample_industrials:
        p_file = fund_dir / f"{s}_IS.parquet"
        if not p_file.exists():
            continue
        df = pd.read_parquet(p_file)
        print(f"{s}: {len(df)} çeyrek | CFO mevcut: {df['cfo'].notna().sum()} | FCF verim: {df['fcf_verim'].notna().sum()} | İhracat: {df['ihracat_orani'].notna().sum()}")

    print("\n--- BANKA NUMUNELERİ TESTİ ---")
    for b in sample_banks:
        p_file = fund_dir / f"{b}_IS.parquet"
        if not p_file.exists():
            continue
        df = pd.read_parquet(p_file)
        print(f"{b}: {len(df)} çeyrek | ROE: {df['roe'].notna().sum()} | Karşılık: {df['kredi_karsiligi'].notna().sum()}")

    # Cache JSON'larından detaylı rasyo çekimini test et
    print("\n--- CACHE JSON DETAY TESTİ ---")
    with open(cache_dir / "AEFES_2020_XI_29.json", "r", encoding="utf-8") as f:
        aefes_j = json.load(f)
    item_map = {x["itemCode"]: x for x in aefes_j}
    donen = item_map.get("1A", {}).get("value4")
    kisa_borc = item_map.get("2A", {}).get("value4")
    satislar = item_map.get("3C", {}).get("value4")
    satis_maliyet = item_map.get("3CA", {}).get("value4")
    print(f"AEFES 2020Q4 -> Dönen: {donen}, Kısa Borç: {kisa_borc}, Satış: {satislar}, Maliyet: {satis_maliyet}")
    if donen and kisa_borc:
        print(f"Cari Oran: {donen / kisa_borc:.2f}")

    with open(cache_dir / "AKBNK_2020_UFRS.json", "r", encoding="utf-8") as f:
        akbnk_j = json.load(f)
    bank_map = {x["itemCode"]: x for x in akbnk_j}
    kredi = bank_map.get("1AF", {}).get("value4")
    npl = bank_map.get("1AFD", {}).get("value4")
    mevduat = bank_map.get("2A", {}).get("value4")
    net_faiz = bank_map.get("3C", {}).get("value4")
    print(f"AKBNK 2020Q4 -> Kredi: {kredi}, NPL: {npl}, Mevduat: {mevduat}, Net Faiz: {net_faiz}")
    if kredi and mevduat:
        print(f"Kredi/Mevduat: {kredi / mevduat:.2f}")
    if npl and kredi:
        print(f"NPL Oranı: %{npl / kredi * 100:.2f}")

if __name__ == "__main__":
    test_extraction()
