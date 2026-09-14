"""
scripts/verify_data_integrity.py
================================
BIST QUANT PORTFÖYÜ: BAĞIMSIZ VERİ BÜTÜNLÜĞÜ VE KALİTE GÜVENCE DENETÇİSİ (CLI)
-------------------------------------------------------------------------------
İşlevler:
  1. data/raw/ ve data/fundamentals/ (veya data/pit/) dizinlerindeki 88 hisseyi tarar.
  2. Son piyasa tarihinde eksik veya geride kalmış hisseleri tespit eder (Tarih Hizalama).
  3. Mükerrer zaman damgalarını (duplicate index/bars) denetler.
  4. Sıfır veya negatif fiyat/hacim anomalilerini yakalar (open, high, low, close <= 0).
  5. Hatalı bölünme (unadjusted split) ve ekstrem getiri sıçramalarını (|günlük getiri| > %50) raporlar.
  6. PIT (Point-in-Time) mali tablo bütünlüğünü (çeyrek sayısı, çeyrek mükerrerliği, kritik boş değerler) inceler.
  7. Renkli konsol formatında (PASS / FAIL / WARN) özet tablo ve çıkış kodu (0 = Başarılı, 1 = Hata) üretir.

Kullanım:
  python scripts/verify_data_integrity.py
  python scripts/verify_data_integrity.py --verbose
  python scripts/verify_data_integrity.py --strict
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple

import pandas as pd
import numpy as np

# Proje Kök Dizini
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Windows UTF-8 ve ANSI Renk Desteği
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if os.name == "nt":
    os.system("")  # Windows ANSI renk kodlarını etkinleştir

import config as cfg

# ANSI Renk Kodları
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


class DataIntegrityAuditor:
    """BIST 88 Hisse ve Makro Veri Bütünlüğü Denetçisi."""

    def __init__(self, raw_dir: Path = None, pit_dir: Path = None, verbose: bool = False, strict: bool = False):
        self.raw_dir = raw_dir or (ROOT_DIR / "data" / "raw")
        
        # PIT dizini kontrolü (data/pit varsa onu, yoksa data/fundamentals kullan)
        default_pit = ROOT_DIR / "data" / "pit"
        if default_pit.exists() and default_pit.is_dir():
            self.pit_dir = pit_dir or default_pit
        else:
            self.pit_dir = pit_dir or (ROOT_DIR / "data" / "fundamentals")

        self.verbose = verbose
        self.strict = strict
        self.tickers = sorted(list(set(cfg.HISSELER)))
        self.macro_series = ["XU100_IS", "XUSIN_IS", "XBANK_IS", "TRY_X", "IDX_VIX"]

        self.results = {
            "tickers_total": len(self.tickers),
            "raw_checked": 0,
            "raw_passed": 0,
            "raw_failed": 0,
            "pit_checked": 0,
            "pit_passed": 0,
            "pit_failed": 0,
            "market_date": None,
            "errors": [],
            "warnings": [],
        }

    def _resolve_raw_path(self, ticker: str) -> Path:
        """Raw parquet dosya yolunu çözer (.IS / _IS uzantısı esnekliği)."""
        base = ticker.replace(".IS", "").replace(".is", "").replace("_IS", "")
        candidates = [
            self.raw_dir / f"{base}_IS.parquet",
            self.raw_dir / f"{base}.parquet",
            self.raw_dir / f"{ticker}.parquet"
        ]
        for c in candidates:
            if c.exists():
                return c
        return self.raw_dir / f"{base}_IS.parquet"

    def _resolve_pit_path(self, ticker: str) -> Path:
        """PIT fundamental parquet dosya yolunu çözer."""
        base = ticker.replace(".IS", "").replace(".is", "").replace("_IS", "")
        candidates = [
            self.pit_dir / f"{base}_IS.parquet",
            self.pit_dir / f"{base}.parquet",
            self.pit_dir / f"{ticker}.parquet"
        ]
        for c in candidates:
            if c.exists():
                return c
        return self.pit_dir / f"{base}_IS.parquet"

    def audit_raw_data(self) -> Dict[str, Any]:
        """Tüm hisseler ve endeksler için ham fiyat/hacim verilerini denetler."""
        print(f"\n{BOLD}{CYAN}1. HAM FİYAT & HACİM VERİ BÜTÜNLÜĞÜ DENETİMİ (data/raw){RESET}")
        print("-" * 80)

        # Referans piyasa tarihini bul (XU100 veya en yaygın son tarih)
        xu100_path = self._resolve_raw_path("XU100")
        max_market_date = None
        if xu100_path.exists():
            try:
                df_xu = pd.read_parquet(xu100_path)
                if not df_xu.empty:
                    max_market_date = df_xu.index[-1].strftime("%Y-%m-%d") if hasattr(df_xu.index[-1], "strftime") else str(df_xu.index[-1])[:10]
            except Exception:
                pass

        self.results["market_date"] = max_market_date
        print(f"📌 Referans Piyasa Kapanış Tarihi (XU100): {BOLD}{max_market_date or 'Bilinmiyor'}{RESET}")

        ticker_issues = {}

        for ticker in self.tickers:
            self.results["raw_checked"] += 1
            issues = []
            warnings = []
            fpath = self._resolve_raw_path(ticker)

            if not fpath.exists():
                issues.append("Dosya bulunamadı (EKSİK PARQUET)")
                ticker_issues[ticker] = {"issues": issues, "warnings": warnings}
                self.results["raw_failed"] += 1
                continue

            try:
                df = pd.read_parquet(fpath)
            except Exception as e:
                issues.append(f"Parquet okuma hatası: {e}")
                ticker_issues[ticker] = {"issues": issues, "warnings": warnings}
                self.results["raw_failed"] += 1
                continue

            if df.empty:
                issues.append("Veri seti tamamen boş (0 satır)")
                ticker_issues[ticker] = {"issues": issues, "warnings": warnings}
                self.results["raw_failed"] += 1
                continue

            # 1. Tarih Hizalama ve Son Tarih Kontrolü
            last_date_str = df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], "strftime") else str(df.index[-1])[:10]
            if max_market_date and last_date_str != max_market_date:
                # Fark kaç gün?
                try:
                    d_ref = datetime.strptime(max_market_date, "%Y-%m-%d")
                    d_cur = datetime.strptime(last_date_str, "%Y-%m-%d")
                    diff_days = (d_ref - d_cur).days
                    if diff_days >= 2:
                        issues.append(f"Son tarih {last_date_str} (Piyasa {max_market_date}'den {diff_days} gün geride - BAYAT VERİ)")
                    else:
                        warnings.append(f"Son tarih {last_date_str} (Piyasa: {max_market_date})")
                except Exception:
                    warnings.append(f"Tarih uyuşmazlığı ({last_date_str} vs {max_market_date})")

            # 2. Duplicate Zaman Damgası Kontrolü
            if df.index.duplicated().any():
                dup_count = df.index.duplicated().sum()
                issues.append(f"{dup_count} adet mükerrer zaman damgası (duplicate index)")

            # 3. Sıfır veya Negatif Fiyat Kontrolü
            price_cols = [col for col in ["open", "high", "low", "close"] if col in df.columns]
            for col in price_cols:
                invalid_prices = (df[col] <= 0).sum()
                if invalid_prices > 0:
                    issues.append(f"{col} sütununda {invalid_prices} adet sıfır veya negatif fiyat")

            # 4. Mantıksal Bar Tutarlılığı (High >= Low, vb.)
            if "high" in df.columns and "low" in df.columns:
                inconsistent_bars = (df["high"] < df["low"]).sum()
                if inconsistent_bars > 0:
                    issues.append(f"{inconsistent_bars} adet barda High < Low tutarsızlığı")

            # 5. Negatif Hacim Kontrolü
            if "volume" in df.columns:
                neg_vol = (df["volume"] < 0).sum()
                if neg_vol > 0:
                    issues.append(f"{neg_vol} adet barda negatif hacim")

            # 6. Aşırı Anormal Getiri Sıçraması (Hatalı Bölünme / Split Uyuşmazlığı)
            if "close" in df.columns and len(df) > 1:
                ret = df["close"].pct_change().dropna()
                # Günlük %50'den büyük sıçrama veya düşüş BIST tavan/taban sınırını aşar (bölünme hatası şüphesi)
                extreme_jumps = ret[(ret > 0.50) | (ret < -0.50)]
                if not extreme_jumps.empty:
                    for jump_date, val in extreme_jumps.tail(2).items():
                        j_str = jump_date.strftime("%Y-%m-%d") if hasattr(jump_date, "strftime") else str(jump_date)[:10]
                        warnings.append(f"Anormal getiri sıçraması: {j_str} tarihinde %{val*100:+.1f} (Split düzeltme kontrolü gerekebilir)")

            # Sonuç değerlendirme
            if issues:
                self.results["raw_failed"] += 1
                ticker_issues[ticker] = {"issues": issues, "warnings": warnings}
            else:
                self.results["raw_passed"] += 1
                if warnings:
                    ticker_issues[ticker] = {"issues": [], "warnings": warnings}

        # Endeks ve Makro Dosyaları Denetimi
        print(f"\n{BOLD}Makro ve Endeks Dosyaları Doğrulaması:{RESET}")
        for m in self.macro_series:
            m_path = self.raw_dir / f"{m}.parquet"
            if m_path.exists():
                try:
                    m_df = pd.read_parquet(m_path)
                    m_last = m_df.index[-1].strftime("%Y-%m-%d") if hasattr(m_df.index[-1], "strftime") else str(m_df.index[-1])[:10]
                    print(f"  • {m:<12}: {GREEN}OK{RESET} ({len(m_df)} bar, Son: {m_last})")
                except Exception as e:
                    print(f"  • {m:<12}: {RED}FAIL{RESET} (Hata: {e})")
                    self.results["errors"].append(f"Makro {m} okunamadı: {e}")
            else:
                print(f"  • {m:<12}: {YELLOW}EKSİK{RESET} (Dosya yok)")
                self.results["warnings"].append(f"Makro seri {m}.parquet bulunamadı")

        return ticker_issues

    def audit_pit_fundamentals(self) -> Dict[str, Any]:
        """Tüm hisseler için Point-in-Time (PIT) mali tablo verilerini denetler."""
        print(f"\n{BOLD}{CYAN}2. POINT-IN-TIME (PIT) MALİ TABLO BÜTÜNLÜĞÜ DENETİMİ ({self.pit_dir.name}){RESET}")
        print("-" * 80)

        pit_issues = {}

        if not self.pit_dir.exists():
            err = f"PIT dizini bulunamadı: {self.pit_dir}"
            print(f"{RED}❌ {err}{RESET}")
            self.results["errors"].append(err)
            return pit_issues

        for ticker in self.tickers:
            self.results["pit_checked"] += 1
            issues = []
            warnings = []
            fpath = self._resolve_pit_path(ticker)

            if not fpath.exists():
                issues.append("PIT Fundamental dosyası eksik")
                pit_issues[ticker] = {"issues": issues, "warnings": warnings}
                self.results["pit_failed"] += 1
                continue

            try:
                df = pd.read_parquet(fpath)
            except Exception as e:
                issues.append(f"PIT Parquet okuma hatası: {e}")
                pit_issues[ticker] = {"issues": issues, "warnings": warnings}
                self.results["pit_failed"] += 1
                continue

            if df.empty:
                issues.append("PIT tablosu tamamen boş (0 çeyrek)")
                pit_issues[ticker] = {"issues": issues, "warnings": warnings}
                self.results["pit_failed"] += 1
                continue

            # 1. Asgari Çeyrek Sayısı (En az 4 çeyrek olmalı)
            quarter_count = len(df)
            if quarter_count < 4:
                warnings.append(f"Yetersiz çeyrek geçmişi ({quarter_count} çeyrek < 4)")

            # 2. Mükerrer Çeyrek Kontrolü
            if "ceyrek" in df.columns:
                dup_q = df["ceyrek"].duplicated().sum()
                if dup_q > 0:
                    issues.append(f"{dup_q} adet mükerrer çeyrek kaydı")

            # 3. Geçerlilik Tarihi (PIT Eşitleme) Kontrolü
            if "gecerlilik_tarihi" in df.columns:
                null_dates = df["gecerlilik_tarihi"].isna().sum()
                if null_dates > 0:
                    issues.append(f"{null_dates} çeyrekte gecerlilik_tarihi tanımsız (NaN)")

            # 4. Kritik Finansal Değişken Boşluk Kontrolü
            for col in ["ozkaynaklar", "net_kar", "satislar"]:
                if col in df.columns:
                    nan_count = df[col].isna().sum()
                    if nan_count > quarter_count * 0.5:
                        warnings.append(f"{col} kolonunda yüksek oranda NaN ({nan_count}/{quarter_count})")

            if issues:
                self.results["pit_failed"] += 1
                pit_issues[ticker] = {"issues": issues, "warnings": warnings}
            else:
                self.results["pit_passed"] += 1
                if warnings:
                    pit_issues[ticker] = {"issues": [], "warnings": warnings}

        return pit_issues

    def print_summary(self, raw_issues: Dict[str, Any], pit_issues: Dict[str, Any]) -> int:
        """Denetim sonuçlarını renkli ve yapılandırılmış konsol tablosu olarak sunar."""
        print(f"\n{BOLD}{'=' * 80}{RESET}")
        print(f"{BOLD}📊 VERİ BÜTÜNLÜĞÜ VE SAĞLIK DENETİM RAPORU (GENEL ÖZET){RESET}")
        print(f"{'=' * 80}")

        # Raw Tablosu
        print(f"Toplam Takip Edilen Hisse Sayısı : {self.results['tickers_total']}")
        print(f"Piyasa Referans Kapanış Tarihi   : {self.results['market_date'] or 'Bilinmiyor'}")
        print(f"Fiyat/Hacim Parquet Başarı Oranı : {GREEN if self.results['raw_failed'] == 0 else RED}{self.results['raw_passed']}/{self.results['raw_checked']} PASS{RESET}")
        print(f"PIT Fundamental Başarı Oranı     : {GREEN if self.results['pit_failed'] == 0 else RED}{self.results['pit_passed']}/{self.results['pit_checked']} PASS{RESET}")

        # Hatalı veya Uyarılı Hisselerin Dökümü
        all_problematic = sorted(list(set(list(raw_issues.keys()) + list(pit_issues.keys()))))
        
        has_critical_error = False

        if all_problematic:
            print(f"\n{BOLD}🔍 DİKKAT GEREKTİREN HİSSELER VE TESPİTLER:{RESET}")
            for t in all_problematic:
                r_info = raw_issues.get(t, {"issues": [], "warnings": []})
                p_info = pit_issues.get(t, {"issues": [], "warnings": []})

                crit_issues = r_info.get("issues", []) + p_info.get("issues", [])
                warns = r_info.get("warnings", []) + p_info.get("warnings", [])

                if crit_issues:
                    has_critical_error = True
                    print(f"  • {BOLD}{RED}[FAIL] {t:<10}{RESET}")
                    for iss in crit_issues:
                        print(f"      {RED}✗ HATA:{RESET} {iss}")
                elif self.verbose or warns:
                    print(f"  • {BOLD}{YELLOW}[WARN] {t:<10}{RESET}")
                
                if self.verbose:
                    for w in warns:
                        print(f"      {YELLOW}! UYARI:{RESET} {w}")

        print(f"\n{'-' * 80}")
        if not has_critical_error and self.results["raw_failed"] == 0 and self.results["pit_failed"] == 0:
            print(f"{BOLD}{GREEN}✅ [PASS] TÜM BÜTÜNLÜK TESTLERİ GEÇTİ.{RESET}")
            print(f"{BOLD}{GREEN}   SİSTEM KURUMSAL ZIRHLA KORUNMAKTADIR (Tarih, Bar, Değer & PIT Sağlam).{RESET}")
            print(f"{'=' * 80}\n")
            return 0
        else:
            print(f"{BOLD}{RED}❌ [FAIL] KRİTİK VERİ BÜTÜNLÜĞÜ HATASI TESPİT EDİLDİ.{RESET}")
            print(f"{BOLD}{RED}   Lütfen yukarıdaki hatalı hisse/tarih verilerini düzeltiniz.{RESET}")
            print(f"{'=' * 80}\n")
            return 1 if self.strict else 0


def main():
    parser = argparse.ArgumentParser(description="BIST Quant Bağımsız Veri Bütünlüğü ve Kalite Denetçisi")
    parser.add_argument("--raw-dir", type=Path, default=None, help="Ham veri dizini (varsayılan: data/raw)")
    parser.add_argument("--pit-dir", type=Path, default=None, help="PIT veri dizini (varsayılan: data/fundamentals veya data/pit)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Detaylı uyarıları ve açıklamaları ekrana bas")
    parser.add_argument("--strict", action="store_true", help="Hata durumunda exit code 1 ile çık (CI/CD / Seans Öncesi Otomasyonu)")
    args = parser.parse_args()

    auditor = DataIntegrityAuditor(
        raw_dir=args.raw_dir,
        pit_dir=args.pit_dir,
        verbose=args.verbose,
        strict=args.strict
    )

    raw_issues = auditor.audit_raw_data()
    pit_issues = auditor.audit_pit_fundamentals()
    exit_code = auditor.print_summary(raw_issues, pit_issues)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
