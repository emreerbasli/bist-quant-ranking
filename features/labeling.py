"""
features/labeling.py — FAZ B1: Triple Barrier Method — 3 Sınıflı (Multiclass) Etiketleme
==========================================================================================
Plan referansı: FAZ B1 (iyileştirme planı)

Kurallar & Mantık:
  1. Entry (Giriş): T gününün kapanışındaki sinyalle, T+1 Açılış fiyatından (Open) giriş.
  2. Dinamik Bariyerler:
     - Üst Bariyer (TP): entry_price + (k1 * ATR[t]), k1 = 1.5
     - Alt Bariyer (SL): entry_price - (k2 * ATR[t]), k2 = 1.0 (1.5:1 asimetrik oran)
     - Zaman Bariyeri: 5 işlem günü (horizon = 5)
  3. OHLC Dokunma Kontrolü:
     - Gelecek 5 gün boyunca High >= Üst veya Low <= Alt kontrol edilir.
     - Konservatif Kural: Aynı mumda hem TP hem SL dokunulursa, SL önce gerçekleşti kabul edilir.
  4. FAZ B1 — 3 SINIFLI ETIKET:
     - label = 2: Hızlı TP  (1-3 gün içinde üst bariyere dokunuldu)  ← EN KALİTELİ
     - label = 1: Yavaş TP  (4-5 gün içinde üst bariyere dokunuldu)
     - label = 0: SL veya Timeout                                     ← KAYIP
  5. Timeout Kararı:
     - 5 gün içinde hiçbir bariyere dokunulmazsa -> label = 0 (zaman kaybı)
     - NOT (eski hatanın düzeltilmesi): 5. günde hisse +%8 olsa bile pozitif
       etiket almak için yine de TP bariyerine dokunulmuş olması gerekir.
  6. Çıktı:
     - data/labeled/{ticker}.parquet dosyaları (label: 0, 1 veya 2)
"""

import sys
import argparse
from pathlib import Path
from typing import Optional, Tuple, Dict

import pandas as pd
import numpy as np
from loguru import logger

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg

# ─── Log ayarı ───────────────────────────────────────────────────────────────
logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add(cfg.LOGS_DIR / "labeling_{time:YYYY-MM-DD}.log",
           rotation="1 day", retention="30 days", level="DEBUG", encoding="utf-8")


def triple_barrier_etiketle(
    df_feat: pd.DataFrame,
    k1: float = cfg.K1,
    k2: float = cfg.K2,
    horizon: int = cfg.ZAMAN_BARIYERI,
    multiclass: bool = True,
    tp_hizli_horizon: int = cfg.TP_HIZLI_HORIZON,
) -> pd.DataFrame:
    """
    Verilen feature dataframe'i üzerinde Triple Barrier Method uygulayarak etiket üretir.

    FAZ B1 — Multiclass Modu (multiclass=True):
      - label=2: TP bariyerine 1-3 gün içinde dokunuldu (Hızlı Kazanç)
      - label=1: TP bariyerine 4-5 gün içinde dokunuldu (Yavaş Kazanç)
      - label=0: SL bariyeri veya Zaman Aşımı (Kayıp)

    Returns:
        DataFrame: Feature'lar + etiket ve işlem detay sütunları.
    """
    df = df_feat.copy().sort_index()
    n = len(df)

    labels = []
    entry_dates = []
    entry_prices = []
    upper_barriers = []
    lower_barriers = []
    exit_dates = []
    exit_prices = []
    exit_reasons = []
    holding_days = []
    trade_returns = []

    for i in range(n):
        if i + horizon >= n:
            labels.append(np.nan)
            entry_dates.append(pd.NaT)
            entry_prices.append(np.nan)
            upper_barriers.append(np.nan)
            lower_barriers.append(np.nan)
            exit_dates.append(pd.NaT)
            exit_prices.append(np.nan)
            exit_reasons.append(None)
            holding_days.append(np.nan)
            trade_returns.append(np.nan)
            continue

        t_atr = df["atr_14"].iloc[i]

        # 1. T+1 Açılış fiyatı ile işleme giriş
        entry_idx   = i + 1
        entry_date  = df.index[entry_idx]
        entry_price = df["open"].iloc[entry_idx]

        if pd.isna(entry_price) or pd.isna(t_atr) or entry_price <= 0 or t_atr <= 0:
            labels.append(np.nan)
            entry_dates.append(pd.NaT)
            entry_prices.append(np.nan)
            upper_barriers.append(np.nan)
            lower_barriers.append(np.nan)
            exit_dates.append(pd.NaT)
            exit_prices.append(np.nan)
            exit_reasons.append(None)
            holding_days.append(np.nan)
            trade_returns.append(np.nan)
            continue

        # 2. Dinamik Bariyerler
        upper_barrier = entry_price + (k1 * t_atr)
        lower_barrier = entry_price - (k2 * t_atr)

        # 3. Gelecek horizon günlerini tara
        label       = None
        exit_date   = None
        exit_price  = None
        exit_reason = None
        h_day       = 0

        for step in range(1, horizon + 1):
            curr_idx   = i + step
            curr_date  = df.index[curr_idx]
            curr_high  = df["high"].iloc[curr_idx]
            curr_low   = df["low"].iloc[curr_idx]
            h_day      = step

            hit_upper = curr_high >= upper_barrier
            hit_lower = curr_low  <= lower_barrier

            # Konservatif kural: Aynı barda hem TP hem SL → SL sayılır
            if hit_upper and hit_lower:
                label       = 0
                exit_date   = curr_date
                exit_price  = lower_barrier
                exit_reason = "SL_SAME_BAR"
                break
            elif hit_lower:
                label       = 0
                exit_date   = curr_date
                exit_price  = lower_barrier
                exit_reason = "SL"
                break
            elif hit_upper:
                # ─── FAZ B1: Hızlı vs Yavaş TP ayrımı ────────────────────────
                if multiclass:
                    if step <= tp_hizli_horizon:
                        label       = 2          # Hızlı TP (1-3 gün)
                        exit_reason = "TP_HIZLI"
                    else:
                        label       = 1          # Yavaş TP (4-5 gün)
                        exit_reason = "TP_YAVAS"
                else:
                    label       = 1
                    exit_reason = "TP"
                exit_date  = curr_date
                exit_price = upper_barrier
                break

        # 4. Zaman Bariyeri (Timeout) → Her zaman 0
        if label is None:
            timeout_idx = i + horizon
            label       = 0
            exit_date   = df.index[timeout_idx]
            exit_price  = df["close"].iloc[timeout_idx]
            exit_reason = "TIMEOUT"
            h_day       = horizon

        trade_ret = (exit_price - entry_price) / entry_price

        labels.append(int(label))
        entry_dates.append(entry_date)
        entry_prices.append(entry_price)
        upper_barriers.append(upper_barrier)
        lower_barriers.append(lower_barrier)
        exit_dates.append(exit_date)
        exit_prices.append(exit_price)
        exit_reasons.append(exit_reason)
        holding_days.append(h_day)
        trade_returns.append(trade_ret)

    # Kolonları ekle
    df["label"]         = labels
    df["entry_date"]    = entry_dates
    df["entry_price"]   = entry_prices
    df["upper_barrier"] = upper_barriers
    df["lower_barrier"] = lower_barriers
    df["exit_date"]     = exit_dates
    df["exit_price"]    = exit_prices
    df["exit_reason"]   = exit_reasons
    df["holding_days"]  = holding_days
    df["trade_return"]  = trade_returns

    df_labeled = df.dropna(subset=["label"]).copy()
    df_labeled["label"]        = df_labeled["label"].astype(int)
    df_labeled["holding_days"] = df_labeled["holding_days"].astype(int)

    return df_labeled


def _tek_hisse_etiketle(sembol: str, multiclass: bool, tp_hizli: int) -> Optional[Tuple[str, dict]]:
    """Tek bir hisseyi etiketler ve kaydeder (Thread-safe worker)."""
    dosya_adi = f"{sembol.replace('.', '_')}.parquet"
    feat_yol  = cfg.DATA_FEAT / dosya_adi

    if not feat_yol.exists():
        logger.error(f"Feature dosyası bulunamadı: {feat_yol}")
        return None

    df_feat    = pd.read_parquet(feat_yol)
    df_labeled = triple_barrier_etiketle(df_feat, multiclass=multiclass, tp_hizli_horizon=tp_hizli)

    hedef_yol = cfg.DATA_LABEL / dosya_adi
    df_labeled.to_parquet(hedef_yol, engine="pyarrow", compression="snappy")

    n_total = len(df_labeled)
    n_2     = int((df_labeled["label"] == 2).sum())   # Hızlı TP
    n_1     = int((df_labeled["label"] == 1).sum())   # Yavaş TP
    n_0     = int((df_labeled["label"] == 0).sum())   # SL / Timeout
    reasons = df_labeled["exit_reason"].value_counts().to_dict()

    ozet = {
        "toplam_ornek":       n_total,
        "label_2_hizli_tp":   n_2,
        "label_1_yavas_tp":   n_1,
        "label_0_kayip":      n_0,
        "hizli_tp_orani_%":   round(n_2 / n_total * 100, 1) if n_total > 0 else 0,
        "yavas_tp_orani_%":   round(n_1 / n_total * 100, 1) if n_total > 0 else 0,
        "kayip_orani_%":      round(n_0 / n_total * 100, 1) if n_total > 0 else 0,
        "cikis_nedenleri":    reasons,
        "tarih_araligi":      f"{df_labeled.index[0].date()} → {df_labeled.index[-1].date()}",
    }

    logger.info(
        f"{sembol:10s} → {n_total} örnek | "
        f"Hızlı TP(2): %{ozet['hizli_tp_orani_%']:.1f} ({n_2}) | "
        f"Yavaş TP(1): %{ozet['yavas_tp_orani_%']:.1f} ({n_1}) | "
        f"Kayıp(0): %{ozet['kayip_orani_%']:.1f} ({n_0})"
    )
    return sembol, ozet


def etiketle_tumunu(hisseler: Optional[list[str]] = None) -> Dict[str, dict]:
    """
    data/features/ altındaki tüm hisseleri paralel 3 sınıflı etiketler ve data/labeled/ altına kaydeder.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if hisseler is None:
        hisseler = cfg.HISSELER

    multiclass = getattr(cfg, "MULTICLASS_LABEL", True)
    tp_hizli   = getattr(cfg, "TP_HIZLI_HORIZON", 3)

    logger.info(f"{'═'*60}")
    logger.info(f"FAZ B1: Paralel Triple Barrier Etiketleme Başlatıldı ({len(hisseler)} Hisse, 8 thread)")
    logger.info(f"Mod: {'MULTICLASS (0/1/2)' if multiclass else 'BINARY (0/1)'}")
    logger.info(f"Parametreler: K1={cfg.K1} (TP), K2={cfg.K2} (SL), Horizon={cfg.ZAMAN_BARIYERI}g, Hızlı TP Eşiği={tp_hizli}g")
    logger.info(f"{'═'*60}")

    cfg.DATA_LABEL.mkdir(parents=True, exist_ok=True)
    raporlar = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_tek_hisse_etiketle, sembol, multiclass, tp_hizli): sembol
            for sembol in hisseler
        }
        for f in as_completed(futures):
            res = f.result()
            if res is not None:
                sembol, ozet = res
                raporlar[sembol] = ozet

    logger.info(f"{'═'*60}")
    logger.info(f"FAZ B1: Multiclass Etiketleme Tamamlandı ({len(raporlar)} hisse etiketlendi).")
    logger.info(f"{'═'*60}")
    return raporlar


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FAZ B1 — Multiclass Triple Barrier Etiketleme")
    parser.add_argument("--ticker", type=str, help="Tek hisse etiketle")
    args = parser.parse_args()

    if args.ticker:
        sembol = args.ticker if args.ticker.endswith(".IS") else f"{args.ticker}.IS"
        etiketle_tumunu([sembol])
    else:
        etiketle_tumunu()
