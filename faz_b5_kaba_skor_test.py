"""
faz_b5_kaba_skor_test.py - Faz B.5 Erken Placebo & Karar Kapisi
================================================================
Mukemmellestirme Plani Faz B.5:

Kaba skor formulu (ML yok, makine ogrenmesi yok):
    Skor = -Z(P/B) + Z(ROE) + Z(Mom_12-1)

Test protokolu:
  1. Her ay hisseleri kaba skorla sirala, Top-10 ve Top-15 portfoy kur.
  2. Portfoyun bir sonraki ayki getirisini hesapla.
  3. 100 farkli rastgele tohumla Monte Carlo Placebo calistir.
  4. p-degeri raporla.

KARAR KAPISI:
  p < 0.10 -> Hipotez calisiyor, KAP scraper'a gec (Faz A)
  p > 0.20 -> Hipotez calismiyor, duraksayip degerlendir
  0.10-0.20 -> Belirsiz, ek analiz gerekli

NOT: yfinance ROE ve P/B verileri GUNCEL (gecmis yok).
Bu test dolayisiyla tam PIT degil; sadece hipotezin
yonunu test eder. Gercek PIT verisiyle sonuclar degisebilir.
"""

import sys
import json
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import numpy as np
from loguru import logger

warnings.filterwarnings("ignore")
logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
from features.fundamental_pit import cek_canli_temel, hesapla_sektor_zscore

# --- PARAMETRELER -------------------------------------------------------------
PORTFOY_BUYUKLUKLERI = [10, 15]
N_PLACEBO_TOHUM      = 100
KOMISYON_AYLIK       = 0.003   # %0.3 gidis-donus aylık
REBALANCE_GUNLERI    = 15      # Ay ortasında rebalancing (BIST için daha stabil)


# --- 1. FİYAT VERİSİ YÜKLEYİCİ ----------------------------------------------
def yukle_fiyat_serileri() -> Dict[str, pd.Series]:
    """Ham parquet dosyalarından aylık kapanış getirilerini yükler."""
    fiyatlar = {}
    for sembol in cfg.HISSELER:
        dosya_adi = sembol.replace("^", "IDX_").replace(".", "_").replace("=", "_")
        dosya = cfg.DATA_RAW / f"{dosya_adi}.parquet"
        if not dosya.exists():
            continue
        try:
            df = pd.read_parquet(dosya)
            if "close" in df.columns and len(df) > 300:
                fiyatlar[sembol] = df["close"].sort_index()
        except Exception:
            pass

    logger.info(f"Fiyat verisi yuklendi: {len(fiyatlar)} hisse")
    return fiyatlar


# --- 2. AYLLIK MOM 12-1 HESAPLAYICI -----------------------------------------
def hesapla_mom_12_1_aylik(fiyatlar: Dict[str, pd.Series],
                             tarih: pd.Timestamp) -> Dict[str, float]:
    """
    Belirli bir tarih icin her hissenin Mom 12-1 degerini hesaplar.
    252 gunluk getiri - 21 gunluk getiri = Net momentum (look-ahead yok).
    """
    result = {}
    for sembol, seri in fiyatlar.items():
        gecmis = seri[seri.index <= tarih]
        if len(gecmis) < 260:
            continue
        try:
            fiyat_bugun = gecmis.iloc[-1]
            fiyat_1ay   = gecmis.iloc[-22] if len(gecmis) >= 22 else np.nan
            fiyat_12ay  = gecmis.iloc[-253] if len(gecmis) >= 253 else np.nan

            if pd.isna(fiyat_1ay) or pd.isna(fiyat_12ay) or fiyat_12ay <= 0 or fiyat_1ay <= 0:
                continue

            ret_12 = (fiyat_bugun - fiyat_12ay) / fiyat_12ay
            ret_1  = (fiyat_bugun - fiyat_1ay)  / fiyat_1ay
            mom    = np.clip(ret_12 - ret_1, -3.0, 3.0)
            result[sembol] = mom
        except Exception:
            pass
    return result


# --- 3. AYLIK GETİRİ HESAPLAYICI ---------------------------------------------
def hesapla_aylik_getiri(fiyatlar: Dict[str, pd.Series],
                          giris_tarihi: pd.Timestamp,
                          cikis_tarihi: pd.Timestamp) -> Dict[str, float]:
    """Iki tarih arasi hisse getirilerini hesaplar."""
    getiriler = {}
    for sembol, seri in fiyatlar.items():
        try:
            pencere = seri[(seri.index >= giris_tarihi) & (seri.index <= cikis_tarihi)]
            if len(pencere) < 5:
                continue
            ret = (pencere.iloc[-1] - pencere.iloc[0]) / pencere.iloc[0]
            getiriler[sembol] = float(ret)
        except Exception:
            pass
    return getiriler


# --- 4. KABA SKOR PORTFOY BACKTESTI ------------------------------------------
def calistir_kaba_skor_backtest(
    fiyatlar: Dict[str, pd.Series],
    df_temel: pd.DataFrame,
    portfoy_k: int = 10,
) -> pd.Series:
    """
    2022-2026 OOS doneminde aylik kaba skor rotasyon backtesti.
    NOT: ROE ve P/B verileri guncel yfinance'tan geliyor (tam PIT degil).
    Mom_12-1 fiyat verisinden tarihsel olarak dogru hesaplaniyor.
    """
    # Aylık rebalancing tarihleri: 2022-01'den 2026-08'a kadar
    tarihler = pd.date_range("2022-01-01", "2026-08-01", freq="MS")

    # Hisseler: Hem fiyat verisi hem temel verisi olanlar
    gecerli_hisseler = [
        s for s in cfg.HISSELER
        if s in fiyatlar and s in df_temel.index
    ]
    logger.info(f"Gecerli hisse sayisi: {len(gecerli_hisseler)}")

    portfoy_getiriler = []
    aktif_portfoy_tarihleri = []

    for i, tarih in enumerate(tarihler[:-1]):
        sonraki_tarih = tarihler[i + 1]

        # O ay icin Mom 12-1 hesapla (tarihsel, look-ahead yok)
        mom_dict = hesapla_mom_12_1_aylik(fiyatlar, tarih)

        # O ay icin gecerli hisseler (fiyat ve mom verisi olanlar)
        mevcut = [s for s in gecerli_hisseler if s in mom_dict]
        if len(mevcut) < portfoy_k + 5:
            continue

        # Kaba skor hesapla
        df_ay = df_temel.loc[df_temel.index.isin(mevcut)].copy()
        df_ay["sembol"] = df_ay.index

        # Sektor z-scorelar
        df_ay_r = df_ay.reset_index(drop=True)
        df_ay_r["sembol"] = df_ay.index
        df_ay["z_pb"]  = hesapla_sektor_zscore(df_ay_r, "pb",  min_grup=3).values
        df_ay["z_roe"] = hesapla_sektor_zscore(df_ay_r, "roe", min_grup=3).values
        df_ay["z_mom"] = df_ay.index.map(
            lambda s: (mom_dict.get(s, 0) - np.mean(list(mom_dict.values()))) /
                      (np.std(list(mom_dict.values())) + 1e-8)
        )

        df_ay["skor"] = (
            df_ay["z_pb"].fillna(0)  * (-1.0) +
            df_ay["z_roe"].fillna(0) *  1.0   +
            df_ay["z_mom"].fillna(0) *  1.0
        )

        # Top-K sec
        top_k = df_ay.nlargest(portfoy_k, "skor").index.tolist()

        # Bir sonraki ayin getirilerini hesapla
        getiriler = hesapla_aylik_getiri(fiyatlar, tarih, sonraki_tarih)
        portfoy_ret = np.mean([
            getiriler.get(s, 0) for s in top_k
            if s in getiriler
        ])

        # Komisyon dususu
        portfoy_ret -= KOMISYON_AYLIK

        portfoy_getiriler.append(portfoy_ret)
        aktif_portfoy_tarihleri.append(tarih)

    return pd.Series(portfoy_getiriler, index=aktif_portfoy_tarihleri, name=f"kaba_skor_top{portfoy_k}")


# --- 5. MONTE CARLO PLACEBO ---------------------------------------------------
def calistir_monte_carlo_placebo(
    fiyatlar: Dict[str, pd.Series],
    portfoy_k: int = 10,
    n_tohum: int = 100,
) -> pd.DataFrame:
    """
    100 farkli rastgele tohumla ayni buyuklukde portfoy kurulur.
    Her sim icin kumulatif getiri hesaplanir.
    """
    tarihler = pd.date_range("2022-01-01", "2026-08-01", freq="MS")
    gecerli_hisseler = [s for s in cfg.HISSELER if s in fiyatlar]

    placebo_serileri = []

    for tohum in range(n_tohum):
        rng = np.random.default_rng(tohum)
        sim_getiriler = []

        for i, tarih in enumerate(tarihler[:-1]):
            sonraki = tarihler[i + 1]
            mevcut  = [s for s in gecerli_hisseler]

            if len(mevcut) < portfoy_k:
                continue

            secilen = rng.choice(mevcut, size=portfoy_k, replace=False).tolist()
            getiriler = hesapla_aylik_getiri(fiyatlar, tarih, sonraki)
            portfoy_ret = np.mean([getiriler.get(s, 0) for s in secilen if s in getiriler])
            portfoy_ret -= KOMISYON_AYLIK
            sim_getiriler.append(portfoy_ret)

        placebo_serileri.append(sim_getiriler)

    return pd.DataFrame(placebo_serileri)  # (n_tohum x n_ay)


# --- 6. SONUC RAPORU ----------------------------------------------------------
def rapor_yazdir(
    model_seri: pd.Series,
    placebo_df: pd.DataFrame,
    portfoy_k: int,
) -> float:
    """Karsilastirma raporu yazar ve p-degerini doner."""
    # Kumulatif getiriler
    model_kumul   = (1 + model_seri).prod() - 1
    placebo_kumul = placebo_df.apply(lambda row: (1 + row).prod() - 1, axis=1)

    p_deger = (placebo_kumul >= model_kumul).mean()

    print(f"\n{'=' * 65}")
    print(f"FAZ B.5 KARAR KAPISI — Kaba Skor Top-{portfoy_k}")
    print(f"{'=' * 65}")
    print(f"  Ay sayisi      : {len(model_seri)}")
    print(f"  Model kumul.   : %{model_kumul * 100:.1f}")
    print(f"  Placebo ortasi : %{placebo_kumul.mean() * 100:.1f}")
    print(f"  Placebo std    : %{placebo_kumul.std() * 100:.1f}")
    print(f"  p-degeri       : {p_deger:.3f}")
    print(f"  Model sirasi   : {(placebo_kumul < model_kumul).mean() * 100:.0f}. persentil")

    # Sharpe (aylik)
    if model_seri.std() > 0:
        sharpe = (model_seri.mean() / model_seri.std()) * np.sqrt(12)
        print(f"  Sharpe (yillik): {sharpe:.2f}")

    # Karar
    print(f"\n{'-' * 65}")
    if p_deger < 0.05:
        print(f"  KARAR: GUCLU DEVAM SINYALI (p={p_deger:.3f} < 0.05) ✅")
        print(f"  Hipotez BIST'te calisiyor. KAP scraper'a gecin (Faz A).")
    elif p_deger < 0.10:
        print(f"  KARAR: ZAYIF DEVAM SINYALI (p={p_deger:.3f} < 0.10) ✅")
        print(f"  Umit verici. PIT veri ile tekrar test onerilir.")
    elif p_deger < 0.20:
        print(f"  KARAR: BELIRSIZ (p={p_deger:.3f}) ⚠️")
        print(f"  Kesin karar icin PIT veri ile test gerekli.")
    else:
        print(f"  KARAR: DUR (p={p_deger:.3f} > 0.20) ❌")
        print(f"  Kaba formul rastgele secimden ayirt edilemiyor.")
        print(f"  Faz C/D'ye gecmeden once hipotezi sorgula.")
    print(f"{'=' * 65}")

    return p_deger


# --- ANA CALISTIRICI ----------------------------------------------------------
def main():
    print("=" * 65)
    print("FAZ B.5 — KABA SKOR ERKEN PLACEBO TESTI")
    print("Mukemmellestirme Plani: -Z(P/B) + Z(ROE) + Z(Mom_12-1)")
    print("NOT: ROE/P/B guncel yfinance; Mom_12-1 tarihsel fiyattan.")
    print("=" * 65)

    # Fiyat verilerini yukle
    fiyatlar = yukle_fiyat_serileri()
    if len(fiyatlar) < 30:
        logger.error("Yeterli fiyat verisi yok! Once 'python features/veri_cek.py' calistirin.")
        return

    # Guncel temel veriyi cek (yfinance)
    print("\n[1/4] yfinance temel veri cekiliyor...")
    df_temel = cek_canli_temel(cfg.HISSELER, zorla=False)
    df_temel = df_temel.set_index("sembol") if "sembol" in df_temel.columns else df_temel

    eksik_pb  = df_temel["pb"].isna().sum()
    eksik_roe = df_temel["roe"].isna().sum()
    print(f"  Temel veri: {len(df_temel)} hisse | "
          f"P/B eksik: {eksik_pb} | ROE eksik: {eksik_roe}")

    sonuclar = {}

    for k in PORTFOY_BUYUKLUKLERI:
        print(f"\n[2/4] Kaba skor backtest: Top-{k}...")
        model_seri = calistir_kaba_skor_backtest(fiyatlar, df_temel, portfoy_k=k)

        print(f"[3/4] Monte Carlo Placebo ({N_PLACEBO_TOHUM} tohum, Top-{k})...")
        placebo_df = calistir_monte_carlo_placebo(fiyatlar, portfoy_k=k,
                                                   n_tohum=N_PLACEBO_TOHUM)

        print(f"[4/4] Sonuclar hesaplaniyor...")
        p = rapor_yazdir(model_seri, placebo_df, portfoy_k=k)
        sonuclar[f"top{k}"] = {
            "p_degeri": p,
            "model_kumul": float((1 + model_seri).prod() - 1),
        }

    # Ozet
    print(f"\n{'=' * 65}")
    print("OZET KARAR TABLOSU")
    print(f"{'-' * 65}")
    print(f"{'Portfoy':<12} {'p-degeri':<12} {'Kumul Getiri':<15} {'Karar'}")
    print(f"{'-' * 65}")
    for ad, res in sonuclar.items():
        p = res["p_degeri"]
        kumul = res["model_kumul"]
        if p < 0.10:
            karar = "DEVAM ✅"
        elif p < 0.20:
            karar = "BELIRSIZ ⚠️"
        else:
            karar = "DUR ❌"
        print(f"{ad:<12} {p:<12.3f} %{kumul*100:<14.1f} {karar}")
    print(f"{'=' * 65}")

    # JSON olarak kaydet
    rapor_dosya = Path("reports") / "faz_b5_karar_raporu.json"
    rapor_dosya.parent.mkdir(exist_ok=True)
    with open(rapor_dosya, "w", encoding="utf-8") as f:
        json.dump(sonuclar, f, ensure_ascii=False, indent=2)
    print(f"\nRapor kaydedildi: {rapor_dosya}")


if __name__ == "__main__":
    main()


