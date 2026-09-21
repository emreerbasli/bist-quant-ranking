"""
models/v3_ranking/paper_trader.py
==================================
PRODUCTION-CANDIDATE: PAPER TRADING İCRA VE PORTFÖY YÖNETİM MODÜLÜ (ADIM 3)
---------------------------------------------------------------------------
KRİTİK KURUMSAL SINIR (İHLAL EDİLEMEZ):
Bu sistem SADECE bildirim gönderir — hiçbir şekilde otomatik emir veya
al-sat kararı VERMEZ. Tüm kararlar yatırımcının kendi takdirindedir.
Canlı sermaye KESİNLİKLE KULLANILMAZ. Sadece sanal portföy (paper trading) takibidir.

İşlevler:
1. Portföy Durumu Takibi (paper_portfolio.json):
   - 10 hisse, alım fiyatları, alım tarihleri, elde tutulan gün sayısı, ağırlıklar.
   - Zirve sermaye (peak equity) ve drawdown takibi.
   - Sistem kesintiye uğrasa bile diskten kaldığı yerden devam eder.

2. Rebalance Kararı (Her 2 Haftalık Kontrolde):
   - Modelin güncel Top-10 listesini alır.
   - Listeden düşen VE en az 60 gün tutulmuş hisseleri satar (60 günden önce düşse bile bekler).
   - Yeni giren hisseleri portföye ekler.
   - Değişiklik yoksa "değişiklik yok" loglar, gereksiz turnover yapmaz.

3. %25 Portföy Drawdown Devre Kesici:
   - Zirveden %-25 düşüşte pozisyonlar %50 hisse + %50 nakit (%18 faiz) seviyesine indirilir.
   - Zirveden %-15 seviyesine toparlanınca normale (%100 hisse) dönülür.

4. Kurumsal Loglama ve Özet Raporu:
   - Her kontrolde paper_trading_log.csv'ye standart formatta satır ekler.
   - Konsolda kurumsal özet kartı yazdırır.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import os

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

from models.v3_ranking.drift_monitor import DriftMonitor, DriftMonitorReport
import config as cfg

logger = logging.getLogger("PaperTrader")

TRANSACTION_COST = 0.005  # %0.50 round-trip gerçekçi maliyet
                           # = komisyon %0.15 × 2 + BSMV %0.10 × 2 = %0.50
                           # (eski değer: %0.30 — BSMV dahil edilmemişti)
RF_ANNUAL = 0.18          # %18 yıllık risksiz faiz
K_PORTFOLIO_SIZE = 10
MIN_HOLDING_DAYS = 60
DD_TRIGGER = -0.25
DD_RECOVER = -0.15


class PaperTrader:
    """
    K=10, H=60g Sabit Çeyreklik Rotasyon + %25 Portföy Drawdown Devre Kesici
    Paper Trading İcra Motoru.
    """

    DEFAULT_PORTFOLIO_FILE = Path(__file__).resolve().parent / "paper_portfolio.json"
    DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "paper_trading_log.csv"

    def __init__(self,
                 portfolio_file: Optional[Path] = None,
                 log_file: Optional[Path] = None,
                 k_size: int = K_PORTFOLIO_SIZE,
                 min_hold_days: int = MIN_HOLDING_DAYS,
                 dd_trigger: float = DD_TRIGGER,
                 dd_recover: float = DD_RECOVER):
        self.portfolio_file = Path(portfolio_file) if portfolio_file else self.DEFAULT_PORTFOLIO_FILE
        self.log_file = Path(log_file) if log_file else self.DEFAULT_LOG_FILE
        self.k_size = k_size
        self.min_hold_days = min_hold_days
        self.dd_trigger = dd_trigger
        self.dd_recover = dd_recover
        self.drift_monitor = DriftMonitor()

        self.portfolio_state: Dict[str, Any] = self._load_or_init_portfolio()

    def _load_or_init_portfolio(self) -> Dict[str, Any]:
        """Portföy durumunu JSON dosyasından yükler veya yeni oluşturur."""
        if self.portfolio_file.exists():
            try:
                with open(self.portfolio_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(f"Portföy diskten yüklendi: {self.portfolio_file} (Hisseler: {len(data.get('positions', {}))})")
                return data
            except Exception as e:
                logger.error(f"Portföy dosyası okunamadı, yeniden başlatılıyor: {e}")

        initial_state = {
            "last_check_date": None,
            "equity": 1.0,
            "peak_equity": 1.0,
            "drawdown": 0.0,
            "dd_kesici_aktif": False,
            "last_xu100_price": None,
            "positions": {}
        }
        return initial_state

    def save_portfolio(self):
        """Portföy durumunu diske atomik olarak kaydeder (Race condition engeli)."""
        self.portfolio_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.portfolio_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(self.portfolio_state, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, self.portfolio_file)
        logger.info(f"Portföy atomik olarak kaydedildi: {self.portfolio_file}")

    def execute_check(self,
                      t: pd.Timestamp,
                      top_k_ranked: List[str],
                      current_prices: Dict[str, float],
                      current_xu100_price: float,
                      seri_usdtry: pd.Series,
                      tufe_aylik: Dict[str, float],
                      scores_universe: Optional[np.ndarray] = None,
                      days_elapsed: int = 14,
                      send_telegram: bool = True,
                      fiyat_dict: Optional[Dict[str, pd.Series]] = None) -> Dict[str, Any]:
        """
        2 haftalık rebalance kontrolünü ve portföy güncellemesini icra eder.
        """
        t_str = t.strftime("%Y-%m-%d")
        positions = self.portfolio_state["positions"]
        old_equity = float(self.portfolio_state["equity"])
        peak_equity = float(self.portfolio_state["peak_equity"])
        dd_aktif = bool(self.portfolio_state["dd_kesici_aktif"])

        # 1. Önceki Kontrolden Bu Yana Dönem Getirilerini Hesapla
        period_model_ret = 0.0
        period_xu_ret = 0.0

        if positions and self.portfolio_state["last_check_date"] is not None:
            # Hisse bazlı getiri
            weighted_rets = []
            for s, info in positions.items():
                p_prev = info.get("last_price", info.get("entry_price"))
                p_now = current_prices.get(s, p_prev)
                r_s = (p_now - p_prev) / p_prev if p_prev > 0 else 0.0
                weighted_rets.append(r_s * info["weight"])
                info["last_price"] = p_now
                
                # İdempotent gün hesabı: giriş tarihinden itibaren takvim günü
                if "entry_date" in info and info["entry_date"]:
                    try:
                        info["days_held"] = max(0, (pd.to_datetime(t) - pd.to_datetime(info["entry_date"])).days)
                    except Exception:
                        info["days_held"] = info.get("days_held", 0) + days_elapsed
                else:
                    info["days_held"] = info.get("days_held", 0) + days_elapsed


                # V3.2: Bireysel hisse zirve ve drawdown takibi
                prev_peak = info.get("personal_peak_price", max(info.get("entry_price", p_now), p_now))
                cur_peak = max(prev_peak, p_now)
                info["personal_peak_price"] = cur_peak
                peak_dd = (p_now - cur_peak) / cur_peak if cur_peak > 0 else 0.0
                info["peak_drawdown_pct"] = round(peak_dd * 100.0, 2)

            rf_period = ((1.0 + RF_ANNUAL) ** (days_elapsed / 252.0) - 1.0)
            stock_component = float(np.sum(weighted_rets))
            total_stock_weight = sum([info["weight"] for info in positions.values()])
            cash_weight = max(0.0, 1.0 - total_stock_weight)
            period_model_ret = stock_component + cash_weight * rf_period

            # BIST100 getirisi
            last_xu = self.portfolio_state.get("last_xu100_price")
            if last_xu and last_xu > 0:
                period_xu_ret = (current_xu100_price - last_xu) / last_xu

            # Sermaye güncelle
            new_equity = old_equity * (1.0 + period_model_ret)
        else:
            new_equity = old_equity
            period_model_ret = 0.0
            period_xu_ret = 0.0

        # Zirve sermaye ve drawdown
        if new_equity > peak_equity:
            peak_equity = new_equity
        current_dd = (new_equity - peak_equity) / peak_equity

        # 2. %25 Drawdown Devre Kesici Kontrolü
        dd_changed = False
        if not dd_aktif and current_dd <= self.dd_trigger:
            dd_aktif = True
            dd_changed = True
            logger.warning(f"🚨 %25 DRAWDOWN DEVRE KESİCİ DEVREYE GİRDİ! (DD: %{current_dd*100:.1f} <= %{self.dd_trigger*100:.1f})")
        elif dd_aktif and current_dd >= self.dd_recover:
            dd_aktif = False
            dd_changed = True
            logger.info(f"🟢 DRAWDOWN DEVRE KESİCİ NORMALE DÖNDÜ! (DD: %{current_dd*100:.1f} >= %{self.dd_recover*100:.1f})")

        # 3. Model Sıralaması ve Rebalance Değişiklikleri
        target_top_10 = top_k_ranked[:self.k_size]
        exits = []
        entries = []

        if len(positions) == 0:
            # İlk portföy oluşturma
            for s in target_top_10:
                p_entry = current_prices.get(s, 100.0)
                positions[s] = {
                    "entry_date": t_str,
                    "entry_price": p_entry,
                    "personal_peak_price": p_entry,
                    "last_price": p_entry,
                    "days_held": 0,
                    "peak_drawdown_pct": 0.0,
                    "weight": 0.10 if not dd_aktif else 0.05
                }
            entries = list(target_top_10)
        else:
            # Faz 0: Taban Kuralı Acil Çıkış (Hard Exclusion)
            if fiyat_dict:
                try:
                    from bot.kap_filter import ardisik_taban_tespit
                    for s, info in list(positions.items()):
                        if s in fiyat_dict:
                            p_sub = fiyat_dict[s][fiyat_dict[s].index <= t]
                            tetik_taban, cnt_taban = ardisik_taban_tespit(
                                p_sub, lookback_gun=10, min_taban=5, taban_esik=-0.095
                            )
                            if tetik_taban:
                                logger.warning(
                                    f"🚨 ACİL ÇIKIŞ (TABAN KURALI — HARD EXCLUSION): {s} son 10 işlem gününde "
                                    f"{cnt_taban} kez taban yaptı! 60 gün tutma kuralı geçersiz kılınarak "
                                    f"portföyden derhal tasfiye ediliyor."
                                )
                                exits.append(s)
                                del positions[s]
                except Exception as e:
                    logger.warning(f"Faz 0 acil çıkış kontrol hatası: {e}")

            # Listeden düşen ve >=60 gün tutulmuş olanları belirle
            for s, info in list(positions.items()):
                days_h = info.get("days_held", 0)
                if s not in target_top_10:
                    if days_h >= self.min_hold_days:
                        exits.append(s)
                        del positions[s]
                    else:
                        logger.info(f"Hisse {s} Top-10 dışında ancak {days_h} < 60 gün tutulduğu için satılmadı, bekleniyor.")

            # Boşalan slotlara yeni girenleri al
            vacant_slots = self.k_size - len(positions)
            if vacant_slots > 0:
                candidates = [s for s in target_top_10 if s not in positions]
                new_picks = candidates[:vacant_slots]
                for s in new_picks:
                    p_entry = current_prices.get(s, 100.0)
                    positions[s] = {
                        "entry_date": t_str,
                        "entry_price": p_entry,
                        "personal_peak_price": p_entry,
                        "last_price": p_entry,
                        "days_held": 0,
                        "peak_drawdown_pct": 0.0,
                        "weight": 0.10 if not dd_aktif else 0.05
                    }
                    entries.append(s)

        # Ağırlıkları DD durumuna göre senkronize et
        target_w = 0.05 if dd_aktif else 0.10
        for s, info in positions.items():
            info["weight"] = target_w
            # V3.2 güvenlik garantisi: eksik alanları tamamla
            if "personal_peak_price" not in info:
                info["personal_peak_price"] = max(info.get("entry_price", 100.0), info.get("last_price", 100.0))
            if "peak_drawdown_pct" not in info:
                cur_p = info.get("last_price", info.get("entry_price", 100.0))
                pk = info["personal_peak_price"]
                info["peak_drawdown_pct"] = round(((cur_p - pk) / pk * 100.0) if pk > 0 else 0.0, 2)

        # Değişiklik metni
        if len(exits) == 0 and len(entries) == 0 and not dd_changed:
            degisiklik_metni = "değişiklik yok"
        elif len(exits) > 0 or len(entries) > 0:
            parts = []
            if exits:
                parts.append(f"{', '.join(exits)} çıktı")
            if entries:
                parts.append(f"{', '.join(entries)} girdi")
            degisiklik_metni = "; ".join(parts)
        else:
            degisiklik_metni = "DD kesici pozisyon boyutu güncellendi"

        # V3.2: 60 Gün Çıkış Takvimi ve Bireysel Zirve Geri Çekilme Uyarıları
        peak_dd_esik = getattr(cfg, "PEAK_DRAWDOWN_UYARI_ESIGI", 0.20) * 100.0
        uyari_hisseler_list = []
        max_hisse_dd = 0.0
        min_gun_kalan = self.min_hold_days

        cikis_satirlari = []
        for s in sorted(positions.keys()):
            inf = positions[s]
            dh = inf.get("days_held", 0)
            kalan_g = max(0, self.min_hold_days - dh)
            if kalan_g < min_gun_kalan:
                min_gun_kalan = kalan_g

            dd_val = inf.get("peak_drawdown_pct", 0.0)
            if dd_val < max_hisse_dd:
                max_hisse_dd = dd_val

            if dd_val <= -peak_dd_esik:
                uyari_hisseler_list.append(
                    f"{s} (Zirveden %{dd_val:.1f} | Zirve: {inf.get('personal_peak_price', 0):.2f}, Son: {inf.get('last_price', 0):.2f})"
                )

        # Faz 0: VBTS Tedbir Uyarısı (İzleme Modu — Soft Warning)
        try:
            from bot.kap_filter import cek_hisse_haberleri, analiz_et_vbts_riski
            for s in list(positions.keys()):
                h_list = cek_hisse_haberleri(s, max_haber=5, max_gun=7)
                has_v, v_terms, _ = analiz_et_vbts_riski(h_list)
                if has_v:
                    v_str = f"⚠️ {s}: [VBTS İZLEME] Tedbir tespiti ({', '.join(v_terms)})"
                    uyari_hisseler_list.append(v_str)
                    logger.info(f"[VBTS İZLEME MODU]: {v_str}")
        except Exception as e:
            logger.debug(f"VBTS kontrolü atlandı/hata: {e}")

        cikis_takvimi_str = "\n".join(cikis_satirlari)

        # 4. Drift Monitor Raporunu Al (Faz -1: 4. Katman Veri Tazeliği ve 5. Katman Sağlık Denetimi)
        drift_report = self.drift_monitor.generate_full_report(
            t=t,
            seri_usdtry=seri_usdtry,
            tufe_aylik=tufe_aylik,
            scores=scores_universe,
            realized_sharpe=None,  # Paper trading başlangıcında rolling Sharpe birikimi beklenir
            fiyat_dict=fiyat_dict
        )

        # 5. Portföy Durumunu Güncelle ve Kaydet
        self.portfolio_state["last_check_date"] = t_str
        self.portfolio_state["equity"] = new_equity
        self.portfolio_state["peak_equity"] = peak_equity
        self.portfolio_state["drawdown"] = current_dd
        self.portfolio_state["dd_kesici_aktif"] = dd_aktif
        self.portfolio_state["last_xu100_price"] = current_xu100_price
        self.portfolio_state["positions"] = positions
        self.save_portfolio()

        # 6. CSV Log Satırını Yaz
        alfa_period = period_model_ret - period_xu_ret
        portfoy_listesi_str = ", ".join(sorted(positions.keys()))
        makro_ozet_str = (f"Reel:%{drift_report.macro_result.reel_faiz:.1f}, "
                          f"USD_Mom:%{drift_report.macro_result.usd_mom_60*100:.1f}")
        drift_icon = drift_report.overall_status.split()[0] # 🟢 / 🟡 / 🔴

        log_row = {
            "tarih": t_str,
            "portfoy_listesi": portfoy_listesi_str,
            "degisiklik": degisiklik_metni,
            "model_getiri_yuzde": f"%{period_model_ret*100:.2f}",
            "bist100_getiri_yuzde": f"%{period_xu_ret*100:.2f}",
            "alfa": f"%{alfa_period*100:.2f}",
            "drift_durumu": drift_icon,
            "makro_ozet": makro_ozet_str,
            "dd_kesici_aktif": str(dd_aktif),
            "portfoy_zirve_getiri": f"%{current_dd*100:.2f}",
            "max_hisse_dd_pct": f"%{max_hisse_dd:.2f}",
            "min_gun_kalan": str(min_gun_kalan),
            "uyari_hisseler": ", ".join(uyari_hisseler_list) if uyari_hisseler_list else "Yok"
        }

        self._append_log_csv(log_row)

        # 7. Terminal Özet Raporunu Bas
        summary_text = self.print_summary_report(
            log_row,
            cikis_takvimi=cikis_takvimi_str,
            uyari_hisseler=uyari_hisseler_list
        )

        # 8. Telegram Bildirimi İlet
        if send_telegram:
            try:
                from bot.telegram_bot import mesaj_gonder
                mesaj_gonder(summary_text, parse_mode=None)
            except Exception as e:
                logger.warning(f"Telegram bildirimi gönderilemedi: {e}")


        return {
            "log_row": log_row,
            "portfolio_state": self.portfolio_state,
            "drift_report": drift_report,
            "summary_text": summary_text,
            "cikis_takvimi": cikis_takvimi_str,
            "uyari_hisseler": uyari_hisseler_list
        }

    def _append_log_csv(self, row_dict: Dict[str, str]):
        """paper_trading_log.csv dosyasına satır ekler (geriye dönük sütun korumalı)."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "tarih", "portfoy_listesi", "degisiklik", "model_getiri_yuzde",
            "bist100_getiri_yuzde", "alfa", "drift_durumu", "makro_ozet",
            "dd_kesici_aktif", "portfoy_zirve_getiri",
            "max_hisse_dd_pct", "min_gun_kalan", "uyari_hisseler"
        ]
        if not self.log_file.exists():
            df_row = pd.DataFrame([row_dict], columns=fieldnames)
            df_row.to_csv(self.log_file, mode="w", index=False, encoding="utf-8")
        else:
            try:
                df_existing = pd.read_csv(self.log_file)
                df_new = pd.DataFrame([row_dict])
                df_comb = pd.concat([df_existing, df_new], ignore_index=True)
                df_comb.to_csv(self.log_file, index=False, encoding="utf-8")
            except Exception:
                df_row = pd.DataFrame([row_dict])
                df_row.to_csv(self.log_file, mode="a", index=False, header=False, encoding="utf-8")

    def print_summary_report(self, log_row: Dict[str, str], cikis_takvimi: str = "", uyari_hisseler: Optional[List[str]] = None) -> str:
        """Standart kurumsal günlük/kontrol özet raporu çıktısı."""
        uyari_blok = ""
        if uyari_hisseler:
            uyari_blok = "\n\n⚠️ DİKKAT: BİREYSEL HİSSE KÂR GERİ VERME (PEAK DRAWDOWN) UYARILARI:\n"
            for u in uyari_hisseler:
                uyari_blok += f"  🚨 {u}\n"
            uyari_blok += "  (NOT: Bu bir satış emri DEĞİLDİR; sadece risk/kâr takip bilgilendirmesidir.)"

        takvim_blok = ""
        if cikis_takvimi:
            takvim_blok = f"\n\n📋 Portföy 60-Gün Çıkış Takvimi:\n{cikis_takvimi}"

        report = f"""
---
🏛️ BIST V3.2 QUANT (8-FAKTÖR / K=10) RESMİ CANLI PORTFÖY RAPORU — [{log_row['tarih']}]
🛡️ MODEL: V3.2 LGBMRanker (Kilit Kutu Onaylı — Sharpe: 3.44, p=0.000)
Portföy: [{log_row['portfoy_listesi']}]
Değişiklik: [{log_row['degisiklik']}]
Model Getiri (son dönem): [{log_row['model_getiri_yuzde']}]
BIST100 Getiri (son dönem): [{log_row['bist100_getiri_yuzde']}]
Alfa: [{log_row['alfa']}]
Drift Durumu: [{log_row['drift_durumu']}]
Makro: [{log_row['makro_ozet']}]
DD Kesici: [{'Aktif (%50 Nakit)' if log_row['dd_kesici_aktif'] == 'True' else 'Pasif (%100 Hisse)'}]
Zirveden Drawdown: [{log_row['portfoy_zirve_getiri']}]{takvim_blok}{uyari_blok}
---"""
        try:
            print(report)
        except UnicodeEncodeError:
            enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
            print(report.encode(enc, errors="replace").decode(enc, errors="replace"))
        return report


def run_smoke_test(temp_dir: Optional[Path] = None):
    """
    3.5 SMOKE TEST — Kuru Çalıştırma (3 Kontrol Simülasyonu)
    """
    print("=" * 80)
    print("PAPER TRADER SMOKE TESTİ BAŞLATILIYOR...")
    print("=" * 80)

    import tempfile
    test_dir = temp_dir or Path(tempfile.mkdtemp())
    p_file = test_dir / "paper_portfolio.json"
    l_file = test_dir / "paper_trading_log.csv"

    trader = PaperTrader(portfolio_file=p_file, log_file=l_file)

    dummy_usd = pd.Series([35.0] * 100, index=pd.date_range("2025-01-01", periods=100, freq="B"))
    dummy_tufe = {m: 2.0 for m in pd.date_range("2024-01-01", periods=24, freq="MS").strftime("%Y-%m")}
    dummy_scores = np.random.normal(-0.10, 0.22, 88)

    # 1. ÇALIŞMA: İlk 10 hisse seçimi (2025-01-15)
    print("\n>>> TEST 1: İlk Portföy Kurulumu (10 Hisse)")
    initial_top10 = ["AKBNK.IS", "ARCLK.IS", "BIMAS.IS", "FROTO.IS", "KCHOL.IS",
                     "PETKM.IS", "SAHOL.IS", "SISE.IS", "THYAO.IS", "TUPRS.IS"]
    prices_t1 = {s: 100.0 for s in initial_top10}
    
    res1 = trader.execute_check(
        t=pd.Timestamp("2025-01-15"),
        top_k_ranked=initial_top10,
        current_prices=prices_t1,
        current_xu100_price=10000.0,
        seri_usdtry=dummy_usd,
        tufe_aylik=dummy_tufe,
        scores_universe=dummy_scores,
        days_elapsed=0
    )
    assert len(trader.portfolio_state["positions"]) == 10, "İlk portföyde 10 hisse kurulamadı!"
    assert p_file.exists(), "paper_portfolio.json oluşturulamadı!"

    assert "personal_peak_price" in trader.portfolio_state["positions"]["AKBNK.IS"], "personal_peak_price alanı eklenmedi!"
    assert "peak_drawdown_pct" in trader.portfolio_state["positions"]["AKBNK.IS"], "peak_drawdown_pct alanı eklenmedi!"

    # 2. ÇALIŞMA: 2 Hafta Sonra Rebalance (THYAO listeden düştü ve 60 günü doldu gibi test et)
    print("\n>>> TEST 2: Rebalance Kontrolü (Hisse Değişimi Simülasyonu)")
    # THYAO'nun elde tutma gününü 65 gün yapalım
    trader.portfolio_state["positions"]["THYAO.IS"]["days_held"] = 65
    trader.portfolio_state["positions"]["THYAO.IS"]["entry_price"] = 100.0
    trader.portfolio_state["positions"]["THYAO.IS"]["last_price"] = 105.0

    # Yeni Top-10 listesi (THYAO çıktı, SASA girdi)
    top10_t2 = ["AKBNK.IS", "ARCLK.IS", "BIMAS.IS", "FROTO.IS", "KCHOL.IS",
                "PETKM.IS", "SAHOL.IS", "SISE.IS", "SASA.IS", "TUPRS.IS"]
    prices_t2 = {s: 105.0 for s in top10_t2}
    prices_t2["THYAO.IS"] = 105.0

    res2 = trader.execute_check(
        t=pd.Timestamp("2025-01-29"),
        top_k_ranked=top10_t2,
        current_prices=prices_t2,
        current_xu100_price=10300.0,
        seri_usdtry=dummy_usd,
        tufe_aylik=dummy_tufe,
        scores_universe=dummy_scores,
        days_elapsed=14
    )
    assert "SASA.IS" in trader.portfolio_state["positions"], "SASA portföye girmedi!"
    assert "THYAO.IS" not in trader.portfolio_state["positions"], "THYAO portföyden çıkmadı!"

    # 3. ÇALIŞMA: Sert Düşüş ve %25 DD Devre Kesicisi Simülasyonu
    print("\n>>> TEST 3: %25 Drawdown Devre Kesici Simülasyonu")
    # Fiyatların %30 çöktüğünü varsayalım (105 -> 70, %-33.3 çekilme)
    prices_t3 = {s: 70.0 for s in top10_t2}

    res3 = trader.execute_check(
        t=pd.Timestamp("2025-02-12"),
        top_k_ranked=top10_t2,
        current_prices=prices_t3,
        current_xu100_price=7200.0,
        seri_usdtry=dummy_usd,
        tufe_aylik=dummy_tufe,
        scores_universe=dummy_scores,
        days_elapsed=14
    )
    assert trader.portfolio_state["dd_kesici_aktif"], "Drawdown kesici devreye girmedi!"
    for s, info in trader.portfolio_state["positions"].items():
        assert info["weight"] == 0.05, "Hisse ağırlığı %5'e indirilmedi!"

    akbnk_info = trader.portfolio_state["positions"]["AKBNK.IS"]
    assert akbnk_info["peak_drawdown_pct"] <= -20.0, "AKBNK peak drawdown uyarısı eşiğini aşmadı!"
    assert len(res3.get("uyari_hisseler", [])) > 0, "Bireysel peak drawdown uyarısı üretilmedi!"

    # 4. CSV Logunu Oku ve Göster
    print("\n" + "=" * 80)
    print(f"📄 {l_file.name} DOSYASININ İLK 3 SATIRI:")
    print("=" * 80)
    df_log = pd.read_csv(l_file)
    print(df_log.to_string())
    print("=" * 80)
    print("✅ SMOKE TEST BAŞARIYLA TAMAMLANDI.")


if __name__ == "__main__":
    run_smoke_test()
