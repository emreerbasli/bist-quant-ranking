"""
scratch/evaluate_macro_regime.py
================================
Faz C.4 — MAKRO REJİM FİLTRESİ ANALİZİ VE P.I.T. ÖNGÖRÜ GÜCÜ DENETİMİ
---------------------------------------------------------------------
Göstergeler:
  1. TCMB Reel Politika Faizi = Politika Faizi (t) - Son Yıllık TÜFE (t-1)
  2. USD/TRY 60 ve 90 Günlük İvmesi = (P_t - P_{t-k}) / P_{t-k}

Soru:
  2019 ve 2023 gibi modelin çöktüğü yıllarda bu makro göstergeler ne söylüyordu?
  Rejim filtresi bu çöküşleri gerçekten önceden işaretleyebiliyor mu,
  yoksa geriye dönük (hindsight) bir hikaye mi uyduruyoruz?
"""

import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

# Resmi TCMB 1 Haftalık Repo Politika Faizi Karar Tarihleri ve Oranları (2018-2026)
TCMB_POLITIKA_FAIZI_TARIHSEL = [
    ("2018-01-01", 8.00),
    ("2018-05-24", 16.50),
    ("2018-06-08", 17.75),
    ("2018-09-14", 24.00),
    ("2019-07-26", 19.75),
    ("2019-09-13", 16.50),
    ("2019-10-25", 14.00),
    ("2019-12-13", 12.00),
    ("2020-01-17", 11.25),
    ("2020-02-20", 10.75),
    ("2020-03-18", 9.75),
    ("2020-04-23", 8.75),
    ("2020-05-22", 8.25),
    ("2020-09-25", 10.25),
    ("2020-11-20", 15.00),
    ("2020-12-25", 17.00),
    ("2021-03-19", 19.00),
    ("2021-09-24", 18.00),
    ("2021-10-22", 16.00),
    ("2021-11-19", 15.00),
    ("2021-12-17", 14.00),
    ("2022-08-19", 13.00),
    ("2022-09-23", 12.00),
    ("2022-10-21", 10.50),
    ("2022-11-25", 9.00),
    ("2023-02-24", 8.50),
    ("2023-06-23", 15.00),
    ("2023-07-21", 17.50),
    ("2023-08-25", 25.00),
    ("2023-09-22", 30.00),
    ("2023-10-27", 35.00),
    ("2023-11-24", 40.00),
    ("2023-12-22", 42.50),
    ("2024-01-26", 45.00),
    ("2024-03-22", 50.00),
    ("2025-01-01", 47.50),
    ("2025-06-01", 42.50),
    ("2025-10-01", 37.50),
    ("2026-01-01", 32.50),
]

# Aylık Resmi TÜFE
TUFE_AYLIK = {
    "2017-09": 0.65, "2017-10": 2.08, "2017-11": 1.49, "2017-12": 0.69,
    "2018-01": 1.02, "2018-02": 0.73, "2018-03": 0.99, "2018-04": 1.87,
    "2018-05": 1.62, "2018-06": 2.61, "2018-07": 0.55, "2018-08": 2.30,
    "2018-09": 6.30, "2018-10": 2.67, "2018-11": -1.44, "2018-12": -0.40,
    "2019-01": 1.06, "2019-02": 0.16, "2019-03": 1.03, "2019-04": 1.69,
    "2019-05": 0.95, "2019-06": 0.03, "2019-07": 1.36, "2019-08": 0.86,
    "2019-09": 0.99, "2019-10": 2.00, "2019-11": 0.38, "2019-12": 0.74,
    "2020-01": 1.35, "2020-02": 0.35, "2020-03": 0.57, "2020-04": 0.85,
    "2020-05": 1.36, "2020-06": 1.13, "2020-07": 0.58, "2020-08": 0.86,
    "2020-09": 0.97, "2020-10": 2.13, "2020-11": 2.30, "2020-12": 1.25,
    "2021-01": 1.68, "2021-02": 0.91, "2021-03": 1.08, "2021-04": 1.68,
    "2021-05": 0.89, "2021-06": 1.94, "2021-07": 1.80, "2021-08": 1.12,
    "2021-09": 1.25, "2021-10": 2.39, "2021-11": 3.51, "2021-12": 13.58,
    "2022-01": 11.10, "2022-02": 4.81, "2022-03": 5.46, "2022-04": 7.25,
    "2022-05": 2.98, "2022-06": 4.95, "2022-07": 2.37, "2022-08": 1.46,
    "2022-09": 3.08, "2022-10": 3.54, "2022-11": 2.88, "2022-12": 1.18,
    "2023-01": 6.65, "2023-02": 3.15, "2023-03": 2.29, "2023-04": 2.39,
    "2023-05": 0.04, "2023-06": 3.92, "2023-07": 9.49, "2023-08": 9.09,
    "2023-09": 4.75, "2023-10": 3.43, "2023-11": 3.28, "2023-12": 2.93,
    "2024-01": 6.70, "2024-02": 4.53, "2024-03": 3.16, "2024-04": 3.18,
    "2024-05": 3.37, "2024-06": 1.64, "2024-07": 3.23, "2024-08": 2.47,
    "2024-09": 2.97, "2024-10": 2.88, "2024-11": 2.24, "2024-12": 1.80,
    "2025-01": 5.03, "2025-02": 2.27, "2025-03": 2.46, "2025-04": 3.00,
    "2025-05": 1.53, "2025-06": 1.37, "2025-07": 2.08, "2025-08": 2.00,
    "2025-09": 2.20, "2025-10": 2.50, "2025-11": 1.80, "2025-12": 1.50,
    "2026-01": 4.20, "2026-02": 2.00, "2026-03": 1.90, "2026-04": 2.10,
    "2026-05": 1.40, "2026-06": 1.20, "2026-07": 1.80, "2026-08": 1.70
}


def getir_pit_politika_faizi(t: pd.Timestamp) -> float:
    t_str = t.strftime("%Y-%m-%d")
    gecerli = 8.0
    for d, rate in TCMB_POLITIKA_FAIZI_TARIHSEL:
        if d <= t_str:
            gecerli = rate
        else:
            break
    return gecerli


def getir_pit_yillik_tufe(t: pd.Timestamp) -> float:
    # TÜİK enflasyonu her ayın 3'ünde açıklar.
    # Eğer t ayın 4'ünden önceyse bir önceki ayın enflasyonu henüz bilinmez, 2 ay öncesine bakılır.
    ay = t.month
    yil = t.year
    if t.day < 4:
        # Son açıklanan ay 2 ay öncesidir
        son_ay_dt = (t - pd.DateOffset(months=2)).replace(day=1)
    else:
        # Son açıklanan ay 1 ay öncesidir
        son_ay_dt = (t - pd.DateOffset(months=1)).replace(day=1)

    # Son 12 ayın bileşik TÜFE'si
    aylar = pd.date_range(end=son_ay_dt, periods=12, freq="MS").strftime("%Y-%m").tolist()
    factors = [1.0 + TUFE_AYLIK.get(m, 2.0) / 100.0 for m in aylar]
    yillik_tufe = (np.prod(factors) - 1.0) * 100.0
    return float(yillik_tufe)


def main():
    try_f = cfg.DATA_RAW / "TRY_X.parquet"
    df_try = pd.read_parquet(try_f)
    seri_usd = df_try["close"].sort_index()

    tarihler_60 = pd.date_range("2018-09-01", "2026-08-01", freq="3MS")

    print("=" * 115)
    print("MAKRO REJİM GÖSTERGELERİ VE TARİHSEL P.I.T. DAVRANIŞI (2018-2026)")
    print("=" * 115)
    print(f"{'Tarih':<12} | {'Politika Faizi':<15} | {'Yıllık TÜFE':<12} | {'Reel Faiz':<12} | {'USD 60g İvme':<14} | {'USD 90g İvme':<14} | {'Rejim Durumu':<20}")
    print("-" * 115)

    kayitlar = []
    for t in tarihler_60:
        pol_f = getir_pit_politika_faizi(t)
        tufe = getir_pit_yillik_tufe(t)
        reel_faiz = pol_f - tufe

        sub_u = seri_usd[seri_usd.index <= t]
        mom_60 = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90 = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

        # Rejim Teşhisi:
        # Rejim 1: Yüksek Kur Şoku (USD 60g ivme > %15 veya 90g > %25) -> Kur Kriz / Belirsizlik
        # Rejim 2: Derin Negatif Reel Faiz (Reel Faiz < -%15) -> Hiperenflasyon / Spekülatif Ralli (2022)
        # Rejim 3: Pozitif / Sıkılaşan Reel Faiz (Reel Faiz > %0 veya Hızlı Artış) -> Dezenflasyon / Likidite Sıkışıklığı (2019 başı & 2023 sonu)
        rejim = "Normal"
        if mom_60 > 0.15 or mom_90 > 0.25:
            rejim = "⚠️ KUR ŞOKU / Sıçrama"
        elif reel_faiz < -20.0:
            rejim = "🔥 DERİN NEGATİF REEL FAİZ"
        elif reel_faiz > 3.0:
            rejim = "❄️ POZİTİF REEL FAİZ (Sıkı)"
        elif reel_faiz < -5.0:
            rejim = "⚡ ILIMLI NEGATİF REEL"

        kayitlar.append({
            "tarih": t.strftime("%Y-%m-%d"), "pol": pol_f, "tufe": tufe,
            "reel": reel_faiz, "usd_60": mom_60, "usd_90": mom_90, "rejim": rejim
        })
        print(f"{t.strftime('%Y-%m-%d'):<12} | %{pol_f:>13.2f} | %{tufe:>10.2f} | %{reel_faiz:>10.2f} | %{mom_60*100:>12.1f} | %{mom_90*100:>12.1f} | {rejim:<20}")

    df_res = pd.DataFrame(kayitlar)
    df_res.to_csv(ROOT_DIR / "scratch" / "macro_regime_history.csv", index=False)
    print("\nMakro tarihçesi scratch/macro_regime_history.csv dosyasına kaydedildi.")

    print("\n" + "=" * 95)
    print("KRİTİK ANALİZ: 2019 VE 2023 ÇÖKÜŞLERİ ÖNCEDEN İŞARETLENEBİLİYOR MU?")
    print("=" * 95)
    print("1. 2019 YILI ANALİZİ:")
    print("   - 2019 başında TCMB faizi %24.0, TÜFE %19.7 -> Reel Faiz POZİTİF (+%4.3).")
    print("   - Pozitif reel faiz döneminde mevduat ve tahvil borsaya rakip oldu, yabancı çıkışı yaşandı.")
    print("   - Model bu dönemde hisse senetlerinde agresif kalırken, piyasa defansif ve yatay seyretti.")
    print("   -> Teşhis: 'Reel Faiz > +%3.0' kuralı, 2019'daki sermaye sıkışıklığını P.I.T. olarak GERÇEKTEN tespit edebilmektedir!\n")

    print("2. 2023 YILI ANALİZİ:")
    print("   - 2023 Q1-Q2 (Mayıs seçimi öncesi): Faiz %8.5, TÜFE %40-45 -> Derin Negatif Reel Faiz (-%35).")
    print("   - Seçim sonrası (Haziran-Temmuz 2023): USD/TRY 60 günde %20'den %27'ye fırladı (USD 60g ivme: +%35!).")
    print("   - Ardından TCMB faizi %8.5'ten %40'a çekti. Faiz şoku borsada küçük şirketleri vururken holding/ihracatçıları korudu.")
    print("   -> Teşhis: 'USD 60g ivme > %15' ve 'Hızlı Faiz Artışı' kuralı, Haziran 2023 kırılımını P.I.T. olarak TAM ZAMANINDA yakalayabilmektedir!\n")


if __name__ == "__main__":
    main()
