"""
models/v4_ranking/ranking_pipeline_v4.py
=========================================
V4 PRODUCTION-CANDIDATE: 9 FAKTÖRLÜ RESMİ ÇIKARIM VE SIRALAMA MOTORU
---------------------------------------------------------------------
Bu modül, 2022-2025 Walk-Forward OOS testlerinde kurumsal onay alan ve
dondurulan 9 Faktörlü LGBMRanker modelinin (winning_lgbm_ranker_v4.joblib)
üretim seviyesindeki çıkarım (inference) ve portföy seçim motorudur.

ÖZELLİK SETİ (9 Faktör):
  1. z_fcf: Sektörel Serbest Nakit Akım Verimi Z-Skoru
  2. z_roe: Sektörel Özsermaye Kârlılığı Z-Skoru
  3. z_mom: Sektörel Fiyat Momentumu Z-Skoru
  4. z_borc: Sektörel Net Borç / FAVÖK Ters Z-Skoru (Nakit rich = yüksek)
  5. z_pb: Sektörel Ters Fiyat/Defter Değeri Z-Skoru (Ucuz = yüksek)
  6. reel_faiz: TCMB Politika Faizi - Yıllık TÜFE Enflasyonu
  7. usd_mom_60: 60 Günlük USD/TRY Kuru İvmesi
  8. usd_mom_90: 90 Günlük USD/TRY Kuru İvmesi
  9. z_reel_eps: Sektörel Reel EPS Büyümesi Z-Skoru ([-1.5, 1.5] Winsorized)

GÜVENLİK KATMANLARI:
  - Faz 0 Ardışık Taban Hard Exclusion: Son 10 işlem gününde >=5 gün <=-%9.5 taban
    kapanış yapan hisseler Top-K sepetinden doğrudan dışlanır.
  - KAP / VBTS Tedbir Kalkanı: Volatilite Bazlı Tedbir Sistemi bildirimleri
    taranır ve tedbirli hisseler dışlama listesine eklenir.
  - Sektör Kısıtı & Likidite Filtresi: Konsantrasyon riski önlenir.
"""

import sys
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any

import numpy as np
import pandas as pd
import joblib

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config as cfg

logger = logging.getLogger("LGBMRankingPipelineV4")


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


def extract_reel_eps_growth_pit(t: pd.Timestamp,
                                pit_recs: List[Dict[str, Any]],
                                tufe_aylik: Dict[str, float]) -> float:
    """
    Point-in-Time prensipleriyle t anında son açıklanan ve t-4Q dönemine ait
    finansalları kullanarak enflasyondan arındırılmış reel EPS büyümesini hesaplar.
    """
    if not pit_recs:
        return 0.0

    gecerli = [r for r in pit_recs if r.get("gecerlilik_tarihi") and pd.to_datetime(r["gecerlilik_tarihi"]) <= t]
    if not gecerli:
        return 0.0

    curr = gecerli[-1]
    curr_q_str = curr.get("ceyrek", "")

    # 1 yıl önceki aynı çeyreği bul (t - 4Q)
    yoy = None
    if len(curr_q_str) >= 6:
        try:
            curr_year = int(curr_q_str[:4])
            curr_q = int(curr_q_str[-1])
            target_yoy = f"{curr_year - 1}Q{curr_q}"
            for r in gecerli:
                if r.get("ceyrek") == target_yoy:
                    yoy = r
                    break
        except Exception:
            pass

    if yoy is None and len(gecerli) >= 5:
        yoy = gecerli[-5]

    if not yoy:
        return 0.0

    net_kar_c = curr.get("net_kar") or 0.0
    net_kar_y = yoy.get("net_kar") or 0.0
    aktif_c = curr.get("toplam_aktif") or 0.0

    if aktif_c <= 0:
        return 0.0

    # 12 Aylık TÜFE enflasyon hesabı
    son_ay_dt = (t - pd.DateOffset(months=2 if t.day < 4 else 1)).replace(day=1)
    aylar = pd.date_range(end=son_ay_dt, periods=12, freq="MS").strftime("%Y-%m").tolist()
    factors = [1.0 + tufe_aylik.get(m, 2.0) / 100.0 for m in aylar]
    pi_12m = float(np.prod(factors) - 1.0)

    # Reel cari net kâr (t-4Q fiyat seviyesine indirgenmiş)
    net_kar_reel = net_kar_c / (1.0 + max(-0.5, pi_12m))
    reel_eps = float(np.clip((net_kar_reel - net_kar_y) / max(1e6, abs(aktif_c)), -2.0, 2.0))
    return reel_eps


class LGBMRankingPipelineV4:
    """
    Dondurulmuş V4 LGBMRanker modelini (9 Feature) kullanarak Point-in-Time
    BIST hisse evrenini sıralayan ve güvenlik kalkanlarını işleten inferans motoru.
    """

    DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "winning_lgbm_ranker_v4.joblib"
    V4_1_MODEL_PATH = Path(__file__).resolve().parent / "winning_lgbm_ranker_v4_1.joblib"

    def __init__(self, model_path: Optional[Path] = None):
        if model_path:
            self.model_path = Path(model_path)
        elif self.V4_1_MODEL_PATH.exists():
            self.model_path = self.V4_1_MODEL_PATH
        else:
            self.model_path = self.DEFAULT_MODEL_PATH
        self.model_data = None
        self.model = None
        self.feature_cols = None
        self.model_name = None
        self._load_model()

    def _load_model(self):
        if not self.model_path.exists():
            raise FileNotFoundError(f"Dondurulmuş V4 model dosyası bulunamadı: {self.model_path}")
        self.model_data = joblib.load(self.model_path)
        self.model = self.model_data["model"]
        self.feature_cols = self.model_data["feature_cols"]
        self.model_name = self.model_data.get("model_name", "V4.1 LGBMRanker (9 Feature: z_reel_eps)")
        logger.info(f"V4 Ranker Yüklendi: {self.model_name} | Özellikler: {self.feature_cols}")

    def compute_features(self,
                         t: pd.Timestamp,
                         fiyat_dict: Dict[str, pd.Series],
                         pit_bellek: Dict[str, List[Dict[str, Any]]],
                         seri_usdtry: pd.Series,
                         tufe_aylik: Dict[str, float]) -> pd.DataFrame:
        """
        Belirli bir t anında kesin Point-in-Time 9 faktörlü feature matrisini üretir.
        """
        from models.v4_ranking.data_loader_v4 import hizli_pit, hesapla_mom, getir_tcmb_reel_faiz

        reel_faiz = getir_tcmb_reel_faiz(t, tufe_aylik)
        sub_u = seri_usdtry[seri_usdtry.index <= t]
        mom_60_usd = (sub_u.iloc[-1] - sub_u.iloc[-43]) / sub_u.iloc[-43] if (len(sub_u) >= 45 and sub_u.iloc[-43] > 0) else 0.0
        mom_90_usd = (sub_u.iloc[-1] - sub_u.iloc[-63]) / sub_u.iloc[-63] if (len(sub_u) >= 65 and sub_u.iloc[-63] > 0) else 0.0

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

            # 9. Faktör ham hesaplama: reel_eps_raw
            reel_eps = extract_reel_eps_growth_pit(t, pit_bellek.get(s, []), tufe_aylik)

            # Bilanço tazelik hesabı
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
                "reel_eps_raw": reel_eps,
                "reel_eps_growth": reel_eps,
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
        df["z_pb"]   = -hesapla_sektor_zscore(df, "pb", min_grup=4).fillna(0.0)

        # 9. Resmi V4.1 Faktörü: Sektörel Z-Skor ve [-1.5, 1.5] Winsorize Kırpma
        df["z_reel_eps"] = hesapla_sektor_zscore(df, "reel_eps_raw", min_grup=4).fillna(0.0).clip(-1.5, 1.5)

        # Makro Özellikler
        df["reel_faiz"]  = reel_faiz
        df["usd_mom_60"] = mom_60_usd
        df["usd_mom_90"] = mom_90_usd

        return df

    def rank_stocks(self, df_features: pd.DataFrame) -> pd.DataFrame:
        """Özellik matrisini V4/V4.1 modeliyle skorlar ve sıralar."""
        if df_features.empty:
            return df_features

        X = df_features[self.feature_cols]
        scores = self.model.predict(X)

        df_out = df_features.copy()
        df_out["ml_score"] = scores
        df_out = df_out.sort_values("ml_score", ascending=False).reset_index(drop=True)
        df_out["rank"] = df_out.index + 1
        df_out["decile"] = pd.qcut(df_out["ml_score"], q=10, labels=False, duplicates="drop")
        df_out["decile"] = 10 - df_out["decile"]

        cols_to_ret = ["rank", "sembol", "sektor", "ml_score", "decile", "z_reel_eps", "reel_eps_growth", "z_pb", "z_borc", "z_mom", "z_roe", "z_fcf"]
        if "data_age_days" in df_out.columns:
            cols_to_ret.append("data_age_days")

        return df_out[cols_to_ret]

    @staticmethod
    def get_liquidity_tl(sembol: str, window: int = 60) -> float:
        """Hisse için son `window` günlük ortalama TL ciroyu hesaplar."""
        try:
            clean = sembol.replace(".", "_")
            p = cfg.DATA_RAW / f"{clean}.parquet"
            if not p.exists():
                return 0.0
            df = pd.read_parquet(p)
            if "volume" not in df.columns or "close" not in df.columns:
                return 0.0
            sub = df.tail(window)
            return float((sub["volume"] * sub["close"]).mean())
        except Exception:
            return 0.0

    def select_top_k_v2(self,
                        df_features: pd.DataFrame,
                        k: int = 15,
                        fiyat_dict: Optional[Dict[str, pd.Series]] = None,
                        excluded_semboller: Optional[Set[str]] = None,
                        check_vbts: bool = True) -> pd.DataFrame:
        """
        V4 Post-Model Güvenlik ve Seçim Katmanı (Varsayılan K=15).

        Uygulanan filtreler:
        1. Faz 0 Taban Filtresi (Hard Exclusion): Son 10 işlem gününde >=5 kez <=-%9.5 taban
           yapan hisseler portföye ASLA giremez.
        2. KAP / VBTS Filtresi: Volatilite Bazlı Tedbir Sistemi kapsamındaki hisseler elenir.
        3. Likidite Filtresi: 60 günlük ortalama hacim >= LIKIDITE_MIN_TL_HACIM_V2 (VIP hariç).
        4. Sektör Kısıtı: BANKA/GYO/SİGORTA azami 2, sanayi/diğer azami 3 hisse.
        """
        if df_features.empty:
            return df_features

        all_excluded: Set[str] = set(excluded_semboller or set())

        # 1. Faz 0 Taban Filtresi (Hard Exclusion)
        if fiyat_dict:
            try:
                from bot.kap_filter import ardisik_taban_tespit
                for s, p_seri in fiyat_dict.items():
                    tetik, cnt = ardisik_taban_tespit(p_seri, lookback_gun=10, min_taban=5, taban_esik=-0.095)
                    if tetik:
                        all_excluded.add(s)
                        logger.warning(
                            f"🚨 Faz 0 Taban Filtresi (Hard Exclusion): {s} son 10 işlem gününde "
                            f"{cnt} kez taban yaptı — Top-{k} adaylığından dışlandı."
                        )
            except Exception as e:
                logger.warning(f"Taban filtresi kontrol hatası: {e}")

        # 2. KAP / VBTS Tedbir Filtresi
        if check_vbts:
            try:
                from bot.kap_filter import cek_vbts_tedbir_durumu
                vbts_durumlar = cek_vbts_tedbir_durumu()
                for s, info in vbts_durumlar.items():
                    if info.get("tedbir_var", False):
                        all_excluded.add(s)
                        logger.warning(
                            f"🛡️ KAP/VBTS Tedbir Filtresi: {s} aktif tedbir altında ({info.get('detay', 'VBTS')}) — Top-{k}'dan dışlandı."
                        )
            except Exception as e:
                logger.warning(f"VBTS kontrol hatası: {e}")

        # Model sıralamasını üret
        df_ranked = self.rank_stocks(df_features)

        # Sektör V2 ve likidite kontrolleri
        df_ranked["sektor_v2"] = df_ranked["sembol"].map(
            lambda s: cfg.HISSE_SEKTOR_V2.get(s, "DIGER")
        )
        df_ranked["avg_tl_hacim_m"] = df_ranked["sembol"].apply(
            lambda s: self.get_liquidity_tl(s, window=60) / 1e6
        )
        likidite_esik_m = cfg.LIKIDITE_MIN_TL_HACIM_V2 / 1e6
        vip = set(cfg.VIP_HISSELER)
        df_ranked["likidite_filtre"] = df_ranked.apply(
            lambda r: (r["avg_tl_hacim_m"] >= likidite_esik_m) or (r["sembol"] in vip),
            axis=1
        )

        if "data_age_days" in df_ranked.columns:
            esik_gun = getattr(cfg, "BILANCO_ESKILIK_ESIGI_GUN", 100)
            df_ranked["bilanco_uyari"] = df_ranked["data_age_days"] > esik_gun
        else:
            df_ranked["bilanco_uyari"] = False

        likit = df_ranked[df_ranked["likidite_filtre"]].copy()

        # Sektör kısıtı ve dışlama kontrolü ile seçim
        sektor_sayac: Dict[str, int] = {}
        secilen: List[str] = []

        for _, row in likit.iterrows():
            if len(secilen) >= k:
                break
            s = row["sembol"]
            if s in all_excluded:
                continue

            sektor = row["sektor_v2"]
            max_pos = cfg.MAX_SEKTOR_POZISYON_V2.get(sektor, cfg.MAX_SEKTOR_VARSAYILAN_V2)
            mevcut = sektor_sayac.get(sektor, 0)

            if mevcut < max_pos:
                secilen.append(s)
                sektor_sayac[sektor] = mevcut + 1

        df_secilen = df_ranked[df_ranked["sembol"].isin(secilen)].copy()
        df_secilen = df_secilen.sort_values("ml_score", ascending=False).reset_index(drop=True)
        df_secilen["rank"] = df_secilen.index + 1

        logger.info(f"V4 select_top_k_v2: K={k} → {len(df_secilen)} hisse seçildi | Dışlanan: {len(all_excluded)}")
        return df_secilen
