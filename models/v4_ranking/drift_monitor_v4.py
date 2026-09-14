"""
models/v4_ranking/drift_monitor_v4.py
======================================
V4 PRODUCTION-CANDIDATE: SÜREKLİ İZLEME VE DRİFT TESPİT MODÜLÜ
--------------------------------------------------------------
Bu modül, dondurulmuş 9 Faktörlü V4 LGBMRanker modelinin ve portföyün
canlı operasyon esnasındaki sağlığını 5 bağımsız güvenlik katmanında denetler:

Katman 1 — Makro Rejim İzleyici (Haftalık):
  - TCMB politika faizi ve 12 aylık kümülatif TÜFE'den Reel Faiz hesaplar.
  - USD/TRY 60 günlük ivmesini (USD_Mom_60) hesaplar.
  - Reel Faiz <= -%10.0 -> "MAKRO_ALARM: Negatif reel faiz rejimi"
  - USD_Mom_60 >= +%20.0 -> "MAKRO_ALARM: Kur şoku"

Katman 2 — Model Skor Drift İzleyici:
  - V4 modelinin ürettiği ham tahmin skorlarının dağılımını denetler.
  - V4 tarihsel çıpası: Mean = -0.0985, Std = 0.2358.
  - |Z-Score| > 2.5 sapma -> "SKOR_DRIFT: Dağılım kaymış" uyarısı üretir.

Katman 3 — Performans Sapma Dedektörü:
  - Portföyün gerçekleşen rolling 12-ay veya kümülatif Sharpe oranını denetler.
  - V4 Referans Sharpe = 0.972, Alarm eşiği = 0.58 (Sharpe <= 0.58 -> "PERFORMANS_ALARM").

Katman 4 — Veri Tazelik Güvencesi (EMNİYET KAPISI / FAZ -1):
  - En güncel BIST piyasa verisi referans tarihten >= 2 İŞ GÜNÜ eskiyse
    operasyonu doğrudan KİLİTLER / DURDURUR (should_halt = True).
  - BIST resmi ve dini bayram takvimine tam duyarlıdır.

Katman 5 — Veri Sağlık Kontrolü:
  - 88 hissenin fiyat serisi doluluğu, NaN oranı (<%0.5) ve PIT bilanço tazeliğini (>100 gün) denetler.

Genel Durum Sinyali:
  🟢 YEŞİL: Tüm katmanlar normal, veri taze.
  🟡 SARI:  Makro alarm veya skor drifti var; performans normal.
  🔴 KIRMIZI: Performans alarmı aktif VEYA veri bayatlığı nedeniyle operasyon kilitli.
"""

import sys
import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg

logger = logging.getLogger("DriftMonitorV4")

# ==============================================================================
# V4 TARİHSEL ÇIPALARI VE GÜVENLİK EŞİKLERİ
# ==============================================================================
MACRO_REAL_RATE_ALARM_THRESHOLD: float = -10.0  # Reel Faiz <= -%10.0 (Negatif faiz balonu)
MACRO_USD_MOM_ALARM_THRESHOLD: float = 0.20     # USD 60g İvmesi >= +%20.0 (Kur şoku)

# V4 Model Skor Dağılımı Çıpaları (9 Feature LGBMRanker)
HISTORICAL_V4_BATCH_MEAN_MU: float = -0.0985
HISTORICAL_V4_BATCH_MEAN_SIGMA: float = 0.0450
HISTORICAL_V4_BATCH_STD_MU: float = 0.2358
HISTORICAL_V4_BATCH_STD_SIGMA: float = 0.0420
SCORE_DRIFT_Z_THRESHOLD: float = 2.5

# V4 Performans Çıpası
REFERENCE_SHARPE_V4: float = 0.972
SHARPE_DEGRADATION_TOLERANCE: float = 0.40      # %40 azami izin verilen kayıp
PERFORMANCE_ALARM_SHARPE_THRESHOLD: float = REFERENCE_SHARPE_V4 * (1.0 - SHARPE_DEGRADATION_TOLERANCE)  # ~0.58

# Veri Tazelik Sınırı (İş Günü)
MAX_STALE_BUSINESS_DAYS: int = 2


@dataclass
class MacroCheckResult:
    status: str
    reel_faiz: float
    usd_mom_60: float
    politika_faizi: float
    yillik_tufe: float
    is_alarm: bool
    details: str


@dataclass
class ScoreDriftResult:
    status: str
    current_mean: float
    current_std: float
    current_min: float
    current_max: float
    z_score_mean: float
    z_score_std: float
    is_drift: bool
    details: str


@dataclass
class PerformanceCheckResult:
    status: str
    realized_sharpe: float
    reference_sharpe: float
    alarm_threshold: float
    is_alarm: bool
    details: str


@dataclass
class DataFreshnessResult:
    status: str
    market_date: str
    reference_date: str
    business_days_lag: int
    max_allowed_lag: int
    is_stale: bool
    should_halt: bool
    details: str


@dataclass
class DataHealthResult:
    status: str
    tickers_count: int
    total_bars: int
    nan_ratio_pct: float
    pit_tickers_count: int
    stale_financials_count: int
    macro_usd_status: str
    macro_cpi_status: str
    details: str


@dataclass
class DriftMonitorReportV4:
    timestamp: pd.Timestamp
    overall_status: str
    macro_result: MacroCheckResult
    score_result: Optional[ScoreDriftResult]
    performance_result: Optional[PerformanceCheckResult]
    freshness_result: Optional[DataFreshnessResult] = None
    health_result: Optional[DataHealthResult] = None
    summary_message: str = ""


class DriftMonitorV4:
    """
    V4 Ranker Sürekli İzleme ve Drift / Sağlık Denetim Motoru.
    """

    def __init__(self,
                 real_rate_alarm_threshold: float = MACRO_REAL_RATE_ALARM_THRESHOLD,
                 usd_mom_alarm_threshold: float = MACRO_USD_MOM_ALARM_THRESHOLD,
                 score_z_threshold: float = SCORE_DRIFT_Z_THRESHOLD,
                 reference_sharpe: float = REFERENCE_SHARPE_V4,
                 performance_threshold: float = PERFORMANCE_ALARM_SHARPE_THRESHOLD):
        self.real_rate_alarm_threshold = real_rate_alarm_threshold
        self.usd_mom_alarm_threshold = usd_mom_alarm_threshold
        self.score_z_threshold = score_z_threshold
        self.reference_sharpe = reference_sharpe
        self.performance_threshold = performance_threshold

    # --------------------------------------------------------------------------
    # KATMAN 1: MAKRO REJİM İZLEYİCİ
    # --------------------------------------------------------------------------
    def check_macro_regime(self,
                           t: pd.Timestamp,
                           seri_usdtry: pd.Series,
                           tufe_aylik: Dict[str, float],
                           politika_faizi_override: Optional[float] = None) -> MacroCheckResult:
        """TCMB reel faiz ve 60 günlük USD/TRY ivmesini denetler."""
        from models.v4_ranking.data_loader_v4 import getir_tcmb_reel_faiz

        sub_u = seri_usdtry[seri_usdtry.index <= t]
        if len(sub_u) >= 45:
            lag_idx = -43 if len(sub_u) >= 43 else 0
            denom_u = float(sub_u.iloc[lag_idx])
            usd_mom_60 = float((sub_u.iloc[-1] - denom_u) / denom_u) if denom_u > 0 else 0.0
        else:
            usd_mom_60 = 0.0

        reel_faiz = float(getir_tcmb_reel_faiz(t, tufe_aylik))
        son_ay_dt = (t - pd.DateOffset(months=2 if t.day < 4 else 1)).replace(day=1)
        aylar = pd.date_range(end=son_ay_dt, periods=12, freq="MS").strftime("%Y-%m").tolist()
        yillik_tufe = float((np.prod([1.0 + tufe_aylik.get(m, 2.0) / 100.0 for m in aylar]) - 1.0) * 100.0)
        pol_faiz = float(reel_faiz + yillik_tufe)

        if politika_faizi_override is not None:
            pol_faiz = float(politika_faizi_override)
            reel_faiz = pol_faiz - yillik_tufe

        alarms = []
        if reel_faiz <= self.real_rate_alarm_threshold:
            alarms.append(f"Negatif reel faiz rejimi (Reel Faiz: %{reel_faiz:.1f} <= %{self.real_rate_alarm_threshold:.1f})")
        if usd_mom_60 >= self.usd_mom_alarm_threshold:
            alarms.append(f"Kur şoku (USD 60g Mom: %{usd_mom_60*100:.1f} >= %{self.usd_mom_alarm_threshold*100:.1f})")

        is_alarm = len(alarms) > 0
        if is_alarm:
            status = f"MAKRO_ALARM: {' & '.join(alarms)}"
            details = f"⚠️ MAKRO REJİM ALARMI: {status}. V4 modeli defansif parametrelerle çalışır."
        else:
            status = "MAKRO_NORMAL"
            details = f"Makro rejim stabil (Reel Faiz: %{reel_faiz:.1f}, USD 60g İvme: %{usd_mom_60*100:.1f})."

        return MacroCheckResult(
            status=status, reel_faiz=reel_faiz, usd_mom_60=usd_mom_60,
            politika_faizi=pol_faiz, yillik_tufe=yillik_tufe,
            is_alarm=is_alarm, details=details
        )

    # --------------------------------------------------------------------------
    # KATMAN 2: MODEL SKOR DRİFT İZLEYİCİ (V4)
    # --------------------------------------------------------------------------
    def check_score_drift(self, scores: np.ndarray) -> ScoreDriftResult:
        """V4 modelinin evren için ürettiği ham tahmin skorlarının dağılımını test eder."""
        if len(scores) == 0:
            return ScoreDriftResult(
                status="SKOR_BELİRSİZ", current_mean=0.0, current_std=0.0,
                current_min=0.0, current_max=0.0, z_score_mean=0.0, z_score_std=0.0,
                is_drift=False, details="Skor dizisi boş."
            )

        arr = np.array(scores, dtype=float)
        c_mean = float(np.mean(arr))
        c_std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        c_min = float(np.min(arr))
        c_max = float(np.max(arr))

        z_mean = float((c_mean - HISTORICAL_V4_BATCH_MEAN_MU) / HISTORICAL_V4_BATCH_MEAN_SIGMA)
        z_std = float((c_std - HISTORICAL_V4_BATCH_STD_MU) / HISTORICAL_V4_BATCH_STD_SIGMA)

        is_drift = (abs(z_mean) > self.score_z_threshold) or (abs(z_std) > self.score_z_threshold)

        if is_drift:
            status = "SKOR_DRIFT: Dağılım kaymış"
            details = (f"⚠️ V4 MODEL SKOR DRİFT UYARISI: Ortalama skor={c_mean:.4f} (Z={z_mean:+.2f}), "
                       f"Std={c_std:.4f} (Z={z_std:+.2f}). Tarihsel V4 dağılımının 2.5 sigma dışına çıkıldı!")
        else:
            status = "SKOR_NORMAL"
            details = f"V4 Skor dağılımı olağan (Ort: {c_mean:.4f}, Std: {c_std:.4f}, Z_mean: {z_mean:+.2f})."

        return ScoreDriftResult(
            status=status, current_mean=c_mean, current_std=c_std,
            current_min=c_min, current_max=c_max,
            z_score_mean=z_mean, z_score_std=z_std,
            is_drift=is_drift, details=details
        )

    # --------------------------------------------------------------------------
    # KATMAN 3: PERFORMANS SAPMA DEDEKTÖRÜ (V4)
    # --------------------------------------------------------------------------
    def check_performance_degradation(self, realized_sharpe: float) -> PerformanceCheckResult:
        """V4 gerçekleşen portföy Sharpe oranını denetler."""
        is_alarm = realized_sharpe <= self.performance_threshold
        if is_alarm:
            status = "PERFORMANS_ALARM: Sharpe kritik eşiğin altında"
            details = (f"🚨 V4 PERFORMANS ALARMI: Gerçekleşen Sharpe={realized_sharpe:.2f} <= {self.performance_threshold:.2f} "
                       f"(V4 Referans={self.reference_sharpe:.2f}). Model performansı yapısal bozulma gösteriyor!")
        else:
            status = "PERFORMANS_NORMAL"
            details = f"V4 Portföy performansı normal (Gerçekleşen Sharpe={realized_sharpe:.2f} > {self.performance_threshold:.2f})."

        return PerformanceCheckResult(
            status=status, realized_sharpe=realized_sharpe,
            reference_sharpe=self.reference_sharpe,
            alarm_threshold=self.performance_threshold,
            is_alarm=is_alarm, details=details
        )

    # --------------------------------------------------------------------------
    # KATMAN 4: VERİ TAZELİK GÜVENCESİ (BIST İŞ GÜNÜ DUYARLI EMNİYET KAPISI)
    # --------------------------------------------------------------------------
    def check_data_freshness(self,
                             t: pd.Timestamp,
                             fiyat_dict: Dict[str, pd.Series],
                             max_lag_business_days: int = MAX_STALE_BUSINESS_DAYS) -> DataFreshnessResult:
        """
        En güncel piyasa verisinin referans tarihten kaç İŞ GÜNÜ eski olduğunu hesaplar.
        BIST resmi tatillerini filtreler.
        Eğer gecikme >= max_lag_business_days (2 iş günü) ise operasyonu KESİNLİKLE DURDURUR.
        """
        if not fiyat_dict:
            return DataFreshnessResult(
                status="VERİ_BAYAT: Fiyat verisi boş",
                market_date="YOK",
                reference_date=t.strftime("%Y-%m-%d"),
                business_days_lag=999,
                max_allowed_lag=max_lag_business_days,
                is_stale=True,
                should_halt=True,
                details="🚨 EMNİYET KAPISI: Fiyat verisi sözlüğü boş! V4 Karar üretimi durduruldu."
            )

        all_max_dates = [s.index.max() for s in fiyat_dict.values() if not s.empty]
        if not all_max_dates:
            return DataFreshnessResult(
                status="VERİ_BAYAT: Tarih tespit edilemedi",
                market_date="YOK",
                reference_date=t.strftime("%Y-%m-%d"),
                business_days_lag=999,
                max_allowed_lag=max_lag_business_days,
                is_stale=True,
                should_halt=True,
                details="🚨 EMNİYET KAPISI: Geçerli fiyat serisi bulunamadı."
            )

        latest_market_dt = pd.Timestamp(max(all_max_dates)).normalize()
        ref_dt = pd.Timestamp(t).normalize()

        business_days_lag = 0
        if ref_dt > latest_market_dt:
            candidate_dates = pd.date_range(latest_market_dt + pd.Timedelta(days=1), ref_dt, freq="D")
            for cur_d in candidate_dates:
                if cfg.bist_is_gunu_mu(cur_d):
                    business_days_lag += 1

        is_stale = (business_days_lag >= max_lag_business_days)
        should_halt = is_stale

        market_date_str = latest_market_dt.strftime("%Y-%m-%d")
        ref_date_str = ref_dt.strftime("%Y-%m-%d")

        if is_stale:
            status = f"VERİ_BAYAT: Son veri {business_days_lag} iş günü eski"
            details = (
                f"🚨 V4 VERİ_BAYAT: Son piyasa verisi {market_date_str} tarihli olup, "
                f"referans tarihten ({ref_date_str}) {business_days_lag} İŞ GÜNÜ eskidir "
                f"(Azami izin: {max_lag_business_days} iş günü). "
                f"Sessizce yanlış karar vermemek için V4 kararı üretilmedi ve operasyon DURDURULDU."
            )
        else:
            status = "VERİ_TAZE"
            details = (
                f"V4 Piyasa verisi taze ({market_date_str} kapanışı, referans: {ref_date_str}, "
                f"gecikme: {business_days_lag} iş günü <= {max_lag_business_days})."
            )

        return DataFreshnessResult(
            status=status, market_date=market_date_str,
            reference_date=ref_date_str,
            business_days_lag=business_days_lag,
            max_allowed_lag=max_lag_business_days,
            is_stale=is_stale, should_halt=should_halt,
            details=details
        )

    # --------------------------------------------------------------------------
    # KATMAN 5: VERİ SAĞLIK KONTROLÜ (88 HİSSE & PIT BİLANÇO SAĞLIĞI)
    # --------------------------------------------------------------------------
    def check_data_health(self,
                          fiyat_dict: Dict[str, pd.Series],
                          pit_bellek: Optional[Dict[str, Any]] = None,
                          tufe_aylik: Optional[Dict[str, float]] = None,
                          t: Optional[pd.Timestamp] = None) -> DataHealthResult:
        """Fiyat, bilanço ve makro verilerin eksiksizlik ve sağlık özetini denetler."""
        t_ref = t or pd.Timestamp.now()
        tickers_count = len(fiyat_dict)
        total_bars = sum([len(s) for s in fiyat_dict.values()]) if fiyat_dict else 0
        total_nans = sum([s.isnull().sum() for s in fiyat_dict.values()]) if fiyat_dict else 0
        nan_ratio = (total_nans / max(1, total_bars + total_nans)) * 100.0

        pit_tickers = len(pit_bellek) if pit_bellek else 0
        stale_pit_count = 0
        if pit_bellek:
            from models.v4_ranking.data_loader_v4 import hizli_pit
            for sym in fiyat_dict.keys():
                curr, _ = hizli_pit(pit_bellek, sym, t_ref)
                if curr:
                    try:
                        g_tarih = pd.to_datetime(curr.get("gecerlilik_tarihi"))
                        age_days = (t_ref - g_tarih).days
                        if age_days > 100:
                            stale_pit_count += 1
                    except Exception:
                        pass
                else:
                    stale_pit_count += 1

        macro_usd_status = "OK"
        macro_cpi_status = "OK" if tufe_aylik and len(tufe_aylik) >= 24 else "EKSİK"

        is_healthy = (tickers_count >= 80) and (nan_ratio < 0.5)
        status = "SAĞLIKLI" if is_healthy else "UYARI"
        details = (
            f"Fiyat: {tickers_count} hisse ({total_bars:,} bar, NaN: %{nan_ratio:.2f}) | "
            f"PIT Bilanço: {pit_tickers} hisse (100g+ eski: {stale_pit_count}) | "
            f"Makro: USD={macro_usd_status}, TÜFE={macro_cpi_status}"
        )

        return DataHealthResult(
            status=status, tickers_count=tickers_count,
            total_bars=total_bars, nan_ratio_pct=round(nan_ratio, 3),
            pit_tickers_count=pit_tickers, stale_financials_count=stale_pit_count,
            macro_usd_status=macro_usd_status, macro_cpi_status=macro_cpi_status,
            details=details
        )

    # --------------------------------------------------------------------------
    # KONSOLİDE RAPORLAMA VE JSON PERSISTENCE
    # --------------------------------------------------------------------------
    def generate_full_report(self,
                             t: pd.Timestamp,
                             seri_usdtry: pd.Series,
                             tufe_aylik: Dict[str, float],
                             scores: Optional[np.ndarray] = None,
                             realized_sharpe: Optional[float] = None,
                             fiyat_dict: Optional[Dict[str, pd.Series]] = None,
                             pit_bellek: Optional[Dict[str, Any]] = None) -> DriftMonitorReportV4:
        """Tüm 5 katmanı çalıştırır ve konsolide durum üretir."""
        macro_res = self.check_macro_regime(t, seri_usdtry, tufe_aylik)
        score_res = self.check_score_drift(scores) if scores is not None else None
        perf_res = self.check_performance_degradation(realized_sharpe) if realized_sharpe is not None else None

        freshness_res = None
        if fiyat_dict is not None:
            freshness_res = self.check_data_freshness(t, fiyat_dict)

        health_res = None
        if fiyat_dict is not None:
            health_res = self.check_data_health(fiyat_dict, pit_bellek, tufe_aylik, t)

        # Durum belirleme
        if (freshness_res and freshness_res.should_halt) or (perf_res and perf_res.is_alarm):
            overall = "🔴 KIRMIZI"
        elif macro_res.is_alarm or (score_res and score_res.is_drift):
            overall = "🟡 SARI"
        else:
            overall = "🟢 YEŞİL"

        parts = []
        if freshness_res and freshness_res.is_stale:
            parts.append(freshness_res.details)
        if macro_res.is_alarm:
            parts.append(macro_res.details)
        if score_res and score_res.is_drift:
            parts.append(score_res.details)
        if perf_res and perf_res.is_alarm:
            parts.append(perf_res.details)

        summary = " | ".join(parts) if parts else "Tüm güvenlik ve drift katmanları nominal."

        report = DriftMonitorReportV4(
            timestamp=t, overall_status=overall,
            macro_result=macro_res, score_result=score_res,
            performance_result=perf_res, freshness_result=freshness_res,
            health_result=health_res, summary_message=summary
        )

        # Atomik JSON çıktısı
        try:
            out_file = Path(__file__).resolve().parent / "latest_drift_report_v4.json"
            temp_file = out_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({
                    "as_of": t.strftime("%Y-%m-%d"),
                    "generated_at": pd.Timestamp.now().isoformat(),
                    "overall_status": overall,
                    "summary_message": summary,
                    "macro": asdict(macro_res),
                    "score": asdict(score_res) if score_res else None,
                    "performance": asdict(perf_res) if perf_res else None,
                    "freshness": asdict(freshness_res) if freshness_res else None,
                    "health": asdict(health_res) if health_res else None
                }, f, ensure_ascii=False, indent=2, default=str)
            os.replace(temp_file, out_file)
        except Exception as e:
            logger.warning(f"Drift raporu kaydedilemedi: {e}")

        return report
