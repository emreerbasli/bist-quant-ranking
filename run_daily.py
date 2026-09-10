"""
run_daily.py — BIST Sinyal Botu Ana Giriş ve Günlük Çalıştırma Motoru
====================================================================
Plan referansı: FAZ 0.2 & FAZ 7.1 (bist_sinyal_botu_proje_plani_v2.md)

Çalışma Akışı (Her iş günü 18:45):
  1. FAZ 1: Güncel hisse, endeks ve makro verileri çekilir (yfinance).
  2. FAZ 5.5: Health Check & PSI drift kontrolü yapılır.
  3. FAZ 2: Feature Engineering motoru çalıştırılır.
  4. FAZ 2.4: XU100 Piyasa Rejimi ve VIX makro risk durumu belirlenir.
  5. FAZ 4: Kalibre Ensemble modeli ile tüm hisseler için olasılıklar üretilir.
  6. FAZ 5.0.1: İşlem skorları hesaplanır ve adaylar elenir.
  7. FAZ 5.7: Sinyal adaylarına KAP haber filtresi uygulanır.
  8. FAZ 7: Türkçe sinyal ve bülten bildirimleri hazır hale getirilir.

Kullanım:
    python run_daily.py              # Anlık tek seferlik çalıştırma
    python run_daily.py --schedule   # Her iş günü 18:45'te otomatik çalıştır
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path
from loguru import logger
import pandas as pd

# Windows konsol Unicode (emoji) encoding koruması
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent))
import config as cfg
from features.veri_cek import veri_guncelle
from features.feature_engine import (
    hesapla_tumunu,
    hesapla_momentum_tukenmesi,
    hesapla_deger_momentum_celiskisi,
)
from features.piyasa_rejimi import piyasa_rejimi, vix_makro_filtresi, detayli_piyasa_rejimi
from models.predict import yukle_aktif_model, tahmin_uret_tum_evren
from bot.sinyal_skoru import hesapla_islem_skoru
from bot.health_check import health_check_verisi, formatla_admin_health_mesaji
from bot.kap_filter import kap_filtresi_uygula
from bot.paper_trader import getir_acik_pozisyonlar, bakiye_getir, guncelle_gunluk_paper_trading
from backtest.risk_kurallari import portfoy_korelasyon_kalkani
from bot.telegram_messages_tr import formatla_yeni_sinyal_mesaji, formatla_gunluk_bulten
from bot.signal_logger import kaydet_sinyal_girisi, init_signal_log_db

from features.emsal_analizi import hesapla_emsal_grubu_metrikleri, tek_hisse_emsal_analizi
from features.temel_analiz import getir_hisse_temel_featurelari

# Log yapılandırması
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add(
    cfg.LOGS_DIR / "daily_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
    encoding="utf-8",
)


def calistir_gunluk(min_islem_skoru: int = 65, telegram_gonder: bool = False):
    """
    Her iş günü 18:45'te tetiklenen ana analiz döngüsü.
    """
    bugun_str = str(datetime.now().date())
    logger.info("=" * 70)
    logger.info(f"BIST GÜNLÜK SNIPER ANALİZİ BAŞLATILDI — {bugun_str}")
    logger.info("=" * 70)

    try:
        # ─── ADIM 1: VERİ GÜNCELLEME (FAZ 1) ──────────────────────────────────
        logger.info("Adım 1: Güncel borsa ve makro verileri çekiliyor...")
        veri_guncelle()

        # Açık pozisyonların gün sonu kâr koruma / TP / SL güncellemelerini yap
        try:
            kapananlar = guncelle_gunluk_paper_trading(bugun_str=bugun_str)
            if kapananlar:
                logger.info(f"Portföy Senkronizasyonu: {len(kapananlar)} adet işlem TP/SL veya süre ile sonuçlandı.")
        except Exception as e:
            logger.warning(f"Paper trading pozisyon güncelleme uyarısı: {e}")

        # ─── ADIM 2: HEALTH CHECK & PSI DRIFT (FAZ 5.5) ───────────────────────
        logger.info("Adım 2: Veri sağlığı ve kayma kontrolü yapılıyor...")
        health_sonuc = health_check_verisi()
        admin_mesaji = formatla_admin_health_mesaji(health_sonuc)
        logger.info(f"Health Check Durumu: {health_sonuc['durum']}")

        # ─── ADIM 3: FEATURE ENGINEERING (FAZ 2) ─────────────────────────────
        logger.info("Adım 3: Feature setleri hesaplanıyor...")
        hesapla_tumunu()

        # ─── ADIM 4: PİYASA REJİMİ & VIX FİLTRESİ (FAZ 2.4 / D1) ─────────────
        logger.info("Adım 4: XU100 piyasa rejimi ve VIX makro filtresi okunuyor...")
        df_xu100 = pd.read_parquet(cfg.DATA_RAW / "XU100_IS.parquet")
        df_vix = pd.read_parquet(cfg.DATA_RAW / "IDX_VIX.parquet")

        rejim_detay = detayli_piyasa_rejimi(df_xu100)
        rejim = rejim_detay["rejim"]
        vix_durum = vix_makro_filtresi(df_vix)
        logger.info(f"Piyasa Rejimi (D1 4-Bileşen): {rejim} ({rejim_detay['aciklama']}) | VIX: {vix_durum}")

        # ─── ADIM 4.5: G1 MİKRO EMSAL GRUBU ANALİZİ (AŞAMA 3) ────────────────
        logger.info("Adım 4.5: Mikro Emsal Grubu güç ve ivme analizi yapılıyor (G1)...")
        tum_feat_dict = {}
        for s in cfg.HISSELER:
            dosya = cfg.DATA_FEAT / f"{s.replace('.', '_')}.parquet"
            if dosya.exists():
                try:
                    tum_feat_dict[s] = pd.read_parquet(dosya)
                except Exception:
                    pass
        emsal_metrikleri = hesapla_emsal_grubu_metrikleri(tum_feat_dict)

        # ─── ADIM 5: MODEL TAHMİNLERİ (FAZ 4) ─────────────────────────────────
        logger.info("Adım 5: Kalibre Ensemble model tahminleri üretiliyor...")
        tahminler_df = tahmin_uret_tum_evren()

        # ─── ADIM 6: İŞLEM SKORLAMA & ELENME (FAZ 5.0.1 / F1 / F2 / B2 / A4 / H1 / G1) ─
        logger.info("Adım 6: Çok faktörlü işlem skorları hesaplanıyor...")
        adaylar = []
        radar_kayitlari = []

        for _, row in tahminler_df.iterrows():
            sembol = row["sembol"]
            feat_dosya = cfg.DATA_FEAT / f"{sembol.replace('.', '_')}.parquet"
            if not feat_dosya.exists():
                continue
            df_feat = pd.read_parquet(feat_dosya)
            son_bar = df_feat.iloc[-1]

            kapanis = float(row["kapanis_fiyati"])
            atr = float(row["atr_14"])
            planlanan_giris = kapanis * (1.0 - getattr(cfg, "LIMIT_GIRIS_ISKONTO", 0.003))
            hedef = planlanan_giris + (getattr(cfg, "K1", 1.5) * atr)
            stop  = planlanan_giris - (getattr(cfg, "K2", 1.0) * atr)

            # B2: Momentum Tükenmesi Analizi
            mom_info = hesapla_momentum_tukenmesi(df_feat)
            mom_skoru = mom_info["skor"]
            fiyat_ma20_sapma = float(son_bar.get("fiyat_ma20_sapma", mom_info["fiyat_ma20_sapma"]))
            ret_10d = float(son_bar.get("ret_10d", mom_info["ret_10d"]))

            # H1: Sektöre Özel Değerleme ve Çarpanlar
            temel_info = getir_hisse_temel_featurelari(sembol)
            fk_sektor_orani = float(temel_info.get("fk_sektor_orani", 0.0))
            h1_deger_skoru  = float(temel_info.get("h1_deger_skoru", 0.0))
            h1_deger_etiketi= str(temel_info.get("h1_deger_etiketi", "ADIL"))
            pd_dd           = float(temel_info.get("pd_dd", 1.0))
            roe             = float(temel_info.get("roe", 0.14))
            roa             = float(temel_info.get("roa", 0.06))

            # A4: Değerleme — Momentum Çelişki Analizi
            celiski_info = hesapla_deger_momentum_celiskisi(
                fk_sektor_orani=fk_sektor_orani,
                momentum_tukenmesi_skoru=mom_skoru,
                fiyat_ma20_sapma=fiyat_ma20_sapma,
                ret_10d=ret_10d,
            )

            # G1: Mikro Emsal Grubu Göreceli Güç
            emsal_info = emsal_metrikleri.get(sembol, tek_hisse_emsal_analizi(sembol, df_feat))
            emsal_lideri = bool(emsal_info.get("emsal_lideri", False))
            rel_str_emsal_5d = float(emsal_info.get("rel_str_emsal_5d", 0.0))
            emsal_grubu = str(emsal_info.get("emsal_grubu", cfg.HISSE_SEKTOR.get(sembol, "GENEL_BIST")))

            # Sinyal Skoru ve Aksiyon Kararı
            skor_dict = hesapla_islem_skoru(
                model_olasiligi=row["kalibre_olasilik"],
                risk_odul=1.5,
                vol_ratio_20=float(son_bar.get("vol_ratio_20", 1.0)),
                hacim_soku=int(son_bar.get("hacim_soku", 0)),
                rel_str_xu100_5d=float(son_bar.get("rel_str_xu100_5d", 0.0)),
                rel_str_sektor_5d=float(son_bar.get("rel_str_sektor_5d", 0.0)),
                vix_durum=vix_durum,
                piyasa_rejimi=rejim,
                # Faz A
                fx_beta_60d=float(son_bar.get("fx_beta_60d", 0.0)),
                usdtry_ret_5d=float(son_bar.get("usdtry_ret_5d", 0.0)),
                vol_rejim_orani=float(son_bar.get("vol_rejim_orani", 1.0)),
                # Faz C2
                fk_sektor_orani=fk_sektor_orani,
                eps_surpriz_yonu=int(temel_info.get("eps_surpriz_yonu", 0)),
                # Aşama 1: F2 & B2
                son_kapanis=kapanis,
                hedef_fiyat=hedef,
                stop_fiyat=stop,
                momentum_tukenmesi=mom_skoru,
                # Aşama 3: H1 & G1
                h1_deger_skoru=h1_deger_skoru,
                emsal_lideri=emsal_lideri,
                rel_str_emsal_5d=rel_str_emsal_5d,
                # 3 Altın Teknik: CMF & Squeeze
                cmf_20=float(son_bar.get("cmf_20", 0.0)),
                squeeze_on=int(son_bar.get("squeeze_on", 0)),
                squeeze_fired=int(son_bar.get("squeeze_fired", 0)),
                squeeze_momentum=float(son_bar.get("squeeze_momentum", 0.0)),
                # CRO Likidite Kalkanı
                gunluk_tl_hacim=float(son_bar.get("close", 0.0)) * float(son_bar.get("volume", 0.0)),
            )
            skor = skor_dict["islem_skoru"]
            karar_aksiyonu = skor_dict.get("karar_aksiyonu", "YOK_SAY")

            # Radar tablosu için kaydet
            radar_kayitlari.append({
                "sembol": sembol,
                "model_guveni": f"%{row['kalibre_olasilik']*100:.1f}",
                "islem_skoru": skor,
                "karar": karar_aksiyonu,
                "cmf": f"{float(son_bar.get('cmf_20', 0.0)):+.2f}",
                "squeeze": "🔥 PATLADI" if int(son_bar.get("squeeze_fired", 0)) == 1 else ("⚡ SIKIŞTI" if int(son_bar.get("squeeze_on", 0)) == 1 else "NORMAL"),
                "h1_deger": h1_deger_etiketi,
                "emsal_lider": "EVET" if emsal_lideri else "HAYIR",
                "rr": skor_dict.get("gercek_rr", 0.0),
            })

            # F1, CMF & B2 Filtresi: Karar aksiyonu YOK_SAY ise veya skor yetersizse adaya alma
            if skor >= min_islem_skoru and karar_aksiyonu not in ["YOK_SAY"] and row["fikir_birligi_std"] <= cfg.CONSENSUS_STD_MAX:
                adaylar.append({
                    "sembol": sembol,
                    "sektor": cfg.HISSE_SEKTOR.get(sembol, "XU100.IS"),
                    "tarih": bugun_str,
                    "kapanis_fiyati": kapanis,
                    "planlanan_giris": planlanan_giris,
                    "hedef_fiyat": hedef,
                    "stop_fiyat": stop,
                    "atr": atr,
                    "atr_14": atr,
                    "islem_skoru": skor,
                    "karar_aksiyonu": karar_aksiyonu,
                    "karar_aciklama": skor_dict.get("karar_aciklama", ""),
                    "kalibre_olasilik": row["kalibre_olasilik"],
                    "model_olasiligi": row["kalibre_olasilik"],
                    "fikir_birligi_std": row["fikir_birligi_std"],
                    "vix_durum": vix_durum,
                    "piyasa_rejimi": rejim,
                    "gercek_rr": skor_dict.get("gercek_rr", 1.5),
                    # 3 Altın Teknik (CMF & Squeeze)
                    "cmf_20": float(son_bar.get("cmf_20", 0.0)),
                    "cmf_bonus": skor_dict.get("cmf_bonus", 0.0),
                    "cmf_ceza": skor_dict.get("cmf_ceza", 0.0),
                    "squeeze_on": int(son_bar.get("squeeze_on", 0)),
                    "squeeze_fired": int(son_bar.get("squeeze_fired", 0)),
                    "squeeze_momentum": float(son_bar.get("squeeze_momentum", 0.0)),
                    "squeeze_bonus": skor_dict.get("squeeze_bonus", 0.0),
                    # Teknik
                    "rsi_14": float(son_bar.get("rsi_14", 50.0)),
                    "macd_hist": float(son_bar.get("macd_hist", 0.0)),
                    "stoch_k": float(son_bar.get("stoch_k", 50.0)),
                    "vol_ratio_20": float(son_bar.get("vol_ratio_20", 1.0)),
                    "hacim_soku": int(son_bar.get("hacim_soku", 0)),
                    "fiyat_ma20_sapma": fiyat_ma20_sapma,
                    "ret_5d": float(son_bar.get("ret_5d", 0.0)),
                    "ret_10d": ret_10d,
                    "momentum_tukenmesi_skoru": mom_skoru,
                    "momentum_karar": mom_info["karar"],
                    # Temel (H1)
                    "fk_orani": float(temel_info.get("fk_orani", 8.5)),
                    "fk_sektor_orani": fk_sektor_orani,
                    "pd_dd": pd_dd,
                    "roe": roe,
                    "roa": roa,
                    "h1_deger_skoru": h1_deger_skoru,
                    "h1_deger_etiketi": h1_deger_etiketi,
                    "eps_surpriz_yonu": int(temel_info.get("eps_surpriz_yonu", 0)),
                    "eps_aciklama": str(temel_info.get("eps_aciklama", "")),
                    "eps_guvenilirlik": str(temel_info.get("eps_guvenilirlik", "ORTA")),
                    "deger_momentum_celiski": 1 if celiski_info["celiski_var"] else 0,
                    "deger_momentum_aciklama": celiski_info["aciklama"],
                    # Göreceli & Emsal (G1)
                    "fx_beta_60d": float(son_bar.get("fx_beta_60d", 0.0)),
                    "vol_rejim_orani": float(son_bar.get("vol_rejim_orani", 1.0)),
                    "rel_str_xu100_5d": float(son_bar.get("rel_str_xu100_5d", 0.0)),
                    "rel_str_sektor_5d": float(son_bar.get("rel_str_sektor_5d", 0.0)),
                    "emsal_grubu": emsal_grubu,
                    "rel_str_emsal_5d": rel_str_emsal_5d,
                    "emsal_lideri": emsal_lideri,
                    "emsal_aciklama": emsal_info.get("emsal_aciklama", ""),
                })

        # Radar özetini logla
        if radar_kayitlari:
            df_radar = pd.DataFrame(radar_kayitlari).sort_values(by="islem_skoru", ascending=False)
            logger.info("\n" + "=" * 70 + "\n📊 GÜNLÜK RADAR — İLK 10 HİSSE ANALİZİ:\n" + "=" * 70 + "\n" + df_radar.head(10).to_string(index=False) + "\n" + "=" * 70)

        # ─── ADIM 7: KAP HABER FİLTRESİ (FAZ 5.7) ─────────────────────────────
        logger.info(f"Adım 7: {len(adaylar)} aday için KAP haber taraması yapılıyor...")
        adaylar = kap_filtresi_uygula(adaylar)

        # ─── ADIM 7.5: PORTFÖY KORELASYON KALKANI (FAZ C3) ────────────────────
        logger.info("Adım 7.5: Açık pozisyonlarla portföy korelasyon kalkanı denetleniyor...")
        acik_pozlar = getir_acik_pozisyonlar()
        acik_semboller = [p["sembol"] for p in acik_pozlar] if acik_pozlar else []

        if acik_semboller and adaylar:
            logger.info(f"Mevcut Açık Pozisyonlar ({len(acik_semboller)}): {acik_semboller}")
            onayli_adaylar = []
            for aday in adaylar:
                sembol = aday["sembol"]
                gecerli, max_corr, en_yuksek_sym, detaylar = portfoy_korelasyon_kalkani(
                    sembol, acik_semboller, esik=cfg.KORELASYON_ESIGI, pencere=30
                )
                if gecerli:
                    aday["max_korelasyon"] = max_corr
                    aday["korelasyon_eslesen"] = en_yuksek_sym
                    onayli_adaylar.append(aday)
                else:
                    logger.warning(
                        f"🛡️ {sembol}: KORELASYON KALKANI DEVREDE! Açık pozisyon #{en_yuksek_sym} "
                        f"ile 30g korelasyon {max_corr:.2f} > {cfg.KORELASYON_ESIGI} -> Sinyal İPTAL edildi."
                    )
            adaylar = onayli_adaylar

        # ─── ADIM 7.8: E3 SİNYAL GÜNLÜĞÜNE KAYDETME ───────────────────────────
        logger.info(f"Adım 7.8: {len(adaylar)} adet onaylı sinyal analitik veri tabanına loglanıyor (E3)...")
        for aday in adaylar:
            try:
                kaydet_sinyal_girisi(aday)
            except Exception as e:
                logger.warning(f"Sinyal loglama hatası ({aday.get('sembol')}): {e}")

        # ─── ADIM 8: TELEGRAM MESAJLARI OLUŞTURMA (FAZ 5.7.4) ─────────────────
        logger.info("Adım 8: Bildirim mesajları formatlanıyor...")

        sinyal_mesajlari = []
        for aday in adaylar:
            msg = formatla_yeni_sinyal_mesaji(aday)
            sinyal_mesajlari.append(msg)
            print("\n" + msg + "\n")

        bulten_mesaji = formatla_gunluk_bulten(
            tarih=bugun_str,
            portfoy_degeri=734_138.0,
            gunluk_getiri_pct=0.0,
            acik_pozisyonlar=[],
            piyasa_rejimi=rejim,
            vix_durum=vix_durum,
        )
        print("\n" + bulten_mesaji + "\n")

        logger.info(f"Günlük analiz başarıyla tamamlandı. Üretilen Sinyal Sayısı: {len(adaylar)}")
        return adaylar

    except Exception as e:
        logger.error(f"KRİTİK HATA: {e}", exc_info=True)
        raise


def zamanlanmis_calistir():
    """APScheduler ile her iş günü 18:45'te çalıştır."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="Europe/Istanbul")
    scheduler.add_job(
        calistir_gunluk,
        trigger="cron",
        day_of_week="mon-fri",
        hour=cfg.CALISMA_SAATI,
        minute=cfg.CALISMA_DAKIKA,
        id="gunluk_analiz",
    )
    logger.info(
        f"Zamanlayıcı başlatıldı — her iş günü {cfg.CALISMA_SAATI}:{cfg.CALISMA_DAKIKA:02d}'te çalışacak"
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Zamanlayıcı durduruldu.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BIST Sinyal Botu — Günlük Analiz")
    parser.add_argument("--schedule", action="store_true", help="APScheduler ile zamanlanmış modda çalıştır")
    args = parser.parse_args()

    if args.schedule:
        zamanlanmis_calistir()
    else:
        calistir_gunluk()
