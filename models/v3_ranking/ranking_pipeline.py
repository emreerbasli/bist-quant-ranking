"""
models/v3_ranking/ranking_pipeline.py
======================================
PRODUCTION-CANDIDATE — CANLI SERMAYE YOK, PAPER TRADING AŞAMASINDA
------------------------------------------------------------------
Bu modül, Kilit Kutu (Lockbox) protokolünden 4/4 tam onay alarak geçen
dondurulmuş LGBMRanker (Aday 1: Aşırı Muhafazakâr Sığ Ağaç) modelinin
resmi çıkarım (inference) ve sıralama motorudur.

KRİTİK KURUMSAL UYARILAR:
1. Kilit kutu örneklemi (n=5 çeyrek) istatistiksel olarak küçüktür. Sharpe 2-3
   seviyeleri geniş bir belirsizlik aralığı taşımaktadır. 2025Q2 döneminde tüm piyasa
   birlikte yükselmiştir (beta rallisi); modelin saf şirket seçme alfasının bu genel
   dalgadan ayrıştırılması ancak uzun soluklu paper trading ile mümkündür.
2. K=20 portföy boyutunda basit kaba formülün ham p-değeri (0.000), ML modelinden
   (0.060) daha düşüktü. Dolayısıyla makine öğrenmesinin asıl katma değeri
   "her boyutta mutlak getiri rekoru" değil; aşırı oynaklığı baskılaması (%0.0 Max Drawdown)
   ve 2026 gibi faiz stres dönemlerinde borçlu hisseleri ayıklayarak gösterdiği dayanıklılıktır.
"""

import sys
from pathlib import Path
import logging
from typing import List, Dict, Optional, Tuple, Any

import pandas as pd
import numpy as np
import joblib

logger = logging.getLogger("LGBMRankingPipeline")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg


def hesapla_sektor_zscore(df: pd.DataFrame, col: str, min_grup: int = 4) -> pd.Series:
    """Kesitsel sektör bazlı z-score hesaplayıcı."""
    zscores = pd.Series(np.nan, index=df.index)
    for sektor, grup in df.groupby("sektor"):
        gecerli = grup[col].dropna()
        if len(gecerli) >= min_grup:
            mu  = gecerli.mean()
            std = gecerli.std()
        else:
            gecerli = df[col].dropna()
            mu  = gecerli.mean()
            std = gecerli.std()
        if std > 1e-8:
            zscores.loc[grup.index] = (grup[col] - mu) / std
        else:
            zscores.loc[grup.index] = 0.0
    return zscores.clip(-3.0, 3.0)


class LGBMRankingPipeline:
    """
    Dondurulmuş LGBMRanker modelini kullanarak belirli bir tarihte (Point-in-Time)
    BIST hisse evrenini sıralayan kurumsal inferans sınıfı.
    """

    DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "winning_lgbm_ranker.joblib"

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or self.DEFAULT_MODEL_PATH
        self.model_data = None
        self.model = None
        self.feature_cols = None
        self.candidate_name = None
        self._load_model()

    def _load_model(self):
        if not self.model_path.exists():
            raise FileNotFoundError(f"Dondurulmuş model dosyası bulunamadı: {self.model_path}")
        self.model_data = joblib.load(self.model_path)
        self.model = self.model_data["model"]
        self.feature_cols = self.model_data["feature_cols"]
        self.candidate_name = self.model_data.get("candidate_name", "Aday 1 (Aşırı Muhafazakâr)")
        logger.info(f"Yüklendi: {self.candidate_name} | Özellikler: {self.feature_cols}")

    def compute_features(self,
                         t: pd.Timestamp,
                         fiyat_dict: Dict[str, pd.Series],
                         pit_bellek: Dict[str, List[Dict[str, Any]]],
                         seri_usdtry: pd.Series,
                         tufe_aylik: Dict[str, float]) -> pd.DataFrame:
        """
        Belirli bir t anında kesin Point-in-Time (sıfır sızıntı) feature matrisi üretir.
        """
        from models.v3_ranking.data_loader import hizli_pit, hesapla_mom, getir_tcmb_reel_faiz

        reel_faiz = getir_tcmb_reel_faiz(t, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if len(sub_u) >= 45 else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if len(sub_u) >= 65 else 0.0

        satirlar = []
        for s in sorted(fiyat_dict.keys()):
            curr, _ = hizli_pit(pit_bellek, s, t)
            if not curr:
                continue
            is_bank = bool(curr.get("is_bank", False))
            sektor = cfg.HISSE_SEKTOR.get(s, "XBANK.IS" if is_bank else "XUSIN.IS")
            mom = hesapla_mom(fiyat_dict[s], t)
            pb = curr.get("pb", np.nan)
            roe = curr.get("roe", np.nan)
            fcf_v = curr.get("fcf_verim", np.nan)
            net_b = curr.get("net_borc", 0.0) or 0.0
            ebit = curr.get("ebitda", 1.0) or 1.0
            borc_ebitda = -net_b / max(1.0, abs(ebit)) if not is_bank else np.nan

            # Bilanço tazelik hesabı (Point-in-Time geçerlilik tarihinden geçen gün sayısı)
            gecerlilik_t = curr.get("gecerlilik_tarihi")
            if gecerlilik_t is not None:
                try:
                    data_age_days = int((t - pd.to_datetime(gecerlilik_t)).days)
                except Exception:
                    data_age_days = 999
            else:
                data_age_days = 999

            satirlar.append({
                "sembol": s, "sektor": sektor, "is_bank": is_bank,
                "fcf_v": fcf_v, "roe": roe, "mom": mom,
                "borc_ebitda": borc_ebitda, "pb": pb,
                "data_age_days": data_age_days
            })

        df = pd.DataFrame(satirlar)
        if df.empty:
            return df

        # Sektörel Kesitsel Z-Skorları
        df["z_fcf"]  = hesapla_sektor_zscore(df, "fcf_v", min_grup=4).fillna(0.0)
        df["z_roe"]  = hesapla_sektor_zscore(df, "roe", min_grup=4).fillna(0.0)
        df["z_mom"]  = hesapla_sektor_zscore(df, "mom", min_grup=4).fillna(0.0)
        df["z_borc"] = hesapla_sektor_zscore(df, "borc_ebitda", min_grup=4).fillna(0.0)
        df["z_pb"]   = -hesapla_sektor_zscore(df, "pb", min_grup=4).fillna(0.0)  # Ters PB

        # Makro Rejim Özellikleri
        df["reel_faiz"]  = reel_faiz
        df["usd_mom_60"] = mom_60_usd
        df["usd_mom_90"] = mom_90_usd

        return df

    def rank_stocks(self, df_features: pd.DataFrame) -> pd.DataFrame:
        """
        Özellik matrisi verilen hisseleri model skoru ile sıralar ve desil atar.
        """
        if df_features.empty:
            return df_features

        X = df_features[self.feature_cols]
        scores = self.model.predict(X)

        df_out = df_features.copy()
        df_out["ml_score"] = scores
        df_out = df_out.sort_values("ml_score", ascending=False).reset_index(drop=True)
        df_out["rank"] = df_out.index + 1
        df_out["decile"] = pd.qcut(df_out["ml_score"], q=10, labels=False, duplicates="drop")
        df_out["decile"] = 10 - df_out["decile"]  # 1: En iyi %10, 10: En kötü %10

        cols_to_ret = ["rank", "sembol", "sektor", "ml_score", "decile", "z_pb", "z_borc", "z_mom", "z_roe", "z_fcf"]
        if "data_age_days" in df_out.columns:
            cols_to_ret.append("data_age_days")

        return df_out[cols_to_ret]

    def select_top_k(self, df_features: pd.DataFrame, k: int = 15) -> pd.DataFrame:
        """En yüksek skora sahip Top-K hisseyi döner (V1 — geriye dönük uyum için korundu)."""
        df_ranked = self.rank_stocks(df_features)
        return df_ranked.head(k)

    # ------------------------------------------------------------------
    # V3.1: SEKTÖR KISIT FİLTRESİ + LİKİDİTE FİLTRESİ
    # ------------------------------------------------------------------

    @staticmethod
    def get_liquidity_tl(sembol: str, window: int = 60) -> float:
        """
        Hisse için son `window` günlük ortalama TL ciroyu hesaplar.
        Dosya bulunamazsa 0.0 döner.
        """
        try:
            import config as _cfg
            clean = sembol.replace(".", "_")
            p = _cfg.DATA_RAW / f"{clean}.parquet"
            if not p.exists():
                return 0.0
            df = pd.read_parquet(p)
            if "volume" not in df.columns or "close" not in df.columns:
                return 0.0
            sub = df.tail(window)
            avg_tl = float((sub["volume"] * sub["close"]).mean())
            return avg_tl
        except Exception:
            return 0.0

    def select_top_k_v2(self,
                        df_features: pd.DataFrame,
                        k: int = 10,
                        fiyat_dict: Optional[Dict[str, pd.Series]] = None,
                        excluded_semboller: Optional[set] = None) -> pd.DataFrame:
        """
        V3.1 Post-Model Filtre Katmanı — select_top_k'nın geliştirilmiş versiyonu.

        Uygulanan filtreler (sırasıyla):
        1. Faz 0 Taban Filtresi (Hard Exclusion): Son 10 günde >=5 kez <=-%9.5 taban
           kapanış yapan hisseler elenir.
        2. Likidite: Son 60 günlük ortalama günlük TL hacim >= LIKIDITE_MIN_TL_HACIM_V2
        3. Sektör kısıtı: HISSE_SEKTOR_V2 + MAX_SEKTOR_POZISYON_V2 ile
           aynı sektörden maksimum N hisse (BANKA/GYO/SİGORTA için 2, diğerleri 3)
        4. VIP hisseler likidite filtresinden muaf tutulur (config.VIP_HISSELER)

        Dönen DataFrame ek sütunlar içerir:
          - sektor_v2: Granüler sektör etiketi
          - avg_tl_hacim_m: 60 günlük ortalama günlük TL hacim (Milyon TL)
          - likidite_filtre: True = filtreden geçti
        """
        import config as _cfg

        if df_features.empty:
            return df_features

        # Faz 0 Taban Filtresi (Hard Exclusion)
        taban_excl = set()
        if fiyat_dict:
            try:
                from bot.kap_filter import ardisik_taban_tespit
                for s, p_seri in fiyat_dict.items():
                    tetik, cnt = ardisik_taban_tespit(p_seri, lookback_gun=10, min_taban=5, taban_esik=-0.095)
                    if tetik:
                        taban_excl.add(s)
                        logger.warning(
                            f"🚨 Faz 0 Taban Filtresi (Hard Exclusion): {s} son 10 işlem gününde "
                            f"{cnt} kez taban yaptı — Top-{k} adaylığından dışlandı."
                        )
            except Exception as e:
                logger.warning(f"Taban filtresi kontrol hatası: {e}")

        all_excluded = set(excluded_semboller or set()).union(taban_excl)

        # Tam sıralamayı al
        df_ranked = self.rank_stocks(df_features)

        # Sektör V2 ve likidite sütunlarını ekle
        df_ranked["sektor_v2"] = df_ranked["sembol"].map(
            lambda s: _cfg.HISSE_SEKTOR_V2.get(s, "DIGER")
        )
        df_ranked["avg_tl_hacim_m"] = df_ranked["sembol"].apply(
            lambda s: self.get_liquidity_tl(s, window=60) / 1e6
        )
        likidite_esik_m = _cfg.LIKIDITE_MIN_TL_HACIM_V2 / 1e6
        vip = set(_cfg.VIP_HISSELER)
        df_ranked["likidite_filtre"] = df_ranked.apply(
            lambda r: (r["avg_tl_hacim_m"] >= likidite_esik_m) or (r["sembol"] in vip),
            axis=1
        )

        # Bilanço tazelik uyarısı sütunu (>100 gün için True)
        if "data_age_days" in df_ranked.columns:
            esik_gun = getattr(_cfg, "BILANCO_ESKILIK_ESIGI_GUN", 100)
            df_ranked["bilanco_uyari"] = df_ranked["data_age_days"] > esik_gun
        else:
            df_ranked["bilanco_uyari"] = False

        # Likidite filtresini uygula
        likit = df_ranked[df_ranked["likidite_filtre"]].copy()
        elenen = df_ranked[~df_ranked["likidite_filtre"]]["sembol"].tolist()
        if elenen:
            logger.warning(
                f"Likidite filtresi — {len(elenen)} hisse elendi "
                f"(<{likidite_esik_m:.0f}M TL/gün): {elenen}"
            )

        # Sektör kısıtı ve dışlama filtresi ile greedy seçim
        sektor_sayac: dict[str, int] = {}
        secilen: list[str] = []

        for _, row in likit.iterrows():
            if len(secilen) >= k:
                break
            s       = row["sembol"]
            if s in all_excluded:
                logger.warning(
                    f"Dışlama kalkanı — {s} kural kısıtı nedeniyle Top-{k} sepetine alınmadı."
                )
                continue

            sektor  = row["sektor_v2"]
            max_pos = _cfg.MAX_SEKTOR_POZISYON_V2.get(sektor, _cfg.MAX_SEKTOR_VARSAYILAN_V2)
            mevcut  = sektor_sayac.get(sektor, 0)

            if mevcut < max_pos:
                secilen.append(s)
                sektor_sayac[sektor] = mevcut + 1
            else:
                logger.info(
                    f"Sektör kısıtı — {s} ({sektor}) atlandı "
                    f"[{mevcut}/{max_pos} dolu]"
                )

        df_secilen = df_ranked[df_ranked["sembol"].isin(secilen)].copy()
        # Orijinal ML skor sırasını koru
        df_secilen = df_secilen.sort_values("ml_score", ascending=False).reset_index(drop=True)
        df_secilen["rank"] = df_secilen.index + 1

        logger.info(
            f"select_top_k_v2: K={k} → {len(df_secilen)} hisse seçildi | "
            f"Sektörler: {sektor_sayac}"
        )
        return df_secilen

