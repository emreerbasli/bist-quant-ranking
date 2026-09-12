# PROJE HAFIZASI VE MİMARİ KARAR TUTANAĞI (PROJECT_MEMORY.md)
*BIST V3.2 Kantitatif Çapraz Sıralama & Karar Destek Sistemi*
*Son Güncelleme: 2026-09-12*

---

> ⚠️ **BU BELGENİN AMACI VE YENİ AI ASİSTANINA TALİMAT:**  
> Bu belge, BIST Sniper / V3 Kantitatif Karar Destek Sistemi projesinin tüm kurumsal hafızasını, matematiksel temellerini, test edilip reddedilen fikirlerin gerekçelerini ve katı operasyonel sınırlarını içerir.  
> Bu sohbet oturumu kapandıktan sonra görevi devralan yeni AI asistanı, kod tabanına tek bir satır dahi yazmadan önce BU DOSYAYI BAŞTAN SONA OKUMAK VE BURADAKİ KARARLARA BAĞLI KALMAKLA YÜKÜMLÜDÜR.  
> Buradaki kararlar teorik tahminler değil; yüzlerce saatlik ampirik testler, Monte Carlo placebo simülasyonları ve kurumsal denetimler sonucunda kanla yazılmış kurallardır.

---

## BÖLÜM 1: PROJENİN AMACI VE KAPSAMI

### 1.1 Ne Yapıyoruz?
* **Hedef:** Borsa İstanbul (BIST) pay piyasasında işlem gören 85+ hisselik seçkin likit evren üzerinde, **Point-in-Time (PIT) temel analiz bilançoları** ve **faktör yatırımı (Factor Investing)** dinamiklerini kullanarak hisseleri göreli performanslarına göre sıralayan bir **Kantitatif Karar Destek Sistemi (Quantitative Decision Support System - DSS)** ve **Sanal Portföy (Paper Trading)** takip motoru işletiyoruz.
* **Çekirdek Felsefe:** Gelecekteki nominal fiyat seviyelerini veya piyasa yönünü tahmin etmeye çalışmıyoruz (BIST gibi enflasyonist ve kur oynaklığı yüksek piyasalarda yön tahmini gürültüden ibarettir). Bunun yerine, **Learning-to-Rank (LambdaMART)** mimarisiyle piyasanın yönü ne olursa olsun en güçlü ve sağlam hisseleri kesitsel olarak (cross-sectional) tespit edip en üst dilime yerleştiriyoruz.
* **Raporlama & Arayüz:** Model çıktısını her 14 günde bir Telegram bildirim kartı olarak iletir; anlık portföy durumunu, 60 günlük çıkış takvimini ve makro rejim alarmlarını Streamlit tabanlı modern yönetim paneli (`app.py`) üzerinden görselleştirir.

### 1.2 Ne Yapmıyoruz? (İHLAL EDİLEMEZ SINIRLAR)
1. **Asla Otomatik Emir Göndermiyoruz:** Sistemin hiçbir aracı kuruma API bağlantısı, doğrudan emir iletim protokolü veya otomatik al-sat yetkisi YOKTUR ve KESİNLİKLE EKLENMEYECEKTİR.
2. **Canlı Sermaye Yönetmiyoruz:** Sistem sadece matematiksel simülasyon ve sanal bakiye (normalized equity) takibi yapar. Gerçek yatırım kararları tamamen kullanıcının kendi hür iradesindedir.
3. **Mevzuat Uyumu:** Türkiye Sermaye Piyasası Kurulu (SPK) lisanssız portföy yöneticiliği ve yatırım danışmanlığı yasaklarına %100 riayet edilir. Sistem bir yatırım danışmanı değil, algoritmik bir araştırma aracıdır.

---

## BÖLÜM 2: SİSTEMİN MİMARİSİ (ŞU ANKİ HALİ)

### 2.1 Dosya Haritası ve Görev Dağılımı

```
bist-bot/
├── config.py                   # Tüm hisse evreni, sektör tanımları, risk eşikleri ve sabitler
├── main.py                     # Konsol interaktif kontrol merkezi
├── app.py                      # Streamlit interaktif web terminali (V3.2 metrikleri tam entegre)
├── run_daily.py                # Günlük veri indirme, PIT senkronizasyonu ve önbellek tazeleme servisi
├── run_paper_trader.py         # 14 günlük periyodik rebalance ve denetim scheduler servisi
├── requirements.txt            # Python bağımlılıkları (Python 3.11+)
│
├── features/                   # Özellik Mühendisliği ve PIT Veri Katmanı
│   ├── veri_cek.py             # yfinance üzerinden fiyat/hacim indirme motoru
│   ├── fundamental_pit.py      # KAP açıklanma tarihleriyle lag-hizalı PIT bilanço motoru
│   ├── feature_engine.py       # Teknik ve temel faktör hesaplama, kesitsel z-score normalizasyonu
│   └── piyasa_rejimi.py        # Makro rejim göstergeleri (Reel faiz, USD momentum)
│
├── models/                     # Makine Öğrenimi Katmanı
│   ├── dataset_loader.py       # Eğitim veri seti birleştirici
│   └── v3_ranking/             # Üretim Mimarisi (V3.2)
│       ├── ranking_pipeline.py # Canlı PIT skorlama, sektör kısıtları ve Top-10 seçim motoru
│       ├── drift_monitor.py    # 3 katmanlı model, makro ve Sharpe kayma denetçisi
│       ├── paper_trader.py     # Portföy durumu, bireysel peak DD takibi, 60g çıkış takvimi, %25 DD kesici
│       ├── winning_lgbm_ranker.joblib # 6.75 yıllık eğitimle dondurulmuş 37 KB'lık resmi model
│       ├── paper_portfolio.json       # Anlık sanal portföy durumu ve hisse bazlı zirve fiyatlar
│       └── paper_trading_log.csv      # Her kontrolde genişletilen 13 sütunlu resmi işlem günlüğü
│
├── bot/                        # İletişim ve Sağlık Katmanı
│   ├── telegram_bot.py         # Güvenli Telegram mesaj gönderim modülü (.env entegre)
│   └── health_check.py         # Sistem bileşenleri sağlık denetimi
│
├── docs/                       # Mimari Tasarım ve Proje Planları
└── reports/                    # Resmi Denetim ve Kilit Kutu Tutanakları
```

### 2.2 Uçtan Uca Veri Akışı
1. **Veri Toplama:** `run_daily.py`, BIST seans kapanışı (18:10) ve takas mutabakatı (18:30) sonrası piyasa kapanışlarını çeker (`data/raw/*.parquet`).
2. **PIT Hizalama:** Şirketlerin bilanço verileri, resmi KAP bildirim tarihleriyle eşleştirilir. 30 Haziran tarihli bilanço asla 30 Haziran'da işlenmez; KAP'a düştüğü tarih (örn. 15 Ağustos) baz alınır. Böylece **sıfır geleceğe bakma hatası (zero lookahead bias)** garanti edilir.
3. **Faktör Türetimi:** `feature_engine.py`, 85+ hisselik evrende teknik ve temel faktörleri hesaplar. Her gün için evren genelinde kesitsel medyan ve standart sapma ile Z-Score normalizasyonu uygulanır.
4. **Sıralama (Ranking):** Dondurulmuş `winning_lgbm_ranker.joblib`, LambdaMART formülasyonuyla tüm hisselere göreli bir skor (`ml_score`) atar.
5. **Kurumsal Filtreler (`select_top_k_v2`):**
   - *Likidite Kapısı:* Son 20 günlük ortalama günlük işlem hacmi < 20 Milyon TL olan hisseler elenir.
   - *Sektör Çeşitlendirme Kalkanı:* Aynı sektörden portföye en fazla 3 hisse girebilir.
   - *Bilanço Tazelik Kontrolü:* Son bilançosu üzerinden 100 günden fazla geçmiş hisseler ⚠️ olarak etiketlenir.
6. **Portföy İcrası (`paper_trader.py`):**
   - Top-10 hisse belirlenir.
   - 60 günlük asgari tutma süresini doldurmayan hisseler model sıralamasından düşse dahi satılmaz.
   - Zirveden %25 Drawdown Devre Kesici kontrol edilir.
   - Bireysel hisselerde yerel zirveden %20 kâr geri verme alarmı kontrol edilir.
   - İdempotent takvim hesabı yapılır (`(t - entry_date).days`).
7. **İletim:** Özet kartı Telegram'a gönderilir, `paper_trading_log.csv` güncellenir ve Streamlit panelinde canlıya alınır.

---

## BÖLÜM 3: MODEL KARARLARI VE GEREKÇELERİ

### 3.1 Neden LGBMRanker (LambdaMART)?
* **Neden Regresyon Değil?** Regresyon modelleri ($R^2$ hedefleyen) finansal zaman serilerinde yüksek gürültüye takılır. BIST'te %60 enflasyon olan bir yılda tüm hisselerin fiyatı nominal olarak artar. Regresyon modeli genel fiyat seviyesini tahmin ederken hisseler arasındaki göreli üstünlüğü kaçırır.
* **Neden Binary Classification (Sınıflandırma) Değil?** Sınıflandırma ("hisse gelecek 60 günde %10 artacak mı? 1/0") yapay bir eşik koyar. %9.9 artan hisse ile %10.1 artan hisse arasında yapay bir uçurum yaratır ve portföyün en tepe dilimini (sağ kuyruk) optimize edemez.
* **Neden LambdaMART (NDCG@10)?** Bilgi erişim (Information Retrieval) ve arama motoru sıralama algoritmasıdır. Amacı portföye girecek ilk 10 hissenin (top of the ranking list) doğru sırada olmasını maksimize etmektir. 50. sıradaki hissenin 60. sıraya düşmesiyle ilgilenmez; enerjisini tamamen $K=10$ diliminde piyasayı yenecek hisseleri öne çıkarmaya odaklar.

### 3.2 Neden K=10, H=60 Gün ve %25 DD Kesici?
* **Neden $K=10$?**
  - Finansal ekonometride portföy çeşitlendirmesi (Diversification): Portföydeki hisse sayısı $K < 5$ olduğunda idiyosinkratik (şirkete özel skandallar, CEO ayrılığı, fabrika yangını) risk portföyü felç eder.
  - $K > 20$ olduğunda ise portföy BIST 100 endeksine yakınsar (index tracking) ve alfa üretilemez.
  - Yapılan duyarlılık analizlerinde en yüksek net Sharpe oranı $K=10$ seviyesinde gerçekleşmiştir ($K=10$ Sharpe: 1.26; $K=20$ Sharpe: 0.98).
* **Neden $H=60$ İşlem Günü (Çeyreklik Rotasyon)?**
  - Temel analiz verileri (bilançolar) 3 ayda bir (yaklaşık 60-65 işlem günü) gelir.
  - Bir hissenin güçlü bilanço ve ucuzluk faktörünün piyasa tarafından fiyatlanması zaman alır (Alpha Decay süresi BIST'te 40-70 gün aralığındadır).
  - Portföyü her ay yenilemek (H=20g) komisyon ve piyasa etki maliyetlerini (slippage) 3 katına çıkarırken getiriyi artırmamıştır.
* **Neden %25 Drawdown Devre Kesici?**
  - BIST piyasası tarihsel olarak derin sistemik krizler (2018 kur şoku, 2020 pandemi, 2021 Naci Ağbal şoku) yaşar.
  - Portföy tepe sermayesinden %-25 düştüğünde, sistem otomatik olarak **%50 Nakit / %50 Hisse** kalkanına geçer. Tepe noktasından -%15 seviyesine toparlanana kadar nakit faizinde bekler.
  - Bu asimetrik kural, maksimum çekilmeyi (Max DD) %-45 seviyelerinden %-28'e düşürmüş, sermaye erimesini engellemiştir.

### 3.3 Neden Eşit Ağırlık (%10 Her Hisse)?
* **Neden Markowitz Ortalama-Varyans Değil?** Ortalama-varyans optimizasyonu geçmiş getiri ve kovaryans matrisini tersine çevirir. Finansal piyasalarda kovaryans matrisi aşırı derecede kararsızdır (non-stationary). Geçmişte harika çalışan bir ağırlıklandırma, rejim değiştiğinde en kötü hisseye %40 ağırlık vererek portföyü batırır (Estimation Error Maximizer).
* **Neden Ters Volatilite Değil?** BIST'te düşük volatiliteli hisseler genelde endeksin gerisinde kalan hantal kamu veya holding hisseleridir. Ters volatilite alfayı öldürmüştür.
* **1/N Üstünlüğü:** DeMiguel, Garlappi ve Uppal (2009) tarafından ispatlandığı üzere, hiçbir parametre tahmini gerektirmeyen eşit ağırlık (1/N), out-of-sample dönemde tüm karmaşık optimizasyon modellerini geride bırakır.

### 3.4 Hiperparametre Seçimleri ve Matematiksel Nedenleri
* `max_depth = 2` ve `num_leaves = 3`: **Aşırı Sığ Ağaçlar.** Finansal veride sinyal/gürültü oranı (SNR) %5'in altındadır. Derin ağaçlar ($depth \ge 5$) piyasa gürültüsünü ezberler. Derinliği 2'de tutmak modelin sadece en kuvvetli 2 faktörün kesişimini öğrenmesini sağlar; ezberlemeyi imkansız kılar.
* `learning_rate = 0.03`, `n_estimators = 60`: Yavaş ve kontrollü öğrenme.
* `min_child_samples = 15`: Bir yaprakta en az 15 hisselik gözlem bulunma zorunluluğu (tekil ekstrem hisselere ağaç dallanmasını engeller).
* `reg_lambda = 1.0`: Aşırı katsayı büyümesini cezalandıran L2 regülarizasyonu.

---

## BÖLÜM 4: TEST EDİLİP REDDEDİLEN FİKİRLER (EN KRİTİK BÖLÜM)

*Yeni gelen bir araştırmacı veya AI, "şunu da denesek mi" dediğinde aşağıdaki listeye bakmalıdır. Bu fikirler denenmiş, başarısız olmuş ve neden başarısız oldukları ampirik verilerle ispatlanmıştır.*

| Reddedilen Fikir | Nasıl Test Edildi? | Sonuç ve Neden Reddedildi? | Tekrar Denenmeli mi? |
|:---|:---|:---|:---:|
| **1. Bireysel Stop-Loss (TP/SL)** | 25 farklı SL (%-5'ten %-15'e) ve Trailing Stop kombinasyonu 2018-2025 backtestinde simüle edildi. | **TAMAMI ÇÖKTÜ.** Net Sharpe 1.26'dan 0.70-0.85 bandına geriledi, kümülatif getiri yarıya indi. BIST'in doğası gereği hisseler %7-10 silkeler ve ardından %80 ralli yapar. Bireysel SL, portföyün en büyük kazananlarını dipte sattırıp gürültüyü realize etti; sağ kuyruk kârlarını budadı. | ❌ **ASLA** |
| **2. Aylık Kesitsel Rotasyon (H=20g)** | Model her 20 işlem gününde bir Top-10'u baştan seçip portföyü tamamen yeniledi. | **RASTGELEDEN FARKSIZ ÇIKTI.** Yıllık turnover %400'ü aştı, komisyon getiriyi eritti. Faktör alfası 20 günde olgunlaşmaz. Placebo karşısında istatistiksel anlamlılık kayboldu ($p > 0.35$). | ❌ **ASLA** |
| **3. Kısmi Rotasyon (Dinamik Çıkış)** | 60 gün beklemeden sıralamadan düşen hisseyi erken çıkarma kuralı denendi. | **PERFORMANS DÜŞTÜ.** Sıralamadan geçici olarak düşen hisseler çeyrek sonunda güçlü toparlanarak sistemi aldattı. 60 günlük sabit tutma disiplini gürültüyü filtrelemek için zorunludur. | ❌ **ASLA** |
| **4. Piotroski F-Score ve İhracat Oranı** | Şirket kalitesini ölçmek için 9 kriterli Piotroski skoru ve ihracat yüzdesi faktör olarak eklendi. | **OOS DÖNEMİNDE ÇÖKTÜ.** Bilgi Katsayısı (IC) negatif çıktı. Türkiye'deki yüksek enflasyon, enflasyon muhasebesi anomalileri ve kur sabitleme dönemleri Piotroski rasyolarının mantığını altüst etti; modele sadece gürültü ekledi. | ❌ **ASLA** |
| **5. SMA200 Trend Filtresi** | Fiyatı 200 günlük hareketli ortalamanın altında olan hisseleri almama kuralı eklendi. | **ALFAYI ÖLDÜRDÜ.** BIST'te en yüksek alfa üreten değer hisseleri, aşırı satım bölgesinde SMA200'ün altındayken yakalanır. SMA200 filtresi modelin en kârlı dip alımlarını engelledi. | ❌ **ASLA** |
| **6. Ters Volatilite Ağırlıklandırması** | Düşük oynaklıklı hisselere daha yüksek, yüksek oynaklıklı hisselere daha düşük ağırlık verildi. | **GETİRİ ÇÖKTÜ.** BIST'te volatilite sadece risk değil, aynı zamanda büyüme ve getiri kaynağıdır. Model defansif, prim yapmayan hantal hisselere yığıldı. Eşit ağırlık (1/N) çok daha üstün çıktı. | ❌ **ASLA** |
| **7. Taktik Tilt (Core-Satellite)** | %70 ana çekirdek portföy, %30 kısa vadeli momentum trade uydusu kuruldu. | **ALFA ÜRETMEDİ.** Uydu portföy işlem maliyetlerini patlattı, operasyonel karmaşıklığı 3 katına çıkardı ama risk ayarlı getiriye net katkısı sıfır oldu. | ❌ **ASLA** |

---

## BÖLÜM 5: KİLİT KUTU (LOCKBOX) PROTOKOLÜ VE SONUÇLARI

### 5.1 Protokol Neden Uygulandı?
Finansal yapay zekada araştırmacıların kendi kendilerini kandırmasının 1 numaralı sebebi **"Overfitting / Data Snooping Bias"**tır. Model geçmiş veride sürekli kurcalanır, parametreler ayarlanır ve sonunda geçmişe mükemmel uyan ama gelecekte batan bir model üretilir. Bunu engellemek için **Kilit Kutu (Lockbox)** karantinası uygulandı.

### 5.2 Nasıl Uygulandı?
1. **Eğitim ve Geliştirme Penceresi:** `2018-09-01` $\rightarrow$ `2025-05-31` (6.75 Yıl / 27 Çeyrek). Model yalnızca bu tarihler arasındaki veriyi gördü.
2. **Model Mühürleme:** En başarılı sığ ağaç modeli seçildi, eğitildi ve `winning_lgbm_ranker.joblib` olarak donduruldu. Hiperparametrelerine bir daha asla dokunulmadı.
3. **Kilit Kutu Karantina Dönemi:** `2025-06-01` $\rightarrow$ `2026-09-07` (Son 15 Ay / 5 Çeyrek). Bu veri modelden tamamen saklandı. Model ilk ve son kez bu veriye canlıdaymış gibi sokuldu.

### 5.3 Resmi Kilit Kutu Sonuçları (15 Aylık Saf OOS)

| Metrik | Dondurulmuş Model (K=10) | BIST 100 Endeksi | Üstünlük / Alfa |
|:---|:---:|:---:|:---:|
| **Kümülatif Net Getiri** | **+%137.3** | +%61.4 | **+%75.9 Net Alfa** 🔥 |
| **CAGR (Yıllıklandırılmış)** | **+%99.6** | +%46.7 | 2.13x Katlama |
| **Sharpe Oranı ($\sqrt{4}$)** | **3.41** | 1.01 | 3.3x Risk-Getiri |
| **Maksimum Drawdown** | **%0.0 (çeyreklik)** / -%8.2 (günlük) | -%15.0+ | Sermaye Kaybı Yok |
| **100 Tohumlu Monte Carlo Placebo** | **p = 0.000** | Baseline | %100 İstatistiki Güvenilirlik |

**Sonuç:** Model, kilit kutu süresince test edilen 100 rastgele hisse seçicisinin tamamını geride bırakmış ($p=0.000$) ve resmi kurumsal test tutanağıyla onaylanmıştır.

---

## BÖLÜM 6: DÜRÜSTLÜK NOTLARI VE MODEL SINIRLAMALARI

*Bu sistem bir mucize değil, kuralları olan bir faktör makinesidir.*

### 6.1 Model Hangi Koşullarda Çalışır?
* **DNA Yapısı:** Modelin faktör önem dağılımı **%57.3 Değer / Ucuzluk (Ters P/B, Esas Faaliyet Marjı, ROE)**, **%19.4 Düşük Borçluluk (Borç/Özkaynak)** ve **%23.3 Momentum/Oynaklık** şeklindedir.
* **İdeal Rejim:** **Pozitif Reel Faiz ve Ortodoks Para Politikası.** Paranın pahalı olduğu, faizlerin yüksek olduğu ortamlarda borçlu ve zayıf şirketler ezilirken, modelin seçtiği nakit zengini, borçsuz, kâr üreten sağlam şirketler piyasayı darmadağın eder.

### 6.2 Model Hangi Koşullarda Çuvallar? (Aşil Tendonu)
* **Tehlikeli Rejim:** **Derin Negatif Reel Faiz ve Enflasyonist Balon Dönemleri.**
* Reel faizin %-10 ve altına indiği ortamlarda (2022-2023 dönemi gibi), piyasada temel analiz çalışmaz. En çok borçlanan, aşırı değerli, spekülatif büyüme hisseleri saçma sapan çarpanlara ulaşarak ralli yapar.
* Model bu dönemlerde rasyonel ve muhafazakar kaldığı için spekülatif hisselerin gerisinde kalabilir. Bu durum bir "arıza" değil, modelin kurumsal felsefesinin bir sonucudur.

### 6.3 n=5 Çeyrek Kilit Kutu Şerhi
* Kilit kutu döneminde ölçülen Sharpe=3.41 olağanüstü bir başarıdır; ancak bu dönemin pozitif reel faiz uygulanan süper bir döngüye denk geldiği unutulmamalıdır.
* Uzun vadeli gerçekçi beklenti Sharpe=3.41 değil; 6.75 yıllık geniş pencerede kanıtlanan **Sharpe = 1.26** tabanıdır.

---

## BÖLÜM 7: PASEU VAKASI VE ÖĞRENİLEN DERS

### 7.1 Ne Oldu?
* `PASEU.IS` (Pasifik Eurasia Lojistik), 2026 Ağustos ayı sonunda 268.00 TL zirvesinden başlayarak **6 işlem günü üst üste taban (-%10)** çekmiş ve 142.60 TL'ye düşmüştür (%46.8 kayıp).
* Şirket hisselerinde VBTS (Volatilite Bazlı Tedbir Sistemi) kredili işlem yasağı, brüt takas tedbirleri ve MKK pay sahipliği değişimleri yaşanmıştır.
* Ancak 07 Eylül 2026 tarihindeki rebalance testinde, model `PASEU.IS` hissesini **Top-10 listesine (7. sıradan)** sokmuştur.

### 7.2 Neden Oldu? Sistemin Neresinde Açık Vardı?
1. **Gecikmeli PIT Bilanço Yanılsaması:** Modelin elindeki en güncel bilanço 2026Q2 idi (Ağustos ortasında açıklandı). Şirketin o bilançodaki kârlılığı ve büyümesi kusursuz görünüyordu.
2. **Yapay Çarpan Ucuzlaması:** Hisse 6 gün taban çekince F/K ve PD/DD oranları matematiksel olarak yarıya indi. Model bunu "harika bir şirketin muazzam iskontoyla satılması" olarak algıladı.
3. **Likidite Filtresinin Aşılması:** Taban günlerinde dahi tahtada günde 1 - 3 Milyar TL hacim döndüğü için sistemin 20M TL'lik likidite filtresine takılmadı.
4. **Kör Nokta:** Model sadece çeyreklik bilanço ve fiyat geçmişine baktığı için; şirketin anlık regülasyon krizini, patron satışlarını ve taban serisi dinamiklerini (düşen bıçak / falling knife) göremedi.

### 7.3 Öğrenilen Dersler ve V3.2'ye Eklenen Savunmalar
1. **Bireysel Zirveden Çekilme (Peak DD) Takibi:** Portföydeki her hissenin kendi yerel zirvesinden ne kadar düştüğü sisteme eklendi. %20 ve üzeri düşüşlerde sisteme Telegram ve konsol uyarısı entegre edildi.
2. **Bilanço Tazelik İzleyicisi:** Bilançosu 100 günden eski olan hisselere ⚠️ uyarısı zorunlu kılındı.
3. **Karar Destek Sistemi (DSS) Zorunluluğu:** Bu vaka, sistemin neden **ASLA otomatik emir göndermemesi gerektiğini**, nihai filtrede bir insan aklının ve temel haber takibinin şart olduğunu tartışmasız şekilde kanıtlamıştır.

---

## BÖLÜM 8: ŞU AN AKTİF OLAN PAPER TRADING

### 8.1 Canlı Portföy Durumu (paper_portfolio.json)
* **Giriş Tarihi:** 2026-09-07
* **Başlangıç Sermayesi:** 1.0 (Birim Sermaye)
* **Portföy Büyüklüğü ($K=10$ Eşit Ağırlık - Her Biri %10):**
  1. `LOGO.IS` (Logo Yazılım) — Giriş: 136.60 TL
  2. `ONCSM.IS` (Oncosem Onkolojik) — Giriş: 181.50 TL
  3. `BIZIM.IS` (Bizim Toptan) — Giriş: 23.90 TL
  4. `KCAER.IS` (Kocaer Çelik) — Giriş: 14.24 TL
  5. `MTRKS.IS` (Matriks Bilgi Dağıtım) — Giriş: 33.16 TL
  6. `SELEC.IS` (Selçuk Ecza Deposu) — Giriş: 358.25 TL
  7. `PASEU.IS` (Pasifik Eurasia) — Giriş: 142.60 TL
  8. `MIATK.IS` (Mia Teknoloji) — Giriş: 33.76 TL
  9. `MAVI.IS` (Mavi Giyim) — Giriş: 36.30 TL
  10. `VAKBN.IS` (Vakıfbank) — Giriş: 33.44 TL

### 8.2 Aktif Risk ve İzleme Mekanizmaları
* **60 Gün Çıkış Takvimi:** Portföydeki tüm hisseler için `days_held` takip edilir (Şu an 3. gününde, 57 gün beklemededir). 60 gün dolmadan hisse satılamaz.
* **İdempotent Gün Sayacı:** Gün sayısı körü körüne toplanmaz; her kontrolde `(t - entry_date).days` formülüyle takvim farkı olarak kesin ve hatasız hesaplanır.
* **Drawdown Devre Kesici:** Portföy tepe değerinden %-25 düşerse devreye girer; %-15'e toparlanana kadar nakitte bekler.
* **Drift ve Makro Radarı:**
  - Reel Faiz $\le -\%10$ $\rightarrow$ 🔴 Kırmızı Makro Alarmı
  - $USD\_Mom_{60} \ge +\%20$ $\rightarrow$ 🔴 Kırmızı Kur Şoku Alarmı
  - Model Z-Skor Kayması $|Z| > 2.5$ $\rightarrow$ 🟡 Skor Drift Uyarısı
  - Gerçekleşen Sharpe $\le 0.75$ $\rightarrow$ 🔴 Model Bozulma Alarmı

---

## BÖLÜM 9: SIRADAKİ PLANLI ADIMLAR

1. **Piyasa Kapanış Veri Güncellemesi:**
   - Seans kapanışı (18:10) ve takas mutabakatı (18:30) sonrasında `python run_daily.py` çalıştırılarak en güncel BIST fiyatları indirilecek.
2. **GitHub Uzak Depo (Remote) Bağlantısı:**
   - Kullanıcı GitHub üzerinde private/public reposunu oluşturup linkini verdiğinde:
     ```bash
     git remote add origin https://github.com/<kullanici>/<repo>.git
     git branch -M main
     git push -u origin main
     ```
     adımlarıyla temiz kod tabanı push edilecek (Sormadan push etmeme kuralına sadık kalınarak).
3. **14 Günlük Rebalance Döngüsü:**
   - Portföy 07 Eylül 2026'da kurulduğu için ilk resmi ara kontrol 21 Eylül 2026 tarihinde icra edilecektir.

---

## BÖLÜM 10: ASLA DOKUNULMAMASI GEREKEN KURALLAR (TABULAR)

*Aşağıdaki maddeler projenin temel direkleridir. Gelecekteki herhangi bir AI veya geliştirici bu kuralları esnetemez veya değiştiremez:*

1. 🛑 **Bireysel Stop-Loss Eklemeye Çalışma:** 25 kombinasyonla test edildi ve getiriyi çökerttiği kanıtlandı. Bireysel SL yerine portföy düzeyinde %25 Drawdown Devre Kesici kullanılır.
2. 🛑 **H=60 Günlük Tutma Süresini Kısaltma:** Faktör getirilerinin olgunlaşması için asgari 60 işlem günü şarttır. Aylık veya haftalık rotasyona geçilemez.
3. 🛑 **Modeli Derinleştirme:** Ağaç derinliği 2'den, yaprak sayısı 3'ten yukarı çıkarılamaz. Karmaşık derin ağaçlar finansal gürültüyü ezberler.
4. 🛑 **Eşit Ağırlıktan (1/N) Sapma:** Portföy ağırlıklandırması Markowitz, ters volatilite veya piyasa değeri yapılamaz.
5. 🛑 **Canlı Broker Bağlantısı Kurma:** Sisteme aracı kurum API'si eklenemez, otomatik emir verdirilemez. Sistem bir Karar Destek Sistemi (DSS) olarak kalacaktır.
6. 🛑 **Hassas Dosyaları (.env, data/raw/) Git'e Atma:** Siber güvenlik ve gizlilik kuralları tavizsizdir.
