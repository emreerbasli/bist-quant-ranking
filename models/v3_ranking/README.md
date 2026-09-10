# models/v3_ranking — Production-Candidate Model
> ⚠️ **UYARI:** BU KLASÖR **PRODUCTION-CANDIDATE** STATÜSÜNDEDİR.  
> **CANLI SERMAYE KESİNLİKLE YOKTUR. SADECE PAPER TRADING VE İZLEME AŞAMASINDADIR.**

---

## 1. Model Mimarisi ve Kimlik Kartı

- **Model Tipi:** LightGBM Ranker (`LGBMRanker` — LambdaMART NDCG Optimizasyonu)
- **Aday Adı:** `Aday 1 (Aşırı Muhafazakâr Sığ Ağaç)`
- **Hiperparametreler:**
  - `max_depth = 2`
  - `num_leaves = 3`
  - `learning_rate = 0.03`
  - `n_estimators = 60`
  - `min_child_samples = 15`
  - `reg_lambda = 1.0` (L2 Ridge Düzenlileştirmesi)
- **Eğitim Penceresi:** `2018-09-01` $\rightarrow$ `2025-05-31` (27 Çeyrek)
- **Seçim Gerekçesi (Tie-Breaker):** 4 adaylı Purged Walk-Forward CV yarışında, Aday 2 ile arasındaki NDCG farkı (%+0.89) sözleşme eşiği olan %2.5'in altında kalmış; daha düşük fold volatilitesi (0.0540 vs 0.0835) ve sıfıra yakın aşırı uyum riski nedeniyle Aday 1 seçilmiş ve dondurulmuştur.

---

## 2. Girdi Faktörleri (Feature Set)

1. **`z_pb` (Ters P/B):** Gain Payı **%57.3** (Ana değerleme ve enflasyonist varlık çapası).
2. **`z_borc` (-Net Borç/EBITDA):** Gain Payı **%19.4** (Finansal sağlık ve faiz şoku kalkanı).
3. **`z_mom` (12-1 Momentum):** Gain Payı **%13.7** (Fiyat eğilimi ve fon akışı).
4. **`z_roe` (Özsermaye Kârlılığı):** Gain Payı **%3.7** (Kâr üretme kapasitesi).
5. **`usd_mom_60` (USD 60g İvmesi):** Gain Payı **%3.6** (Makro kur şoku rejim filtresi).
6. **`z_fcf` (FCF Verimi):** Gain Payı **%1.9** (Serbest nakit akım desteği).
7. **`reel_faiz` (TCMB Reel Politika Faizi):** Gain Payı **%0.4** (Makro likidite durumu).

---

## 3. İKİ DÜRÜST KURUMSAL UYARI (KAYITLARA GEÇEN ŞERHLER)

> [!WARNING]
> ### 1. Küçük Kilit Kutu Örneklemi ve Beta Sıçraması Riski
> Kilit kutu dönemi **$n=5$ çeyrektir** (15 ay). Küçük örneklemlerde Sharpe 2-3 aralığında çıkan sonuçlar geniş bir belirsizlik payı taşır.
> Özellikle **2025Q2 döneminde** tüm stratejiler (model +%24.7, kaba skor +%37.4, placebo +%29.3, BIST100 +%25.2) birlikte sıçramıştır. Bu durum, o çeyrekteki getirinin saf bir model seçim alfasından ziyade **genel bir piyasa/beta rüzgarı** olduğunu göstermektedir. Modelin gerçek alfa gücü ancak uzun soluklu paper trading testinde netleşecektir.

> [!WARNING]
> ### 2. Basit Kural Kıyaslaması ve ML'in Gerçek Rolü
> $K=20$ portföy boyutunda basit kaba formülün (-PB+ROE+Mom) ham p-değeri (**$p=0.000$**), ML modelinden (**$p=0.060$**) istatistiksel olarak daha güçlü çıkmıştır.
> Dolayısıyla `LGBMRanker`'ın katkısı *"her boyutta kesin getiri üstünlüğü"* olarak değil; **drawdown kontrolü (%0.0 Max DD)** ve faizlerin %50'de kaldığı **2026 stres döneminde borçlu şirketleri ayıklayarak sermayeyi koruma dayanıklılığı** olarak çerçevelenmelidir.

---

## 4. KRİTİK KURUMSAL SINIR (İHLAL EDİLEMEZ)

> [!CAUTION]
> ### 🛑 KESİN OPERASYONEL SINIR
> **Bu sistem SADECE bildirim gönderir — hiçbir şekilde otomatik emir veya al-sat kararı VERMEZ.**  
> - Sistemin hiçbir aracı kurum API bağlantısı veya doğrudan piyasaya emir gönderme yetkisi yoktur.  
> - Tüm çıktılar (sıralamalar, rebalance listeleri, drift alarmları) yalnızca kantitatif bir **karar destek sistemi (decision support)** ve **sanal portföy (paper trading)** mahiyetindedir.  
> - Nihai al-sat, portföy dağılımı ve risk yönetimi kararları tamamen yatırımcının kendi hür iradesi ve takdirindedir.

---

## 5. Operasyonel Modüller ve Mimari

1. **`models/v3_ranking/ranking_pipeline.py`:**
   - Dondurulmuş LGBMRanker modelini kullanarak güncel Point-in-Time (PIT) bilançolar ve piyasa verileri üzerinden hisse sıralaması ve $K=10$ portföyünü üretir.
2. **`models/v3_ranking/drift_monitor.py`:**
   - Üç katmanlı denetim: Makro Rejim (Reel Faiz $\le -\%10$, $USD\_Mom_{60} \ge +\%20$), Model Skor Kayması ($|Z| > 2.5$) ve Sharpe Bozulması ($Sharpe \le 0.75$).
3. **`models/v3_ranking/paper_trader.py`:**
   - Portföy durumunu `paper_portfolio.json` üzerinde saklar, 60 günlük asgari tutma süresini ve zirveden %-25 drawdown devre kesicisini (%50 nakit kalkanı) simüle eder. Her kontrolde terminal kartı ve Telegram bildirimi üretir.
4. **`run_paper_trader.py`:**
   - 14 günlük periyotlarla çalışan zamanlayıcı servis. Hafta sonu veya BIST resmi tatillerinde çalışmayı atlar. Her icrada `logs/paper_trading_service.log` dosyasına `"sistem çalıştı"` teyidi yazar.
5. **`bot/telegram_bot.py`:**
   - `mesaj_gonder(metin)` fonksiyonu üzerinden `paper_trader.py` özet kartını Telegram botuna iletir. Token ve chat ID bilgileri kod içine yazılmaz; `.env`/`config.py` üzerinden güvenli okunur.

---

## 6. İlgili Dosyalar ve Kanıtlar

- 📜 [KILIT_KUTU_KANIT.md](KILIT_KUTU_KANIT.md) — Kilit kutu resmi sözleşmesi, test tutanağı ve 4/4 onay kanıtı.
- 📦 `winning_lgbm_ranker.joblib` — Dondurulmuş ikili model dosyası.
- ⚙️ [ranking_pipeline.py](ranking_pipeline.py) — Sıralama inferans modülü.
- 🛡️ [drift_monitor.py](drift_monitor.py) — Model ve makro denetim motoru.
- 💼 [paper_trader.py](paper_trader.py) — Portföy icra ve takip motoru.


