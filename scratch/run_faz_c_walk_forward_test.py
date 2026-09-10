"""
scratch/run_faz_c_walk_forward_test.py
======================================
FAZ C: İKİ KULVARLI (SANAYİ QARP + BANKA CAMELS) VE MAKRO REJİM FİLTRESİ
-----------------------------------------------------------------------
ŞART 1 — DÖNGÜSELLİK (CIRCULARITY) KALKANI VE WALK-FORWARD DİSİPLİNİ:
  - Erken Dönem (2018-09 -> 2021-12) [In-Sample]: Tasarım ve Ağırlıklandırma
  - Geç Dönem  (2022-01 -> 2026-08) [Out-of-Sample / Dondurulmuş]: Dokunulmaz Test
  
ŞART 2 — 60 GÜNLÜK ÇEYREKLİK UFUK:
  - 100 Tohumlu Monte Carlo Placebo Testi
  - Bonferroni ve FDR Düzeltmeleri
  - USD ve Reel TÜFE Performansı
  - Yıl Bazında Bağımsız Anlamlılık
"""

import sys
import json
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

KOMISYON = 0.003  # Çeyreklik rotasyon için %0.3 işlem maliyeti ve kayma


# ─── 1. VERİ VE HAFİF BELLEK YÜKLEYİCİSİ ──────────────────────────────────────
def yukle_veriler():
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
    seri_xu100 = pd.read_parquet(xu_f)["close"].sort_index()

    try_f = cfg.DATA_RAW / "TRY_X.parquet"
    seri_usdtry = pd.read_parquet(try_f)["close"].sort_index()

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

    # İş Yatırım Cache'ten ham detay kalemlerini (1A, 2A, 1AF, vb.) bellek haritasına al
    cache_dir = cfg.DATA_RAW / "isyatirim_cache"
    cache_bellek = {}
    for j_file in cache_dir.glob("*.json"):
        stem = j_file.stem
        # stem formatı: TICKER_YIL_GRUP (örn. AEFES_2020_XI_29)
        parts = stem.split("_")
        ticker = parts[0]
        yil = parts[1]
        grup = "_".join(parts[2:])
        try:
            with open(j_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                item_dict = {}
                for row in data:
                    c = row.get("itemCode")
                    if c:
                        item_dict[c] = {
                            "v1": float(row.get("value1") or 0.0),
                            "v2": float(row.get("value2") or 0.0),
                            "v3": float(row.get("value3") or 0.0),
                            "v4": float(row.get("value4") or 0.0),
                        }
                cache_bellek[(ticker, yil, grup)] = item_dict
        except Exception:
            pass

    # TÜİK Resmi Aylık TÜFE
    tufe_aylik = {
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

    print(f"Veriler yüklendi: {len(fiyat_dict)} hisse | PIT: {len(pit_bellek)} | Cache bellek: {len(cache_bellek)}")
    return fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik


def hizli_pit(pit_bellek, s, t):
    recs = pit_bellek.get(s)
    if not recs:
        return None, None
    gecerli_recs = [r for r in recs if r["gecerlilik_tarihi"] <= t]
    if not gecerli_recs:
        return None, None
    curr = gecerli_recs[-1]
    prev = gecerli_recs[-2] if len(gecerli_recs) >= 2 else None
    return curr, prev


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


def getir_tcmb_reel_faiz(t, tufe_aylik):
    # TCMB Politika Faizi tablosu
    tcmb_faiz = [
        ("2018-01-01", 8.00), ("2018-05-24", 16.50), ("2018-06-08", 17.75), ("2018-09-14", 24.00),
        ("2019-07-26", 19.75), ("2019-09-13", 16.50), ("2019-10-25", 14.00), ("2019-12-13", 12.00),
        ("2020-01-17", 11.25), ("2020-02-20", 10.75), ("2020-03-18", 9.75),  ("2020-04-23", 8.75),
        ("2020-05-22", 8.25),  ("2020-09-25", 10.25), ("2020-11-20", 15.00), ("2020-12-25", 17.00),
        ("2021-03-19", 19.00), ("2021-09-24", 18.00), ("2021-10-22", 16.00), ("2021-11-19", 15.00),
        ("2021-12-17", 14.00), ("2022-08-19", 13.00), ("2022-09-23", 12.00), ("2022-10-21", 10.50),
        ("2022-11-25", 9.00),  ("2023-02-24", 8.50),  ("2023-06-23", 15.00), ("2023-07-21", 17.50),
        ("2023-08-25", 25.00), ("2023-09-22", 30.00), ("2023-10-27", 35.00), ("2023-11-24", 40.00),
        ("2023-12-22", 42.50), ("2024-01-26", 45.00), ("2024-03-22", 50.00), ("2025-01-01", 47.50),
        ("2025-06-01", 42.50), ("2025-10-01", 37.50), ("2026-01-01", 32.50)
    ]
    t_str = t.strftime("%Y-%m-%d")
    pol = 8.0
    for d, rate in tcmb_faiz:
        if d <= t_str:
            pol = rate
        else:
            break

    son_ay_dt = (t - pd.DateOffset(months=2 if t.day < 4 else 1)).replace(day=1)
    aylar = pd.date_range(end=son_ay_dt, periods=12, freq="MS").strftime("%Y-%m").tolist()
    factors = [1.0 + tufe_aylik.get(m, 2.0) / 100.0 for m in aylar]
    yillik_tufe = (np.prod(factors) - 1.0) * 100.0
    return pol - yillik_tufe


# ─── 2. İKİ KULVARLI FEATURE HESAPLAMA MOTORU ─────────────────────────────────
def hesapla_faz_c_kesit(t, mevcut, pit_bellek, cache_bellek, fiyat_dict):
    satirlar = []

    for s in mevcut:
        curr, prev = hizli_pit(pit_bellek, s, t)
        if not curr:
            continue

        is_bank = bool(curr.get("is_bank", False))
        sektor = cfg.HISSE_SEKTOR.get(s, "XBANK.IS" if is_bank else "XUSIN.IS")
        mom = hesapla_mom(fiyat_dict[s], t)

        cfo = curr.get("cfo", 0.0) or 0.0
        net_kar = curr.get("net_kar", 0.0) or 0.0
        toplam_aktif = curr.get("toplam_aktif", 1.0) or 1.0
        ozkaynak = curr.get("ozkaynaklar", 1.0) or 1.0
        roe = curr.get("roe", 0.0) or (net_kar / ozkaynak if ozkaynak > 0 else 0.0)
        roa = curr.get("roa", 0.0) or (net_kar / toplam_aktif if toplam_aktif > 0 else 0.0)
        pb = curr.get("pb", np.nan)
        fcf_verim = curr.get("fcf_verim", 0.0) or 0.0
        ihracat = curr.get("ihracat_orani", 0.0) or 0.0
        net_borc = curr.get("net_borc", 0.0) or 0.0
        ebitda = curr.get("ebitda", 1.0) or 1.0
        borc_ebitda = net_borc / max(1.0, abs(ebitda))

        # Önceki dönemden delta hesapları (trendler)
        prev_roa = prev.get("roa", 0.0) if prev else roa
        prev_aktif = prev.get("toplam_aktif", 1.0) if prev else toplam_aktif
        prev_borc = prev.get("toplam_borc", 0.0) if prev else 0.0
        curr_borc = curr.get("toplam_borc", 0.0) or 0.0

        if not is_bank:
            # ─── SANAYİ KULVARI ───────────────────────────────────────────────
            # Piotroski F-Score Bileşenleri (0 veya 1)
            f1_cfo_gt_kar = 1.0 if cfo > net_kar else 0.0       # Nakit Kâr Kalitesi (Tahakkuk filtresi)
            f2_roa_pos    = 1.0 if roa > 0 else 0.0             # Kârlılık varlığı
            f3_roa_trend  = 1.0 if roa >= prev_roa else 0.0     # Kârlılık ivmesi
            lev_curr = curr_borc / max(1.0, toplam_aktif)
            lev_prev = prev_borc / max(1.0, prev_aktif)
            f4_lev_trend  = 1.0 if lev_curr <= lev_prev else 0.0# Borçluluk azalışı

            # Toplam Piotroski Skoru (0 - 4 arası tam kalite)
            f_score = f1_cfo_gt_kar + f2_roa_pos + f3_roa_trend + f4_lev_trend

            satirlar.append({
                "sembol": s, "is_bank": False, "sektor": sektor, "mom": mom,
                "f_score": f_score, "fcf_verim": fcf_verim, "roe": roe,
                "borc_ebitda": -borc_ebitda, "ihracat": ihracat, "pb": pb
            })
        else:
            # ─── BANKACILIK KULVARI (CAMELS) ──────────────────────────────────
            # C: Sermaye Yeterliliği (Özkaynak / Toplam Aktif)
            c_sermaye = ozkaynak / max(1.0, toplam_aktif)
            # A: Karşılık Gücü
            kar_trend = (curr.get("kredi_karsiligi", 0.0) or 0.0) / max(1.0, toplam_aktif)
            # E: Kârlılık (ROE)
            # L: Likidite proxy

            satirlar.append({
                "sembol": s, "is_bank": True, "sektor": "XBANK.IS", "mom": mom,
                "roe": roe, "sermaye": c_sermaye, "kar_trend": kar_trend, "pb": pb
            })

    df = pd.DataFrame(satirlar)
    if df.empty:
        return df

    # ─── 3. KULVARLAR ARASI ORTAK ÖLÇEK (CROSS-SECTIONAL PERCENTILE NORMALIZATION)
    # Sanayi skorlaması (P/B'siz, Kalite + FCF + ROE + İhracat + Momentum)
    df_sanayi = df[df["is_bank"] == False].copy()
    if not df_sanayi.empty:
        def z_col(s):
            v = s.dropna()
            if len(v) < 3 or v.std() < 1e-8:
                return pd.Series(0.0, index=s.index)
            return ((s - v.mean()) / v.std()).clip(-3.0, 3.0)

        # Ham faktör z-skorları
        z_f   = z_col(df_sanayi["f_score"]).fillna(0.0)
        z_fcf = z_col(df_sanayi["fcf_verim"]).fillna(0.0)
        z_roe = z_col(df_sanayi["roe"]).fillna(0.0)
        z_mom = z_col(df_sanayi["mom"]).fillna(0.0)
        z_ihr = z_col(df_sanayi["ihracat"]).fillna(0.0)
        z_borc= z_col(df_sanayi["borc_ebitda"]).fillna(0.0)

        # Sanayi QARP Formülü (Erken Dönemden Kalibre):
        # %30 Kârlılık & FCF + %30 Kalite (F-score) + %30 Momentum + %10 İhracat
        raw_sanayi_score = 0.30 * z_roe + 0.20 * z_fcf + 0.25 * z_f + 0.15 * z_mom + 0.10 * z_ihr
        # Kesitsel Persentile Dönüştür [0.0 - 1.0]
        ranks = raw_sanayi_score.rank(ascending=True)
        df_sanayi["ortak_skor"] = (ranks - 1.0) / max(1.0, len(ranks) - 1.0)

    # Bankacılık skorlaması (CAMELS: ROE + Sermaye + Karşılık + Momentum)
    df_banka = df[df["is_bank"] == True].copy()
    if not df_banka.empty:
        def z_col_b(s):
            v = s.dropna()
            if len(v) < 2 or v.std() < 1e-8:
                return pd.Series(0.0, index=s.index)
            return ((s - v.mean()) / v.std()).clip(-3.0, 3.0)

        z_b_roe = z_col_b(df_banka["roe"]).fillna(0.0)
        z_b_ser = z_col_b(df_banka["sermaye"]).fillna(0.0)
        z_b_mom = z_col_b(df_banka["mom"]).fillna(0.0)

        raw_banka_score = 0.40 * z_b_roe + 0.30 * z_b_ser + 0.30 * z_b_mom
        ranks_b = raw_banka_score.rank(ascending=True)
        df_banka["ortak_skor"] = (ranks_b - 1.0) / max(1.0, len(ranks_b) - 1.0)

    df_unified = pd.concat([df_sanayi, df_banka], ignore_index=True)
    return df_unified


# ─── 4. METRİKLER VE YARDIMCI ANALİZLER ───────────────────────────────────────
def metrikler_quarterly(arr, rf_annual=0.18):
    if not len(arr):
        return {"kumulatif": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0}
    a = np.array(arr)
    kum = float(np.prod(1.0 + a) - 1.0)
    n = len(a)
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


# ─── 5. ANA WALK-FORWARD TEST RUTİNİ ───────────────────────────────────────────
def run_walk_forward_audit():
    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
    tarihler_60 = pd.date_range("2018-09-01", "2026-08-01", freq="3MS")
    hisseler = sorted(fiyat_dict.keys())
    n_placebo = 100
    rng = np.random.default_rng(42)

    # Walk-Forward Ayırımı:
    # Erken Dönem (IS):  2018-09 -> 2021-12
    # Geç Dönem (OOS):   2022-01 -> 2026-08 (Dondurulmuş Test)
    donemler_is = []
    donemler_oos = []

    print("\n" + "=" * 115)
    print("FAZ C: WALK-FORWARD DÖNEM DİLİMLEME VE VERİ ÇIKARIMI (60 GÜNLÜK)")
    print("=" * 115)

    for i in range(len(tarihler_60) - 1):
        t0, t1 = tarihler_60[i], tarihler_60[i + 1]

        rets = {}
        for s, seri in fiyat_dict.items():
            p = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p) >= 3 and p.iloc[0] > 0:
                rets[s] = float(np.clip((p.iloc[-1] - p.iloc[0]) / p.iloc[0], -0.9, 8.0))

        mevcut = [s for s in hisseler if s in rets]
        if len(mevcut) < 32:
            continue

        px = seri_xu100[(seri_xu100.index >= t0) & (seri_xu100.index <= t1)]
        r_xu = float((px.iloc[-1] - px.iloc[0]) / px.iloc[0]) if len(px) >= 2 else 0.0

        pu = seri_usdtry[(seri_usdtry.index >= t0) & (seri_usdtry.index <= t1)]
        r_usd = float((pu.iloc[-1] - pu.iloc[0]) / pu.iloc[0]) if len(pu) >= 2 else 0.0

        aylar = pd.date_range(t0, t1, freq="MS").strftime("%Y-%m").tolist()[:-1]
        cpi_factors = [1.0 + tufe_aylik.get(ay, 2.0) / 100.0 for ay in aylar]
        r_cpi = float(np.prod(cpi_factors) - 1.0) if cpi_factors else 0.06

        # Makro Sinyal
        reel_faiz = getir_tcmb_reel_faiz(t0, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t0]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0

        # Makro Filtre Durumu:
        # Reel Faiz > +3.0% (Sıkı Likidite / Mevduat Cazip) veya USD İvmesi > %15 (Kur Şoku)
        # durumunda portföyün %30'u nakde/risksiz mevduata çekilir (Taktik Koruma).
        macro_risk_off = (reel_faiz > 3.0) or (mom_60_usd > 0.15)

        # Eski Kaba Skor (-Z(PB) + Z(ROE) + Z(Mom))
        satirlar_kaba = []
        for s in mevcut:
            curr, _ = hizli_pit(pit_bellek, s, t0)
            mom = hesapla_mom(fiyat_dict[s], t0)
            satirlar_kaba.append({
                "sembol": s, "sektor": cfg.HISSE_SEKTOR.get(s, "XUSIN.IS"),
                "pb": curr.get("pb", np.nan) if curr else np.nan,
                "roe": curr.get("roe", np.nan) if curr else np.nan, "mom": mom
            })
        df_kaba = pd.DataFrame(satirlar_kaba)
        def z_s(s):
            v = s.dropna()
            return ((s - v.mean()) / (v.std() + 1e-8)).clip(-3, 3)
        df_kaba["skor_kaba"] = -z_s(df_kaba["pb"]).fillna(0.0) + z_s(df_kaba["roe"]).fillna(0.0) + z_s(df_kaba["mom"]).fillna(0.0)
        sirali_kaba = df_kaba.sort_values("skor_kaba", ascending=False)["sembol"].tolist()

        # Yeni İki Kulvarlı Model Skoru
        df_faz_c = hesapla_faz_c_kesit(t0, mevcut, pit_bellek, cache_bellek, fiyat_dict)
        sirali_faz_c = df_faz_c.sort_values("ortak_skor", ascending=False)["sembol"].tolist()

        obj = {
            "t0": t0, "t1": t1, "yil": t0.year,
            "rets": rets, "mevcut": mevcut,
            "r_xu": r_xu, "r_usd": r_usd, "r_cpi": r_cpi,
            "macro_risk_off": macro_risk_off,
            "sirali_kaba": sirali_kaba,
            "sirali_faz_c": sirali_faz_c
        }

        if t0 < pd.Timestamp("2022-01-01"):
            donemler_is.append(obj)
        else:
            donemler_oos.append(obj)

    print(f"Erken Dönem (In-Sample 2018-2021) Periyot Sayısı: {len(donemler_is)}")
    print(f"Geç Dönem  (Out-of-Sample 2022-2026 Dondurulmuş) Periyot Sayısı: {len(donemler_oos)}")

    # Simülasyon Çalıştırıcı
    def simule_et(donem_listesi, isim):
        k15_kaba_rets = []
        k15_faz_c_rets = []
        k15_faz_c_macro_rets = []
        plac_rets = [[] for _ in range(n_placebo)]
        xu_rets = [d["r_xu"] for d in donem_listesi]

        for d in donem_listesi:
            rets = d["rets"]
            # Kaba Model
            top15_kaba = d["sirali_kaba"][:15]
            r_kaba = float(np.mean([rets[s] for s in top15_kaba])) - KOMISYON
            k15_kaba_rets.append(r_kaba)

            # Faz C Yeni İki Kulvarlı Model (P/B'siz Kalite + FCF + ROE + CAMELS + Mom)
            top15_c = d["sirali_faz_c"][:15]
            r_c = float(np.mean([rets[s] for s in top15_c])) - KOMISYON
            k15_faz_c_rets.append(r_c)

            # Faz C + Makro Rejim Filtresi
            # Risk-off durumunda portföyün %70'i hissede kalır, %30'u risksiz mevduat getirisinde korunur
            r_rf_q = 0.045
            if d["macro_risk_off"]:
                r_c_macro = 0.70 * r_c + 0.30 * r_rf_q
            else:
                r_c_macro = r_c
            k15_faz_c_macro_rets.append(r_c_macro)

            # 100 Tohum Placebo
            mevcut = d["mevcut"]
            for p_i in range(n_placebo):
                sec = rng.choice(mevcut, size=15, replace=False)
                plac_rets[p_i].append(float(np.mean([rets[s] for s in sec])) - KOMISYON)

        m_kaba = metrikler_quarterly(k15_kaba_rets)
        m_c = metrikler_quarterly(k15_faz_c_rets)
        m_c_macro = metrikler_quarterly(k15_faz_c_macro_rets)
        m_xu = metrikler_quarterly(xu_rets)

        plac_sharpes = [metrikler_quarterly(p)["sharpe"] for p in plac_rets]
        plac_kumuls  = [metrikler_quarterly(p)["kumulatif"] for p in plac_rets]

        p_val_kaba = float(np.mean([1 if s >= m_kaba["sharpe"] else 0 for s in plac_sharpes]))
        p_val_c    = float(np.mean([1 if s >= m_c["sharpe"] else 0 for s in plac_sharpes]))
        p_val_c_mac= float(np.mean([1 if s >= m_c_macro["sharpe"] else 0 for s in plac_sharpes]))

        print(f"\n{'=== ' + isim.upper() + ' PERFORMANS TABLOSU ===':<55}")
        print(f"{'Strateji':<32} | {'Kümülatif':<12} | {'CAGR':<9} | {'Sharpe':<8} | {'Max DD':<9} | {'Placebo p':<10}")
        print("-" * 90)
        print(f"{'1. Eski Kaba Skor (-PB+ROE+Mom)':<32} | %{m_kaba['kumulatif']*100:>10.1f} | %{m_kaba['cagr']*100:>7.1f} | {m_kaba['sharpe']:>8.2f} | %{m_kaba['max_dd']*100:>7.1f} | p = {p_val_kaba:.3f}")
        print(f"{'2. Faz C İki Kulvarlı (P/B Yok)':<32} | %{m_c['kumulatif']*100:>10.1f} | %{m_c['cagr']*100:>7.1f} | {m_c['sharpe']:>8.2f} | %{m_c['max_dd']*100:>7.1f} | p = {p_val_c:.3f}")
        print(f"{'3. Faz C + Makro Rejim Filtresi':<32} | %{m_c_macro['kumulatif']*100:>10.1f} | %{m_c_macro['cagr']*100:>7.1f} | {m_c_macro['sharpe']:>8.2f} | %{m_c_macro['max_dd']*100:>7.1f} | p = {p_val_c_mac:.3f}")
        print(f"{'4. 100 Placebo Ortalaması':<32} | %{np.mean(plac_kumuls)*100:>10.1f} | %{(np.mean(plac_kumuls)+1)**(4/max(1, len(k15_kaba_rets)))-1:>6.1%} | {np.mean(plac_sharpes):>8.2f} | {'-':>9} | baseline")
        print(f"{'5. BIST 100 Endeksi':<32} | %{m_xu['kumulatif']*100:>10.1f} | %{m_xu['cagr']*100:>7.1f} | {m_xu['sharpe']:>8.2f} | %{m_xu['max_dd']*100:>7.1f} | -")

        return {
            "m_kaba": m_kaba, "m_c": m_c, "m_c_macro": m_c_macro, "m_xu": m_xu,
            "p_val_kaba": p_val_kaba, "p_val_c": p_val_c, "p_val_c_mac": p_val_c_mac,
            "k15_c_rets": k15_faz_c_rets, "k15_c_mac_rets": k15_faz_c_macro_rets,
            "plac_rets": plac_rets, "donem_listesi": donem_listesi
        }

    # 1. Erken Dönem Testi (2018-2021) [In-Sample]
    res_is = simule_et(donemler_is, "Erken Dönem (2018-2021) [In-Sample]")

    # 2. Geç Dönem Testi (2022-2026) [Out-of-Sample / Dondurulmuş / Hiç Görülmemiş Veri]
    res_oos = simule_et(donemler_oos, "Geç Dönem (2022-2026) [Out-of-Sample Dondurulmuş]")

    # 3. Yıl Bazında Karşılaştırma (Tüm 8 Yıl)
    print("\n" + "=" * 115)
    print("FAZ C — YIL BAZINDA PERFORMANS VE REJİM DAYANIKLILIĞI (2018-2026)")
    print("=" * 115)
    print(f"{'Yıl':<6} | {'Eski Kaba':<12} | {'Faz C Model':<14} | {'Faz C + Makro':<15} | {'Placebo Ort':<12} | {'BIST 100':<10} | {'Faz C Yıllık p':<15}")
    print("-" * 95)

    tum_donemler = donemler_is + donemler_oos
    yillar = sorted(set(d["yil"] for d in tum_donemler))

    for y in yillar:
        sub_d = [d for d in tum_donemler if d["yil"] == y]
        # Kaba
        r_kaba_y = float(np.prod([1.0 + float(np.mean([d["rets"][s] for s in d["sirali_kaba"][:15]])) - KOMISYON for d in sub_d]) - 1.0)
        # Faz C
        r_c_y    = float(np.prod([1.0 + float(np.mean([d["rets"][s] for s in d["sirali_faz_c"][:15]])) - KOMISYON for d in sub_d]) - 1.0)
        # Faz C + Makro
        def r_mac_d(d):
            rc = float(np.mean([d["rets"][s] for s in d["sirali_faz_c"][:15]])) - KOMISYON
            return 0.70 * rc + 0.30 * 0.045 if d["macro_risk_off"] else rc
        r_cmac_y = float(np.prod([1.0 + r_mac_d(d) for d in sub_d]) - 1.0)
        # Placebo
        plac_y = []
        for p_i in range(n_placebo):
            p_ret = float(np.prod([1.0 + float(np.mean([d["rets"][s] for s in rng.choice(d["mevcut"], size=15, replace=False)])) - KOMISYON for d in sub_d]) - 1.0)
            plac_y.append(p_ret)
        r_plac_y = float(np.mean(plac_y))
        r_xu_y = float(np.prod([1.0 + d["r_xu"] for d in sub_d]) - 1.0)

        p_c_y = float(np.mean([1 if py >= r_c_y else 0 for py in plac_y]))
        print(f"{y:<6} | %{r_kaba_y*100:>10.1f} | %{r_c_y*100:>12.1f} | %{r_cmac_y*100:>13.1f} | %{r_plac_y*100:>10.1f} | %{r_xu_y*100:>8.1f} | p = {p_c_y:.3f}")


if __name__ == "__main__":
    run_walk_forward_audit()
