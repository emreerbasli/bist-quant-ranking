"""
Faz B.5 PIT verisiyle dogrulama testi.
fundamental_pit.py MOD 2 uzerinden ceyreklik PIT verisini okur,
kaba skor hesaplar ve 5 hisse ornegi gosterir.
"""
import sys
sys.path.insert(0, ".")
import pandas as pd
import config as cfg
from features.fundamental_pit import cek_pit_kesit, pit_mevcut_mu

test_hisseler = ["THYAO.IS", "AKBNK.IS", "BIMAS.IS", "EREGL.IS", "TUPRS.IS"]
tarih = pd.Timestamp("2026-01-01")

print(f"PIT Veri Dogrulama — Tarih: {tarih.date()}")
print("=" * 65)

for sembol in test_hisseler:
    if pit_mevcut_mu(sembol):
        kayit = cek_pit_kesit(sembol, tarih)
        if kayit:
            print(f"{sembol:<12} | ceyrek: {kayit.get('ceyrek','?'):<8} | "
                  f"ROE: {kayit.get('roe',0) or 0:.3f} | "
                  f"P/B: {kayit.get('pb',0) or 0:.2f} | "
                  f"gecerlilik: {str(kayit.get('gecerlilik_tarihi','?'))[:10]}")
        else:
            print(f"{sembol:<12} | Bu tarih icin veri yok")
    else:
        print(f"{sembol:<12} | PIT dosyasi EKSIK")
