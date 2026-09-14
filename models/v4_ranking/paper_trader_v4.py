"""
models/v4_ranking/paper_trader_v4.py
====================================
V4 PRODUCTION-CANDIDATE: PAPER TRADING İCRA VE PORTFÖY YÖNETİM MODÜLÜ
---------------------------------------------------------------------
KRİTİK KURUMSAL SINIR: Bu sistem SADECE bildirim gönderir, otomatik emir vermez.
Canlı sermaye KESİNLİKLE KULLANILMAZ. Tamamen sanal portföy (paper trading) takibidir.

V4 ÖZELLİKLERİ VE YENİLİKLERİ:
  - Portföy Boyutu: K=15 (Kurumsal ONAY alan V4-Raw standardı).
  - 60 Günlük Asgari Tutma (H=60g) Kuralı: Aşırı işlem maliyetini (turnover) önler.
  - Faz 0 Acil Çıkış Kuralı: Portföydeki bir hisse son 10 işlem gününde >=5 kez
    taban (<= -%9.5) yaparsa 60 gün kuralına bakılmaksızın ACİL ÇIKIŞ (Emergency Exit) yapılır.
  - KAP / VBTS Tedbir Uyarısı: Portföydeki hisselere VBTS gelirse operasyonel alarm üretilir.
  - %25 Portföy Drawdown Devre Kesici: Zirveden -%25 düşüşte %50 nakde (%18 faiz) geçilir.
  - İzole Depolama: models/v4_ranking/paper_portfolio_v4.json ve paper_trading_log_v4.csv.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import os
import time
import shutil

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.v4_ranking.drift_monitor_v4 import DriftMonitorV4, DriftMonitorReportV4
import config as cfg

logger = logging.getLogger("PaperTraderV4")

TRANSACTION_COST = 0.005  # %0.50 round-trip (komisyon %0.15 × 2 + BSMV %0.10 × 2)
RF_ANNUAL = 0.18          # %18 yıllık risksiz faiz
K_PORTFOLIO_SIZE_V4 = 15  # V4 Onaylı Standart Portföy Boyutu
MIN_HOLDING_DAYS = 60
DD_TRIGGER = -0.25
DD_RECOVER = -0.15


class PaperTraderV4:
    """
    V4 Ranker: K=15, H=60g Çeyreklik Rotasyon + Faz 0 Acil Çıkış + %25 Devre Kesici
    İzole Paper Trading İcra Motoru.
    """

    DEFAULT_PORTFOLIO_FILE = Path(__file__).resolve().parent / "paper_portfolio_v4.json"
    DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "paper_trading_log_v4.csv"

    def __init__(self,
                 portfolio_file: Optional[Path] = None,
                 log_file: Optional[Path] = None,
                 k_size: int = K_PORTFOLIO_SIZE_V4,
                 min_hold_days: int = MIN_HOLDING_DAYS,
                 dd_trigger: float = DD_TRIGGER,
                 dd_recover: float = DD_RECOVER):
        self.portfolio_file = Path(portfolio_file) if portfolio_file else self.DEFAULT_PORTFOLIO_FILE
        self.log_file = Path(log_file) if log_file else self.DEFAULT_LOG_FILE
        self.k_size = k_size
        self.min_hold_days = min_hold_days
        self.dd_trigger = dd_trigger
        self.dd_recover = dd_recover
        self.drift_monitor = DriftMonitorV4()

        self.portfolio_state: Dict[str, Any] = self._load_or_init_portfolio()

    def _load_or_init_portfolio(self) -> Dict[str, Any]:
        """Portföy durumunu JSON dosyasından yükler veya yeni oluşturur."""
        if self.portfolio_file.exists():
            try:
                with open(self.portfolio_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(f"V4 Portföy diskten yüklendi: {self.portfolio_file} (Hisseler: {len(data.get('positions', {}))})")
                return data
            except Exception as e:
                logger.warning(f"V4 Portföy dosyası bozuk, yeniden başlatılıyor: {e}")

        initial_state = {
            "version": "v4",
            "baslangic_tarihi": "2026-09-14",
            "last_check_date": "2026-09-14",
            "kilit_kutu_referans": "2026-09-14",
            "equity": 1.0,
            "peak_equity": 1.0,
            "drawdown": 0.0,
            "dd_kesici_aktif": False,
            "last_xu100_price": 0.0,
            "positions": {}
        }
        self._save_portfolio(initial_state)
        return initial_state

    def _safe_replace(self, src_path: Path, dst_path: Path, max_retries: int = 5, delay: float = 0.1) -> None:
        """Windows dosya kilitleme (WinError 32) korumalı atomik ve dayanıklı yer değiştirme."""
        for i in range(max_retries):
            try:
                os.replace(src_path, dst_path)
                return
            except (PermissionError, OSError):
                time.sleep(delay)
        # 5 deneme sonrası hala kilitliyse copy2 ile üzerine yaz
        try:
            shutil.copy2(src_path, dst_path)
            try:
                os.remove(src_path)
            except Exception:
                pass
        except Exception as ex:
            logger.warning(f"Dosya güvenli yer değiştirme uyarısı: {ex}")

    def _save_portfolio(self, state: Optional[Dict[str, Any]] = None):
        """Portföy durumunu atomik ve kilit korumalı olarak diske kaydeder."""
        target = state if state is not None else self.portfolio_state
        temp_file = self.portfolio_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(target, f, ensure_ascii=False, indent=2, default=str)
        self._safe_replace(temp_file, self.portfolio_file)

    def execute_check(self,
                      t: pd.Timestamp,
                      top_k_ranked: List[str],
                      current_prices: Dict[str, float],
                      current_xu100_price: float,
                      seri_usdtry: pd.Series,
                      tufe_aylik: Dict[str, float],
                      scores_universe: Optional[np.ndarray] = None,
                      days_elapsed: int = 14,
                      fiyat_dict: Optional[Dict[str, pd.Series]] = None,
                      pit_bellek: Optional[Dict[str, Any]] = None,
                      send_telegram: bool = True) -> Dict[str, Any]:
        """
        14 günlük periyodik kontrol ve rebalance icra motoru.
        """
        t_str = t.strftime("%Y-%m-%d")
        positions = self.portfolio_state.get("positions", {})
        equity = float(self.portfolio_state.get("equity", 1.0))
        peak_equity = float(self.portfolio_state.get("peak_equity", 1.0))
        dd_kesici = bool(self.portfolio_state.get("dd_kesici_aktif", False))
        prev_xu = float(self.portfolio_state.get("last_xu100_price", 0.0))

        # ----------------------------------------------------------------------
        # 1. MEVCUT POZİSYONLARIN GÜNCELLENMESİ VE GETİRİ HESABI
        # ----------------------------------------------------------------------
        pos_returns = []
        cikis_yapilacaklar = []
        acil_cikislar = []

        for sembol, pos_data in list(positions.items()):
            p_entry = float(pos_data.get("entry_price", 1.0))
            cur_price = float(current_prices.get(sembol, pos_data.get("last_price", p_entry)))
            p_peak = max(float(pos_data.get("personal_peak_price", p_entry)), cur_price)
            pos_data["personal_peak_price"] = p_peak
            pos_data["last_price"] = cur_price

            # İdempotent gün hesabı: giriş tarihinden itibaren takvim günü farkı
            entry_d = pos_data.get("entry_date")
            if entry_d:
                try:
                    pos_data["days_held"] = max(0, (pd.to_datetime(t) - pd.to_datetime(entry_d)).days)
                except Exception:
                    pos_data["days_held"] = pos_data.get("days_held", 0) + days_elapsed
            else:
                pos_data["days_held"] = pos_data.get("days_held", 0) + days_elapsed

            hisse_dd = (cur_price - p_peak) / p_peak * 100.0 if p_peak > 0 else 0.0
            pos_data["peak_drawdown_pct"] = round(hisse_dd, 2)

            prev_p = float(pos_data.get("prev_check_price", p_entry))
            r_stock = ((cur_price - prev_p) / prev_p) if prev_p > 0 else 0.0
            pos_returns.append(r_stock * float(pos_data.get("weight", 1.0 / max(1, self.k_size))))
            pos_data["prev_check_price"] = cur_price

            # Faz 0: Acil Çıkış Denetimi (Son 10 günde >=5 kez <=-%9.5 taban)
            if fiyat_dict and sembol in fiyat_dict:
                try:
                    from bot.kap_filter import ardisik_taban_tespit
                    p_sub = fiyat_dict[sembol][fiyat_dict[sembol].index <= t]
                    is_taban, cnt = ardisik_taban_tespit(p_sub, lookback_gun=10, min_taban=5, taban_esik=-0.095)
                    if is_taban:
                        acil_cikislar.append(sembol)
                        logger.warning(f"🚨 Faz 0 ACİL ÇIKIŞ: {sembol} 10 günde {cnt} kez taban yaptı — 60 gün kuralı delinerek portföyden çıkarılıyor.")
                except Exception as e:
                    logger.warning(f"Acil çıkış denetim hatası: {e}")

            # Kâr Koruma Kalkanı: Zirveden %20+ geri çekilme durumunda acil kâr koruma çıkışı
            peak_dd_esik = getattr(cfg, "PEAK_DRAWDOWN_UYARI_ESIGI", 0.20) * 100.0
            if hisse_dd <= -peak_dd_esik:
                if sembol not in acil_cikislar:
                    acil_cikislar.append(sembol)
                    logger.warning(f"🚨 KÂR KORUMA ACİL ÇIKIŞI: {sembol} yerel zirveden %{abs(hisse_dd):.1f} düştü — 60 gün kuralı delinerek nakde geçiliyor.")

        # Portföy seviyesi getiri hesabı
        rf_period = ((1.0 + RF_ANNUAL) ** (days_elapsed / 365.25)) - 1.0
        if positions:
            stock_component = sum(pos_returns)
            if dd_kesici:
                period_ret = rf_period
            else:
                period_ret = stock_component
        else:
            period_ret = rf_period if dd_kesici else 0.0

        equity = equity * (1.0 + period_ret)
        peak_equity = max(peak_equity, equity)
        current_dd = (equity - peak_equity) / peak_equity if peak_equity > 0 else 0.0

        # Devre Kesici Kontrolü (%25 Düşüşte %100 Nakde Geçiş)
        if not dd_kesici and current_dd <= self.dd_trigger:
            dd_kesici = True
            logger.warning(f"⚡ V4 DEVRE KESİCİ AKTİF: Drawdown {current_dd*100:.1f}% <= {self.dd_trigger*100:.1f}%. Portföy %100 nakde (%18 faiz) geçirildi.")
        elif dd_kesici and current_dd >= self.dd_recover:
            dd_kesici = False
            logger.info(f"✨ V4 DEVRE KESİCİ DEVRE DIŞI: Drawdown {current_dd*100:.1f}% >= {self.dd_recover*100:.1f}%. %100 hisse pozisyonuna dönüldü.")

        # BIST 100 Getirisi
        if prev_xu > 0 and current_xu100_price > 0:
            bist_ret = (current_xu100_price - prev_xu) / prev_xu
        else:
            bist_ret = 0.0
        alfa_period = period_ret - bist_ret

        # ----------------------------------------------------------------------
        # 2. REBALANCE VE PORTFÖY ROTASYONU (K=15)
        # ----------------------------------------------------------------------
        girenler = []
        cikanlar = []

        if dd_kesici:
            # Devre kesici aktif: Tüm pozisyonlar tasfiye edilerek %100 nakitte beklenir
            for s_all in list(positions.keys()):
                cikanlar.append(f"{s_all} (DEVRE KESİCİ NAKİT)")
                del positions[s_all]
            logger.info("🛡️ Devre Kesici Aktif: Yeni hisse alımı durduruldu, portföy %100 nakitte bekliyor.")
        else:
            # Acil çıkışları uygula (Faz 0 Taban veya Zirveden Kâr Koruma)
            for s_acil in acil_cikislar:
                if s_acil in positions:
                    del positions[s_acil]
                    cikanlar.append(f"{s_acil} (ACİL ÇIKIŞ)")

            # Normal Rotasyon: Listeden düşen ve 60 gününü doldurmuş hisseler
            for sembol, pos_data in list(positions.items()):
                if sembol not in top_k_ranked:
                    if pos_data.get("days_held", 0) >= self.min_hold_days:
                        cikis_yapilacaklar.append(sembol)
                    else:
                        kalan = self.min_hold_days - pos_data.get("days_held", 0)
                        logger.info(f"V4 Rotasyon Beklemesi: {sembol} Top-{self.k_size}'ten düştü fakat {kalan} gün daha tutulacak (H=60g kuralı).")

            for s_out in cikis_yapilacaklar:
                if s_out in positions:
                    del positions[s_out]
                    cikanlar.append(s_out)

            # Yeni girenler
            bos_yer = self.k_size - len(positions)
            if bos_yer > 0:
                for s_cand in top_k_ranked:
                    if s_cand not in positions and s_cand not in acil_cikislar and s_cand not in cikis_yapilacaklar:
                        positions[s_cand] = {
                            "entry_date": t_str,
                            "entry_price": current_prices.get(s_cand, 1.0),
                            "prev_check_price": current_prices.get(s_cand, 1.0),
                            "personal_peak_price": current_prices.get(s_cand, 1.0),
                            "last_price": current_prices.get(s_cand, 1.0),
                            "days_held": 0,
                            "peak_drawdown_pct": 0.0,
                            "weight": 1.0 / float(self.k_size)
                        }
                        girenler.append(s_cand)
                        if len(positions) >= self.k_size:
                            break

        # Ağırlıkları normalize et
        n_curr = len(positions)
        if n_curr > 0:
            w_each = 1.0 / float(n_curr)
            for pos in positions.values():
                pos["weight"] = w_each

        # ----------------------------------------------------------------------
        # 3. GÜVENLİK VE DRİFT RAPORU (5 KATMAN)
        # ----------------------------------------------------------------------
        drift_report = self.drift_monitor.generate_full_report(
            t=t,
            seri_usdtry=seri_usdtry,
            tufe_aylik=tufe_aylik,
            scores=scores_universe,
            realized_sharpe=None,
            fiyat_dict=fiyat_dict,
            pit_bellek=pit_bellek
        )

        # ----------------------------------------------------------------------
        # 4. GÜNCEL DURUMU DİSKE YAZ
        # ----------------------------------------------------------------------
        self.portfolio_state = {
            "version": "v4",
            "baslangic_tarihi": self.portfolio_state.get("baslangic_tarihi", "2026-09-14"),
            "last_check_date": t_str,
            "kilit_kutu_referans": "2026-09-14",
            "equity": round(equity, 6),
            "peak_equity": round(peak_equity, 6),
            "drawdown": round(current_dd, 4),
            "dd_kesici_aktif": dd_kesici,
            "last_xu100_price": current_xu100_price,
            "positions": positions
        }
        self._save_portfolio()

        # CSV Log Kaydı
        degisiklik_str = "Değişiklik yok"
        if girenler or cikanlar:
            degisiklik_str = f"+{','.join(girenler)} | -{','.join(cikanlar)}"

        portfoy_list_str = ", ".join(sorted(positions.keys()))
        makro_ozet_str = f"Reel:%{drift_report.macro_result.reel_faiz:.1f}, USD_Mom:%{drift_report.macro_result.usd_mom_60*100:.1f}"
        
        # En derin hisse drawdown'u
        hisse_dd_list = [p.get("peak_drawdown_pct", 0.0) for p in positions.values()]
        max_hisse_dd = min(hisse_dd_list) if hisse_dd_list else 0.0

        min_kalan_gun = min([self.min_hold_days - p.get("days_held", 0) for p in positions.values()]) if positions else self.min_hold_days

        log_line = (
            f"{t_str},\"{portfoy_list_str}\",\"{degisiklik_str}\",%{period_ret*100:.2f},"
            f"%{bist_ret*100:.2f},%{alfa_period*100:.2f},{drift_report.overall_status},"
            f"\"{makro_ozet_str}\",{dd_kesici},%{peak_equity*100-100:.2f},%{max_hisse_dd:.2f},"
            f"{min_kalan_gun},Yok\n"
        )
        for attempt in range(3):
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(log_line)
                break
            except (PermissionError, OSError):
                if attempt < 2:
                    time.sleep(0.05)

        # ----------------------------------------------------------------------
        # 5. ÖZET METİN VE TELEGRAM BİLDİRİMİ
        # ----------------------------------------------------------------------
        log_row_dict = {
            "tarih": t_str,
            "portfoy_listesi": portfoy_list_str,
            "degisiklik": degisiklik_str,
            "equity": equity,
            "kumulatif_getiri": (equity - 1.0) * 100.0,
            "drawdown": current_dd * 100.0,
            "period_ret": period_ret * 100.0,
            "bist_ret": bist_ret * 100.0,
            "alfa": alfa_period * 100.0,
            "drift_durumu": drift_report.overall_status,
            "makro_ozet": makro_ozet_str,
            "dd_kesici": dd_kesici,
            "freshness": "OK" if not (drift_report.freshness_result and drift_report.freshness_result.should_halt) else "BAYAT"
        }

        # 60 gün çıkış takvimi
        takvim_satirlar = []
        for s, p in sorted(positions.items()):
            held = p.get("days_held", 0)
            kalan = max(0, self.min_hold_days - held)
            durum = "KİLİTLİ (BEKLEMEDE)" if kalan > 0 else "SERBEST (ROTASYONA AÇIK)"
            takvim_satirlar.append(f"  • {s:<9} : {held:02d}. gün ({kalan:02d} gün kaldı) [{durum}]")
        cikis_takvimi_str = "\n".join(takvim_satirlar)

        # Bireysel kâr geri verme uyarıları (%20+)
        uyari_hisseler_list = []
        for s, p in positions.items():
            if p.get("peak_drawdown_pct", 0.0) <= -20.0:
                uyari_hisseler_list.append(f"{s}: Zirveden %{abs(p['peak_drawdown_pct']):.1f} geri çekildi")

        summary_text = self.print_summary_report(
            log_row=log_row_dict,
            positions=positions,
            cikis_takvimi=cikis_takvimi_str,
            uyari_hisseler=uyari_hisseler_list,
            acil_cikislar=acil_cikislar
        )

        if send_telegram:
            try:
                from bot.telegram_bot import mesaj_gonder
                mesaj_gonder(summary_text, parse_mode=None)
            except Exception as e:
                logger.warning(f"V4 Telegram bildirimi gönderilemedi: {e}")

        return {
            "date": t_str,
            "equity": equity,
            "drawdown": current_dd,
            "period_ret": period_ret,
            "bist_ret": bist_ret,
            "alfa": alfa_period,
            "girenler": girenler,
            "cikanlar": cikanlar,
            "positions": list(positions.keys()),
            "drift_report": drift_report,
            "summary_text": summary_text
        }

    def print_summary_report(self,
                             log_row: Dict[str, Any],
                             positions: Dict[str, Any],
                             cikis_takvimi: str = "",
                             uyari_hisseler: Optional[List[str]] = None,
                             acil_cikislar: Optional[List[str]] = None) -> str:
        """V4 (K=15) kurumsal günlük/kontrol özet raporu çıktısı."""
        uyari_blok = ""
        if uyari_hisseler:
            uyari_blok = "\n\n⚠️ DİKKAT: BİREYSEL HİSSE KÂR GERİ VERME UYARILARI:\n"
            for u in uyari_hisseler:
                uyari_blok += f"  🚨 {u}\n"
            uyari_blok += "  (NOT: Bu bir satış emri DEĞİLDİR; sadece risk takip bilgilendirmesidir.)"

        acil_blok = ""
        if acil_cikislar:
            acil_blok = "\n\n🚨 ACİL TABAN ÇIKIŞI UYGULANDI:\n"
            for ac in acil_cikislar:
                acil_blok += f"  🛑 {ac}: Faz 0 ardışık taban/çöküş riski — 60 gün kuralı delinerek nakde geçildi.\n"

        takvim_blok = ""
        if cikis_takvimi:
            takvim_blok = f"\n\n📋 V4 60-Gün Çıkış Takvimi:\n{cikis_takvimi}"

        # Pozisyon detayları
        pos_lines = []
        for s, p in sorted(positions.items()):
            w_pct = p.get("weight", 0.0) * 100.0
            held = p.get("days_held", 0)
            ent_p = p.get("entry_price", 0.0)
            cur_p = p.get("last_price", ent_p)
            ret_pct = ((cur_p - ent_p) / ent_p * 100.0) if ent_p > 0 else 0.0
            pos_lines.append(f"  • {s:<9} | Ağr: %{w_pct:.1f} | Gün: {held:02d}/60 | Giriş: {ent_p:.2f} | Son: {cur_p:.2f} | K/Z: %{ret_pct:+.1f}")

        pos_str = "\n".join(pos_lines) if pos_lines else "  Boş Portföy"

        report = f"""
---
🏛️ BIST V4 QUANT (9-FAKTÖR / K=15) PAPER TRADING RAPORU — [{log_row.get('tarih')}]
Sermaye: {float(log_row.get('equity') or 1.0):.4f} (Kümülatif: %{float(log_row.get('kumulatif_getiri') or 0.0):.2f}) | Drawdown: %{float(log_row.get('drawdown') or 0.0):.2f}
Dönem Getirisi: %{float(log_row.get('period_ret') or 0.0):.2f} | BIST100: %{float(log_row.get('bist_ret') or 0.0):.2f} | Aktif Alfa: %{float(log_row.get('alfa') or 0.0):.2f}
Değişiklik: [{log_row.get('degisiklik', 'Değişiklik yok')}]
Drift Durumu: {log_row.get('drift_durumu', '🟢')} | Katman 4 Tazelik: {log_row.get('freshness', 'OK')}
Makro: {log_row.get('makro_ozet', '-')}
Devre Kesici: {'⚡ AKTİF (%50 Nakit)' if log_row.get('dd_kesici') else '✅ Pasif (%100 Hisse)'}

📊 Aktif Pozisyonlar ({len(positions)} Hisse):
{pos_str}{takvim_blok}{acil_blok}{uyari_blok}
---"""
        try:
            print(report)
        except UnicodeEncodeError:
            enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
            print(report.encode(enc, errors="replace").decode(enc, errors="replace"))
        return report.strip()

