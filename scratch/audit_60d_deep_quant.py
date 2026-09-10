"""
scratch/audit_60d_deep_quant.py
===============================
ŞART 2 — 60 GÜNLÜK UFUK İÇİN 5 BOYUTLU TAM KANTİTATİF DENETİM
-------------------------------------------------------------
1. Konsantrasyon Taraması (K in [5, 10, 15, 20, 25, 30]) + 100 Tohumlu Placebo + Bonferroni & FDR
2. USD ve Reel TÜFE Düzeltilmiş Performans (Model, Placebo, BIST100, 88 Eşit Ağırlık)
3. Formül Hassasiyeti ve Bileşen Ayrıştırması (-Z(PB), Z(ROE), Z(Mom), EV/EBITDA) 60g ufukta
4. Yıl Bazında Bağımsız İstatistiksel Anlamlılık (2018-2026 yıllık p-değeri analizi)
5. Ciro (Turnover), İşlem Maliyeti ve Max Drawdown Karşılaştırması (21g vs 60g)
"""

import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("audit_60d")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

def hesapla_sektor_zscore(df: pd.DataFrame, kolon: str, min_grup: int = 4) -> pd.Series:
    zscores = pd.Series(np.nan, index=df.index)
    for sektor, grup in df.groupby("sektor"):
        gecerli = grup[kolon].dropna()
        if len(gecerli) >= min_grup:
            mu  = gecerli.mean()
            std = gecerli.std()
        else:
            gecerli = df[kolon].dropna()
            mu  = gecerli.mean()
            std = gecerli.std()
        if std > 1e-8:
            zscores.loc[grup.index] = (grup[kolon] - mu) / std
        else:
            zscores.loc[grup.index] = 0.0
    return zscores.clip(-3.0, 3.0)

KOMISYON_60G = 0.003  # Çeyreklik rotasyon için %0.3 işlem maliyeti ve kayma


def yukle_tum_veriler():
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

    xu_f = cfg.DATA_RAW / "XU100_IS.parquet"
    if not xu_f.exists():
        xu_f = cfg.DATA_RAW / "IDX_XU100_IS.parquet"
    df_idx = pd.read_parquet(xu_f)
    seri_xu100 = df_idx["close"].sort_index()

    try_f = cfg.DATA_RAW / "TRY_X.parquet"
    df_try = pd.read_parquet(try_f)
    seri_usdtry = df_try["close"].sort_index()

    pit_bellek = {}
    fund_dir = cfg.BASE_DIR / "data" / "fundamentals"
    for s in fiyat_dict.keys():
        d = s.replace("^", "IDX_").replace(".", "_").replace("=", "_")
        p_dosya = fund_dir / f"{d}.parquet"
        if p_dosya.exists():
            try:
                df_p = pd.read_parquet(p_dosya)
                df_p["gecerlilik_tarihi"] = pd.to_datetime(df_p["gecerlilik_tarihi"])
                pit_bellek[s] = df_p.sort_values("gecerlilik_tarihi").to_dict("records")
            except Exception:
                pass

    tufe_aylik_pct = {
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

    logger.info(f"Yüklendi: {len(fiyat_dict)} hisse | PIT: {len(pit_bellek)} | XU100: {len(seri_xu100)}")
    return fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, tufe_aylik_pct


def hizli_pit(pit_bellek, s, t):
    recs = pit_bellek.get(s)
    if not recs:
        return None
    for r in reversed(recs):
        if r["gecerlilik_tarihi"] <= t:
            return r
    return None


def hesapla_mom(seri, t, n_gun=252, n_lag=21):
    g = seri[seri.index <= t]
    if len(g) < (n_gun + 1):
        return 0.0
    f_t = g.iloc[-1]
    f_lag = g.iloc[-(n_lag + 1)]
    f_long = g.iloc[-(n_gun + 1)]
    if f_lag <= 0 or f_long <= 0:
        return 0.0
    r_long = (f_t - f_long) / f_long
    r_lag = (f_t - f_lag) / f_lag
    return float(np.clip(r_long - r_lag, -3.0, 3.0))


def metrikler_quarterly(arr, rf_annual=0.18):
    if not len(arr):
        return {"kumulatif": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0}
    a = np.array(arr)
    kum = float(np.prod(1.0 + a) - 1.0)
    n = len(a)
    # Çeyreklik frekansta yılda 4 periyot vardır
    cagr = float((1.0 + kum) ** (4.0 / max(1, n)) - 1.0) if kum > -0.99 else -0.99
    rf_q = (1.0 + rf_annual) ** (1.0 / 4.0) - 1.0
    diff = a - rf_q
    std = float(np.std(a, ddof=1)) if len(a) > 1 else 1e-6
    sharpe = float(np.mean(diff) / (std + 1e-8) * np.sqrt(4))

    zs = np.cumprod(1.0 + a)
    pk = np.maximum.accumulate(zs)
    dd = (zs - pk) / pk
    mdd = float(np.min(dd))
    return {"kumulatif": kum, "cagr": cagr, "sharpe": sharpe, "max_dd": mdd}


def hazirla_60g_donem_verisi(fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, tufe_aylik_pct):
    tarihler_60 = pd.date_range("2018-09-01", "2026-08-01", freq="3MS")
    hisseler = sorted(fiyat_dict.keys())
    donem_list = []

    for i in range(len(tarihler_60) - 1):
        t0, t1 = tarihler_60[i], tarihler_60[i + 1]

        # Hisse getirileri
        rets = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        mevcut = [s for s in hisseler if s in rets]
        if len(mevcut) < 32:
            continue

        # Endeks ve Makro getirileri
        px = seri_xu100[(seri_xu100.index >= t0) & (seri_xu100.index <= t1)]
        r_xu = float((px.iloc[-1] - px.iloc[0]) / px.iloc[0]) if len(px) >= 2 else 0.0

        pu = seri_usdtry[(seri_usdtry.index >= t0) & (seri_usdtry.index <= t1)]
        r_usd = float((pu.iloc[-1] - pu.iloc[0]) / pu.iloc[0]) if len(pu) >= 2 else 0.0

        # Çeyreklik enflasyon (3 aylık bileşik)
        aylar = pd.date_range(t0, t1, freq="MS").strftime("%Y-%m").tolist()[:-1]
        cpi_factors = [1.0 + tufe_aylik_pct.get(ay, 2.0) / 100.0 for ay in aylar]
        r_cpi = float(np.prod(cpi_factors) - 1.0) if cpi_factors else 0.06

        satirlar = []
        for s in mevcut:
            pit = hizli_pit(pit_bellek, s, t0)
            mom = hesapla_mom(fiyat_dict[s], t0)
            satirlar.append({
                "sembol": s,
                "sektor": cfg.HISSE_SEKTOR.get(s, "XUSIN.IS"),
                "pb": pit.get("pb", np.nan) if pit else np.nan,
                "roe": pit.get("roe", np.nan) if pit else np.nan,
                "ev_ebitda": pit.get("ev_ebitda", np.nan) if pit else np.nan,
                "mom": mom
            })
        df_k = pd.DataFrame(satirlar)
        z_pb = hesapla_sektor_zscore(df_k, "pb", min_grup=4)
        z_roe = hesapla_sektor_zscore(df_k, "roe", min_grup=4)
        z_mom = hesapla_sektor_zscore(df_k, "mom", min_grup=4)
        z_ev = hesapla_sektor_zscore(df_k, "ev_ebitda", min_grup=4)

        df_k["skor_base"] = -z_pb.fillna(0.0) + z_roe.fillna(0.0) + z_mom.fillna(0.0)
        df_k["skor_pb"]   = -z_pb.fillna(0.0)
        df_k["skor_roe"]  = z_roe.fillna(0.0)
        df_k["skor_mom"]  = z_mom.fillna(0.0)
        df_k["skor_ev"]   = -z_ev.fillna(0.0) + z_roe.fillna(0.0) + z_mom.fillna(0.0)

        donem_list.append({
            "t0": t0, "t1": t1, "yil": t0.year,
            "rets": rets, "mevcut": mevcut,
            "r_xu": r_xu, "r_usd": r_usd, "r_cpi": r_cpi,
            "df_scores": df_k
        })

    logger.info(f"60 günlük periyot sayısı: {len(donem_list)}")
    return donem_list


def audit_1_konsantrasyon_60g(donem_list):
    print("\n" + "=" * 105, flush=True)
    print("60G AUDIT — 1. TAM KONSANTRASYON TARAMASI (K in [5, 10, 15, 20, 25, 30])", flush=True)
    print("=" * 105, flush=True)

    k_list = [5, 10, 15, 20, 25, 30]
    n_placebo = 100
    rng = np.random.default_rng(42)

    sonuclar = []
    p_raw_list = []

    for k in k_list:
        model_rets = []
        plac_rets = [[] for _ in range(n_placebo)]

        for d in donem_list:
            rets = d["rets"]
            sirali = d["df_scores"].sort_values("skor_base", ascending=False)["sembol"].tolist()
            top_k = sirali[:k]
            r_mod = float(np.mean([rets[s] for s in top_k])) - KOMISYON_60G
            model_rets.append(r_mod)

            mevcut = d["mevcut"]
            for p_i in range(n_placebo):
                sec = rng.choice(mevcut, size=k, replace=False)
                plac_rets[p_i].append(float(np.mean([rets[s] for s in sec])) - KOMISYON_60G)

        m_mod = metrikler_quarterly(model_rets)
        plac_sharpes = [metrikler_quarterly(p)["sharpe"] for p in plac_rets]
        plac_kumuls  = [metrikler_quarterly(p)["kumulatif"] for p in plac_rets]

        p_val = float(np.mean([1 if s >= m_mod["sharpe"] else 0 for s in plac_sharpes]))
        p_raw_list.append(p_val)

        sonuclar.append({
            "k": k, "mod_kum": m_mod["kumulatif"], "mod_cagr": m_mod["cagr"],
            "mod_sharpe": m_mod["sharpe"], "mod_mdd": m_mod["max_dd"],
            "plac_kum": float(np.mean(plac_kumuls)), "plac_sharpe": float(np.mean(plac_sharpes)),
            "p_raw": p_val, "model_rets": model_rets, "plac_rets": plac_rets
        })

    # Çoklu Karşılaştırma Düzeltmeleri
    m_tests = len(k_list)
    # Bonferroni
    for r in sonuclar:
        r["p_bonf"] = min(1.0, r["p_raw"] * m_tests)

    # Benjamini-Hochberg FDR
    sirali_idx = np.argsort([r["p_raw"] for r in sonuclar])
    fdr_vals = [0.0] * m_tests
    for rank, idx in enumerate(sirali_idx, 1):
        fdr_vals[idx] = min(1.0, sonuclar[idx]["p_raw"] * m_tests / rank)
    for i, r in enumerate(sonuclar):
        r["p_fdr"] = fdr_vals[i]

    print(f"{'K':<5} | {'Model Küm.':<12} | {'CAGR':<8} | {'Sharpe':<8} | {'Max DD':<9} | {'Plac. Küm.':<12} | {'Plac. Sh':<9} | {'Ham p':<7} | {'Bonf p':<7} | {'FDR p':<7}", flush=True)
    print("-" * 105, flush=True)
    for r in sonuclar:
        print(f"K={r['k']:<3} | %{r['mod_kum']*100:>10.1f} | %{r['mod_cagr']*100:>6.1f} | {r['mod_sharpe']:>8.2f} | %{r['mod_mdd']*100:>7.1f} | %{r['plac_kum']*100:>10.1f} | {r['plac_sharpe']:>9.2f} | {r['p_raw']:>7.3f} | {r['p_bonf']:>7.3f} | {r['p_fdr']:>7.3f}", flush=True)

    return sonuclar


def audit_2_usd_ve_reel_60g(donem_list, sonuclar_k):
    print("\n" + "=" * 105, flush=True)
    print("60G AUDIT — 2. USD VE REEL TÜFE DÜZELTİLMİŞ PERFORMANS (60 GÜNLÜK)", flush=True)
    print("=" * 105, flush=True)

    k15_res = [r for r in sonuclar_k if r["k"] == 15][0]
    mod_tl_rets = k15_res["model_rets"]
    plac_tl_rets_list = k15_res["plac_rets"]

    xu_rets = [d["r_xu"] for d in donem_list]
    usd_rets = [d["r_usd"] for d in donem_list]
    cpi_rets = [d["r_cpi"] for d in donem_list]

    ew_rets = [float(np.mean(list(d["rets"].values()))) - KOMISYON_60G for d in donem_list]

    def to_usd(rets_tl, r_usds):
        return [(1.0 + r) / (1.0 + u) - 1.0 for r, u in zip(rets_tl, r_usds)]

    def to_reel(rets_tl, r_cpis):
        return [(1.0 + r) / (1.0 + c) - 1.0 for r, c in zip(rets_tl, r_cpis)]

    # Model
    mod_usd = to_usd(mod_tl_rets, usd_rets)
    mod_reel = to_reel(mod_tl_rets, cpi_rets)
    m_tl = metrikler_quarterly(mod_tl_rets)
    m_usd = metrikler_quarterly(mod_usd, rf_annual=0.03)
    m_reel = metrikler_quarterly(mod_reel, rf_annual=0.02)

    # Placebo Ortalaması
    plac_tl_avg = [float(np.mean([plac_tl_rets_list[p][i] for p in range(len(plac_tl_rets_list))])) for i in range(len(mod_tl_rets))]
    plac_usd = to_usd(plac_tl_avg, usd_rets)
    plac_reel = to_reel(plac_tl_avg, cpi_rets)
    p_tl = metrikler_quarterly(plac_tl_avg)
    p_usd = metrikler_quarterly(plac_usd, rf_annual=0.03)
    p_reel = metrikler_quarterly(plac_reel, rf_annual=0.02)

    # BIST 100
    x_usd = to_usd(xu_rets, usd_rets)
    x_reel = to_reel(xu_rets, cpi_rets)
    x_tl = metrikler_quarterly(xu_rets)
    x_usd_m = metrikler_quarterly(x_usd, rf_annual=0.03)
    x_reel_m = metrikler_quarterly(x_reel, rf_annual=0.02)

    # 88 Eşit
    ew_usd = to_usd(ew_rets, usd_rets)
    ew_reel = to_reel(ew_rets, cpi_rets)
    ew_tl_m = metrikler_quarterly(ew_rets)
    ew_usd_m = metrikler_quarterly(ew_usd, rf_annual=0.03)
    ew_reel_m = metrikler_quarterly(ew_reel, rf_annual=0.02)

    tablo = [
        ("Top-15 60g Model", m_tl, m_usd, m_reel),
        ("100 Placebo Ort.", p_tl, p_usd, p_reel),
        ("BIST 100 Endeksi", x_tl, x_usd_m, x_reel_m),
        ("88 Eşit Ağırlık", ew_tl_m, ew_usd_m, ew_reel_m),
    ]

    print(f"{'Strateji':<18} | {'TL Küm.':<10} | {'TL CAGR':<8} | {'TL Sh':<6} | {'USD Küm.':<10} | {'USD CAGR':<9} | {'USD Sh':<7} | {'Reel Küm.':<10} | {'Reel CAGR':<10} | {'Reel Sh':<7}", flush=True)
    print("-" * 115, flush=True)
    for isim, t, u, r in tablo:
        print(f"{isim:<18} | %{t['kumulatif']*100:>8.1f} | %{t['cagr']*100:>6.1f} | {t['sharpe']:>6.2f} | %{u['kumulatif']*100:>8.1f} | %{u['cagr']*100:>7.1f} | {u['sharpe']:>7.2f} | %{r['kumulatif']*100:>8.1f} | %{r['cagr']*100:>8.1f} | {r['sharpe']:>7.2f}", flush=True)

    return mod_tl_rets, plac_tl_rets_list, xu_rets


def audit_3_formul_duyarliligi_60g(donem_list):
    print("\n" + "=" * 105, flush=True)
    print("60G AUDIT — 3. FORMÜL HASSASİYETİ VE DEĞER TUZAĞI KONTROLÜ (60 GÜNLÜK)", flush=True)
    print("=" * 105, flush=True)

    varyasyonlar = [
        ("Kaba Baz: -Z(PB)+Z(ROE)+Z(Mom)", "skor_base"),
        ("Sadece Değer: -Z(PB)", "skor_pb"),
        ("Sadece Kârlılık: Z(ROE)", "skor_roe"),
        ("Sadece Momentum: Z(Mom)", "skor_mom"),
        ("EV/EBITDA Bazlı: -Z(EV)+Z(ROE)+Z(Mom)", "skor_ev"),
    ]

    print(f"{'Formül Varyasyonu':<40} | {'Kümülatif':<12} | {'CAGR':<9} | {'Sharpe':<8} | {'Max DD':<9}", flush=True)
    print("-" * 88, flush=True)
    for isim, col in varyasyonlar:
        rets_var = []
        for d in donem_list:
            sirali = d["df_scores"].sort_values(col, ascending=False)["sembol"].tolist()
            top15 = sirali[:15]
            r = float(np.mean([d["rets"][s] for s in top15])) - KOMISYON_60G
            rets_var.append(r)
        m = metrikler_quarterly(rets_var)
        print(f"{isim:<40} | %{m['kumulatif']*100:>10.1f} | %{m['cagr']*100:>7.1f} | {m['sharpe']:>8.2f} | %{m['max_dd']*100:>7.1f}", flush=True)


def audit_4_yil_bazinda_anlamlilik_60g(donem_list, mod_tl_rets, plac_tl_rets_list, xu_rets):
    print("\n" + "=" * 105, flush=True)
    print("60G AUDIT — 4. YIL BAZINDA İSTATİSTİKSEL ANLAMLILIK (60 GÜNLÜK)", flush=True)
    print("=" * 105, flush=True)

    df_y = pd.DataFrame({
        "yil": [d["yil"] for d in donem_list],
        "mod": mod_tl_rets,
        "xu": xu_rets
    })
    for p_i, p_arr in enumerate(plac_tl_rets_list):
        df_y[f"p_{p_i}"] = p_arr

    yillar = sorted(df_y["yil"].unique())

    print(f"{'Yıl':<6} | {'Model Getiri':<13} | {'Placebo Ort':<12} | {'BIST 100':<10} | {'Net Alfa':<10} | {'Yıllık p':<10} | {'Karar':<22}", flush=True)
    print("-" * 95, flush=True)

    sig_count = 0
    for y in yillar:
        sub = df_y[df_y["yil"] == y]
        r_mod = float(np.prod(1.0 + sub["mod"]) - 1.0)
        r_xu  = float(np.prod(1.0 + sub["xu"]) - 1.0)

        plac_y_rets = []
        for p_i in range(len(plac_tl_rets_list)):
            plac_y_rets.append(float(np.prod(1.0 + sub[f"p_{p_i}"]) - 1.0))

        r_plac_avg = float(np.mean(plac_y_rets))
        p_val_y = float(np.mean([1 if py >= r_mod else 0 for py in plac_y_rets]))
        net_alfa = r_mod - r_plac_avg

        if p_val_y < 0.05:
            karar = "Anlamlı Pozitif (p<0.05)"
            sig_count += 1
        elif p_val_y < 0.10:
            karar = "Sınırda Anlamlı (p<0.10)"
            sig_count += 1
        elif net_alfa < 0:
            karar = "Placebo Gerisinde"
        else:
            karar = "Ayırt Edilemez"

        print(f"{y:<6} | %{r_mod*100:>11.1f} | %{r_plac_avg*100:>10.1f} | %{r_xu*100:>8.1f} | %{net_alfa*100:>8.1f} | {p_val_y:>10.3f} | {karar:<22}", flush=True)

    print(f"\nToplam 9 Yılın {sig_count} Yılında p < 0.10 ile anlamlı alfa üretildi.", flush=True)


def audit_5_turnover_ve_maliyet_kiyaslama(fiyat_dict, pit_bellek):
    print("\n" + "=" * 105, flush=True)
    print("60G AUDIT — 5. CİRO (TURNOVER), İŞLEM MALİYETİ VE MAX DRAWDOWN KIYASLAMASI", flush=True)
    print("=" * 105, flush=True)

    # 21 günlük (aylık) model pozisyonları
    tarihler_21 = pd.date_range("2018-09-01", "2026-08-01", freq="MS")
    turnover_21 = []
    prev_set_21 = None
    for t in tarihler_21:
        satirlar = []
        for s in fiyat_dict.keys():
            pit = hizli_pit(pit_bellek, s, t)
            mom = hesapla_mom(fiyat_dict[s], t)
            satirlar.append({"sembol": s, "sektor": cfg.HISSE_SEKTOR.get(s, "XUSIN.IS"),
                             "pb": pit.get("pb", np.nan) if pit else np.nan,
                             "roe": pit.get("roe", np.nan) if pit else np.nan, "mom": mom})
        df_k = pd.DataFrame(satirlar)
        z_pb = hesapla_sektor_zscore(df_k, "pb", min_grup=4)
        z_roe = hesapla_sektor_zscore(df_k, "roe", min_grup=4)
        z_mom = hesapla_sektor_zscore(df_k, "mom", min_grup=4)
        df_k["skor"] = -z_pb.fillna(0.0) + z_roe.fillna(0.0) + z_mom.fillna(0.0)
        curr_set = set(df_k.sort_values("skor", ascending=False)["sembol"].iloc[:15])
        if prev_set_21 is not None:
            degisen = len(curr_set - prev_set_21)
            turnover_21.append(degisen / 15.0)
        prev_set_21 = curr_set

    # 60 günlük (çeyreklik) model pozisyonları
    tarihler_60 = pd.date_range("2018-09-01", "2026-08-01", freq="3MS")
    turnover_60 = []
    prev_set_60 = None
    for t in tarihler_60:
        satirlar = []
        for s in fiyat_dict.keys():
            pit = hizli_pit(pit_bellek, s, t)
            mom = hesapla_mom(fiyat_dict[s], t)
            satirlar.append({"sembol": s, "sektor": cfg.HISSE_SEKTOR.get(s, "XUSIN.IS"),
                             "pb": pit.get("pb", np.nan) if pit else np.nan,
                             "roe": pit.get("roe", np.nan) if pit else np.nan, "mom": mom})
        df_k = pd.DataFrame(satirlar)
        z_pb = hesapla_sektor_zscore(df_k, "pb", min_grup=4)
        z_roe = hesapla_sektor_zscore(df_k, "roe", min_grup=4)
        z_mom = hesapla_sektor_zscore(df_k, "mom", min_grup=4)
        df_k["skor"] = -z_pb.fillna(0.0) + z_roe.fillna(0.0) + z_mom.fillna(0.0)
        curr_set = set(df_k.sort_values("skor", ascending=False)["sembol"].iloc[:15])
        if prev_set_60 is not None:
            degisen = len(curr_set - prev_set_60)
            turnover_60.append(degisen / 15.0)
        prev_set_60 = curr_set

    yillik_to_21 = np.mean(turnover_21) * 12.0
    yillik_to_60 = np.mean(turnover_60) * 4.0

    print(f"21 Günlük (Aylık) Ortalama Periyot Değişim Oranı: %{np.mean(turnover_21)*100:.1f} | Yıllık Kümülatif Turnover: %{yillik_to_21*100:.1f}")
    print(f"60 Günlük (Çeyreklik) Ortalama Periyot Değişim Oranı: %{np.mean(turnover_60)*100:.1f} | Yıllık Kümülatif Turnover: %{yillik_to_60*100:.1f}")
    print(f"Yıllık İşlem Maliyeti Tasarrufu (bps): {(yillik_to_21 - yillik_to_60) * 0.003 * 10000:.0f} bps net komisyon ve kayma avantajı.")


def main():
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, tufe_aylik_pct = yukle_tum_veriler()
    donem_list = hazirla_60g_donem_verisi(fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, tufe_aylik_pct)

    sonuclar_k = audit_1_konsantrasyon_60g(donem_list)
    mod_tl_rets, plac_tl_rets_list, xu_rets = audit_2_usd_ve_reel_60g(donem_list, sonuclar_k)
    audit_3_formul_duyarliligi_60g(donem_list)
    audit_4_yil_bazinda_anlamlilik_60g(donem_list, mod_tl_rets, plac_tl_rets_list, xu_rets)
    audit_5_turnover_ve_maliyet_kiyaslama(fiyat_dict, pit_bellek)


if __name__ == "__main__":
    main()
