"""
faz_b5_tam_pit_test.py — 7 Yıllık Tam PIT Placebo & Karar Kapısı Testi (2018-2026)
================================================================================
Mükemmelleştirme Planı Referansı: FAZ B.5-TAM

Bu test:
  1. 88 hissenin 2018-2026 arası 34 çeyreklik tam PIT temel verisini (data/fundamentals/*.parquet) kullanır.
  2. 2018-09 -> 2026-08 (95 aylık rebalancing dönemi, ~8 yıl) boyunca:
     - Her ay başında o gün bilinen en son PIT verilerini (P/B, ROE) çeker.
     - Mom 12-1 (252g - 21g) momentum faktörünü hesaplar.
     - Sektör içi z-score normalizasyonu uygular (küçük sektör emniyeti dahil).
     - Kaba skor = -Z(P/B) + Z(ROE) + Z(Mom_12-1) formülüyle hisseleri sıralar.
     - Top-10 ve Top-15 eşit ağırlıklı portföy kurar.
  3. 100 farklı tohumlu Monte Carlo Placebo (rastgele seçim) çalıştırır.
  4. Kümülatif getiri, Sharpe, Max Drawdown, yıllık bazda başarı ve nihai p-değerini raporlar.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import warnings
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

import pandas as pd
import numpy as np
from loguru import logger

warnings.filterwarnings("ignore")
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {message}", colorize=False)

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg
from features.fundamental_pit import cek_pit_kesit, hesapla_sektor_zscore

KOMISYON = 0.003  # %0.3 gidiş-dönüş aylık işlem maliyeti ve kayma


# ─── 1. FİYAT VE ENDEKS MATRİSİ YÜKLE ─────────────────────────────────────────
def yukle_veriler() -> Tuple[Dict[str, pd.Series], pd.Series]:
    """Tüm hisselerin ve XU100'ün günlük kapanış fiyat serilerini yükler."""
    fiyat_dict = {}
    for s in cfg.HISSELER:
        d = s.replace("^", "IDX_").replace(".", "_").replace("=", "_")
        f = cfg.DATA_RAW / f"{d}.parquet"
        if f.exists():
            try:
                df = pd.read_parquet(f)
                if "close" in df.columns and len(df) > 300:
                    fiyat_dict[s] = df["close"].sort_index()
            except Exception:
                pass

    xu100_f = cfg.DATA_RAW / "XU100_IS.parquet"
    if not xu100_f.exists():
        xu100_f = cfg.DATA_RAW / "IDX_XU100_IS.parquet"
    df_idx = pd.read_parquet(xu100_f)
    seri_xu100 = df_idx["close"].sort_index()

    logger.info(f"Yüklendi: {len(fiyat_dict)} hisse fiyat serisi | XU100: {len(seri_xu100)} gün")
    return fiyat_dict, seri_xu100


# ─── 2. AYLIK GETİRİ VE MOMENTUM HESAPLAYICILAR ──────────────────────────────
def hesapla_aylik_getiriler(fiyat_dict: Dict[str, pd.Series],
                            t_giris: pd.Timestamp,
                            t_cikis: pd.Timestamp) -> Dict[str, float]:
    """İki tarih arasındaki aylık getiriyi (look-ahead yok) hesaplar."""
    getiriler = {}
    for s, seri in fiyat_dict.items():
        p = seri[(seri.index >= t_giris) & (seri.index <= t_cikis)]
        if len(p) >= 3:
            f0 = p.iloc[0]
            f1 = p.iloc[-1]
            if f0 > 0:
                ret = (f1 - f0) / f0
                getiriler[s] = float(np.clip(ret, -0.90, 5.0))
    return getiriler


def hesapla_mom_12_1(seri: pd.Series, t: pd.Timestamp) -> float:
    """Tarih t itibarıyla 252 günlük getiri - 21 günlük getiri (Mom 12-1)."""
    g = seri[seri.index <= t]
    if len(g) < 253:
        return 0.0
    f_t   = g.iloc[-1]
    f_21  = g.iloc[-22]
    f_252 = g.iloc[-253]
    if f_21 <= 0 or f_252 <= 0:
        return 0.0
    r_12 = (f_t - f_252) / f_252
    r_1  = (f_t - f_21) / f_21
    return float(np.clip(r_12 - r_1, -3.0, 3.0))


# ─── 3. METRİK VE SHARPE HESAPLAYICI ──────────────────────────────────────────
def hesapla_performans(aylik_getiriler: List[float]) -> Dict[str, float]:
    """Aylık getiri serisinden performans metriklerini hesaplar."""
    if not aylik_getiriler:
        return {"kumulatif": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0}

    arr = np.array(aylik_getiriler)
    kumulatif = float(np.prod(1.0 + arr) - 1.0)
    n_ay = len(arr)
    cagr = float((1.0 + kumulatif) ** (12.0 / max(1, n_ay)) - 1.0) if kumulatif > -0.99 else -0.99

    rf_aylik = 0.015  # %1.5 aylık risksiz faiz proxy
    fark = arr - rf_aylik
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 1e-6
    sharpe = float(np.mean(fark) / (std + 1e-8) * np.sqrt(12))

    # Drawdown
    zaman_serisi = np.cumprod(1.0 + arr)
    zirve = np.maximum.accumulate(zaman_serisi)
    dd = (zaman_serisi - zirve) / zirve
    max_dd = float(np.min(dd))

    return {
        "kumulatif": kumulatif,
        "cagr": cagr,
        "sharpe": sharpe,
        "max_dd": max_dd
    }


# ─── 4. ANA BACKTEST VE MONTE CARLO MOTORU ────────────────────────────────────
def calistir_tam_b5_testi():
    logger.info("=" * 70)
    logger.info("FAZ B.5-TAM: 7 YILLIK PIT TABANLI PLACEBO VE KARAR KAPISI TESTİ")
    logger.info("=" * 70)

    fiyat_dict, seri_xu100 = yukle_veriler()

    # Rebalancing tarihleri: 2018-09-01 -> 2026-08-01 (Ayın 1'i)
    tarihler = pd.date_range("2018-09-01", "2026-08-01", freq="MS")
    logger.info(f"Rebalancing Dönemi: {tarihler[0].date()} -> {tarihler[-1].date()} ({len(tarihler)-1} ay)")

    hisseler = sorted(fiyat_dict.keys())
    rng = np.random.default_rng(42)

    # PIT verilerini bir kez belleğe yükle (ultra hızlı erişim)
    pit_bellek = {}
    fund_dir = cfg.BASE_DIR / "data" / "fundamentals"
    for s in hisseler:
        d = s.replace("^", "IDX_").replace(".", "_").replace("=", "_")
        p_dosya = fund_dir / f"{d}.parquet"
        if p_dosya.exists():
            try:
                df_p = pd.read_parquet(p_dosya)
                df_p["gecerlilik_tarihi"] = pd.to_datetime(df_p["gecerlilik_tarihi"])
                pit_bellek[s] = df_p.sort_values("gecerlilik_tarihi")
            except Exception:
                pass
    logger.info(f"PIT Temel Veri Belleğe Alındı: {len(pit_bellek)} hisse")

    def hizli_pit_kesit(s, t):
        df_p = pit_bellek.get(s)
        if df_p is None or df_p.empty:
            return None
        sub = df_p[df_p["gecerlilik_tarihi"] <= t]
        if sub.empty:
            return None
        return sub.iloc[-1].to_dict()

    model_10_aylik = []
    model_15_aylik = []
    xu100_aylik    = []
    esit_88_aylik  = []

    n_placebo = 100
    placebo_10_aylik = [[] for _ in range(n_placebo)]
    placebo_15_aylik = [[] for _ in range(n_placebo)]

    # Yıllık bazda takip için
    yillik_kayitlar = []

    for i in range(len(tarihler) - 1):
        t_giris = tarihler[i]
        t_cikis = tarihler[i + 1]

        getiriler = hesapla_aylik_getiriler(fiyat_dict, t_giris, t_cikis)
        mevcut_hisseler = [s for s in hisseler if s in getiriler]

        if len(mevcut_hisseler) < 25:
            continue

        # XU100 getiri
        idx_sub = seri_xu100[(seri_xu100.index >= t_giris) & (seri_xu100.index <= t_cikis)]
        ret_idx = (idx_sub.iloc[-1] - idx_sub.iloc[0]) / idx_sub.iloc[0] if len(idx_sub) >= 2 else 0.0
        xu100_aylik.append(ret_idx)

        # 88 Eşit Ağırlık Benchmark
        ret_esit = float(np.mean([getiriler[s] for s in mevcut_hisseler])) - (KOMISYON * 0.2)
        esit_88_aylik.append(ret_esit)

        # PIT Temel Verileri ve Mom 12-1 Çek
        satirlar = []
        for s in mevcut_hisseler:
            pit = hizli_pit_kesit(s, t_giris)
            mom = hesapla_mom_12_1(fiyat_dict[s], t_giris)
            pb = pit.get("pb", np.nan) if pit else np.nan
            roe = pit.get("roe", np.nan) if pit else np.nan
            sektor = cfg.HISSE_SEKTOR.get(s, "XUSIN.IS")
            satirlar.append({
                "sembol": s,
                "sektor": sektor,
                "pb": pb,
                "roe": roe,
                "mom_12_1": mom
            })

        df_kesit = pd.DataFrame(satirlar)

        # Sektör Z-Score hesapla
        z_pb  = hesapla_sektor_zscore(df_kesit, "pb", min_grup=4)
        z_roe = hesapla_sektor_zscore(df_kesit, "roe", min_grup=4)
        z_mom = hesapla_sektor_zscore(df_kesit, "mom_12_1", min_grup=4)

        # Kaba Skor = -Z(P/B) + Z(ROE) + Z(Mom_12-1)
        df_kesit["skor"] = (
            z_pb.fillna(0.0) * (-1.0) +
            z_roe.fillna(0.0) * (1.0) +
            z_mom.fillna(0.0) * (1.0)
        )

        df_sirali = df_kesit.sort_values("skor", ascending=False).reset_index(drop=True)

        top10_syms = df_sirali.head(10)["sembol"].tolist()
        top15_syms = df_sirali.head(15)["sembol"].tolist()

        ret_top10 = float(np.mean([getiriler[s] for s in top10_syms])) - KOMISYON
        ret_top15 = float(np.mean([getiriler[s] for s in top15_syms])) - KOMISYON

        model_10_aylik.append(ret_top10)
        model_15_aylik.append(ret_top15)

        # 100 Tohumlu Monte Carlo Placebo
        for p_idx in range(n_placebo):
            secim_10 = rng.choice(mevcut_hisseler, size=10, replace=False)
            secim_15 = rng.choice(mevcut_hisseler, size=15, replace=False)

            p_ret_10 = float(np.mean([getiriler[s] for s in secim_10])) - KOMISYON
            p_ret_15 = float(np.mean([getiriler[s] for s in secim_15])) - KOMISYON

            placebo_10_aylik[p_idx].append(p_ret_10)
            placebo_15_aylik[p_idx].append(p_ret_15)

        yillik_kayitlar.append({
            "yil": t_giris.year,
            "ay": t_giris.month,
            "top10": ret_top10,
            "top15": ret_top15,
            "xu100": ret_idx,
            "esit88": ret_esit
        })

    # ─── SONUÇLAR VE METRİKLER ────────────────────────────────────────────────
    res_10 = hesapla_performans(model_10_aylik)
    res_15 = hesapla_performans(model_15_aylik)
    res_idx = hesapla_performans(xu100_aylik)
    res_esit = hesapla_performans(esit_88_aylik)

    # Placebo ortalamaları ve p-değerleri
    plac_10_sharpes = [hesapla_performans(p)["sharpe"] for p in placebo_10_aylik]
    plac_15_sharpes = [hesapla_performans(p)["sharpe"] for p in placebo_15_aylik]
    plac_10_kumul   = [hesapla_performans(p)["kumulatif"] for p in placebo_10_aylik]
    plac_15_kumul   = [hesapla_performans(p)["kumulatif"] for p in placebo_15_aylik]

    p_val_sharpe_10 = float(np.mean([1 if s >= res_10["sharpe"] else 0 for s in plac_10_sharpes]))
    p_val_sharpe_15 = float(np.mean([1 if s >= res_15["sharpe"] else 0 for s in plac_15_sharpes]))
    p_val_kumul_10  = float(np.mean([1 if k >= res_10["kumulatif"] else 0 for k in plac_10_kumul]))
    p_val_kumul_15  = float(np.mean([1 if k >= res_15["kumulatif"] else 0 for k in plac_15_kumul]))

    print("\n" + "=" * 75)
    print(" [RAPOR] FAZ B.5-TAM: 7 YILLIK PURE POINT-IN-TIME SONUC RAPORU (2018-2026)")
    print("=" * 75)
    print(f"{'Strateji':<22} | {'Kumulatif':<12} | {'CAGR':<10} | {'Sharpe':<8} | {'Max DD':<10} | {'Placebo p':<10}")
    print("-" * 75)
    print(f"{'Top-10 PIT Model':<22} | %{res_10['kumulatif']*100:>10.1f} | %{res_10['cagr']*100:>8.1f} | {res_10['sharpe']:>8.2f} | %{res_10['max_dd']*100:>8.1f} | p = {p_val_sharpe_10:.3f}")
    print(f"{'Top-15 PIT Model':<22} | %{res_15['kumulatif']*100:>10.1f} | %{res_15['cagr']*100:>8.1f} | {res_15['sharpe']:>8.2f} | %{res_15['max_dd']*100:>8.1f} | p = {p_val_sharpe_15:.3f}")
    print(f"{'100 Tohum Placebo (10)':<22} | %{np.mean(plac_10_kumul)*100:>10.1f} | %{(np.mean(plac_10_kumul)+1)**(12/len(model_10_aylik))-1:>7.1%} | {np.mean(plac_10_sharpes):>8.2f} | {'-':>10} | {'baseline':>10}")
    print(f"{'100 Tohum Placebo (15)':<22} | %{np.mean(plac_15_kumul)*100:>10.1f} | %{(np.mean(plac_15_kumul)+1)**(12/len(model_15_aylik))-1:>7.1%} | {np.mean(plac_15_sharpes):>8.2f} | {'-':>10} | {'baseline':>10}")
    print(f"{'BIST 100 Endeks':<22} | %{res_idx['kumulatif']*100:>10.1f} | %{res_idx['cagr']*100:>8.1f} | {res_idx['sharpe']:>8.2f} | %{res_idx['max_dd']*100:>8.1f} | {'market':>10}")
    print(f"{'88 Hisse Esit Agirlik':<22} | %{res_esit['kumulatif']*100:>10.1f} | %{res_esit['cagr']*100:>8.1f} | {res_esit['sharpe']:>8.2f} | %{res_esit['max_dd']*100:>8.1f} | {'benchmark':>10}")
    print("=" * 75)

    # Yıllık bazda getiri tablosu
    df_yil = pd.DataFrame(yillik_kayitlar)
    print("\nYILLIK BAZDA GETIRI DAGILIMI:")
    print("-" * 65)
    print(f"{'Yil':<6} | {'Top-10 Model':<14} | {'Top-15 Model':<14} | {'BIST 100':<12} | {'88 Esit':<12}")
    print("-" * 65)
    for y, g in df_yil.groupby("yil"):
        r_top10 = np.prod(1.0 + g["top10"]) - 1.0
        r_top15 = np.prod(1.0 + g["top15"]) - 1.0
        r_xu    = np.prod(1.0 + g["xu100"]) - 1.0
        r_esit  = np.prod(1.0 + g["esit88"]) - 1.0
        print(f"{y:<6} | %{r_top10*100:>12.1f} | %{r_top15*100:>12.1f} | %{r_xu*100:>10.1f} | %{r_esit*100:>10.1f}")
    print("=" * 65)

    # Karar Kapısı Değerlendirmesi
    print("\nKARAR KAPISI (KILL CRITERIA) DEGERLENDIRMESI:")
    p_secilen = min(p_val_sharpe_10, p_val_sharpe_15)
    if p_secilen < 0.05:
        print(f"  [+] GUCLU ONAY (p = {p_secilen:.3f} < 0.05): Temel rasyolar BIST'te olaganustu istatistiksel alfa uretiyor!")
        print("  -> Guvenle FAZ C (Feature Seti) ve FAZ D (LGBMRanker Mimarisi)'ne gecilebilir.")
    elif p_secilen < 0.10:
        print(f"  [+] ONAY (p = {p_secilen:.3f} < 0.10): Hipotez rastgele secimden belirgin sekilde ayrısıyor.")
        print("  -> FAZ C ve FAZ D'ye gecis uygundur.")
    elif p_secilen <= 0.20:
        print(f"  [!] SINIRDA (p = {p_secilen:.3f} <= 0.20): Sinyal pozitif ancak varyans yuksek.")
    else:
        print(f"  [-] RET (p = {p_secilen:.3f} > 0.20): Kaba kural rastgele dart atisindan ayrilamiyor.")

    # Raporu kaydet
    rapor_yolu = ROOT_DIR / "reports" / "faz_b5_tam_pit_raporu.md"
    rapor_yolu.parent.mkdir(parents=True, exist_ok=True)
    with open(rapor_yolu, "w", encoding="utf-8") as f:
        f.write(f"# Faz B.5-TAM: 7 Yıllık Point-in-Time Placebo & Karar Kapısı Raporu\n\n")
        f.write(f"- **Dönem:** 2018-09-01 -> 2026-08-01 ({len(model_10_aylik)} ay)\n")
        f.write(f"- **Veri:** 88 hisse x 34 çeyrek (İş Yatırım PIT Parquet)\n")
        f.write(f"- **Top-15 Kümülatif Getiri:** %{res_15['kumulatif']*100:.1f} (Placebo: %{np.mean(plac_15_kumul)*100:.1f}, BIST 100: %{res_idx['kumulatif']*100:.1f})\n")
        f.write(f"- **Top-15 Sharpe Oranı:** {res_15['sharpe']:.2f} (Placebo: {np.mean(plac_15_sharpes):.2f}, BIST 100: {res_idx['sharpe']:.2f})\n")
        f.write(f"- **Monte Carlo Placebo p-değeri:** {p_val_sharpe_15:.4f}\n")
    logger.info(f"Rapor kaydedildi: {rapor_yolu}")


if __name__ == "__main__":
    calistir_tam_b5_testi()
