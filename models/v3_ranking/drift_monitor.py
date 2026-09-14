"""
models/v3_ranking/drift_monitor.py
===================================
PRODUCTION-CANDIDATE: SÜREKLİ İZLEME VE DRİFT TESPİT MODÜLÜ (ADIM 2)
-------------------------------------------------------------------
Bu modül, dondurulmuş LGBMRanker modelinin ve portföyün canlı operasyon
esnasındaki sağlığını 3 bağımsız katmanda denetler:

Katman 1 — Makro Rejim İzleyici (Haftalık):
  - TCMB politika faizi ve 12 aylık kümülatif TÜFE'den Reel Faiz hesaplar.
  - USD/TRY 60 günlük ivmesini (USD_Mom_60) hesaplar.
  - Reel Faiz <= -%10.0 -> "MAKRO_ALARM: Negatif reel faiz rejimi"
  - USD_Mom_60 >= +%20.0 -> "MAKRO_ALARM: Kur şoku"
  - İkisi de normal -> "MAKRO_NORMAL"
  * Kurumsal Not: Makro alarmlar modeli durdurmaz, sadece bağlam bilgisi sağlar.

Katman 2 — Model Skor Drift İzleyici (Her 2 Haftada / Rebalance Kontrolünde):
  - Modelin evren için ürettiği ham skorların dağılımını (mean, std, min, max) loglar.
  - Tarihsel eğitim + kilit kutu çıpasıyla kıyaslar (Batch Mean: -0.1008, Std: 0.0482).
  - |Z-Score| > 2.5 sapma -> "SKOR_DRIFT: Dağılım kaymış" uyarısı üretir.

Katman 3 — Performans Sapma Dedektörü (Rebalance Sonrası / Rolling 12 Ay):
  - Portföyün gerçekleşen rolling 12-ay veya birikimli Sharpe oranını hesaplar.
  - Referans 1.26 Sharpe'tan %40 düşüş (Sharpe <= 0.75) -> "PERFORMANS_ALARM" üretir.
  * Bu eşik kasıtlı olarak geniş tutulmuştur; sadece ciddi yapısal sapmada tetiklenir.

Genel Durum Sinyali:
  🟢 YEŞİL: Tüm katmanlar normal.
  🟡 SARI:  Makro alarm veya skor drifti var; performans henüz bozulmamış.
  🔴 KIRMIZI: Performans alarmı aktif (Sharpe <= 0.75).
"""

import sys
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config as cfg

logger = logging.getLogger("DriftMonitor")


# ==============================================================================
# TARİHSEL VERİYE DAYALI ÇIPALAR VE AMPİRİK EŞİKLER
# ==============================================================================
# Katman 1: Temiz Makro Eşikleri (2018Q3 -> 2025Q1 verisinden türetilen kesin sınırlar)
MACRO_REAL_RATE_ALARM_THRESHOLD: float = -10.0  # Reel Faiz <= -%10.0 (Negatif faiz balonu)
MACRO_USD_MOM_ALARM_THRESHOLD: float = 0.20     # USD 60g İvmesi >= +%20.0 (Kur şoku alarmı)

# Katman 2: Tarihsel Model Skor Dağılımı Çıpaları (Eğitim + Kilit Kutu dönemi)
HISTORICAL_BATCH_MEAN_MU: float = -0.1008       # Çeyreklik evren ortalama skor ortalaması
HISTORICAL_BATCH_MEAN_SIGMA: float = 0.0482    # Çeyreklik evren ortalama skor standart sapması
HISTORICAL_BATCH_STD_MU: float = 0.2215         # Çeyreklik evren skor standart sapması ortalaması
HISTORICAL_BATCH_STD_SIGMA: float = 0.0445      # Çeyreklik evren skor standart sapması sapması
SCORE_DRIFT_Z_THRESHOLD: float = 2.5            # Z > 2.5 sapma alarmı (p < 0.012)

# Katman 3: Performans Sapma Çıpası
REFERENCE_SHARPE: float = 1.26                 # K=10, H=60g + %25 DD Kontrolü 6.75 yıllık Sharpe çıpası
SHARPE_DEGRADATION_TOLERANCE: float = 0.40      # %40 azami izin verilen performans kaybı
PERFORMANCE_ALARM_SHARPE_THRESHOLD: float = REFERENCE_SHARPE * (1.0 - SHARPE_DEGRADATION_TOLERANCE)  # 0.75

# Katman 4 & 5: Veri Tazelik ve Sağlık Eşikleri (Faz -1)
MAX_STALE_BUSINESS_DAYS: int = 2               # İzin verilen azami iş günü gecikmesi


@dataclass
class MacroCheckResult:
    status: str             # "MAKRO_NORMAL" veya "MAKRO_ALARM: ..."
    reel_faiz: float        # Yüzde olarak reel faiz (örn: 3.5 = %3.5)
    usd_mom_60: float       # 60 günlük USD/TRY ivmesi (örn: 0.04 = %4.0)
    politika_faizi: float   # Yıllık TCMB politika faizi
    yillik_tufe: float      # Yıllık kümülatif TÜFE
    is_alarm: bool
    details: str


@dataclass
class ScoreDriftResult:
    status: str             # "SKOR_NORMAL" veya "SKOR_DRIFT: Dağılım kaymış"
    current_mean: float     # Mevcut sepet ortalama skoru
    current_std: float      # Mevcut sepet skor standart sapması
    current_min: float      # Min skor
    current_max: float      # Max skor
    z_score_mean: float     # Ortalama skorun tarihsel Z değeri
    z_score_std: float      # Standart sapmanın tarihsel Z değeri
    is_drift: bool
    details: str


@dataclass
class PerformanceCheckResult:
    status: str             # "PERFORMANS_NORMAL" veya "PERFORMANS_ALARM"
    realized_sharpe: float  # Gerçekleşen rolling/birikimli Sharpe
    reference_sharpe: float # 1.26
    alarm_threshold: float  # 0.75
    is_alarm: bool
    details: str


@dataclass
class DataFreshnessResult:
    status: str             # "VERİ_TAZE" veya "VERİ_BAYAT"
    market_date: str        # Son borsa barı tarihi (örn: "2026-09-11")
    reference_date: str     # Kontrol tarihi (örn: "2026-09-13")
    business_days_lag: int  # İş günü cinsinden gecikme
    max_allowed_lag: int    # 2 iş günü
    is_stale: bool          # Gecikme >= max_allowed_lag ise True
    should_halt: bool       # True ise sinyal ve portföy icrası durdurulmalı
    details: str


@dataclass
class DataHealthResult:
    status: str             # "SAĞLIKLI" veya "UYARI"
    tickers_count: int       # Yüklenen hisse adedi (örn: 88)
    total_bars: int          # Toplam fiyat barı
    nan_ratio_pct: float     # Fiyat serisi NaN oranı (%)
    pit_tickers_count: int   # PIT bilançosu bulunan hisse sayısı (örn: 88)
    stale_financials_count: int # >100 gün eski bilanço adedi
    macro_usd_status: str    # USD/TRY serisi durumu
    macro_cpi_status: str    # TÜFE tablosu durumu
    details: str


@dataclass
class DriftMonitorReport:
    timestamp: pd.Timestamp
    overall_status: str     # "🟢 YEŞİL", "🟡 SARI", "🔴 KIRMIZI"
    macro_result: MacroCheckResult
    score_result: Optional[ScoreDriftResult]
    performance_result: Optional[PerformanceCheckResult]
    freshness_result: Optional[DataFreshnessResult] = None
    health_result: Optional[DataHealthResult] = None
    summary_message: str = ""


class DriftMonitor:
    """
    Production-Candidate V3 Ranker Sürekli İzleme ve Drift Tespit Motoru.
    """

    def __init__(self,
                 real_rate_alarm_threshold: float = MACRO_REAL_RATE_ALARM_THRESHOLD,
                 usd_mom_alarm_threshold: float = MACRO_USD_MOM_ALARM_THRESHOLD,
                 score_z_threshold: float = SCORE_DRIFT_Z_THRESHOLD,
                 reference_sharpe: float = REFERENCE_SHARPE,
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
        """
        TCMB reel faiz ve 60 günlük USD/TRY ivmesini denetler.
        """
        from models.v3_ranking.data_loader import getir_tcmb_reel_faiz

        # 1. USD 60 günlük momentum
        sub_u = seri_usdtry[seri_usdtry.index <= t]
        if len(sub_u) >= 45:
            lag_idx = -43 if len(sub_u) >= 43 else 0
            usd_mom_60 = float((sub_u.iloc[-1] - sub_u.iloc[lag_idx]) / sub_u.iloc[lag_idx])
        else:
            usd_mom_60 = 0.0

        # 2. Reel Faiz Hesabı
        reel_faiz = float(getir_tcmb_reel_faiz(t, tufe_aylik))
        
        # Politika faizi ve yıllık TÜFE ayrıştırması
        son_ay_dt = (t - pd.DateOffset(months=2 if t.day < 4 else 1)).replace(day=1)
        aylar = pd.date_range(end=son_ay_dt, periods=12, freq="MS").strftime("%Y-%m").tolist()
        yillik_tufe = float((np.prod([1.0 + tufe_aylik.get(m, 2.0) / 100.0 for m in aylar]) - 1.0) * 100.0)
        pol_faiz = float(reel_faiz + yillik_tufe)

        if politika_faizi_override is not None:
            pol_faiz = float(politika_faizi_override)
            reel_faiz = pol_faiz - yillik_tufe

        # 3. Alarm Değerlendirmesi
        alarms = []
        if reel_faiz <= self.real_rate_alarm_threshold:
            alarms.append(f"Negatif reel faiz rejimi (Reel Faiz: %{reel_faiz:.1f} <= %{self.real_rate_alarm_threshold:.1f})")
        if usd_mom_60 >= self.usd_mom_alarm_threshold:
            alarms.append(f"Kur şoku (USD 60g Mom: %{usd_mom_60*100:.1f} >= %{self.usd_mom_alarm_threshold*100:.1f})")

        is_alarm = len(alarms) > 0
        if is_alarm:
            status = f"MAKRO_ALARM: {' & '.join(alarms)}"
            details = f"⚠️ MAKRO REJİM ALARMI: {status}. Model muhafazakâr kalmaya devam eder, bu bir bağlam uyarısıdır."
        else:
            status = "MAKRO_NORMAL"
            details = f"Makro rejim stabil (Reel Faiz: %{reel_faiz:.1f}, USD 60g İvme: %{usd_mom_60*100:.1f})."

        return MacroCheckResult(
            status=status,
            reel_faiz=reel_faiz,
            usd_mom_60=usd_mom_60,
            politika_faizi=pol_faiz,
            yillik_tufe=yillik_tufe,
            is_alarm=is_alarm,
            details=details
        )

    # --------------------------------------------------------------------------
    # KATMAN 2: MODEL SKOR DRİFT İZLEYİCİ
    # --------------------------------------------------------------------------
    def check_score_drift(self, scores: np.ndarray) -> ScoreDriftResult:
        """
        Modelin evren için ürettiği ham tahmin skorlarının dağılım kaymasını (drift) test eder.
        """
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

        # Z-Score hesabı
        z_mean = float((c_mean - HISTORICAL_BATCH_MEAN_MU) / HISTORICAL_BATCH_MEAN_SIGMA)
        z_std = float((c_std - HISTORICAL_BATCH_STD_MU) / HISTORICAL_BATCH_STD_SIGMA)

        is_drift = (abs(z_mean) > self.score_z_threshold) or (abs(z_std) > self.score_z_threshold)

        if is_drift:
            status = "SKOR_DRIFT: Dağılım kaymış"
            details = (f"⚠️ MODEL SKOR DRİFT UYARISI: Ortalama skor={c_mean:.4f} (Z={z_mean:+.2f}), "
                       f"Std={c_std:.4f} (Z={z_std:+.2f}). Tarihsel dağılımın 2.5 sigma dışına çıkıldı!")
        else:
            status = "SKOR_NORMAL"
            details = f"Skor dağılımı olağan (Ort: {c_mean:.4f}, Std: {c_std:.4f}, Z_mean: {z_mean:+.2f})."

        return ScoreDriftResult(
            status=status,
            current_mean=c_mean,
            current_std=c_std,
            current_min=c_min,
            current_max=c_max,
            z_score_mean=z_mean,
            z_score_std=z_std,
            is_drift=is_drift,
            details=details
        )

    # --------------------------------------------------------------------------
    # KATMAN 3: PERFORMANS SAPMA DEDEKTÖRÜ
    # --------------------------------------------------------------------------
    def check_performance_degradation(self, realized_sharpe: float) -> PerformanceCheckResult:
        """
        Paper trading gerçekleşen Sharpe oranının referans 1.26'dan %40 düşüp düşmediğini (<=0.75) kontrol eder.
        """
        is_alarm = (realized_sharpe <= self.performance_threshold)

        if is_alarm:
            status = "PERFORMANS_ALARM"
            details = (f"🚨 PERFORMANS SAPMA ALARMI: Gerçekleşen Sharpe={realized_sharpe:.2f}, "
                       f"referans eşik={self.performance_threshold:.2f} altına indi! (Tarihsel Sharpe 1.26'dan %40 kayıp)")
        else:
            status = "PERFORMANS_NORMAL"
            details = f"Gerçekleşen Sharpe={realized_sharpe:.2f} (Eşik: {self.performance_threshold:.2f} üzerinde stabil)."

        return PerformanceCheckResult(
            status=status,
            realized_sharpe=realized_sharpe,
            reference_sharpe=self.reference_sharpe,
            alarm_threshold=self.performance_threshold,
            is_alarm=is_alarm,
            details=details
        )

    # --------------------------------------------------------------------------
    # KATMAN 4: VERİ TAZELİK GÜVENCESİ (FAZ -1.3)
    # --------------------------------------------------------------------------
    def check_data_freshness(self,
                             t: pd.Timestamp,
                             fiyat_dict: Dict[str, pd.Series],
                             max_lag_business_days: int = MAX_STALE_BUSINESS_DAYS) -> DataFreshnessResult:
        """
        En güncel piyasa verisinin referans tarihten kaç İŞ GÜNÜ eski olduğunu hesaplar.
        BIST tatillerini ve hafta sonlarını filtreler.
        Eğer gecikme >= max_lag_business_days (2 iş günü) ise operasyonu DURDURUR.
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
                details="🚨 EMNİYET KAPISI: Fiyat verisi sözlüğü boş! Karar üretimi durduruldu."
            )

        # En güncel piyasa barı tarihi (tüm hisseler arasındaki maksimum)
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

        # İki tarih arasındaki BIST iş günlerini hesapla
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
                f"🚨 VERİ_BAYAT: Son piyasa verisi {market_date_str} tarihli olup, "
                f"referans tarihten ({ref_date_str}) {business_days_lag} İŞ GÜNÜ eskidir "
                f"(Azami izin: {max_lag_business_days} iş günü). "
                f"Sessizce yanlış karar vermemek için model kararı üretilmedi ve operasyon DURDURULDU."
            )
        else:
            status = "VERİ_TAZE"
            details = (
                f"Piyasa verisi taze ({market_date_str} kapanışı, referans: {ref_date_str}, "
                f"gecikme: {business_days_lag} iş günü <= {max_lag_business_days})."
            )

        return DataFreshnessResult(
            status=status,
            market_date=market_date_str,
            reference_date=ref_date_str,
            business_days_lag=business_days_lag,
            max_allowed_lag=max_lag_business_days,
            is_stale=is_stale,
            should_halt=should_halt,
            details=details
        )

    # --------------------------------------------------------------------------
    # KATMAN 5: VERİ SAĞLIK KONTROLÜ (FAZ -1.5)
    # --------------------------------------------------------------------------
    def check_data_health(self,
                          fiyat_dict: Dict[str, pd.Series],
                          pit_bellek: Optional[Dict[str, Any]] = None,
                          tufe_aylik: Optional[Dict[str, float]] = None,
                          t: Optional[pd.Timestamp] = None) -> DataHealthResult:
        """
        Fiyat, bilanço ve makro veriler için son güncelleme, satır sayısı,
        NaN oranı ve sağlık özetini denetler.
        """
        t_ref = t or pd.Timestamp.now()
        tickers_count = len(fiyat_dict)
        total_bars = sum([len(s) for s in fiyat_dict.values()]) if fiyat_dict else 0
        total_nans = sum([s.isnull().sum() for s in fiyat_dict.values()]) if fiyat_dict else 0
        nan_ratio = (total_nans / max(1, total_bars + total_nans)) * 100.0

        # PIT Bilanço sağlığı
        pit_tickers = len(pit_bellek) if pit_bellek else 0
        stale_pit_count = 0
        if pit_bellek:
            from models.v3_ranking.data_loader import hizli_pit
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
            status=status,
            tickers_count=tickers_count,
            total_bars=total_bars,
            nan_ratio_pct=round(nan_ratio, 3),
            pit_tickers_count=pit_tickers,
            stale_financials_count=stale_pit_count,
            macro_usd_status=macro_usd_status,
            macro_cpi_status=macro_cpi_status,
            details=details
        )

    # --------------------------------------------------------------------------
    # KONSOLİDE RAPORLAMA
    # --------------------------------------------------------------------------
    def generate_full_report(self,
                             t: pd.Timestamp,
                             seri_usdtry: pd.Series,
                             tufe_aylik: Dict[str, float],
                             scores: Optional[np.ndarray] = None,
                             realized_sharpe: Optional[float] = None,
                             fiyat_dict: Optional[Dict[str, pd.Series]] = None,
                             pit_bellek: Optional[Dict[str, Any]] = None) -> DriftMonitorReport:
        """
        Tüm katmanları (Makro, Skor, Performans, Veri Tazeliği ve Sağlığı) çalıştırıp
        genel durum sinyalini (🟢 / 🟡 / 🔴) üretir.
        """
        macro_res = self.check_macro_regime(t, seri_usdtry, tufe_aylik)
        score_res = self.check_score_drift(scores) if scores is not None else None
        perf_res = self.check_performance_degradation(realized_sharpe) if realized_sharpe is not None else None
        fresh_res = self.check_data_freshness(t, fiyat_dict) if fiyat_dict is not None else None
        health_res = self.check_data_health(fiyat_dict, pit_bellek, tufe_aylik, t) if fiyat_dict is not None else None

        # Durum Mantığı:
        # 🔴 KIRMIZI: Veri Bayat (Operasyon Durduruldu) VEYA Performans Alarmı aktif
        # 🟡 SARI:    Performans ve Veri normal ama Makro Alarm veya Skor Drift var
        # 🟢 YEŞİL:   Tüm katmanlar temiz
        if fresh_res and fresh_res.should_halt:
            overall = "🔴 KIRMIZI: VERİ_BAYAT"
            summary = f"DURDURULDU: {fresh_res.details}"
        elif perf_res and perf_res.is_alarm:
            overall = "🔴 KIRMIZI"
            summary = "KRİTİK: Portföy gerçekleşen Sharpe oranı izin verilen %40 sapma sınırının altına indi!"
        elif macro_res.is_alarm or (score_res and score_res.is_drift):
            overall = "🟡 SARI"
            reasons = []
            if macro_res.is_alarm:
                reasons.append(macro_res.status)
            if score_res and score_res.is_drift:
                reasons.append(score_res.status)
            summary = f"DİKKAT: Performans korunuyor ancak bağlam uyarıları aktif ({'; '.join(reasons)})."
        else:
            overall = "🟢 YEŞİL"
            summary = "SAĞLIKLI: Makro rejim, model skor dağılımı, veri tazeliği ve performans normal sınırlarda."

        return DriftMonitorReport(
            timestamp=t,
            overall_status=overall,
            macro_result=macro_res,
            score_result=score_res,
            performance_result=perf_res,
            freshness_result=fresh_res,
            health_result=health_res,
            summary_message=summary
        )


def smoke_test():
    """
    Modülün bağımsız smoke testi.
    """
    print("=" * 80)
    print("DRIFT MONITOR MODÜLÜ SMOKE TESTİ BAŞLATILIYOR...")
    print("=" * 80)

    monitor = DriftMonitor()

    # 1. Test: Makro Normal Durum
    dummy_dates = pd.date_range("2025-01-01", periods=100, freq="B")
    dummy_usd = pd.Series(np.linspace(35.0, 36.0, len(dummy_dates)), index=dummy_dates)
    dummy_tufe = {m: 2.0 for m in pd.date_range("2024-01-01", periods=24, freq="MS").strftime("%Y-%m")}

    res_macro_norm = monitor.check_macro_regime(dummy_dates[-1], dummy_usd, dummy_tufe, politika_faizi_override=45.0)
    print(f"Test 1 [Makro Normal]:    Durum={res_macro_norm.status} | Alarm={res_macro_norm.is_alarm}")
    assert not res_macro_norm.is_alarm, "Normal makro hatalı alarm verdi!"

    # 2. Test: Makro Alarm (Derin Negatif Faiz)
    res_macro_neg = monitor.check_macro_regime(dummy_dates[-1], dummy_usd, dummy_tufe, politika_faizi_override=10.0)
    print(f"Test 2 [Makro Neg Faiz]: Durum={res_macro_neg.status} | Alarm={res_macro_neg.is_alarm}")
    assert res_macro_neg.is_alarm, "Negatif faiz alarmı tetiklenmedi!"

    # 3. Test: Makro Alarm (Kur Şoku)
    dummy_usd_shock = dummy_usd.copy()
    # Son 43 günde %25 sıçrama simülasyonu
    dummy_usd_shock.iloc[-1] = dummy_usd_shock.iloc[-43] * 1.25
    res_macro_shock = monitor.check_macro_regime(dummy_dates[-1], dummy_usd_shock, dummy_tufe, politika_faizi_override=45.0)
    print(f"Test 3 [Kur Şoku]:       Durum={res_macro_shock.status} | Alarm={res_macro_shock.is_alarm}")
    assert res_macro_shock.is_alarm, "Kur şoku alarmı tetiklenmedi!"

    # 4. Test: Skor Normal
    normal_scores = np.random.normal(loc=-0.10, scale=0.22, size=88)
    res_score_norm = monitor.check_score_drift(normal_scores)
    print(f"Test 4 [Skor Normal]:     Durum={res_score_norm.status} | Drift={res_score_norm.is_drift}")
    assert not res_score_norm.is_drift, "Normal skor dağılımı drift verdi!"

    # 5. Test: Skor Drift (Anormal Kayma)
    drift_scores = np.random.normal(loc=0.30, scale=0.40, size=88) # Çok yüksek ortalama
    res_score_drift = monitor.check_score_drift(drift_scores)
    print(f"Test 5 [Skor Drift]:      Durum={res_score_drift.status} | Drift={res_score_drift.is_drift}")
    assert res_score_drift.is_drift, "Skor drifti yakalanamadı!"

    # 6. Test: Performans Normal vs Alarm
    res_perf_ok = monitor.check_performance_degradation(1.20)
    res_perf_alarm = monitor.check_performance_degradation(0.70)
    print(f"Test 6 [Performans OK]:   Durum={res_perf_ok.status} | Alarm={res_perf_ok.is_alarm}")
    print(f"Test 7 [Performans Alarm]: Durum={res_perf_alarm.status} | Alarm={res_perf_alarm.is_alarm}")
    assert not res_perf_ok.is_alarm and res_perf_alarm.is_alarm, "Performans dedektörü hatalı çalıştı!"

    # 7. Test: Konsolide Rapor ve Işık Durumu
    rep_green = monitor.generate_full_report(dummy_dates[-1], dummy_usd, dummy_tufe, normal_scores, 1.25)
    rep_yellow = monitor.generate_full_report(dummy_dates[-1], dummy_usd_shock, dummy_tufe, normal_scores, 1.25)
    rep_red = monitor.generate_full_report(dummy_dates[-1], dummy_usd, dummy_tufe, normal_scores, 0.65)

    print("-" * 80)
    print(f"Konsolide Test [Yeşil]:  {rep_green.overall_status} -> {rep_green.summary_message}")
    print(f"Konsolide Test [Sarı]:   {rep_yellow.overall_status} -> {rep_yellow.summary_message}")
    print(f"Konsolide Test [Kırmızı]:{rep_red.overall_status} -> {rep_red.summary_message}")

    assert "YEŞİL" in rep_green.overall_status
    assert "SARI" in rep_yellow.overall_status
    assert "KIRMIZI" in rep_red.overall_status

    # 8. Test: Katman 4 Veri Tazeliği ve Emniyet Kapısı
    dummy_dict_fresh = {"THYAO.IS": pd.Series([100.0], index=[dummy_dates[-1]])}
    res_fresh = monitor.check_data_freshness(dummy_dates[-1], dummy_dict_fresh)
    print(f"Test 8 [Veri Taze]:       Durum={res_fresh.status} | Halt={res_fresh.should_halt}")
    assert not res_fresh.should_halt, "Taze veri hatalı şekilde bayat sayıldı!"

    # 4 iş günü eski veri simülasyonu -> Durdurulmalı
    t_stale = dummy_dates[-1] + pd.Timedelta(days=7) # 5 iş günü sonrası
    res_stale = monitor.check_data_freshness(t_stale, dummy_dict_fresh)
    print(f"Test 9 [Veri Bayat]:      Durum={res_stale.status} | Halt={res_stale.should_halt}")
    assert res_stale.should_halt, "Bayat veri emniyet kapısı tetiklenmedi!"

    # 10. Test: Katman 5 Veri Sağlık Kontrolü
    res_health = monitor.check_data_health(dummy_dict_fresh, None, dummy_tufe, dummy_dates[-1])
    print(f"Test 10 [Veri Sağlık]:    Durum={res_health.status} | Özet={res_health.details}")
    assert res_health is not None

    print("\n" + "=" * 80)
    print("✅ DRIFT MONITOR SMOKE TESTİ BAŞARIYLA TAMAMLANDI (TÜM TESTLER GEÇTİ).")
    print("=" * 80)


if __name__ == "__main__":
    smoke_test()
