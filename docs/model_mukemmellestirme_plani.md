# BIST Modelini Mükemmelleştirme Planı — Veri Bilimi + Finans Uzmanlığı Sentezi
*(Kurumsal Seviye Revizyonu — Sürüm 2.0)*

## Başlangıç Noktası: Neyi Koruyoruz, Neyi Değiştiriyoruz

Aylarca süren titiz teşhis süreci bize kesin bir şey öğretti: **sorun model mühendisliği değil, girdi bilgisi ve ufuk uyumsuzluğuydu.** RSI/MACD/Stokastik gibi kısa vadeli teknik göstergeler, dört farklı mimaride (sabit eşik, kesitsel sıralama, aylık rotasyon, taktik tilt) Monte Carlo testlerinde rastgele seçimden istatistiksel olarak ayırt edilemedi ($p=0.27 - 0.53$). Ayrıca nakitte bekleme mimarisinin BIST gibi yüksek enflasyonlu piyasalarda serveti reel olarak erittiği (%-80 reel kayıp) kesinleşti.

**Korunanlar (Sağlam Mühendislik Altyapısı):**
- Purged Walk-Forward + embargo altyapısı (zaman sızıntısız doğrulama)
- 3'lü ensemble (LightGBM + RF + LogReg) ve zaman-sıralı nested kalibrasyon mimarisi
- Execution motoru (limit emir simülasyonu, gap kontrolü, komisyon ve likiditeye duyarlı kayma/slippage)
- KAP kurumsal aksiyon ve etkinlik filtreleri
- **En kritik olan: Monte Carlo Placebo Testi disiplini** — artık her yeni fikir ve model baştan rastgele seçim kontrolünden geçirilecek.

**Değişenler (Stratejik Paradigma Değişimi):**
1. **Girdi Bilgisi:** Gürültü üreten 5-14 günlük mikro teknik göstergeler tamamen terk edilerek, akademik literatürde gelişen piyasalarda kanıtlanmış **Point-in-Time Temel Analiz (Değer/Value + Kalite/Quality) ve Makro Rejim** faktörlerine geçilecek.
2. **Ufuk Uyumu:** Çeyreklik temel veriler ile etiketleme/tahmin ufku (aylık/çeyreklik) birbirine tam senkronize edilecek.
3. **Piyasa Betasından Ayrışma:** Hisse getirileri genel piyasa dalgasından arındırılarak (Market-Residual Return) model yalnızca gerçek şirket seçme alfasına odaklanacak.

---

## FAZ A — Point-in-Time Temel Veri Altyapısı & Dinamik Evren (7-10 gün)

**Bu faz projenin omurgasıdır; burada yapılacak tek bir sızıntı tüm sistemi çökertecektir.**

### A.0 Veri Kaynağı Somutlaştırması
KAP ham finansal tabloları doğrudan tablo formatında sunmamaktadır (PDF/XBRL). Şu yollardan biri netleştirilecektir:
- **Seçenek 1 (Önerilen/Hızlı):** Finnet, İş Yatırım veya TradingView API/veri tabanından geçmiş çeyreklik verilerin çekilmesi.
- **Seçenek 2 (Açık Kaynak/Maliyet Sıfır):** KAP XBRL paketlerini parse eden otomatik bir Python pipeline'ı (emek yoğun, 2018-2026 arası 32 çeyrek × 88 hisse = 2.816 bilanço).
- **Seçenek 3:** Hibrit yaklaşım — BIST 30/50 için otomatik çekim, kalan yan tahtalar için yapılandırılmış veri tabanından içe aktarım.

*Ek Not:* TÜİK TÜFE aylık enflasyon serisi de her ayın 3'ünde açıklanmaktadır. Reel getiri hesaplamalarında ay sonu tarihi değil, fiili açıklanma tarihi PIT-doğru olarak eşlenecektir.

### A.1 Point-in-Time (PIT) Disiplini (Sıfır Geleceğe Bakış Sızıntısı)
Finansal tablolar çeyrek bitiminden **30 ila 45 gün sonra** kamuya açıklanır. 31 Mart tarihli bilanço, fiilen Mayıs ayının ortasında bilinir. 
```python
# KESİNLİKLE YASAK (Look-ahead bias):
df_fundamentals['gecerlilik_tarihi'] = df_fundamentals['ceyrek_bitis_tarihi']

# KURUMSAL STANDART (PIT Garantisi):
df_fundamentals['gecerlilik_tarihi'] = df_fundamentals['kap_fiili_aciklanma_tarihi']
```
Veri, hisse için ancak ve ancak KAP'a düştüğü andan itibaren modelin kullanımına açılacaktır.

### A.2 Toplanacak Temel Veri Kalemleri
- **Gelir Tablosu:** Satış Gelirleri, Brüt Kâr, Esas Faaliyet Kârı, FAVÖK (EBITDA), Net Dönem Kârı.
- **Bilanço:** Dönen Varlıklar, Kısa Vadeli Yükümlülükler, Toplam Finansal Borç, Nakit ve Nakit Benzerleri, Özkaynaklar, Toplam Aktifler.
- **Nakit Akış Tablosu:** İşletme Faaliyetlerinden Net Nakit Akışı (CFO), Maddi Duran Varlık Alımları (CapEx), Serbest Nakit Akışı ($FCF = CFO - CapEx$).
- **Banka Özel Kalemleri:** Net Faiz Gelirleri, Net Ücret/Komisyon Gelirleri, Takipteki Krediler (NPL), Karşılıklar.

### A.3 TFRS 29 Enflasyon Muhasebesi Kırılması & Sağlam Çarpan Tercihi (BIST'e Özel Çözüm)
BIST şirketleri 2023 sonu itibarıyla enflasyon muhasebesine (TFRS 29) geçmiştir. Bu geçiş, Net Kâr kaleminde "Net Parasal Pozisyon Kazanç/Kayıpları" nedeniyle operasyonel olmayan devasa sıçramalar yaratmış, F/K (P/E) çarpanını gürültülü hale getirmiştir.
- [ ] **Dayanıklı Operasyonel Çarpanlar:** F/K yerine, parasal kazanç/kayıptan etkilenmeyen **Firma Değeri / FAVÖK (EV/EBITDA)** ve **Firma Değeri / Satışlar (EV/Sales)** temel değerleme çarpanı olarak önceliklendirilecektir.
- [ ] **Muhasebe Rejimi İşareti:** 2023 öncesi ve sonrası dönemler kendi içinde normalize edilecek (dönem içi z-score) veya modele `tfrs29_aktif` kategorik bayrağı eklenecektir.

### A.4 Sektörel Normalizasyon ve Küçük Grup Emniyeti
Bankacılık ile Sanayi çarpanları kıyaslanamaz. Her çarpan sektör içinde normalize edilecektir ($Z = (x - \mu_{sektor}) / \sigma_{sektor}$).
- **Küçük Sektör Emniyeti:** Bir sektörde hisse sayısı 6'dan az ise, sektör z-score'u aşırı oynak olur. Bu durumlarda hisse sayısı az olan sektörler mantıksal üst kümelerde (örn. Dayanıklı Tüketim + Otomotiv $\rightarrow$ İmalat Sanayi) birleştirilerek z-score hesaplanacaktır.

### A.5 Dinamik Evren ve Hayatta Kalma Yanlılığı (Survivorship Bias) Engeli
Evrendeki 88 hissenin bir kısmı (AGROT, REEDR, BINHO, KCAER, ASTOR vb.) 2022–2024 arasında halka arz olmuştur.
- Model her çeyrekte sadece **o tarihte borsada fiilen işlem gören ve geriye dönük en az 2 çeyrektir bilançosu açıklanmış olan** hisseleri sıralayacaktır. Halka arz öncesi geçmişe sahte veri veya ortalama atanmayacaktır.

### A.6 Kurumsal Olaylar (Sermaye Artırımı / Temettü) Düzeltmesi
Bedelli/bedelsiz sermaye artırımları hisse başına özkaynak ve kâr rakamlarını yapay olarak sıçratır. Kurumsal işlem takvimine göre hisse başına oranlar geriye dönük düzeltilecektir.

**Faz A Çıktısı:** `data/fundamentals/{ticker}.parquet` — Tam PIT-uyumlu, dinamik evren destekli, TFRS 29 düzeltmeli temiz temel veri seti.

---

## FAZ B — Market-Residual (Beta-Arındırılmış) Etiketleme (3-4 gün)

### B.1 Mantık: Genel Dalgadan Şirket Ayrışmasına
BIST gibi bir piyasada endeks %100 yükselirken her hisse "kazandıran" görünür; endeks %20 düşerken harika bir şirket bile değer kaybeder. Modelin görevi endeksin yönünü tahmin etmek değil, **endeksten bağımsız olarak pozitif ayrışan (alfa üreten) hisseleri bulmaktır.**

### B.2 Shrinkage (Vasicek / Blume) Düzeltmeli Beta ve Residual Getiri
Her hissenin BIST 100 endeksine karşı 60 günlük hareketli betası hesaplanacak; gürültüyü azaltmak için kurumsal literatür standardı olan Vasicek/Blume shrinkage uygulanacaktır:
$$\beta_{adj} = 0.67 \cdot \beta_{rolling} + 0.33 \cdot 1.0$$
Hissenin artık (residual) getirisi:
$$R_{residual, i}(t, t+h) = R_i(t, t+h) - \beta_{adj, i}(t) \cdot R_{XU100}(t, t+h)$$

### B.3 Ufuk Uyumu ve Hedef Değişken Tipi
- Gün içi dar vadeli Triple Barrier kaldırılacak; hedef değişken hissenin **gelecek 21 işlem günü (aylık) veya 60 işlem günü (çeyreklik) boyunca ürettiği kümülatif Residual Getiri** olacaktır.
- Bu sürekli (continuous) getiri, Faz D'deki doğrudan sıralama modeli (`LGBMRanker`) için kusursuz bir hedef teşkil eder.

**Faz B Çıktısı:** `features/labeling_v2.py` — Beta-arındırılmış kesitsel kalıntı getiri hesaplama motoru.

---

## FAZ B.5 — Erken Placebo & Karar Kapısı (Kill Criteria) (1-2 gün)

**Haftalarca sürecek modelleme ve kodlamaya girmeden önce, hipotezin BIST'te en kaba haliyle çalışıp çalışmadığını 48 saatte tespit eden emniyet sübabı.**

Makine öğrenmesine, ensemble'a veya hiperparametre aramasına girmeden, doğrudan finansal sezgiye dayalı kaba bir skor üretilir:
$$Skor_{kaba} = -Z(EV/EBITDA) + Z(ROE) + Z(Mom_{12-1})$$

1. Evrendeki hisseler her ay bu kaba skorla sıralanır ve Top-10 / Top-15 sepeti kurulur.
2. Birebir aynı maliyetlerle **100 farklı rastgele tohumlu Monte Carlo Placebo** testi çalıştırılır.
3. **KARAR KAPISI (Kill Criteria):**
   - **Eğer $p > 0.20$ ise (Kaba kural bile rastgele dart atışından ayrılamıyorsa):** Faz C ve D'ye KESİNLİKLE GEÇİLMEZ. Hipotez baştan sorgulanır; kullanılan temel rasyoların BIST'te prim üretmediği kabul edilir ve zaman tasarrufu sağlanır.
   - **Eğer $p < 0.10$ ise (Kaba formül bile rastgeleden belirgin şekilde ayrışıyorsa):** Veri biliminin bu sinyali büyütebileceği kanıtlanmış olur. Güvenle Faz C'ye geçilir.

**Faz B.5 Çıktısı:** `reports/faz_b5_early_placebo_report.md` — Erken devam/dur karar raporu.

---

## FAZ C — İki Kulvarlı Feature Seti: Sanayi (QARP) vs Bankacılık (CAMELS) (5-7 gün)

### C.1 Sanayi ve Ticaret Şirketleri İçin Feature'lar (QARP: Kaliteyi Makul Fiyata Al)
1. **Değer (Value) Bloğu:**
   - Sektör Z-score EV/EBITDA, EV/Sales, P/B.
   - Serbest Nakit Akışı Getirisi ($FCF / Piyasa\_Degeri$).
2. **Sanayi Kalite (Piotroski F-Score Uyarlaması):**
   - Nakit Kâr Kalitesi: $CFO > Net\_Kar$ mı? (1/0)
   - Bilanço Sağlığı: Net Borç / FAVÖK azaldı mı? (1/0)
   - Kârlılık İvmesi: Brüt Marj ve ROA geçen yıla göre arttı mı? (1/0)
   - Likidite: Cari Oran iyileşti mi? (1/0)
3. **12-1 Aylık Momentum (Jegadeesh & Titman):**
   - Son 12 aylık getiri eksi son 1 aylık getiri (kısa vadeli ortalamaya dönüş gürültüsünü filtreleyen kanıtlanmış momentum faktörü).

### C.2 Finans ve Bankacılık (XBANK) İçin Özel Feature Bloğu
Bankalara sanayi Piotroski kuralları uygulanamaz. Bankalar için kurumsal rasyolar:
1. **Banka Değerleme:** Sektör içi PD/DD (P/B) z-score.
2. **Kârlılık & Verimlilik:** Özkaynak Kârlılığı (ROE) ve Aktif Kârlılığı (ROA).
3. **Aktif Kalitesi & Risk:** Takipteki Alacaklar Oranı (NPL Ratio) eğilimi.
4. **Banka Skor Bileşimi:** $H1 = 0.55 \cdot Z(P/B_{ters}) + 0.30 \cdot Z(ROE) + 0.15 \cdot Z(NPL_{iyilesme})$.

### C.3 Makro Rejim ve Sektör Duyarlılık Katmanı
- **Reel Politika Faizi:** $TCMB\_Faizi - Yillik\_TUFE$.
  - *Negatif Reel Faiz Döneminde:* İhracatçı, döviz zengini, operasyonel FAVÖK üreten sanayi şirketlerine pozitif faktör ağırlığı.
  - *Pozitif Reel Faiz / Sıkılaşma Döneminde:* Yüksek borçlu (Net Borç/FAVÖK > 3.0) şirketlere negatif filtre; nakit zengini ve bankalara pozitif ağırlık.
- **Dolar/TL 60 Günlük İvmesi:** İhracat payı yüksek şirketler için çarpan desteği.

### C.4 Örneklem Büyüklüğü Gerçeği ($N=32$ Çeyrek)
Zaman serisi boyutu $N=32$ çeyrek ile sınırlıdır. Bu nedenle aşırı karmaşık, 100 parametreli feature havuzlarından kaçınılacak; toplam feature sayısı 15–20 adet sağlam, ekonomik mantığı tartışmasız göstergeyle sınırlandırılacaktır (overfitting koruması).

**Faz C Çıktısı:** `features/fundamental_features_v2.py`, `features/banka_features.py`.

---

## FAZ D — Model Mimarisi Deneyleri (Sıralama vs Regresyon) (5-7 gün)

### D.1 Doğrudan Kesitsel Sıralama Motoru: `LGBMRanker` (LambdaMART)
Mevcut sınıflandırma (classification) yaklaşımı hissenin tek başına "kazanıp kazanmayacağını" tahmin etmeye çalışıyordu. Oysa portföy yöneticisinin ihtiyacı: **"Bugün evrendeki 88 hisse içinde en iyi 10-15 hisse hangisi?"** sorusudur.
- `LGBMRanker`, çeyreklik/aylık dönemleri birer `group/query` olarak ele alır.
- Her çeyrekte hisseleri gelecek residual getirilerine göre 1'den 88'e sıralamayı (NDCG metriğini) optimize eder.

### D.2 Benchmark Model: Klasik 3'lü Ensemble + Regresyon
Mevcut Purged Walk-Forward altyapısı korunarak LightGBM Regressor + RF Regressor + Ridge Regresyon ile residual getiriyi tahmin eden model yan kulvarda eğitilir.

### D.3 Model Karşılaştırma Kriteri
İki model aynı OOS pencerelerinde test edilir. Eğer `LGBMRanker` belirgin bir üstünlük sağlamazsa, Occam'ın Usturası prensibiyle daha basit ve yorumlanabilir olan mimari seçilir.

**Faz D Çıktısı:** `models/v3_ranking/` — Sıralama optimizasyonlu model motoru.

---

## FAZ E — Doğrulama Zinciri (Öğrenilen Her Dersin Uygulanması) (5-7 gün)

Hiçbir adım atlanmadan şu 8 aşamalı süzgeç çalıştırılacaktır:

1. **Purged Walk-Forward + 21 Gün Embargo:** Çeyreklik/aylık etiket çakışmalarını önlemek için eğitim ile test arasına tam 21 işlem günü embargo konulacaktır.
2. **Nested Kalibrasyon:** Hiperparametreler sadece Train içinde aranacak, test dilimine asla sızdırılmayacaktır.
3. **OOS Decile Yayılımı:** Modelin en yüksek puan verdiği 10. Decile ile 1. Decile arasındaki residual getiri farkı pozitif ve monoton olmalıdır.
4. **Block Bootstrap Güven Testi:** Elde edilen getiri farkının şans eseri olup olmadığı blok bootstrap ile test edilecektir.
5. **NİHAİ MONTE CARLO PLACEBO TESTİ (100 Tohum):** Modelin nihai portföyü, 100 farklı rastgele seçim simülasyonu karşısına konacaktır. $p < 0.05$ şartı aranacaktır (Model rastgele seçimin en az 95. persentilinde olmalıdır).
6. **3 Boyutlu Adil Benchmark:** TL, Dolar (USD) ve TÜİK Enflasyonundan Arındırılmış Reel Satın Alma Gücü getirileri eşzamanlı raporlanacaktır.
7. **Modeller Arası Baseline Karşılaştırması:** ML modelinin performansı; "Hiçbir Şey Yapma 88 Hisse Eşit Ağırlık Tut" ve "Sadece Kaba Formülle Sırala (ML'siz)" baseline'larını istatistiksel olarak aşmak zorundadır.
8. **Rejim Kararlılığı:** 2022 Enflasyon Rallisi, 2023 Seçim & Kur Şoku, 2024 Sıkılaşma ve 2025-2026 normalleşme yıllarında tutarlı ayrışma aranacaktır.

**Faz E Çıktısı:** `reports/faz_e_comprehensive_validation_report.md` — Nihai bilimsel onay raporu.

---

## FAZ F — Portföy Entegrasyonu & Likidite Kısıtları (3-4 gün)

### F.1 Çekirdek-Pasif + Faktör Tilt Mimarisi
- Nakit ataleti (cash drag) yaratılmayacak; portföy her zaman %100 hisse senedinde kalacaktır.
- **Varyant 1 (Çekirdek + Tilt):** %80 BIST 88 Eşit Ağırlık Pasif Çekirdek + %20 Modelin En Yüksek Puanlı Top-10 Hissesine Aylık Taktik Tilt.
- **Varyant 2 (Tam Faktör Sepeti):** Modelin en yüksek puanlı 25-30 hissesine eşit/skor-ağırlıklı aylık rotasyon (Faz 3 konsantrasyon taramasında $K=25-30$ bandının Sharpe 1.91 ile en ideal çeşitlendirme olduğu kanıtlanmıştı).

### F.2 Likidite ve Slippage Yönetimi (ADTV Kısıtı)
Aylık rebalancing sırasında TERA, FORTE, TUREX gibi düşük hacimli hisselerde piyasa derinliği sığdır.
- Hiçbir hissede, o hissenin **Son 20 Günlük Ortalama Günlük İşlem Hacminin (ADTV) %1'inden fazla tek seferlik emir gönderilmeyecektir.**
- Gerektiğinde rebalancing işlemleri tek günde değil, 2-3 güne yayılarak (TWAP benzeri) icra edilecektir.

**Faz F Çıktısı:** `backtest/trading_engine_v3.py` — Likidite korumalı, çekirdek-faktör portföy motoru.

---

## Zaman Çizelgesi ve Faz Özeti

| Faz | Açıklama | Süre | Kümülatif | Karar Kapısı / Emniyet Sübabı |
| :---: | :--- | :---: | :---: | :--- |
| **Faz A** | PIT Temel Veri Altyapısı (KAP + TFRS 29 + Dinamik Evren) | 7-10 gün | ~10 gün | Bilanço açıklanma tarihleri eksiksiz mi? |
| **Faz B** | Market-Residual (Beta-Arındırılmış) Etiketleme | 3-4 gün | ~14 gün | Shrinkage beta ile residual getiri hazır mı? |
| **Faz B.5** | **Erken Placebo / Baseline Karar Kapısı** | **1-2 gün** | **~16 gün** | **$p > 0.20$ ise DUR, $p < 0.10$ ise DEVAM ET!** |
| **Faz C** | Yeni Feature Seti (QARP Sanayi + CAMELS Banka + Makro) | 5-7 gün | ~23 gün | Sektör z-score ve banka ayrımı tamam mı? |
| **Faz D** | Model Mimarisi Deneyleri (`LGBMRanker` vs Regresyon) | 5-7 gün | ~30 gün | Sıralama metriği (NDCG) anlamlı mı? |
| **Faz E** | 8 Aşamalı Doğrulama Zinciri (Nihai Placebo & 3D Benchmark) | 5-7 gün | ~37 gün | Model rastgele dağılımın $\ge$ %95'inde mi? |
| **Faz F** | Portföy Entegrasyonu (ADTV Likidite Kısıtı + Çekirdek-Tilt) | 3-4 gün | ~41 gün | Canlıya hazır, turnover-kontrollü portföy motoru |

---

## 30 Yıllık Uzmanın Nihai Değerlendirmesi

Bu revize edilmiş plan; önceki teşhis sürecinde tespit edilen **beş büyük finansal açığı** (banka bilançolarının sanayiyle karıştırılması, TFRS 29 enflasyon muhasebesi anomalisi, halka arzlardan kaynaklanan hayatta kalma yanlılığı, ufuk uyumsuzluğu ve işlem maliyeti sürtünmesi) tamamen kapatmıştır.

En önemlisi, **Faz B.5 (Erken Placebo Kapısı)** sayesinde aylarca emek vermeden önce, hipotezin BIST'te en kaba haliyle çalışıp çalışmadığı 15 gün içinde netleşecektir. Eğer bu kapı geçilirse, arkasında sağlam bir veri bilimi ve kurumsal portföy yönetim mantığı olan, BIST enflasyonunu ve dolar getirisini dövebilecek gerçek bir sistem ortaya çıkacaktır.
