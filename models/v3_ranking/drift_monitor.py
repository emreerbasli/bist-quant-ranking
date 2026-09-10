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
class DriftMonitorReport:
    timestamp: pd.Timestamp
    overall_status: str     # "🟢 YEŞİL", "🟡 SARI", "🔴 KIRMIZI"
    macro_result: MacroCheckResult
    score_result: Optional[ScoreDriftResult]
    performance_result: Optional[PerformanceCheckResult]
    summary_message: str


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
    # KONSOLİDE RAPORLAMA
    # --------------------------------------------------------------------------
    def generate_full_report(self,
                             t: pd.Timestamp,
                             seri_usdtry: pd.Series,
                             tufe_aylik: Dict[str, float],
                             scores: Optional[np.ndarray] = None,
                             realized_sharpe: Optional[float] = None) -> DriftMonitorReport:
        """
        Üç katmanın tamamını çalıştırıp genel durum sinyalini (🟢 / 🟡 / 🔴) üretir.
        """
        macro_res = self.check_macro_regime(t, seri_usdtry, tufe_aylik)
        score_res = self.check_score_drift(scores) if scores is not None else None
        perf_res = self.check_performance_degradation(realized_sharpe) if realized_sharpe is not None else None

        # Durum Mantığı:
        # 🔴 KIRMIZI: Performans Alarmı aktif
        # 🟡 SARI:    Performans normal ama Makro Alarm veya Skor Drift var
        # 🟢 YEŞİL:   Tüm katmanlar temiz
        if perf_res and perf_res.is_alarm:
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
            summary = "SAĞLIKLI: Makro rejim, model skor dağılımı ve gerçekleşen performans normal sınırlarda."

        return DriftMonitorReport(
            timestamp=t,
            overall_status=overall,
            macro_result=macro_res,
            score_result=score_res,
            performance_result=perf_res,
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

    print("\n" + "=" * 80)
    print("✅ DRIFT MONITOR SMOKE TESTİ BAŞARIYLA TAMAMLANDI (TÜM TESTLER GEÇTİ).")
    print("=" * 80)


if __name__ == "__main__":
    smoke_test()
