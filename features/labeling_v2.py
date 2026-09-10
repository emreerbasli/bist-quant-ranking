"""
features/labeling_v2.py — Market-Residual (Beta-Arındırılmış) Etiketleme Motoru
================================================================================
Mükemmelleştirme Planı Referansı: FAZ B

Amacı:
  BIST gibi enflasyonist ve genel piyasa dalgasının yüksek olduğu borsalarda,
  hisse getirilerini BIST 100 beta hareketinden arındırarak (Market-Residual Return)
  modelin sadece şirket seçme alfasına odaklanmasını sağlamak.

Matematiksel Model:
  1. Shrinkage Beta (Vasicek / Blume Düzeltmesi):
     - 60 günlük hareketli getiri kovaryansı:
       beta_ham(t) = Cov(R_i, R_XU100) / Var(R_XU100)
     - Blume Shrinkage (akademik ve kurumsal literatür standardı):
       beta_adj(t) = 0.67 * beta_ham(t) + 0.33 * 1.0
     - Emniyet kısıtı: beta_adj [0.2, 2.5] arasına sınırlandırılır.

  2. Gelecek Dönem Kümülatif Residual (Artık) Getiri:
     - horizon = 21 işlem günü (yaklaşık 1 ay)
     - R_hisse(t, t+h)  = [P_i(t+h) - P_i(t)] / P_i(t)
     - R_XU100(t, t+h)  = [P_XU100(t+h) - P_XU100(t)] / P_XU100(t)
     - R_residual(t, t+h) = R_hisse(t, t+h) - beta_adj(t) * R_XU100(t, t+h)

Sıfır Sızıntı (Zero-Leakage) Garantisi:
  - beta_adj(t) yalnızca t ve öncesindeki barlarla hesaplanır.
  - R_residual(t, t+h) t gününün etiketi olarak atanır (geleceğe bakış sızıntısı
    walk-forward ve 21 günlük embargo ile engellenir).
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
from loguru import logger

# Proje kök dizini
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
import config as cfg

DEFAULT_HORIZON = 21      # 21 işlem günü (≈ 1 ay)
DEFAULT_BETA_WINDOW = 60  # 60 günlük hareketli beta
CACHE_DIR = cfg.BASE_DIR / "data" / "processed"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ─── 1. SHRINKAGE BETA HESAPLAYICI ───────────────────────────────────────────
def hesapla_shrinkage_beta(seri_hisse: pd.Series,
                           seri_xu100: pd.Series,
                           window: int = DEFAULT_BETA_WINDOW) -> pd.Series:
    """
    Hisse ve XU100 günlük getirilerinden 60 günlük hareketli Vasicek/Blume
    Shrinkage Beta hesaplar.
    
    beta_adj = 0.67 * beta_ham + 0.33 * 1.0
    Look-ahead bias: Yok (sadece geçmiş pencereler kullanılır).
    """
    ret_hisse = seri_hisse.pct_change(1)
    ret_index = seri_xu100.pct_change(1)

    # Ortak tarihleri hizala
    df_ret = pd.DataFrame({"hisse": ret_hisse, "index": ret_index}).dropna()

    if len(df_ret) < window:
        # Yeterli veri yoksa 1.0 döndür
        return pd.Series(1.0, index=seri_hisse.index)

    # Hareketli kovaryans ve varyans
    cov = df_ret["hisse"].rolling(window=window, min_periods=max(20, window // 2)).cov(df_ret["index"])
    var_idx = df_ret["index"].rolling(window=window, min_periods=max(20, window // 2)).var()

    beta_ham = cov / (var_idx + 1e-8)

    # Blume / Vasicek Shrinkage: Ortalamaya (1.0) çekme
    beta_adj = 0.67 * beta_ham + 0.33 * 1.0

    # Uç değerleri sınırla: [0.20, 2.50]
    beta_adj = beta_adj.clip(0.20, 2.50)

    # Eksik ilk günleri 1.0 ile doldur
    beta_tam = beta_adj.reindex(seri_hisse.index).fillna(1.0)
    return beta_tam


# ─── 2. RESIDUAL GETİRİ HESAPLAYICI ──────────────────────────────────────────
def hesapla_residual_getiriler(df_hisse: pd.DataFrame,
                               df_xu100: pd.DataFrame,
                               horizon: int = DEFAULT_HORIZON,
                               beta_window: int = DEFAULT_BETA_WINDOW) -> pd.DataFrame:
    """
    Bir hissenin kapanış fiyatından XU100 beta-arındırılmış residual getiri
    ve karşılaştırma hedeflerini hesaplar.
    
    Çıktı Sütunları:
      - beta_shrinkage: O tarihte bilinen Blume shrinkage beta
      - ret_fwd_{h}d: Hisse gelecek h günlük mutlak getiri
      - ret_xu100_fwd_{h}d: XU100 gelecek h günlük getiri
      - target_residual_{h}d: Beta-arındırılmış kalıntı getiri (ASIL HEDEF)
      - target_excess_{h}d: Basit endeks üstü getiri (benchmark kıyaslama)
    """
    out = df_hisse.copy()
    fiyat_hisse = out["close"].sort_index()
    fiyat_xu100 = df_xu100["close"].sort_index()

    # Beta hesabı
    beta_seri = hesapla_shrinkage_beta(fiyat_hisse, fiyat_xu100, window=beta_window)
    out["beta_shrinkage"] = beta_seri

    # Gelecek h günlük getiriler (shift(-horizon))
    ret_hisse_fwd = (fiyat_hisse.shift(-horizon) - fiyat_hisse) / fiyat_hisse
    fiyat_xu100_aligned = fiyat_xu100.reindex(fiyat_hisse.index).ffill()
    ret_xu100_fwd = (fiyat_xu100_aligned.shift(-horizon) - fiyat_xu100_aligned) / fiyat_xu100_aligned

    # Sütunları ata
    out[f"ret_fwd_{horizon}d"] = ret_hisse_fwd
    out[f"ret_xu100_fwd_{horizon}d"] = ret_xu100_fwd

    # Residual getiri = R_hisse - beta * R_xu100
    residual = ret_hisse_fwd - beta_seri * ret_xu100_fwd
    out[f"target_residual_{horizon}d"] = residual

    # Basit Excess getiri = R_hisse - R_xu100
    out[f"target_excess_{horizon}d"] = ret_hisse_fwd - ret_xu100_fwd

    return out


# ─── 3. TÜM HİSSELER İÇİN TOPLU ETİKETLEME ────────────────────────────────────
def yukle_ve_etiketle_evren(hisseler: Optional[List[str]] = None,
                             horizon: int = DEFAULT_HORIZON,
                             beta_window: int = DEFAULT_BETA_WINDOW) -> Dict[str, pd.DataFrame]:
    """
    Evrendeki tüm hisseleri data/raw altından yükler, XU100 ile hizalar
    ve her biri için residual getiri etiketlerini üretir.
    """
    if hisseler is None:
        hisseler = cfg.HISSELER

    # XU100 yükle
    xu100_dosya = cfg.DATA_RAW / "XU100_IS.parquet"
    if not xu100_dosya.exists():
        xu100_dosya = cfg.DATA_RAW / "IDX_XU100_IS.parquet"
    if not xu100_dosya.exists():
        xu100_dosya = cfg.DATA_RAW / "^XU100.parquet"
    if not xu100_dosya.exists():
        raise FileNotFoundError(f"XU100 verisi bulunamadı: {xu100_dosya}")

    df_xu100 = pd.read_parquet(xu100_dosya)
    logger.info(f"XU100 endeks serisi yüklendi: {len(df_xu100)} bar ({df_xu100.index[0].date()} -> {df_xu100.index[-1].date()})")

    etiketli_dict = {}
    for s in hisseler:
        dosya_adi = s.replace("^", "IDX_").replace(".", "_").replace("=", "_")
        f = cfg.DATA_RAW / f"{dosya_adi}.parquet"
        if not f.exists():
            continue
        try:
            df = pd.read_parquet(f)
            if "close" in df.columns and len(df) > 100:
                df_etiketli = hesapla_residual_getiriler(df, df_xu100, horizon=horizon, beta_window=beta_window)
                etiketli_dict[s] = df_etiketli
        except Exception as e:
            logger.debug(f"{s} etiketleme hatası: {e}")

    logger.info(f"Etiketleme tamamlandı: {len(etiketli_dict)}/{len(hisseler)} hisse hazırlandı (Horizon={horizon}g).")
    return etiketli_dict


# ─── 4. KESİTSEL SIRALAMA / DECILE ETİKETİ ───────────────────────────────────
def hesapla_kesitsel_rank_etiketleri(etiketli_dict: Dict[str, pd.DataFrame],
                                     target_col: str = f"target_residual_{DEFAULT_HORIZON}d") -> pd.DataFrame:
    """
    Her tarihteki hisseleri target_col residual getirisine göre 0.0 ile 1.0
    arasında percentile rank'e ve 1-10 Decile sınıfına dönüştürür.
    LGBMRanker ve doğrudan sıralama modelleri için hazır girdi sunar.
    """
    # Matris oluştur: index=tarih, columns=hisseler, values=residual_getiri
    seriler = {}
    for s, df in etiketli_dict.items():
        if target_col in df.columns:
            seriler[s] = df[target_col].dropna()

    df_matris = pd.DataFrame(seriler)

    # Her satırda (tarihte) kesitsel rank: 0.0 (en kötü) -> 1.0 (en iyi)
    df_rank = df_matris.rank(axis=1, pct=True)
    # Decile: 1'den 10'a
    df_decile = (df_rank * 10).apply(np.ceil).clip(1, 10)

    return df_rank


# ─── TEST VE RAPOR ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 70)
    print("labeling_v2.py — Market-Residual Etiketleme Testi")
    print("=" * 70)

    test_hisseler = ["THYAO.IS", "AKBNK.IS", "BIMAS.IS", "ASELS.IS", "EREGL.IS"]
    sonuclar = yukle_ve_etiketle_evren(test_hisseler, horizon=21)

    for s, df in sonuclar.items():
        son_satir = df.dropna(subset=["target_residual_21d"]).iloc[-1]
        tarih = df.dropna(subset=["target_residual_21d"]).index[-1].date()
        beta = son_satir["beta_shrinkage"]
        r_hisse = son_satir["ret_fwd_21d"]
        r_idx   = son_satir["ret_xu100_fwd_21d"]
        r_res   = son_satir["target_residual_21d"]
        r_exc   = son_satir["target_excess_21d"]

        print(f"{s:<10} | Tarih: {tarih} | Beta: {beta:.2f} | "
              f"R_hisse: %{r_hisse*100:>+6.1f} | R_XU100: %{r_idx*100:>+6.1f} | "
              f"Residual: %{r_res*100:>+6.1f} | Excess: %{r_exc*100:>+6.1f}")
