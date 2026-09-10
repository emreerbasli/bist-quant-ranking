"""
bot/sinyal_skoru.py — FAZ 5.0.1 & FAZ C2: İşlem Skoru (0-100) Hesaplama Motoru
================================================================================
Plan referansı: FAZ 5.0.1 & FAZ C2

Puanlama Ağırlıkları (Overfit önlemek için mantıksal sabit ağırlıklar):
  1. Kalibre Edilmiş Model Olasılığı (%40):
     - Taban %31.5 olduğu için 0.30 -> 0 puan, 0.45+ -> 100 puan şeklinde ölçeklenir.
  2. Risk / Ödül Oranı (%20):
     - 1:1 -> 50 puan, 1.5:1 -> 75 puan, 2:1+ -> 100 puan
  3. Hacim Teyidi & Hacim Şoku (%15):
     - Hacim Şoku (Spike) varsa tam puan, hacim ortalamanın 1.5x üstündeyse yüksek puan
  4. Göreceli Güç (XU100 & Sektör) (%15):
     - Pozitif ayrışma (+%3+) -> 100 puan, negatif -> 0 puan
  5. KAP ve VIX Makro Riski (%10):
     - VIX Normal -> 100, Artış Uyarısı -> 50, Küresel Panik -> 0

Modifikatörler (Tavan/Ceza — Ağırlıklı toplamdan SONRA uygulanır):
  A2. FX-Beta Modifikatörü:
     - Yüksek fx_beta (>1.5) + TL zayıflığı (usdtry_ret_5d > %1) → +10 puan
     - Düşük fx_beta (<0.0) + TL zayıflığı → -5 puan (TL bazlı hisse zarar görür)
  A3. Volatilite Rejim Cezası:
     - vol_rejim_orani > 1.8 → -15 puan (hisse ralli sonrası normalleşme riskinde)
     - vol_rejim_orani > 2.5 → -25 puan (aşırı volatilite, sisteme girme)
  C2. Temel Değerleme & EPS Modifikatörü:
     - EPS sürprizi pozitif (+1) ve sektörüne göre iskontolu (fk_sektor_orani <= 0) → +5 puan
     - EPS sürprizi negatif (-1) ve sektörüne göre pahalı (fk_sektor_orani > 0.30) → -5 puan

Tavan Kuralı:
  - Piyasa Rejimi PANIK ise skor maksimum 40 ile sınırlandırılır.
"""

from typing import Dict, Any, Optional
import numpy as np


def hesapla_islem_skoru(
    model_olasiligi: float,
    risk_odul: float = 1.5,
    vol_ratio_20: float = 1.0,
    hacim_soku: int = 0,
    rel_str_xu100_5d: float = 0.0,
    rel_str_sektor_5d: float = 0.0,
    vix_durum: str = "NORMAL",
    kap_riski: str = "DUSUK",
    piyasa_rejimi: str = "YATAY",
    # ─── FAZ A: FX-Beta & Volatilite Rejimi ─────────────────────────────────
    fx_beta_60d: float = 0.0,          # Hissenin USD/TRY'ye duyarlılığı (rolling 60g OLS β)
    usdtry_ret_5d: float = 0.0,        # Son 5 günlük USD/TRY değişimi
    vol_rejim_orani: float = 1.0,      # Son 5g vol / Son 60g vol — 1.8+ → aşırı ralli
    # ─── FAZ C2: Temel Analiz Parametreleri ─────────────────────────────
    fk_sektor_orani: float = 0.0,      # Sektör medyanına göre F/K iskontosu (<0 ise ucuz)
    eps_surpriz_yonu: int = 0,         # +1: kâr büyümesi güçlü, -1: daralma, 0: nötr
    # ─── Aşama 1 — YENI PARAMETRELER ───────────────────────────────────────
    # F2: R:R gerçek giriş fiyatından hesaplama için
    son_kapanis: float = 0.0,          # Son kapanış fiyatı (ham)
    hedef_fiyat: float = 0.0,         # Hedef fiyat (TP bariyeri)
    stop_fiyat: float = 0.0,          # Stop fiyatı (SL bariyeri)
    # B2: Momentum tükenmesi skoru (0-100 arası)
    momentum_tukenmesi: int = 0,       # 0: normal, 35+: uyarı, 60+: blok
    # ─── Aşama 3: H1 & G1 Parametreleri ─────────────────────────────────────
    h1_deger_skoru: float = 0.0,       # Sektöre özel bileşik değerleme skoru (-2.0 ile +2.0)
    emsal_lideri: bool = False,        # G1: Mikro emsal grubunun en güçlü %30'unda mı?
    rel_str_emsal_5d: float = 0.0,     # G1: Emsal grubuna göre 5 günlük getiri farkı
    # ─── 3 Altın Teknik: CMF & Squeeze Parametreleri ────────────────────────
    cmf_20: float = 0.0,               # Chaikin Money Flow (-1.0 ile +1.0)
    squeeze_on: int = 0,               # 1: Volatilite Sıkışması var (Bollinger Keltner içinde)
    squeeze_fired: int = 0,            # 1: Sıkışmadan yukarı patlama anı (Breakout)
    squeeze_momentum: float = 0.0,     # Sıkışma ivmesi
    # ─── CRO Likidite Kalkanı: Günlük TL Hacmi ───────────────────────────────
    gunluk_tl_hacim: float = 100_000_000.0, # Son günün TL işlem hacmi (Kapanış * Hacim)
) -> Dict[str, Any]:
    """
    Her bileşeni 0-100 arasına normalize eder ve ağırlıklı işlem skorunu hesaplar.
    FAZ A (FX-Beta, Volatilite) + FAZ C2 (Temel Analiz) + Aşama 1 (F1/F2/B2) + CMF, Squeeze ve Likidite modifikatörleri entegredir.

    Returns:
        dict: toplam skor, karar aksiyonu ve bileşen puanları
    """
    import config as cfg

    # ════════════════════════════════════════════════════════════════
    # F1: MODEL GÜVEN SERT BLOĞU — en önce çalışır
    # Hiçbir bileşenin katkısı bu eşiğin altındaki modeli kurtaramaz.
    # ════════════════════════════════════════════════════════════════
    MIN_BLOK   = cfg.MODEL_GUVEN_MIN_BLOK   # 0.40
    KUCUK_POZ  = cfg.MODEL_GUVEN_KUCUK_POZ  # 0.45

    if model_olasiligi < MIN_BLOK:
        # HARD STOP: Skor hesaplanmaz, direkt sıfır dön
        return {
            "islem_skoru":        0,
            "karar_aksiyonu":     "YOK_SAY",
            "karar_aciklama":     f"⛔ Model güveni çok düşük ({model_olasiligi:.1%} < {MIN_BLOK:.0%}) — sinyal iptal",
            "skor_model":         0.0,
            "skor_ro":            0.0,
            "skor_hacim":         0.0,
            "skor_goreceli_guc":  0.0,
            "skor_makro_kap":     0.0,
            "fx_bonus":           0.0,
            "vol_ceza":           0.0,
            "temel_bonus":        0.0,
            "momentum_ceza":      0.0,
            "cmf_bonus":          0.0,
            "cmf_ceza":           0.0,
            "sig_tahta_ceza":     0.0,
            "sig_tahta_mi":       False,
            "gunluk_tl_hacim":    round(gunluk_tl_hacim, 2),
            "squeeze_bonus":      0.0,
            "cmf_20":             round(cmf_20, 3),
            "squeeze_on":         int(squeeze_on),
            "squeeze_fired":      int(squeeze_fired),
            "fx_beta_60d":        round(fx_beta_60d, 3),
            "vol_rejim_orani":    round(vol_rejim_orani, 2),
            "fk_sektor_orani":    round(fk_sektor_orani, 3),
            "eps_surpriz_yonu":   int(eps_surpriz_yonu),
            "gercek_rr":          0.0,
            "momentum_tukenmesi": int(momentum_tukenmesi),
        }

    # ════════════════════════════════════════════════════════════════
    # F2: GERÇEK GİRİŞ FİYATINDAN R:R HESAPLAMA
    # ════════════════════════════════════════════════════════════════
    gercek_rr = risk_odul  # Varsayılan: dışardan gelen parametre
    if son_kapanis > 0 and hedef_fiyat > 0 and stop_fiyat > 0:
        # Gerçek limit giriş fiyatı: kapanış × (1 - iskonto)
        limit_giris = son_kapanis * (1.0 - cfg.LIMIT_GIRIS_ISKONTO)
        kazanc = hedef_fiyat - limit_giris
        risk   = limit_giris - stop_fiyat
        if risk > 0 and kazanc > 0:
            gercek_rr = round(kazanc / risk, 2)
        else:
            gercek_rr = 0.0  # Ters pozisyon veya sıfır risk — geçersiz

    # Minimum R:R kontrolü
    if gercek_rr < cfg.MIN_RISK_ODUL_ORANI and son_kapanis > 0:
        risk_odul_skorlama = 0.0
    else:
        risk_odul_skorlama = gercek_rr  # Skorda gerçek R:R kullan

    # 1. Model Olasılığı Skoru (%40 Ağırlık)
    skor_model = max(0.0, min(100.0, (model_olasiligi - 0.30) / (0.45 - 0.30) * 100.0))

    # 2. Risk / Ödül Skoru (%20 Ağırlık)
    skor_ro = max(0.0, min(100.0, (risk_odul_skorlama - 0.5) / 1.5 * 100.0))

    # 3. Hacim Skoru (%15 Ağırlık)
    if hacim_soku == 1:
        skor_hacim = 100.0
    else:
        skor_hacim = max(0.0, min(100.0, (vol_ratio_20 - 0.8) / (1.5 - 0.8) * 100.0))

    # 4. Göreceli Güç Skoru (%15 Ağırlık)
    ortalama_rel_str = (rel_str_xu100_5d + rel_str_sektor_5d) / 2.0 * 100.0
    skor_rs = max(0.0, min(100.0, (ortalama_rel_str + 3.0) / 6.0 * 100.0))

    # 5. Makro & KAP Skoru (%10 Ağırlık)
    vix_puanlari = {"NORMAL": 100.0, "ARTIS_UYARISI": 50.0, "KURESEL_PANIK": 0.0}
    kap_puanlari = {"DUSUK": 100.0, "ORTA": 50.0, "YUKSEK": 0.0}
    
    skor_vix = vix_puanlari.get(vix_durum, 50.0)
    skor_kap = kap_puanlari.get(kap_riski, 50.0)
    skor_makro_kap = (skor_vix + skor_kap) / 2.0

    # Ağırlıklı Toplam
    toplam_skor = (
        (skor_model * 0.40) +
        (skor_ro    * 0.20) +
        (skor_hacim * 0.15) +
        (skor_rs    * 0.15) +
        (skor_makro_kap * 0.10)
    )

    # ── VIX Küresel Panik Cezası ──────────────────────────────────────────────
    if vix_durum == "KURESEL_PANIK":
        toplam_skor = max(0.0, toplam_skor - 20.0)
    elif vix_durum == "ARTIS_UYARISI":
        toplam_skor = max(0.0, toplam_skor - 10.0)

    # ── YENİ A2: FX-Beta Modifikatörü ────────────────────────────────────────
    fx_bonus = 0.0
    if usdtry_ret_5d > 0.01:
        if fx_beta_60d >= 1.5:
            fx_bonus = +10.0
        elif fx_beta_60d < 0.0:
            fx_bonus = -5.0
    toplam_skor = max(0.0, min(100.0, toplam_skor + fx_bonus))

    # ── YENİ A3: Volatilite Rejim Cezası ─────────────────────────────────────
    vol_ceza = 0.0
    if vol_rejim_orani > 2.5:
        vol_ceza = -25.0
    elif vol_rejim_orani > 1.8:
        vol_ceza = -15.0
    toplam_skor = max(0.0, toplam_skor + vol_ceza)

    # ── YENİ C2: Temel Analiz & EPS Modifikatörü ─────────────────────────────
    temel_bonus = 0.0
    if eps_surpriz_yonu == 1 and fk_sektor_orani <= 0.0:
        temel_bonus = +5.0
    elif eps_surpriz_yonu == -1 and fk_sektor_orani > 0.30:
        temel_bonus = -5.0
    toplam_skor = max(0.0, min(100.0, toplam_skor + temel_bonus))

    # ── H1: Sektöre Özel Bileşik Değerleme Katkısı (Aşama 3) ─────────────────
    h1_bonus = 0.0
    if h1_deger_skoru >= 1.0:
        h1_bonus = +4.0  # Çok ucuz banka veya sanayi
    elif h1_deger_skoru >= 0.4:
        h1_bonus = +2.0  # İskontolu
    elif h1_deger_skoru <= -1.0:
        h1_bonus = -4.0  # Aşırı pahalı
    toplam_skor = max(0.0, min(100.0, toplam_skor + h1_bonus))

    # ── G1: Mikro Emsal Grubu Liderlik Bonusu (Aşama 3) ──────────────────────
    emsal_bonus = 0.0
    if emsal_lideri:
        emsal_bonus = +3.0  # Emsal grubunun en güçlü %30'unda
    elif rel_str_emsal_5d < -0.05:
        emsal_bonus = -2.0  # Emsal grubunun ciddi gerisinde
    toplam_skor = max(0.0, min(100.0, toplam_skor + emsal_bonus))

    # ── 3 ALTIN TEKNİK: CMF PARA AKIŞI KALKANI ──────────────────────────────
    cmf_bonus = 0.0
    cmf_ceza  = 0.0
    cmf_blok  = False
    cmf_cikis_esik = getattr(cfg, "CMF_CIKIS_BLOK_ESIK", -0.05)
    cmf_giris_esik = getattr(cfg, "CMF_GUCLU_GIRIS_ESIK", 0.08)

    if cmf_20 < cmf_cikis_esik:
        cmf_ceza = -30.0
        cmf_blok = True  # Para çıkışı / boğa tuzağı
    elif cmf_20 >= cmf_giris_esik:
        cmf_bonus = +5.0  # Güçlü kurumsal akümülasyon

    toplam_skor = max(0.0, min(100.0, toplam_skor + cmf_bonus + cmf_ceza))

    # ── CRO KURALI: SIĞ TAHTA & FİKTİF HACİM KALKANI ──────────────────────────
    min_tl_hacim = getattr(cfg, "MIN_GUNLUK_TL_HACIM_ESIK", 25_000_000.0)
    sig_tahta_mi = (gunluk_tl_hacim > 0 and gunluk_tl_hacim < min_tl_hacim)
    sig_tahta_ceza = 0.0

    if sig_tahta_mi:
        # Sığ tahtada CMF bonusu VERİLMEZ (manipülatif / wash trade olabilir) ve ceza kesilir
        if cmf_bonus > 0:
            toplam_skor = max(0.0, toplam_skor - cmf_bonus)
            cmf_bonus = 0.0
        sig_tahta_ceza = -20.0
        toplam_skor = max(0.0, toplam_skor + sig_tahta_ceza)

    # ── 3 ALTIN TEKNİK: TTM SQUEEZE BREAKOUT BONUSA ─────────────────────────
    squeeze_bonus = 0.0
    if squeeze_fired == 1:
        squeeze_bonus = getattr(cfg, "SQUEEZE_FIRE_BONUS", 5.0)  # Sıkışmadan yukarı patlama
    elif squeeze_on == 1 and squeeze_momentum > 0:
        squeeze_bonus = +2.0  # Sıkışma içi pozitif birikim

    toplam_skor = max(0.0, min(100.0, toplam_skor + squeeze_bonus))

    # ══ B2: Momentum Tükenmesi Cezası ─────────────────────────────────────────
    momentum_ceza = 0.0
    momentum_blok = False
    if momentum_tukenmesi >= cfg.MOM_TUKENMESI_BLOK:
        momentum_ceza = -50.0
        momentum_blok = True
    elif momentum_tukenmesi >= cfg.MOM_TUKENMESI_UYARI:
        momentum_ceza = -10.0
    toplam_skor = max(0.0, toplam_skor + momentum_ceza)

    # ── XU100 Panik Rejiminde Tavan Sınırı ───────────────────────────────────
    if piyasa_rejimi == "PANIK":
        toplam_skor = min(40.0, toplam_skor)

    nihai_skor = int(round(toplam_skor))

    # ══ Karar Aksiyonu ───────────────────────────────────────────────────────
    if cmf_blok:
        karar_aksiyonu = "YOK_SAY"
        karar_aciklama = f"⛔ Para çıkışı tespit edildi (CMF={cmf_20:.2f} < {cmf_cikis_esik}) — sahte hacim / tuzak riski"
    elif sig_tahta_mi and nihai_skor < 70:
        karar_aksiyonu = "YOK_SAY"
        karar_aciklama = f"⚠️ Sığ Tahta Uyarısı ({gunluk_tl_hacim/1e6:.1f}M TL < {min_tl_hacim/1e6:.1f}M TL) — Likidite riski"
    elif momentum_blok:
        karar_aksiyonu = "YOK_SAY"
        karar_aciklama = f"⚠️ Momentum tükenmesi ({momentum_tukenmesi}/100) — giriş zamanlaması kötü"
    elif model_olasiligi < KUCUK_POZ:
        karar_aksiyonu = "IZLE"
        karar_aciklama = f"👁️ Model güveni düşük ({model_olasiligi:.1%}) — küçük pozisyon olabilir"
    elif gercek_rr < cfg.MIN_RISK_ODUL_ORANI and son_kapanis > 0:
        karar_aksiyonu = "IZLE"
        karar_aciklama = f"🚫 R:R yetersiz ({gercek_rr:.2f} < {cfg.MIN_RISK_ODUL_ORANI}) — daha iyi giriş bekle"
    elif nihai_skor >= 80 and model_olasiligi >= 0.55:
        karar_aksiyonu = "GUCLU_AL"
        karar_aciklama = f"✅ Güçlü sinyal (skor={nihai_skor}, güven={model_olasiligi:.1%})"
    elif nihai_skor >= 65:
        karar_aksiyonu = "AL"
        karar_aciklama = f"✅ Al sinyali (skor={nihai_skor}, güven={model_olasiligi:.1%})"
    elif nihai_skor >= 50:
        karar_aksiyonu = "KUCUK_POZ"
        karar_aciklama = f"🟡 Küçük pozisyon (skor={nihai_skor})"
    else:
        karar_aksiyonu = "YOK_SAY"
        karar_aciklama = f"❌ Yetersiz sinyal (skor={nihai_skor})"

    return {
        "islem_skoru":        nihai_skor,
        "karar_aksiyonu":     karar_aksiyonu,
        "karar_aciklama":     karar_aciklama,
        "skor_model":         round(skor_model, 1),
        "skor_ro":            round(skor_ro, 1),
        "skor_hacim":         round(skor_hacim, 1),
        "skor_goreceli_guc":  round(skor_rs, 1),
        "skor_makro_kap":     round(skor_makro_kap, 1),
        "fx_beta_60d":        round(fx_beta_60d, 3),
        "fx_bonus":           round(fx_bonus, 1),
        "vol_rejim_orani":    round(vol_rejim_orani, 2),
        "vol_ceza":           round(vol_ceza, 1),
        "fk_sektor_orani":    round(fk_sektor_orani, 3),
        "eps_surpriz_yonu":   int(eps_surpriz_yonu),
        "temel_bonus":        round(temel_bonus, 1),
        # Aşama 1 — Yeni alanlar
        "gercek_rr":          round(gercek_rr, 2),
        "momentum_tukenmesi": int(momentum_tukenmesi),
        "momentum_ceza":      round(momentum_ceza, 1),
        # Aşama 3 — H1 & G1 alanları
        "h1_deger_skoru":     round(h1_deger_skoru, 3),
        "h1_bonus":           round(h1_bonus, 1),
        "emsal_lideri":       bool(emsal_lideri),
        "emsal_bonus":        round(emsal_bonus, 1),
        "rel_str_emsal_5d":   round(rel_str_emsal_5d, 4),
        # 3 Altın Teknik alanları
        "cmf_20":             round(cmf_20, 3),
        "cmf_bonus":          round(cmf_bonus, 1),
        "cmf_ceza":           round(cmf_ceza, 1),
        "sig_tahta_ceza":     round(sig_tahta_ceza, 1),
        "sig_tahta_mi":       bool(sig_tahta_mi),
        "gunluk_tl_hacim":    round(gunluk_tl_hacim, 2),
        "squeeze_on":         int(squeeze_on),
        "squeeze_fired":      int(squeeze_fired),
        "squeeze_bonus":      round(squeeze_bonus, 1),
    }
