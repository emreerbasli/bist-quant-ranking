"""
bot/telegram_bot.py — FAZ 7: BIST Sniper Canlı Telegram Botu & VIP Terminal
=============================================================================
Plan referansı: FAZ 7 (bist_sinyal_botu_proje_plani_v2.md)

Komutlar:
  /start  — Botu başlatır ve interaktif karşılama menüsünü açar.
  /durum  — Fon Yöneticisi & VIP Terminal seviyesinde canlı PnL ve risk raporu.
  /tara   — Manuel anlık günlük tarama çalıştırır ve üretilen sinyalleri döker.
  /bulten — Piyasa rejimi, VIX durumu ve genel portföy özetini gönderir.
  /saglik — Sistem ve veri sağlık denetimi (Health Check).
  /yardim — Risk kuralları ve limit emir kılavuzu.

İnteraktif Butonlar (Inline Keyboard):
  [ 🔄 Canlı Yenile ]  [ 🎯 Sniper Tara ]  [ 🛡️ Sistem Sağlığı ]  [ 📖 Risk Kılavuzu ]

Zamanlayıcı (APScheduler / JobQueue):
  - Hafta içi her gün tam saat 18:45'te otomatik tetiklenir.
"""

import sys
import html
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
import pandas as pd
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    JobQueue,
    filters,
)

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg
from bot.paper_trader import (
    anlik_pnl_durumu_cek, yeni_pozisyon_ac, guncelle_gunluk_paper_trading,
    getir_acik_pozisyonlar, bakiye_getir
)
from bot.telegram_messages_tr import (
    formatla_yeni_sinyal_mesaji, formatla_cikis_mesaji,
    formatla_gunluk_bulten, formatla_master_pnl_mesaji
)
from bot.health_check import health_check_verisi, formatla_admin_health_mesaji
from run_daily import calistir_gunluk
from tasks.haftalik_kalibrasyon import haftalik_kalibrasyon_calistir


def _ana_butonlar() -> InlineKeyboardMarkup:
    """Telegram mesajlarının altındaki interaktif inline buton paneli."""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Canlı Yenile", callback_data="refresh_durum"),
            InlineKeyboardButton("🎯 Sniper Tara", callback_data="btn_tara"),
        ],
        [
            InlineKeyboardButton("🛡️ Sistem Sağlığı", callback_data="btn_saglik"),
            InlineKeyboardButton("📖 Risk Kılavuzu", callback_data="btn_yardim"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def _kalici_klavye_butonlari() -> ReplyKeyboardMarkup:
    """Telegram sohbetinin altında her an hazır duran kalıcı menü klavyesi."""
    keyboard = [
        [KeyboardButton("📊 Portföy & Durum"), KeyboardButton("🎯 Sniper Tara")],
        [KeyboardButton("🛡️ Sistem Sağlığı"), KeyboardButton("📖 Risk Kılavuzu")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)


# ─── KOMUT FONKSİYONLARI ─────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start komutu karşılama mesajı."""
    user_name = update.effective_user.first_name if update.effective_user else "Yatırımcı"
    msg = (
        f"🎯 <b>BIST SNIPER VIP TERMİNALİ'NE HOŞ GELDİNİZ, {user_name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Bu bot, <b>LightGBM + Random Forest + Logistic Regression</b> tabanlı "
        f"kalibre edilmiş makine öğrenimi modeli ile BIST hisselerinde yüksek isabetli "
        f"kısa vadeli (1.5x ATR TP / 1.0x ATR SL / 5 Gün) <b>Sniper</b> fırsatlarını tespit eder.\n\n"
        f"📌 <b>KULLANILABİLİR İŞLEMLER:</b>\n"
        f"Aşağıdaki kalıcı menü butonlarına veya mesaj altındaki butonlara dokunarak anında işlem yapabilirsiniz:\n"
        f"• <b>📊 Portföy & Durum</b> — VIP Portföy & Canlı Risk Raporu\n"
        f"• <b>🎯 Sniper Tara</b> — {len(cfg.HISSELER)} hisselik anlık yapay zeka taraması\n"
        f"• <b>🛡️ Sistem Sağlığı</b> — Veri ve model sağlık denetimi (Health Check)\n"
        f"• <b>📖 Risk Kılavuzu</b> — Disiplin ve limit emir rehberi\n\n"
        f"⏰ <i>Sistem her iş günü saat 18:45'te otomatik olarak piyasa analizini tamamlar.</i>"
    )
    if update.message:
        await update.message.reply_html(msg, reply_markup=_kalici_klavye_butonlari())



async def cmd_durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/durum — Açık pozisyonların Fon Yöneticisi & VIP Terminal formatında canlı raporu."""
    if not update.message:
        return
    wait_msg = await update.message.reply_html("⏳ <i>Canlı portföy ve son fiyatlar alınıyor...</i>")

    try:
        canli_liste = await asyncio.to_thread(anlik_pnl_durumu_cek)
        kasa = await asyncio.to_thread(bakiye_getir, 100_000.0)

        # Piyasa rejimini oku
        rejim = "GUCLU_YUKSELIS"
        try:
            dosya_xu100 = cfg.DATA_FEAT / "THYAO_IS.parquet"
            if dosya_xu100.exists():
                df_temp = pd.read_parquet(dosya_xu100)
                rejim = str(df_temp.get("xu100_rejim", pd.Series(["GUCLU_YUKSELIS"])).iloc[-1])
        except Exception:
            pass

        mesaj = formatla_master_pnl_mesaji(canli_liste, toplam_kasa=kasa, piyasa_rejimi=rejim)
        
        try:
            await wait_msg.delete()
        except Exception:
            pass
        
        await update.message.reply_html(mesaj, reply_markup=_ana_butonlar())
    except Exception as e:
        logger.error(f"cmd_durum hatası: {e}", exc_info=True)
        await update.message.reply_html(f"❌ <b>Portföy raporu alınamadı:</b> <code>{html.escape(str(e))}</code>")


async def cmd_tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/tara — Manuel anlık günlük tarama çalıştırır."""
    if not update.message:
        return
        
    wait_msg = await update.message.reply_html(f"🔍 <i>BIST Sniper taraması başlatıldı ({len(cfg.HISSELER)} hisse taranıyor, ~25 sn)...</i>")
    
    try:
        adaylar = await asyncio.to_thread(calistir_gunluk, min_islem_skoru=60)
        
        try:
            await wait_msg.delete()
        except Exception:
            pass
        
        if not adaylar:
            await update.message.reply_html(
                "🛡️ <b>TARAMA TAMAMLANDI — SİNYAL YOK</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Bugün Sniper kriterlerine (Güven en az %80, Fikir Birliği Sapması en fazla 0.10, İşlem Skoru en az 60) "
                "uygun risksiz alım fırsatı bulunamadı.\n\n"
                "<i>Sniper stratejisi gereği zorlama işlem açılmaz, sermaye nakitte korunur.</i>",
                reply_markup=_ana_butonlar()
            )
            return

        await update.message.reply_html(f"🎯 <b>{len(adaylar)} ADET SNIPER SİNYALİ BULUNDU:</b>")
        for aday in adaylar:
            msg = formatla_yeni_sinyal_mesaji(aday)
            try:
                await update.message.reply_html(msg)
            except Exception as pe:
                logger.error(f"HTML gönderme hatası: {pe}")
                await update.message.reply_text(msg)

    except Exception as e:
        logger.error(f"Tarama hatası: {e}", exc_info=True)
        hata_str = html.escape(str(e))
        await update.message.reply_html(f"❌ <b>Tarama sırasında bir hata oluştu:</b>\n<code>{hata_str}</code>")


async def cmd_saglik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/saglik — Sistem ve veri sağlık denetimi."""
    if not update.message:
        return
        
    wait_msg = await update.message.reply_html("🛡️ <i>Sistem sağlık denetimi (Health Check & PSI Drift) yapılıyor...</i>")
    try:
        hc = await asyncio.to_thread(health_check_verisi)
        msg = formatla_admin_health_mesaji(hc)
        try:
            await wait_msg.delete()
        except Exception:
            pass
        await update.message.reply_html(msg, reply_markup=_ana_butonlar())
    except Exception as e:
        logger.error(f"Sağlık denetimi hatası: {e}", exc_info=True)
        await update.message.reply_html(f"❌ <b>Sağlık denetimi hatası:</b> <code>{html.escape(str(e))}</code>")


async def cmd_yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/yardim — Kullanım ve disiplin kuralları."""
    if not update.message:
        return
        
    msg = (
        f"📖 <b>BIST SNIPER BOTU KULLANIM KILAVUZU</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>1. Limit Emir Kuralı:</b> Sinyal geldiğinde akşamdan veya sabah 09:55'te "
        f"maksimum <b>Kapanış Fiyatı + %0.5</b> limit fiyat belirleyerek emir iletiniz.\n\n"
        f"<b>2. Gap İptal Kuralı:</b> Hisse sabah %4'ten büyük boşlukla (Gap) açılırsa işlemi iptal ediniz.\n\n"
        f"<b>3. Risk Yönetimi:</b> Tek işlemde toplam portföyünüzün en fazla %0.5'ini riske atınız. "
        f"(Lot Sayısı = [Portföy × 0.005] ÷ Stop Mesafesi)\n\n"
        f"<b>4. Çıkış Disiplini:</b> 1.5x ATR Kâr Hedefine, Stop-Loss'a veya 5 gün Zaman Stopu'na "
        f"sadık kalınız. Duygusal müdahale yapmayınız.\n\n"
        f"<i>Bot bir yatırım danışmanı değildir; karar destek yazılımıdır.</i>"
    )
    await update.message.reply_html(msg, reply_markup=_ana_butonlar())


# ─── KALICI KLAVYE METİN İŞLEYİCİSİ ───────────────────────────────────────────

async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcı alt menü klavyesindeki butonlara bastığında ilgili komutu çalıştırır."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if "Portföy & Durum" in text:
        await cmd_durum(update, context)
    elif "Sniper Tara" in text:
        await cmd_tara(update, context)
    elif "Sistem Sağlığı" in text:
        await cmd_saglik(update, context)
    elif "Risk Kılavuzu" in text:
        await cmd_yardim(update, context)


# ─── INLINE BUTON ETKİLEŞİM İŞLEYİCİSİ (CALLBACK QUERY) ─────────────────────

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcı mesaj altındaki inline butonlara bastığında anında ve kesintisiz yanıt verir."""
    query = update.callback_query
    if not query:
        return

    # Telegram timeout'unu engellemek için İLK SATIRDA hemen answer ver
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data

    if data == "refresh_durum":
        try:
            canli_liste = await asyncio.to_thread(anlik_pnl_durumu_cek)
            kasa = await asyncio.to_thread(bakiye_getir, 100_000.0)
            rejim = "GUCLU_YUKSELIS"
            try:
                dosya_xu100 = cfg.DATA_FEAT / "THYAO_IS.parquet"
                if dosya_xu100.exists():
                    df_temp = pd.read_parquet(dosya_xu100)
                    rejim = str(df_temp.get("xu100_rejim", pd.Series(["GUCLU_YUKSELIS"])).iloc[-1])
            except Exception:
                pass

            yeni_mesaj = formatla_master_pnl_mesaji(canli_liste, toplam_kasa=kasa, piyasa_rejimi=rejim)
            try:
                await query.edit_message_text(text=yeni_mesaj, parse_mode="HTML", reply_markup=_ana_butonlar())
            except Exception as edit_err:
                if "Message is not modified" in str(edit_err):
                    await query.answer("ℹ️ Fiyatlar zaten en güncel seviyede (Borsa kapalı).", show_alert=False)
                else:
                    raise edit_err
        except Exception as e:
            logger.error(f"Canlı yenileme hatası: {e}")
            try:
                await query.answer(f"Hata: {e}", show_alert=True)
            except Exception:
                pass

    elif data == "btn_tara":
        if query.message:
            wait_msg = await query.message.reply_html("🔍 <i>BIST Sniper taraması başlatıldı (50 hisse taranıyor, ~20 sn)...</i>")
            try:
                adaylar = await asyncio.to_thread(calistir_gunluk, min_islem_skoru=60)
                try:
                    await wait_msg.delete()
                except Exception:
                    pass

                if not adaylar:
                    await query.message.reply_html(
                        "🛡️ <b>TARAMA:</b> Bugün yeni Sniper sinyali bulunamadı (Nakit korumada).",
                        reply_markup=_ana_butonlar()
                    )
                else:
                    await query.message.reply_html(f"🎯 <b>{len(adaylar)} ADET SNIPER SİNYALİ BULUNDU:</b>")
                    for aday in adaylar:
                        msg = formatla_yeni_sinyal_mesaji(aday)
                        try:
                            await query.message.reply_html(msg)
                        except Exception as parse_err:
                            logger.error(f"HTML mesaj gönderme hatası: {parse_err}")
                            await query.message.reply_text(msg)
            except Exception as e:
                logger.error(f"Tarama hatası: {e}", exc_info=True)
                await query.message.reply_html(f"❌ <b>Tarama hatası:</b> <code>{html.escape(str(e))}</code>")

    elif data == "btn_saglik":
        if query.message:
            try:
                hc = await asyncio.to_thread(health_check_verisi)
                msg = formatla_admin_health_mesaji(hc)
                await query.message.reply_html(msg, reply_markup=_ana_butonlar())
            except Exception as e:
                logger.error(f"Sağlık denetimi hatası: {e}", exc_info=True)
                await query.message.reply_html(f"❌ <b>Sağlık denetimi hatası:</b> <code>{html.escape(str(e))}</code>")

    elif data == "btn_yardim":
        if query.message:
            msg = (
                f"📖 <b>BIST SNIPER BOTU KULLANIM KILAVUZU</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>1. Limit Emir Kuralı:</b> Sinyal geldiğinde akşamdan veya sabah 09:55'te "
                f"maksimum <b>Kapanış Fiyatı + %0.5</b> limit fiyat belirleyerek emir iletiniz.\n\n"
                f"<b>2. Gap İptal Kuralı:</b> Hisse sabah %4'ten büyük boşlukla (Gap) açılırsa işlemi iptal ediniz.\n\n"
                f"<b>3. Risk Yönetimi:</b> Tek işlemde toplam portföyünüzün en fazla %0.5'ini riske atınız.\n\n"
                f"<b>4. Çıkış Disiplini:</b> 1.5x ATR Kâr Hedefine veya Stop-Loss'a sadık kalınız."
            )
            await query.message.reply_html(msg, reply_markup=_ana_butonlar())


# ─── ZAMANLANMIŞ GÖREV (HER İŞ GÜNÜ 18:45) ──────────────────────────────────

async def otomatik_gunluk_analiz_job(context: ContextTypes.DEFAULT_TYPE):
    """Her iş günü 18:45'te JobQueue tarafından tetiklenir."""
    now = datetime.now()
    if now.weekday() >= 5:
        return

    logger.info("Otomatik Günlük Analiz Zamanlayıcısı Çalıştı (18:45)")
    admin_id = cfg.ADMIN_CHAT_ID

    try:
        kapananlar = await asyncio.to_thread(guncelle_gunluk_paper_trading)
        if kapananlar and admin_id:
            for k in kapananlar:
                cikis_msg = formatla_cikis_mesaji(k)
                await context.bot.send_message(chat_id=admin_id, text=cikis_msg, parse_mode="HTML")

        adaylar = await asyncio.to_thread(calistir_gunluk, min_islem_skoru=65)

        if admin_id:
            if adaylar:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"🎯 <b>GÜNÜN SNIPER AL SİNYALLERİ ({len(adaylar)} Adet):</b>",
                    parse_mode="HTML"
                )
                for aday in adaylar:
                    msg = formatla_yeni_sinyal_mesaji(aday)
                    await context.bot.send_message(chat_id=admin_id, text=msg, parse_mode="HTML")
            else:
                kasa = await asyncio.to_thread(bakiye_getir, 100_000.0)
                acik_pozlar = await asyncio.to_thread(getir_acik_pozisyonlar)
                bulten = formatla_gunluk_bulten(
                    tarih=str(now.date()),
                    portfoy_degeri=kasa,
                    gunluk_getiri_pct=0.0,
                    acik_pozisyonlar=acik_pozlar,
                    piyasa_rejimi="GUCLU_YUKSELIS",
                    vix_durum="NORMAL",
                )
                await context.bot.send_message(chat_id=admin_id, text=bulten, parse_mode="HTML", reply_markup=_ana_butonlar())

    except Exception as e:
        logger.error(f"Otomatik günlük analiz hatası: {e}", exc_info=True)
        if admin_id:
            hata_str = html.escape(str(e))
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🚨 <b>GÜNLÜK ANALİZ HATASI:</b>\n<code>{hata_str}</code>",
                parse_mode="HTML"
            )


# ─── FAZ B3: Haftalık Kalibrasyon Job ───────────────────────────────────────

async def haftalik_kalibrasyon_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Her Cumartesi 10:00'da otomatik çalışır. PSI'ya göre kalibrasyon veya tam eğitim yapar."""
    admin_id = cfg.ADMIN_CHAT_ID
    try:
        sonuc = await asyncio.to_thread(haftalik_kalibrasyon_calistir)
        if admin_id:
            await context.bot.send_message(
                chat_id=admin_id,
                text=sonuc["mesaj"],
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"Haftalık kalibrasyon hatası: {e}", exc_info=True)
        if admin_id:
            hata_str = html.escape(str(e))
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🚨 <b>KALİBRASYON HATASI:</b>\n<code>{hata_str}</code>",
                parse_mode="HTML",
            )


# ─── BOTU AYAĞA KALDIRMA ────────────────────────────────────────────────────

def baslat_telegram_botu():
    """Telegram botunu başlatır ve mesajları dinlemeye başlar."""
    token = cfg.TELEGRAM_TOKEN
    
    if not token or token == "your_bot_token_here":
        logger.warning("Telegram Bot Token bulunamadı (.env dosyasını kontrol ediniz).")
        return

    logger.info("Telegram Botu Başlatılıyor...")
    app = ApplicationBuilder().token(token).build()

    # 1. Komut işleyicileri
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("durum",  cmd_durum))
    app.add_handler(CommandHandler("tara",   cmd_tara))
    app.add_handler(CommandHandler("bulten", cmd_durum))
    app.add_handler(CommandHandler("saglik", cmd_saglik))
    app.add_handler(CommandHandler("yardim", cmd_yardim))

    # 2. Kalıcı Klavye Menü Butonları İşleyicisi
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))

    # 3. Buton tıklama işleyicisi (Inline Keyboard Callbacks)
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # 4. Zamanlanmış Görevler (APScheduler / JobQueue)
    job_queue: JobQueue = app.job_queue
    if job_queue:
        import datetime as dt

        # ─── Hafta içi 18:45 Günlük Analiz ──────────────────────────────────
        saat_zamani = dt.time(hour=cfg.CALISMA_SAATI, minute=cfg.CALISMA_DAKIKA)
        job_queue.run_daily(
            otomatik_gunluk_analiz_job,
            time=saat_zamani,
            days=(1, 2, 3, 4, 5),
            name="gunluk_1845_analiz"
        )
        logger.info(f"Telegram JobQueue Zamanlayıcısı Aktif: Her iş günü {cfg.CALISMA_SAATI}:{cfg.CALISMA_DAKIKA:02d}'te çalışacak.")

        # ─── FAZ B3: Cumartesi Haftalık Kalibrasyon ──────────────────────────
        cumartesi_saat = dt.time(hour=10, minute=0)
        job_queue.run_daily(
            haftalik_kalibrasyon_job,
            time=cumartesi_saat,
            days=(6,),          # 6 = Cumartesi
            name="cumartesi_kalibrasyon"
        )
        logger.info("Haftalık Kalibrasyon Zamanlayıcısı Aktif: Her Cumartesi 10:00'da çalışacak.")

    logger.info("✅ VIP Bot başarıyla ayağa kalktı ve Telegram mesajlarını dinliyor!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    baslat_telegram_botu()

