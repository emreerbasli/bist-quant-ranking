"""
bot/telegram_messages_tr.py — FAZ 5.7 & FAZ 7 & FAZ C: Türkçe Telegram Mesaj Şablonları & VIP Terminal
=========================================================================================================
Plan referansı: FAZ 5.7.4, FAZ 7.1, FAZ C (Temel Analiz & Korelasyon Kalkanı Arayüzü)

Özellikler:
  - Fon Yöneticisi & VIP Terminal Rapor Formatı
  - Görsel İlerleme Çubuğu (Progress Bar)
  - Temel Analiz (F/K, Sektör İskontosu, EPS Büyümesi) Şeffaf Bilgi Kartı
  - Portföy Korelasyon Kalkanı Güvenlik Göstergesi
  - Hızlı TP vs Standart Sinyal Göstergesi
  - BIST 100 Rejim & Masa Riski Analizi
  - Kilitli Kâr ve Net TL Hedef Kartları
"""

import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg


import html

def formatla_yeni_sinyal_mesaji(sinyal: Dict[str, Any]) -> str:
    """
    Kullanıcıya gönderilecek 'Yeni Alış Sinyali' mesaj şablonu.
    Aşama 1, 2 ve 3 geliştirmeleri entegre edilmiştir:
      - H1: Sektöre Özel Değerleme (PD/DD, ROE, F/K)
      - G1: Mikro Emsal Grubu Liderliği & Göreceli Güç
      - B1: Teknik İndikatör Kartı (RSI, MACD, Hacim)
      - F2: Gerçek Giriş Fiyatı & R:R Oranı
      - A4: Değer-Momentum Çelişki Uyarısı
    HTML parse hatasına karşı tüm dinamik alanlar html.escape ile korunur.
    """
    ham_sembol = sinyal.get("sembol", "")
    sembol = html.escape(ham_sembol.replace(".IS", ""))
    sektor = html.escape(str(sinyal.get("sektor", "BIST")).replace(".IS", ""))
    tarih = html.escape(str(sinyal.get("tarih", str(datetime.now().date()))))
    fiyat = float(sinyal.get("kapanis_fiyati", sinyal.get("fiyat", 0.0)))
    atr = float(sinyal.get("atr_14", sinyal.get("atr", 1.0)))
    skor = int(sinyal.get("islem_skoru", 75))
    olasilik_pct = float(sinyal.get("kalibre_olasilik", sinyal.get("model_olasiligi", 0.40))) * 100.0
    p_hizli_tp = float(sinyal.get("p_hizli_tp", 0.0))
    is_hizli = sinyal.get("is_hizli_tp", False) or (p_hizli_tp >= cfg.SINYAL_ESIGI_HIZLI_TP)
    vix_durum = html.escape(str(sinyal.get("vix_durum", "NORMAL")))
    kap_riski = html.escape(str(sinyal.get("kap_riski", "DUSUK")))
    piyasa_rejimi = html.escape(str(sinyal.get("piyasa_rejimi", "GUCLU_YUKSELIS")))
    gercek_rr = float(sinyal.get("gercek_rr", 1.5))
    karar_aksiyonu = html.escape(str(sinyal.get("karar_aksiyonu", "AL")))

    # Dinamik Seviyeler
    limit_fiyat = float(sinyal.get("planlanan_giris", fiyat * (1.0 - getattr(cfg, "LIMIT_GIRIS_ISKONTO", 0.003))))
    tp1 = float(sinyal.get("hedef_fiyat", limit_fiyat + (getattr(cfg, "K1", 1.5) * atr)))
    tp2 = limit_fiyat + (2.5 * atr)
    sl  = float(sinyal.get("stop_fiyat", limit_fiyat - (getattr(cfg, "K2", 1.0) * atr)))

    tp1_pct = ((tp1 - limit_fiyat) / limit_fiyat) * 100.0
    sl_pct  = ((sl - limit_fiyat) / limit_fiyat) * 100.0

    skor_emoji = "🔥" if skor >= 75 else "⚡"
    kap_emoji  = "🟢" if kap_riski == "DUSUK" else ("🟡" if kap_riski == "ORTA" else "🔴")
    vix_emoji  = "🟢" if vix_durum == "NORMAL" else ("🟡" if vix_durum == "ARTIS_UYARISI" else "🔴")

    # VIP Hisse Etiketi
    is_vip = (ham_sembol in cfg.VIP_HISSELER or sembol in [s.replace(".IS", "") for s in cfg.VIP_HISSELER])
    vip_etiket = " 👑 <b>[VIP ÖZEL PORTFÖY]</b>" if is_vip else ""

    # Sinyal Hızı / Türü
    sinyal_turu = "🚀 <b>Hızlı Sniper (1-3 Gün Hedef)</b>" if is_hizli else "🎯 <b>Standart Sniper (1-5 Gün)</b>"

    # 1. H1 & Temel Değerleme Bilgi Kartı
    temel_satirlar = []
    pd_dd = sinyal.get("pd_dd")
    roe = sinyal.get("roe")
    h1_etiket = sinyal.get("h1_deger_etiketi")
    fk = sinyal.get("fk_orani")
    eps_yon = sinyal.get("eps_surpriz_yonu", 0)
    eps_aciklama = html.escape(str(sinyal.get("eps_aciklama", "")))
    eps_str = f"🟢 {eps_aciklama}" if eps_yon == 1 else (f"🔴 {eps_aciklama}" if eps_yon == -1 else f"🟡 {eps_aciklama or 'Dengeli'}")

    if "XBANK" in sektor:
        pddd_str = f"PD/DD: <b>{pd_dd:.2f}</b>" if pd_dd else ""
        roe_str = f"ROE: <b>%{roe*100:.1f}</b>" if roe else ""
        etiket_str = f" • <b>{h1_etiket}</b>" if h1_etiket else ""
        temel_satirlar.append(f"🏛️ <b>Banka Değerleme:</b> {pddd_str} | {roe_str}{etiket_str}")
    elif fk is not None:
        fks = sinyal.get("fk_sektor_orani", 0.0)
        iskonto_str = f" <i>(Sektöre göre %{abs(fks)*100:.0f} iskontolu)</i>" if fks <= -0.10 else ""
        temel_satirlar.append(f"📊 <b>Temel F/K       :</b> <b>{fk:.1f}</b>{iskonto_str}")

    temel_satirlar.append(f"📈 <b>Net Kâr Büyümesi:</b> {eps_str}")

    # A4 Çelişki Uyarısı
    if sinyal.get("deger_momentum_celiski"):
        temel_satirlar.append("⚠️ <b>Dikkat:</b> <i>Değerleme ucuz ancak kısa vadede aşırı uzamış!</i>")

    # 2. G1 Mikro Emsal Grubu Bilgi Kartı
    emsal_satirlar = []
    emsal_grubu = html.escape(str(sinyal.get("emsal_grubu", "")))
    if emsal_grubu:
        lider_mi = sinyal.get("emsal_lideri", False)
        lider_str = " 🏆 <b>[Emsal Grubu Lideri]</b>" if lider_mi else ""
        rel_emsal = sinyal.get("rel_str_emsal_5d", 0.0)
        emsal_satirlar.append(f"👥 <b>Mikro Emsal Grubu:</b> {emsal_grubu}{lider_str} (5g Fark: %{rel_emsal*100:+.1f})")

    # 3. B1 Teknik İndikatör & CMF & Squeeze Kartı
    teknik_satirlar = []
    rsi = sinyal.get("rsi_14")
    vol_rat = sinyal.get("vol_ratio_20")
    cmf = sinyal.get("cmf_20")
    sq_fired = int(sinyal.get("squeeze_fired", 0))
    sq_on = int(sinyal.get("squeeze_on", 0))

    if cmf is not None:
        cmf_val = float(cmf)
        if cmf_val >= getattr(cfg, "CMF_GUCLU_GIRIS_ESIK", 0.08):
            cmf_str = f"🟢 <b>Güçlü Kurumsal Para Girişi (+{cmf_val:.2f})</b>"
        elif cmf_val >= 0.0:
            cmf_str = f"🟡 <b>Pozitif Para Akışı (+{cmf_val:.2f})</b>"
        else:
            cmf_str = f"🔴 <b>Hafif Negatif ({cmf_val:.2f})</b>"
        teknik_satirlar.append(f"💰 <b>Para Akışı (CMF):</b> {cmf_str}")

    if sq_fired == 1:
        teknik_satirlar.append("🚀 <b>Volatilite Durumu:</b> 🔥 <b>Sıkışmadan Yukarı Patladı (Squeeze Breakout)!</b>")
    elif sq_on == 1:
        teknik_satirlar.append("⚡ <b>Volatilite Durumu:</b> ⏳ <b>Enerji Sıkışmasında (Patlama Yakın)</b>")

    if rsi is not None:
        rsi_durum = "<i>(Aşırı Alım)</i>" if rsi > 70 else ("<i>(Fırsat Bölgesi)</i>" if rsi < 35 else "")
        vol_str = f"Hacim: <b>{vol_rat:.1f}x</b>" if vol_rat else ""
        teknik_satirlar.append(f"📐 <b>Teknik Gösterge  :</b> RSI(14): <b>{rsi:.1f}</b> {rsi_durum} | {vol_str} | R:R: <b>{gercek_rr:.2f}</b>")

    # Korelasyon Kalkanı Bilgi Satırı
    corr_satir = ""
    if "max_korelasyon" in sinyal:
        max_c = sinyal["max_korelasyon"]
        eslesen = html.escape(str(sinyal.get("korelasyon_eslesen", "")).replace(".IS", ""))
        if max_c > 0:
            corr_satir = f"🛡️ <b>Korelasyon Kalkanı:</b> %{max_c*100:.0f} (Güvenli) • <i>Açık: #{eslesen}</i>\n"
        else:
            corr_satir = f"🛡️ <b>Korelasyon Kalkanı:</b> 🟢 Bağımsız Varlık (Güvenli)\n"

    kartlar_blok = ""
    if temel_satirlar:
        kartlar_blok += "\n".join(temel_satirlar) + "\n"
    if emsal_satirlar:
        kartlar_blok += "\n".join(emsal_satirlar) + "\n"
    if teknik_satirlar:
        kartlar_blok += "\n".join(teknik_satirlar) + "\n"
    if corr_satir:
        kartlar_blok += corr_satir

    tp2_pct = ((tp2 - limit_fiyat) / limit_fiyat) * 100.0

    mesaj = (
        f"🎯 <b>YENİ SNIPER AL SİNYALİ: #{sembol}</b>{vip_etiket}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Sinyal Türü  :</b> {sinyal_turu} • <b>Karar:</b> {karar_aksiyonu}\n"
        f"📊 <b>İşlem Skoru :</b> {skor_emoji} <b>{skor} / 100</b>\n"
        f"🤖 <b>Model Güveni:</b> %{olasilik_pct:.1f} (Kalibre Ensemble)\n"
        f"🏢 <b>Sektör      :</b> {sektor}\n"
        f"📅 <b>Sinyal Tarih:</b> {tarih}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{kartlar_blok}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Son Kapanış :</b> {fiyat:.2f} TL\n"
        f"⏱️ <b>Limit Giriş :</b> <b>T+1 Sabah Açılış</b> (Limit: <b>{limit_fiyat:.2f} TL</b>)\n"
        f"🎯 <b>Kâr Hedefi 1:</b> <b>{tp1:.2f} TL</b> (+%{tp1_pct:.1f}) ➔ <i>%50 Sat & Stop Maliyete Çek</i>\n"
        f"🎯 <b>Kâr Hedefi 2:</b> <b>{tp2:.2f} TL</b> (+%{tp2_pct:.1f}) ➔ <i>Kalan %50 Trend Takibi</i>\n"
        f"🛑 <b>Zarar Durdur:</b> <b>{sl:.2f} TL</b> (-%{abs(sl_pct):.1f}) ➔ <i>(TP1 sonrası Stop: {limit_fiyat:.2f} TL)</i>\n"
        f"⏳ <b>Zaman Stopu :</b> 5 İşlem Günü\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <b>Piyasa Rejimi :</b> {piyasa_rejimi}\n"
        f"🌐 <b>VIX Makro Risk:</b> {vix_emoji} {vix_durum}\n"
        f"📰 <b>KAP Durumu    :</b> {kap_emoji} {kap_riski} Risk\n"
    )

    if sinyal.get("kap_haber_ozeti"):
        haber_txt = html.escape(str(sinyal['kap_haber_ozeti'][0][:60]))
        mesaj += f"<i>Haber: {haber_txt}...</i>\n"

    mesaj += (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>KRİTİK KURALLAR:</b>\n"
        f"• <i>T+1 sabahında %4'ten büyük açılış gap'i varsa işlemi İPTAL ediniz.</i>\n"
        f"• <i>Limit fiyat ({limit_fiyat:.2f} TL) aşılırsa gün içi peşinden koşmayınız.</i>\n"
        f"• <i>Kasa riski maksimum %0.5 olacak şekilde lot ayarlayınız.</i>\n"
        f"• <i>TP1'e ulaşıldığında adedin %50'sini satıp Stop seviyesini derhal {limit_fiyat:.2f} TL maliyetine çekiniz.</i>"
    )
    return mesaj



def _uret_progress_bar(canli_fiyat: float, maliyet: float, sl: float, tp: float) -> str:
    """
    Hissenin canlı fiyatının Alış Maliyeti ile Kâr Hedefi (TP) veya Stop-Loss (SL)
    arasındaki konumunu finansal olarak kusursuz, anlaşılır bir görsel çubukla gösterir.
    """
    # 1. Kâr Hedefine Ulaşıldı
    if canli_fiyat >= tp:
        return "🎉 <b>Hedefe Ulaşıldı (%100+)</b> 🏁[🟩🟩🟩🟩🟩🟩🟩🟩]🎯 <i>(Kâr Satış Bölgesi)</i>"

    # 2. Hissede Kârdayız (Canlı >= Maliyet) -> Hedefe Giden Yol
    if canli_fiyat >= maliyet:
        hedef_mesafe = tp - maliyet
        alinan_yol = canli_fiyat - maliyet
        kat_edilen_pct = min(100, max(0, int(round((alinan_yol / hedef_mesafe) * 100)))) if hedef_mesafe > 0 else 0
        filled = max(1, min(8, int(round(kat_edilen_pct / 100.0 * 8))))
        bar = "🟩" * filled + "⬜" * (8 - filled)
        kalan_pay_pct = max(0.0, ((tp - canli_fiyat) / canli_fiyat) * 100.0)

        if kat_edilen_pct >= 85:
            etiket = f"🚀 <b>Hedefe Çok Yakın (%{kat_edilen_pct} Kat Edildi)</b>"
        elif kat_edilen_pct >= 50:
            etiket = f"🟢 <b>Hedef Yolunda (%{kat_edilen_pct} Kat Edildi)</b>"
        elif kat_edilen_pct >= 20:
            etiket = f"🟢 <b>Kârda İlerliyor (%{kat_edilen_pct} Kat Edildi)</b>"
        else:
            etiket = f"🟡 <b>Maliyet Seviyesinde (%{kat_edilen_pct} Kat Edildi)</b>"

        return f"{etiket} 🏁[{bar}]🎯 <i>(Hedefe Kalan: %{kalan_pay_pct:.1f})</i>"

    # 3. Hissede Zarardayız (Canlı < Maliyet) -> Stop'a Doğru Risk Alanı
    else:
        # Stop seviyesinin altına inilmiş mi?
        if canli_fiyat < sl:
            stop_alt_pct = ((sl - canli_fiyat) / sl) * 100.0
            return f"🚨 <b>Stop Seviyesinin Altında (-%{stop_alt_pct:.1f})</b> 🛑[🟥🟥🟥🟥🟥🟥🟥🟥] <i>(Zarar Kes / Destek Kırıldı)</i>"
        else:
            # Maliyet ile Stop arasında
            stop_mesafe = maliyet - sl
            kayip_yol = maliyet - canli_fiyat
            risk_pct = min(100, max(0, int(round((kayip_yol / stop_mesafe) * 100)))) if stop_mesafe > 0 else 0
            filled = max(1, min(8, int(round(risk_pct / 100.0 * 8))))
            bar = "🟥" * filled + "⬜" * (8 - filled)
            stopa_kalan_pct = max(0.1, ((canli_fiyat - sl) / canli_fiyat) * 100.0)

            if risk_pct >= 75:
                etiket = f"⚠️ <b>Stop Sınırında (%{risk_pct} Risk)</b>"
            else:
                etiket = f"🟡 <b>Maliyetin Hafif Altında (%{risk_pct} Risk)</b>"

            return f"{etiket} 🛑[{bar}] <i>(Stopa %{stopa_kalan_pct:.1f} pay kaldı)</i>"


def formatla_master_pnl_mesaji(
    canli_pozisyonlar: List[Dict[str, Any]],
    toplam_kasa: float = 100_000.0,
    piyasa_rejimi: str = "GUCLU_YUKSELIS"
) -> str:
    """
    Fon Yöneticisi & VIP Terminal Seviyesinde Canlı Portföy ve Risk Raporu.
    Her satırı Türkçe açıklamalı ve eylem odaklıdır.
    """
    simdi_str = datetime.now().strftime("%d.%m.%Y | %H:%M:%S")

    if not canli_pozisyonlar:
        return (
            f"🏛️ <b>BIST SNIPER — CANLI PORTFÖY RAPORU</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 {simdi_str}\n"
            f"💰 <b>Kayıtlı Kasa:</b> {toplam_kasa:,.0f} TL\n"
            f"🛡️ <b>Piyasa Rejimi:</b> 🟢 {piyasa_rejimi}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Şu an portföyünüzde açık pozisyon bulunmamaktadır.</i>\n"
            f"<i>Sermayeniz nakitte güvenle korunmaktadır.</i>\n\n"
            f"💡 <i>Yeni alım fırsatlarını taramak için aşağıdaki <b>[ 🎯 Sniper Tara ]</b> butonuna basabilirsiniz.</i>"
        )

    toplam_hissedeki_tutar = sum(p["anlik_fiyat"] * p["lot_adedi"] for p in canli_pozisyonlar)
    hisse_payi_pct = (toplam_hissedeki_tutar / toplam_kasa) * 100.0 if toplam_kasa > 0 else 0.0
    nakit = max(0.0, toplam_kasa - toplam_hissedeki_tutar)
    nakit_pct = (nakit / toplam_kasa) * 100.0 if toplam_kasa > 0 else 0.0

    toplam_pnl_tl = sum(p["anlik_pnl_tl"] for p in canli_pozisyonlar)
    toplam_kasa_pnl_pct = (toplam_pnl_tl / toplam_kasa) * 100.0 if toplam_kasa > 0 else 0.0

    # Masa Riski (Tüm hisseler stop olursa anlık fiyata göre kaybedilecek max tutar)
    toplam_stop_kaybi_tl = sum(max(0.0, (p["anlik_fiyat"] - p["sl_stop"]) * p["lot_adedi"]) for p in canli_pozisyonlar)
    toplam_risk_pct = (toplam_stop_kaybi_tl / toplam_kasa) * 100.0 if toplam_kasa > 0 else 0.0

    pnl_renk = "🟢" if toplam_pnl_tl >= 0 else "🔴"

    # Öncelikli Aksiyon Radarı
    oncelikli_uyarilar = []
    for p in canli_pozisyonlar:
        s = p["sembol"].replace(".IS", "")
        canli_f = p["anlik_fiyat"]
        maliyet_f = p["giris_fiyati"]
        sl_f = p["sl_stop"]
        tp_f = p["tp_hedef"]
        tp_mesafe = p.get("tp_mesafe_%", 10.0)
        sl_mesafe = p.get("sl_mesafe_%", 10.0)

        if canli_f < sl_f:
            stop_alt_pct = ((sl_f - canli_f) / sl_f) * 100.0
            oncelikli_uyarilar.append(f"• 🚨 <b>#{s}</b> Stop seviyesinin %{stop_alt_pct:.1f} altında (Zarar Durdur / Destek Kırıldı)!")
        elif sl_mesafe <= 3.5:
            oncelikli_uyarilar.append(f"• ⚠️ <b>#{s}</b> desteği test ediyor (Stopa %{sl_mesafe:.1f} pay kaldı).")
        elif tp_mesafe <= 5.0 and canli_f >= maliyet_f:
            tp_kar_tl = (tp_f - maliyet_f) * p["lot_adedi"]
            oncelikli_uyarilar.append(f"• 🎯 <b>#{s}</b> kâr hedefine çok yakın (Kalan Pay: %{tp_mesafe:.1f} ➔ +{tp_kar_tl:,.0f} TL)!")

    mesaj = (
        f"🏛️ <b>BIST SNIPER — MASTER PORTFÖY & RİSK TERMİNALİ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Tarih:</b> {simdi_str} • <b>BIST Trend:</b> 🟢 {piyasa_rejimi}\n"
        f"💰 <b>Kayıtlı Kasa:</b> {toplam_kasa:,.0f} TL  |  💼 <b>Hissede:</b> {toplam_hissedeki_tutar:,.0f} TL (%{hisse_payi_pct:.1f})  |  💵 <b>Nakit:</b> {nakit:,.0f} TL (%{nakit_pct:.1f})\n"
        f"📈 <b>Toplam Net K/Z:</b> {pnl_renk} <b>{toplam_pnl_tl:+,.1f} TL (%{toplam_kasa_pnl_pct:+.1f} Portföy Getirisi)</b>\n"
        f"🛡️ <b>Toplam Masa Riski:</b> -%{toplam_risk_pct:.1f} Kasa <i>(Tüm stoplar patlasa max kayıp: -{toplam_stop_kaybi_tl:,.0f} TL)</i>\n"
    )

    if oncelikli_uyarilar:
        mesaj += f"\n🚨 <b>ÖNCELİKLİ HAREKET RADARI:</b>\n" + "\n".join(oncelikli_uyarilar) + "\n"

    mesaj += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Hisse Kartları
    for p in canli_pozisyonlar:
        s = p["sembol"].replace(".IS", "")
        lot = p["lot_adedi"]
        maliyet = p["giris_fiyati"]
        canli_f = p["anlik_fiyat"]
        pnl_pct = p["anlik_pnl_%"]
        pnl_tl = p["anlik_pnl_tl"]
        tp = p["tp_hedef"]
        sl = p["sl_stop"]
        tp_mesafe = p["tp_mesafe_%"]
        sl_mesafe = p["sl_mesafe_%"]
        gun = p["elde_tutma_gun"]
        poz_degeri = canli_f * lot

        c_emoji = "🟢" if pnl_pct >= 0 else "🔴"
        progress_bar = _uret_progress_bar(canli_f, maliyet, sl, tp)

        # TP'ye ulaşırsa kazanılacak net TL
        tp_net_kar = (tp - maliyet) * lot

        # Kâr koruma veya Stop
        if sl > maliyet:
            kilitli_kar = (sl - maliyet) * lot
            sl_metin = f"🛑 <b>Kâr Koruma (SL):</b> {sl:.2f} TL <i>(Kâr Kilitli: <b>+{kilitli_kar:,.0f} TL</b> • Sıfır Risk)</i>"
        else:
            sl_kayip = (maliyet - sl) * lot
            sl_metin = f"🛑 <b>Stop-Loss (SL)  :</b> {sl:.2f} TL <i>(Risk Limiti: <b>-{sl_kayip:,.0f} TL</b>)</i>"

        # Aksiyon Durumu
        if sl > maliyet:
            if canli_f < sl:
                durum_notu = f"⚠️ Kâr Koruma Sınırında ({sl:.2f} TL) — Kâr Satışı Değerlendirilebilir (+{pnl_tl:,.0f} TL)"
            elif tp_mesafe <= 5.0:
                durum_notu = f"🎯 Hedefe Çok Yakın (Kalan %{tp_mesafe:.1f}) — Kâr Satışı Değerlendirilebilir"
            else:
                durum_notu = f"🚀 Kârda Güçlü Trend — Kâr Koruma ({sl:.2f} TL) ile Taşınıyor"
        else:
            if canli_f >= tp:
                durum_notu = "🎉 Hedefe Ulaşıldı — Kâr Satışı Gerçekleştirebilirsiniz"
            elif tp_mesafe <= 4.0:
                durum_notu = f"🎯 Hedefe Yaklaşıyor (Kalan %{tp_mesafe:.1f}) — Kâr Satışı Düşünülebilir"
            elif canli_f < sl:
                durum_notu = "🚨 Stop Sınırının Altında — Disiplinli Zarar Durdurma Takip Edilmeli"
            elif sl_mesafe <= 3.5:
                durum_notu = f"⚠️ Destek Sınırında (Stopa %{sl_mesafe:.1f}) — Desteği Yakından İzleyiniz"
            elif pnl_pct >= 2.0:
                durum_notu = "🟢 Yükseliş Kanalında — Pozisyonu Koruyunuz"
            else:
                durum_notu = "🟡 Maliyet Bölgesinde — Pozisyon Dengede"

        is_vip = (s in cfg.VIP_HISSELER or f"{s}.IS" in cfg.VIP_HISSELER)
        vip_tag = " 👑 <b>[VIP]</b>" if is_vip else ""

        mesaj += (
            f"📌 <b>#{s}</b>{vip_tag} (<b>{lot:,} Lot</b> • <b>{poz_degeri:,.0f} TL</b> • Süre: <b>{gun}/5 Gün</b>)\n"
            f"  • 💵 <b>Alış Maliyeti :</b> {maliyet:.2f} TL ➔ <b>Canlı Fiyat:</b> {canli_f:.2f} TL\n"
            f"  • {c_emoji} <b>Net Kâr/Zarar :</b> <b>%{pnl_pct:+.2f} ({pnl_tl:+,.1f} TL)</b>\n"
            f"  • 🎯 <b>Kâr Hedefi (TP):</b> <b>{tp:.2f} TL</b> <i>(Kalan Pay: %{tp_mesafe:.1f} ➔ <b>+{tp_net_kar:,.0f} TL Kâr</b>)</i>\n"
            f"  • {sl_metin}\n"
            f"  • 📍 <b>Hedefe İlerleme :</b> {progress_bar}\n"
            f"  • 💡 <b>Aksiyon/Durum :</b> <i>{durum_notu}</i>\n\n"
        )

    mesaj += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return mesaj



def formatla_cikis_mesaji(islem: Dict[str, Any]) -> str:
    """
    Pozisyon kapandığında gönderilecek bildirim şablonu.
    """
    sembol = islem["sembol"].replace(".IS", "")
    cikis_nedeni = islem["cikis_nedeni"]
    giris_fiyat = islem["giris_fiyati"]
    cikis_fiyat = islem["cikis_fiyati"]
    net_getiri = islem["net_getiri_%"]
    net_tl = islem.get("net_kar_zarar_tl", 0.0)
    gun = islem["elde_tutma_gun"]

    if "TP" in cikis_nedeni:
        durum_emoji = "🎉 <b>HEDEF GERÇEKLEŞTİ (TP - KÂR ALINDI)</b>"
    elif "SL" in cikis_nedeni:
        durum_emoji = "🛑 <b>STOP-LOSS ÇALIŞTI (ZARAR KESİLDİ)</b>"
    else:
        durum_emoji = "⏳ <b>ZAMAN AŞIMI ÇIKIŞI (5 GÜN DOLDU)</b>"

    kar_emoji = "🟢" if net_getiri > 0 else "🔴"

    mesaj = (
        f"{durum_emoji}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Hisse       :</b> #{sembol}\n"
        f"📥 <b>Giriş Fiyatı:</b> {giris_fiyat:.2f} TL\n"
        f"📤 <b>Çıkış Fiyatı:</b> {cikis_fiyat:.2f} TL\n"
        f"⏱️ <b>Elde Tutma  :</b> {gun} İşlem Günü\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{kar_emoji} <b>Net Getiri   :</b> %{net_getiri:+.2f} ({net_tl:+,.1f} TL)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Pozisyon kapatılmıştır. Nakit serbest bırakıldı.</i>"
    )
    return mesaj


def formatla_gunluk_bulten(
    tarih: str,
    portfoy_degeri: float,
    gunluk_getiri_pct: float,
    acik_pozisyonlar: List[Dict[str, Any]],
    piyasa_rejimi: str,
    vix_durum: str,
) -> str:
    """
    Her akşam 18:45'te gönderilen Günlük Kapanış Özeti.
    """
    vix_emoji = "🟢" if vix_durum == "NORMAL" else "🔴"

    mesaj = (
        f"📋 <b>GÜNLÜK PİYASA & PORTFÖY BÜLTENİ</b>\n"
        f"📅 Tarih: {tarih}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Portföy Değeri:</b> {portfoy_degeri:,.0f} TL (%{gunluk_getiri_pct:+.2f})\n"
        f"🏛️ <b>Piyasa Rejimi:</b> {piyasa_rejimi}\n"
        f"🌐 <b>Küresel VIX   :</b> {vix_emoji} {vix_durum}\n"
        f"📊 <b>Açık Pozisyon :</b> {len(acik_pozisyonlar)} adet\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    if acik_pozisyonlar:
        mesaj += "<b>Açık İşlemler:</b>\n"
        for p in acik_pozisyonlar:
            s = p["sembol"].replace(".IS", "")
            g = p["elde_tutma_gun"]
            mesaj += f"  • <b>#{s}</b> | Gün: {g}/5 | Giriş: {p['giris_fiyati']:.2f} TL\n"
    else:
        mesaj += "<i>Şu an aktif açık pozisyon bulunmuyor (Nakit korumada).</i>\n"

    return mesaj
