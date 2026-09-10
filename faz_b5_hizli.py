import sys, warnings, json
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path
from loguru import logger
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level:<8} | {message}", colorize=False)

import config as cfg
from features.fundamental_pit import cek_canli_temel, hesapla_sektor_zscore

# ── 1. FİYAT MATRİSİ YükLE ──────────────────────────────────────────────────
print("=" * 60)
print("FAZ B.5 - KABA SKOR HIZLI PLACEBO TESTI")
print("-Z(P/B) + Z(ROE) + Z(Mom_12-1)")
print("=" * 60)

fiyat_dict = {}
for sembol in cfg.HISSELER:
    d = sembol.replace("^","IDX_").replace(".","_").replace("=","_")
    f = cfg.DATA_RAW / f"{d}.parquet"
    if f.exists():
        try:
            df = pd.read_parquet(f)
            if "close" in df.columns and len(df) > 300:
                fiyat_dict[sembol] = df["close"].sort_index()
        except: pass

print(f"Fiyat: {len(fiyat_dict)} hisse yuklendi")

# Ortak tarih dizini - aylik (MS=month start)
tarihler = pd.date_range("2022-01-01", "2026-08-01", freq="MS")
hisseler = sorted(fiyat_dict.keys())

# Fiyat matrisini olustur: tarihler x hisseler (aylik kapanislar)
fiyat_matrix = pd.DataFrame(index=tarihler, columns=hisseler, dtype=float)
for s, seri in fiyat_dict.items():
    # Ay sonu reindex - her ay icin en yakin kapanisi al
    for t in tarihler:
        gecmis = seri[seri.index <= t]
        if len(gecmis) > 0:
            fiyat_matrix.loc[t, s] = gecmis.iloc[-1]

# Aylik getiri matrisi
getiri_matrix = fiyat_matrix.pct_change(axis=0)
getiri_matrix = getiri_matrix.fillna(0)

print(f"Getiri matrisi: {getiri_matrix.shape[0]} ay x {getiri_matrix.shape[1]} hisse")

# ── 2. MOM 12-1 MATRIS ─────────────────────────────────────────────────────
print("Mom 12-1 hesaplaniyor...")
mom_matrix = pd.DataFrame(index=tarihler, columns=hisseler, dtype=float)

for s, seri in fiyat_dict.items():
    for t in tarihler:
        gecmis = seri[seri.index <= t]
        if len(gecmis) < 260: continue
        try:
            p0   = gecmis.iloc[-1]
            p21  = gecmis.iloc[-22]  if len(gecmis) >= 22  else np.nan
            p252 = gecmis.iloc[-253] if len(gecmis) >= 253 else np.nan
            if any(pd.isna([p21,p252])) or p21<=0 or p252<=0: continue
            mom_matrix.loc[t, s] = np.clip((p0-p252)/p252 - (p0-p21)/p21, -3, 3)
        except: pass

# ── 3. TEMEL VERİ ─────────────────────────────────────────────────────────
print("yfinance temel veri yukleniyor...")
df_temel = cek_canli_temel(cfg.HISSELER, zorla=False)
df_temel = df_temel.set_index("sembol") if "sembol" in df_temel.columns else df_temel

pb_dict  = df_temel["pb"].to_dict()
roe_dict = df_temel["roe"].to_dict()
sek_dict = df_temel["sektor"].to_dict() if "sektor" in df_temel.columns else {}

print(f"PB eksik: {df_temel['pb'].isna().sum()} | ROE eksik: {df_temel['roe'].isna().sum()}")

# ── 4. KABA SKOR SIRALAMALARI (aylık) ────────────────────────────────────
KOMISYON = 0.003  # %0.3 aylik

def z_score_cross(vals_dict, hisseler_listesi):
    """Basit cross-sectional z-score"""
    vals = np.array([vals_dict.get(s, np.nan) for s in hisseler_listesi], dtype=float)
    mu = np.nanmean(vals)
    std = np.nanstd(vals)
    if std < 1e-8: return np.zeros(len(vals))
    z = (vals - mu) / std
    return np.clip(np.nan_to_num(z, nan=0.0), -3, 3)

def backtest_topk(k):
    portfoy_ret = []
    for i, t in enumerate(tarihler[:-1]):
        t_sonraki = tarihler[i+1]

        # Gecerli hisseler: getiri verisi olan
        mevcut = [s for s in hisseler if not pd.isna(getiri_matrix.loc[t_sonraki, s])]
        if len(mevcut) < k + 5: continue

        # Kaba skor
        z_pb  = z_score_cross({s: pb_dict.get(s, np.nan) for s in mevcut}, mevcut)
        z_roe = z_score_cross({s: roe_dict.get(s, np.nan) for s in mevcut}, mevcut)
        mom_t = {s: mom_matrix.loc[t, s] if not pd.isna(mom_matrix.loc[t, s]) else 0 for s in mevcut}
        z_mom = z_score_cross(mom_t, mevcut)

        skor = -z_pb + z_roe + z_mom

        # Top-k sec
        idx_topk = np.argsort(skor)[-k:]
        top_hisseler = [mevcut[i] for i in idx_topk]

        # Bir sonraki ay getirisi
        ret = np.mean([float(getiri_matrix.loc[t_sonraki, s]) for s in top_hisseler])
        portfoy_ret.append(ret - KOMISYON)

    return np.array(portfoy_ret)

# ── 5. MONTE CARLO (vektorize) ────────────────────────────────────────────
def monte_carlo_placebo(k, n_seed=100):
    """Vektorize Monte Carlo: tum tohumlar icin getiri matrisi tek seferde"""
    # Her ay icin rastgele k hisse sec (n_seed x n_ay x k)
    aylik_ret = []
    rng = np.random.default_rng(42)

    for i, t in enumerate(tarihler[:-1]):
        t_sonraki = tarihler[i+1]
        mevcut = [s for s in hisseler if not pd.isna(getiri_matrix.loc[t_sonraki, s])]
        if len(mevcut) < k: continue

        # n_seed x k rastgele secim
        secilenler = np.array([rng.choice(len(mevcut), size=k, replace=False) for _ in range(n_seed)])
        getiriler  = np.array([float(getiri_matrix.loc[t_sonraki, mevcut[j]]) for j in range(len(mevcut))])
        sim_ret    = getiriler[secilenler].mean(axis=1) - KOMISYON
        aylik_ret.append(sim_ret)  # (n_seed,)

    return np.array(aylik_ret).T  # (n_seed x n_ay)

# ── 6. CALISTIR VE RAPORLA ───────────────────────────────────────────────
sonuclar = {}

for k in [10, 15]:
    print(f"\nTop-{k} backtest...")
    model = backtest_topk(k)

    print(f"Monte Carlo placebo (100 tohum, Top-{k})...")
    placebo = monte_carlo_placebo(k, n_seed=100)  # (100 x n_ay)

    model_kumul   = float(np.prod(1 + model) - 1)
    placebo_kumul = np.prod(1 + placebo, axis=1) - 1

    p_deger = float((placebo_kumul >= model_kumul).mean())
    persentil = float((placebo_kumul < model_kumul).mean() * 100)
    sharpe = float(model.mean() / (model.std() + 1e-10) * np.sqrt(12))

    print(f"\n{'='*60}")
    print(f"KARAR KAPISI - Top-{k}")
    print(f"{'='*60}")
    print(f"  Ay sayisi        : {len(model)}")
    print(f"  Model kumul.     : %{model_kumul*100:.1f}")
    print(f"  Placebo ortasi   : %{placebo_kumul.mean()*100:.1f}")
    print(f"  Placebo std      : %{placebo_kumul.std()*100:.1f}")
    print(f"  p-degeri         : {p_deger:.3f}")
    print(f"  Model sirasi     : {persentil:.0f}. persentil")
    print(f"  Sharpe (yillik)  : {sharpe:.2f}")
    print(f"  Aylik ortalama   : %{model.mean()*100:.2f}")
    print(f"  En kotu ay       : %{model.min()*100:.1f}")
    print(f"  En iyi ay        : %{model.max()*100:.1f}")

    if p_deger < 0.05:
        karar = "GUCLU DEVAM - p<0.05, KAP scraper'a gec!"
    elif p_deger < 0.10:
        karar = "ZAYIF DEVAM - p<0.10, PIT veriyle tekrar test et"
    elif p_deger < 0.20:
        karar = "BELIRSIZ - PIT veri kesin karar verir"
    else:
        karar = "DUR - Rastgeleden ayirt edilemiyor"

    print(f"\n  KARAR: {karar}")
    sonuclar[f"top{k}"] = {"p": p_deger, "kumul": model_kumul, "sharpe": sharpe, "persentil": persentil}

print(f"\n{'='*60}")
print("OZET")
print(f"{'='*60}")
for ad, r in sonuclar.items():
    p = r["p"]
    if p < 0.10: durum = "DEVAM"
    elif p < 0.20: durum = "BELIRSIZ"
    else: durum = "DUR"
    print(f"  {ad}: p={p:.3f} | Kumul=%{r['kumul']*100:.0f} | Sharpe={r['sharpe']:.2f} | {r['persentil']:.0f}.persentil => {durum}")

Path("reports").mkdir(exist_ok=True)
with open("reports/faz_b5_sonuc.json","w",encoding="utf-8") as f:
    json.dump(sonuclar, f, ensure_ascii=False, indent=2)
print("\nRapor: reports/faz_b5_sonuc.json")
