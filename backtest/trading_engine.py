"""
backtest/trading_engine.py — FAZ 5: Çift Taraflı Portföy Simülasyon Motoru (Backtest Engine)
===========================================================================================
Plan referansı: FAZ 5.0 - 5.3 (bist_sinyal_botu_proje_plani_v2.md)

Özellikler:
  - 2018 - 2026 arası tüm işlem günlerini gün gün (bar-by-bar) kronolojik simüle eder.
  - T günü kapanışında sinyal üretilir -> T+1 sabah açılışında Limit Emir & Gap kontrolü ile pozisyon açılır.
  - Risk bazlı sizing (%0.5 kasa riski, max %20 tek hisse tavanı).
  - Portföy kısıtları: max 5 eşzamanlı pozisyon, sektör başına max 2 pozisyon.
  - Dinamik çıkışlar: Hard Stop (-1.0x ATR), Kâr Hedefi (+1.5x ATR), Zaman Stopu (5 gün).
  - Komisyon (%0.1) ve hisse bazlı kayma (slippage) maliyetlerini düşer.
  - BIST100 (XU100 Buy&Hold) ile eşzamanlı kıyaslama yapar.
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd
import numpy as np
from loguru import logger

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg
from bot.sinyal_skoru import hesapla_islem_skoru
from backtest.risk_kurallari import (
    pozisyon_boyutu_hesapla, gap_kontrolu, limit_emir_simulasyonu,
    kurumsal_aksiyon_maskele, hesapla_islem_maliyeti
)
from models.predict import yukle_aktif_model, tahmin_uret_tek_hisse


class BacktestEngine:
    """
    Kronolojik Günlük Portföy Backtest Motoru.
    """
    def __init__(
        self,
        baslangic_sermaye: float = 100_000.0,
        min_islem_skoru: int = 65,
        min_model_olasiligi: float = 0.35,
        max_pozisyon_sayisi: int = cfg.MAX_ESSZAMANLI_POZISYON,
        max_sektor_pozisyon: int = cfg.MAX_SEKTOR_POZISYON,
    ):
        self.baslangic_sermaye = baslangic_sermaye
        self.kasa = baslangic_sermaye
        self.min_islem_skoru = min_islem_skoru
        self.min_model_olasiligi = min_model_olasiligi
        self.max_pozisyon_sayisi = max_pozisyon_sayisi
        self.max_sektor_pozisyon = max_sektor_pozisyon

        self.acik_pozisyonlar: Dict[str, Dict[str, Any]] = {}
        self.kapanan_islemler: List[Dict[str, Any]] = []
        self.gunluk_kayitlar: List[Dict[str, Any]] = []
        self.bekleyen_emirler: List[Dict[str, Any]] = []

    def calistir(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Backtest simülasyonunu baştan sona çalıştırır.
        
        Returns:
            df_gunluk (DataFrame): Günlük portföy değeri, nakit ve benchmark serisi.
            df_islemler (DataFrame): Kapanan tüm işlemlerin detaylı günlüğü.
        """
        logger.info(f"{'═'*70}")
        logger.info(f"FAZ 5: Backtest Simülasyonu Başlatılıyor (Başlangıç Sermaye: {self.baslangic_sermaye:,.0f} TL)")
        logger.info(f"Filtreler: Min İşlem Skoru={self.min_islem_skoru}, Min Kalibre Olasılık={self.min_model_olasiligi}, Max Pozisyon={self.max_pozisyon_sayisi}")
        logger.info(f"{'═'*70}")

        # 1. Tüm hisse feature parquet dosyalarını yükle
        hisseler_df: Dict[str, pd.DataFrame] = {}
        for sembol in cfg.HISSELER:
            dosya = cfg.DATA_FEAT / f"{sembol.replace('.', '_')}.parquet"
            if dosya.exists():
                hisseler_df[sembol] = pd.read_parquet(dosya).sort_index()

        # 2. XU100 Benchmark verisini yükle
        xu100_dosya = cfg.DATA_RAW / "XU100_IS.parquet"
        df_xu100 = pd.read_parquet(xu100_dosya).sort_index()

        model_pipeline = yukle_aktif_model()
        logger.info("Model tahminleri tüm hisseler için vektörel olarak hesaplanıyor...")
        
        for sembol, df_h in hisseler_df.items():
            X_all = df_h[[c for c in model_pipeline.feature_names if c in df_h.columns]].copy()
            for col in X_all.select_dtypes(include=["object", "category"]).columns:
                X_all[col] = X_all[col].astype("category").cat.codes
            X_all = X_all[model_pipeline.feature_names]
            
            p_all, std_all, _ = model_pipeline.predict_proba_all(X_all)
            df_h["kalibre_olasilik"] = p_all
            df_h["fikir_birligi_std"] = std_all

        # Ortak işlem günlerini bul
        tum_tarihler = sorted(list(set(df_xu100.index)))
        
        # İlk 50 gün model ısınma periyodudur, feature'ların başladığı tarihten itibaren simüle et
        ilk_tarih = min(df.index[0] for df in hisseler_df.values())
        islem_tarihleri = [t for t in tum_tarihler if t >= ilk_tarih]

        logger.info(f"Simülasyon Dönemi: {islem_tarihleri[0].date()} → {islem_tarihleri[-1].date()} ({len(islem_tarihleri)} İşlem Günü)")

        # İlk günkü XU100 fiyatı (Benchmark endeksleme için)
        xu100_baslangic = df_xu100.loc[islem_tarihleri[0], "close"] if islem_tarihleri[0] in df_xu100.index else df_xu100["close"].iloc[0]

        # ─── GÜNLÜK DÖNGÜ (BAR-BY-BAR) ───────────────────────────────────────
        for t_idx, bugun in enumerate(islem_tarihleri):
            bugun_str = str(bugun.date())

            # A. Önceki Günden Bekleyen Emirleri Gerçekleştir (Sabah Açılış)
            self._gerceklestir_bekleyen_emirler(bugun, hisseler_df)

            # B. Açık Pozisyonların Gün İçi TP / SL / Timeout Kontrolü
            self._guncelle_acik_pozisyonlar(bugun, hisseler_df)

            # C. Gün Sonu Portföy Değerlemesi & Kayıt
            portfoy_degeri = self._portfoy_degerle(bugun, hisseler_df)
            xu100_bugun = df_xu100.loc[bugun, "close"] if bugun in df_xu100.index else np.nan
            benchmark_degeri = (xu100_bugun / xu100_baslangic) * self.baslangic_sermaye if not pd.isna(xu100_bugun) else np.nan

            self.gunluk_kayitlar.append({
                "tarih": bugun,
                "kasa_nakit": round(self.kasa, 2),
                "portfoy_degeri": round(portfoy_degeri, 2),
                "acik_pozisyon_sayisi": len(self.acik_pozisyonlar),
                "benchmark_degeri": round(benchmark_degeri, 2),
            })

            # D. Gün Sonu Kapanışında Yeni Sinyalleri Tara (Ertesi Gün İçin)
            if t_idx < len(islem_tarihleri) - 1:
                self._tara_yeni_sinyaller(bugun, hisseler_df, model_pipeline, portfoy_degeri)

        df_gunluk = pd.DataFrame(self.gunluk_kayitlar).set_index("tarih")
        df_islemler = pd.DataFrame(self.kapanan_islemler)
        logger.info(f"Backtest Tamamlandı: {len(df_islemler)} İşlem Gerçekleşti.")
        return df_gunluk, df_islemler

    def _gerceklestir_bekleyen_emirler(self, bugun: pd.Timestamp, hisseler_df: Dict[str, pd.DataFrame]):
        """Ertesi günün açılışında limit emir ve gap kontrolü ile emirleri açar."""
        if not self.bekleyen_emirler:
            return

        portfoy_degeri = self.kasa + sum(p["nominal_deger"] for p in self.acik_pozisyonlar.values())

        for emir in self.bekleyen_emirler:
            sembol = emir["sembol"]
            if sembol in self.acik_pozisyonlar:
                continue

            # Portföy kapasite kontrolü
            if len(self.acik_pozisyonlar) >= self.max_pozisyon_sayisi:
                break

            sektor = cfg.HISSE_SEKTOR.get(sembol, "XU100.IS")
            sektor_poz_sayisi = sum(1 for p in self.acik_pozisyonlar.values() if p["sektor"] == sektor)
            if sektor_poz_sayisi >= self.max_sektor_pozisyon:
                continue

            df_h = hisseler_df.get(sembol)
            if df_h is None or bugun not in df_h.index:
                continue

            row = df_h.loc[bugun]
            t1_open = row["open"]
            t1_high = row["high"]
            t1_low = row["low"]

            # 1. Gap Kontrolü
            gap_ok, _ = gap_kontrolu(emir["sinyal_kapanis"], t1_open, emir["atr"])
            if not gap_ok:
                continue

            # 2. Limit Emir Kontrolü
            limit_ok, giris_fiyati = limit_emir_simulasyonu(emir["sinyal_kapanis"], t1_open, t1_low)
            if not limit_ok:
                continue

            # 3. Pozisyon Boyutu & Risk Sizing
            stop_mesafesi = emir["atr"] * cfg.K2
            lot_adedi, nominal_tutar, risk_tutari = pozisyon_boyutu_hesapla(
                portfoy_degeri=portfoy_degeri,
                stop_mesafesi=stop_mesafesi,
                giris_fiyati=giris_fiyati,
            )

            if lot_adedi <= 0 or nominal_tutar > self.kasa:
                continue

            # 4. Maliyet Hesaplama
            komisyon, slip, toplam_maliyet = hesapla_islem_maliyeti(nominal_tutar, sembol)
            self.kasa -= (nominal_tutar + toplam_maliyet)

            # Dinamik Bariyerler
            upper_barrier = giris_fiyati + (cfg.K1 * emir["atr"])
            lower_barrier = giris_fiyati - (cfg.K2 * emir["atr"])

            self.acik_pozisyonlar[sembol] = {
                "sembol": sembol,
                "sektor": sektor,
                "giris_tarihi": bugun,
                "giris_fiyati": giris_fiyati,
                "lot_adedi": lot_adedi,
                "nominal_deger": nominal_tutar,
                "upper_barrier": upper_barrier,
                "lower_barrier": lower_barrier,
                "atr": emir["atr"],
                "elde_tutma_gun": 1,
                "tp1_alindi": 0,
                "kismi_kar_tl": 0.0,
                "islem_skoru": emir["islem_skoru"],
                "kalibre_olasilik": emir["kalibre_olasilik"],
                "giris_maliyeti": toplam_maliyet,
            }

        self.bekleyen_emirler = []

    def _guncelle_acik_pozisyonlar(self, bugun: pd.Timestamp, hisseler_df: Dict[str, pd.DataFrame]):
        """Açık pozisyonların gün içi Kademeli TP1, Breakeven Stop veya 5 günlük zaman aşımı kontrolünü yapar."""
        kapanacaklar = []

        for sembol, poz in self.acik_pozisyonlar.items():
            df_h = hisseler_df.get(sembol)
            if df_h is None or bugun not in df_h.index:
                continue

            row = df_h.loc[bugun]
            open_price = float(row["open"]) if "open" in row else float(row.get("Open", row["close"]))
            high = row["high"]
            low = row["low"]
            close = row["close"]

            upper = poz["upper_barrier"]
            lower = poz["lower_barrier"]
            tp1_alindi = poz.get("tp1_alindi", 0)
            kismi_kar = poz.get("kismi_kar_tl", 0.0)
            
            cikis_fiyati = None
            cikis_nedeni = None

            hit_upper = high >= upper
            hit_lower = low <= lower

            # ─── KADEMELİ TP1 & BREAKEVEN STOP & GAP SLIPPAGE MOTORU ──────────
            if hit_lower:
                # KRİTİK CRO DÜZELTME: Açılış stopun altındaysa (GAP DOWN / TABAN),
                # gerçek piyasa çıkış fiyatı 'open_price'tır; hayali 'lower' fiyattan çıkılamaz!
                cikis_fiyati = min(open_price, lower)
                cikis_nedeni = "BREAKEVEN_STOP" if tp1_alindi == 1 else ("SL_GAP" if open_price < lower else "SL")

            elif hit_upper and tp1_alindi == 0:
                # 1. Aşama: TP1 Vuruldu -> %50 Realize Et, Stop'u Giriş Maliyetine Çek
                gercek_tp_fiyat = max(open_price, upper)
                lot = poz["lot_adedi"]
                satilan_lot = max(1, lot // 2) if lot > 1 else lot
                kalan_lot = lot - satilan_lot

                satilan_nominal = satilan_lot * gercek_tp_fiyat
                komisyon, slip, kismi_maliyet = hesapla_islem_maliyeti(satilan_nominal, sembol)
                net_tahsilat = satilan_nominal - kismi_maliyet
                self.kasa += net_tahsilat

                bu_kismi_kar = net_tahsilat - (satilan_lot * poz["giris_fiyati"])
                poz["kismi_kar_tl"] += bu_kismi_kar
                poz["lot_adedi"] = kalan_lot
                poz["tp1_alindi"] = 1

                if kalan_lot > 0:
                    # Kalan %50 için Stop -> Giriş Maliyeti (Breakeven), Hedef -> TP2 (+2.5x ATR)
                    poz["lower_barrier"] = poz["giris_fiyati"] * (1.0 + getattr(cfg, "BREAKEVEN_TOLERANS", 0.001))
                    poz["upper_barrier"] = poz["giris_fiyati"] + (2.5 * poz["atr"])
                    poz["elde_tutma_gun"] += 1
                    poz["nominal_deger"] = kalan_lot * close
                    continue
                else:
                    cikis_fiyati = gercek_tp_fiyat
                    cikis_nedeni = "TP1_TAM"

            elif hit_upper and tp1_alindi == 1:
                # 2. Aşama: TP2 Genişletilmiş Hedef Vuruldu
                cikis_fiyati = max(open_price, upper)
                cikis_nedeni = "TP2_GENISLETILMIS"

            elif poz["elde_tutma_gun"] >= cfg.ZAMAN_BARIYERI:
                cikis_fiyati = close
                cikis_nedeni = "TIMEOUT"
            else:
                # Pozisyon taşınmaya devam ediyor
                poz["elde_tutma_gun"] += 1
                poz["nominal_deger"] = poz["lot_adedi"] * close
                continue

            # Çıkış gerçekleşti
            cikis_nominal = poz["lot_adedi"] * cikis_fiyati
            komisyon, slip, cikis_maliyeti = hesapla_islem_maliyeti(cikis_nominal, sembol)
            
            net_tahsilat = cikis_nominal - cikis_maliyeti
            self.kasa += net_tahsilat

            toplam_islem_maliyeti = poz["giris_maliyeti"] + cikis_maliyeti
            net_kar_zarar_tl = net_tahsilat - (poz["lot_adedi"] * poz["giris_fiyati"]) - poz["giris_maliyeti"] + kismi_kar
            net_getiri_yuzde = (net_kar_zarar_tl / (poz["lot_adedi"] * poz["giris_fiyati"])) * 100.0

            self.kapanan_islemler.append({
                "sembol": sembol,
                "sektor": poz["sektor"],
                "giris_tarihi": poz["giris_tarihi"],
                "cikis_tarihi": bugun,
                "giris_fiyati": poz["giris_fiyati"],
                "cikis_fiyati": round(cikis_fiyati, 4),
                "lot_adedi": poz["lot_adedi"],
                "elde_tutma_gun": poz["elde_tutma_gun"],
                "cikis_nedeni": cikis_nedeni,
                "net_kar_zarar_tl": round(net_kar_zarar_tl, 2),
                "net_getiri_%": round(net_getiri_yuzde, 2),
                "islem_skoru": poz["islem_skoru"],
                "kalibre_olasilik": poz["kalibre_olasilik"],
                "toplam_maliyet_tl": round(toplam_islem_maliyeti, 2),
            })
            kapanacaklar.append(sembol)

        for s in kapanacaklar:
            del self.acik_pozisyonlar[s]

    def _tara_yeni_sinyaller(
        self,
        bugun: pd.Timestamp,
        hisseler_df: Dict[str, pd.DataFrame],
        pipeline: Any,
        portfoy_degeri: float,
    ):
        """Gün sonu kapanışında hisseleri tarar ve ertesi gün için bekleyen emirleri sıralar."""
        adaylar = []

        for sembol, df_h in hisseler_df.items():
            if sembol in self.acik_pozisyonlar:
                continue

            if bugun not in df_h.index:
                continue

            loc_idx = df_h.index.get_loc(bugun)
            
            # 1. Kurumsal Aksiyon Maskeleme
            if kurumsal_aksiyon_maskele(df_h, loc_idx, maskeleme_is_gunu=cfg.MASKELEME_GUN):
                continue

            row = df_h.loc[bugun]
            
            # 2. Önceden Hesaplanmış Model Tahmini
            p = float(row["kalibre_olasilik"])
            std = float(row["fikir_birligi_std"])

            if p < self.min_model_olasiligi or std > cfg.CONSENSUS_STD_MAX:
                continue

            # 3. İşlem Skoru Hesabı
            vix_durum = "NORMAL"
            if "vix_ret_3d" in row and not pd.isna(row["vix_ret_3d"]):
                if row["vix_ret_3d"] > cfg.VIX_PANIK_ESIK:
                    vix_durum = "KURESEL_PANIK"
                elif row["vix_ret_3d"] > cfg.VIX_ARTIS_UYARI_ESIK:
                    vix_durum = "ARTIS_UYARISI"

            piyasa_rej = str(row.get("xu100_rejim", "YATAY"))

            skor_dict = hesapla_islem_skoru(
                model_olasiligi=p,
                risk_odul=1.5,
                vol_ratio_20=float(row.get("vol_ratio_20", 1.0)),
                hacim_soku=int(row.get("hacim_soku", 0)),
                rel_str_xu100_5d=float(row.get("rel_str_xu100_5d", 0.0)),
                rel_str_sektor_5d=float(row.get("rel_str_sektor_5d", 0.0)),
                vix_durum=vix_durum,
                piyasa_rejimi=piyasa_rej,
            )
            skor = skor_dict["islem_skoru"]

            if skor >= self.min_islem_skoru:
                adaylar.append({
                    "sembol": sembol,
                    "sinyal_kapanis": float(row["close"]),
                    "atr": float(row["atr_14"]),
                    "kalibre_olasilik": p,
                    "fikir_birligi_std": std,
                    "islem_skoru": skor,
                })

        # Skor ve olasılığa göre en güçlü adayları sırala
        if adaylar:
            adaylar = sorted(adaylar, key=lambda x: (x["islem_skoru"], x["kalibre_olasilik"]), reverse=True)
            self.bekleyen_emirler = adaylar[:self.max_pozisyon_sayisi]

    def _portfoy_degerle(self, bugun: pd.Timestamp, hisseler_df: Dict[str, pd.DataFrame]) -> float:
        """Portföyün toplam piyasa değerini (Nakit + Açık Pozisyonlar) döner."""
        toplam_deger = self.kasa
        for sembol, poz in self.acik_pozisyonlar.items():
            df_h = hisseler_df.get(sembol)
            if df_h is not None and bugun in df_h.index:
                close = df_h.loc[bugun, "close"]
                toplam_deger += (poz["lot_adedi"] * close)
            else:
                toplam_deger += poz["nominal_deger"]
        return toplam_deger
