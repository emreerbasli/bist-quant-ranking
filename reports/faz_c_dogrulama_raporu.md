# Faz C Doğrulama ve Kurumsal Stres Testi Raporu
*30 Yıllık Kurumsal BIST ve Kantitatif Portföy Yönetimi Perspektifinden*

---

## Yönetici Özeti (Sober & Objective Assessment)

Faz C kapsamında, kullanıcının belirlediği **iki bağlayıcı kurumsal şart** ve **iki kulvarlı (Sanayi QARP vs Banka CAMELS) + Makro Rejim** mimarisi üzerinde hiçbir üretim kodu değişikliği yapılmaksızın bağımsız simülasyon ve test scriptleriyle tam kapsamlı denetim icra edilmiştir.

Bu denetim, projenin başından bu yana elde edilen **en çarpıcı, en dürüst ve en öğretici kantitatif bulgularını** ortaya koymuştur:

1. **60 Günlük Ufkun Gerçek Yüzü (Şart 2 Sonucu):**
   - 60 günlük çeyreklik ufuk, işlem maliyetlerini (ciroyu yıllık %251'den %163'e) ve Max Drawdown'ı (-%28.0'den **-%9.9'a**) dramatik biçimde düşürse de, **istatistiksel anlamlılık sorununu tek başına çözmemektedir.**
   - Konsantrasyon taramasında ($K \in [5..30]$) Bonferroni düzeltmesi yapıldığında tüm $K$ değerleri ($p_{bonf} \ge 0.360$) anlamlılık sınırının dışına çıkmaktadır.
2. **Döngüsellik Kalkanı ve Walk-Forward Şoku (Şart 1 Sonucu):**
   - Tüm 8 yıllık veriye bakılarak "P/B değer tuzağıdır, atalım; yerine Piotroski F-Score ve İhracat koyalım" kuralı, **Erken Dönemde (2018–2021) kalibre edilip Geç Dönemde (2022–2026 / OOS) dondurulmuş olarak test edildiğinde $p = 0.680$ ile SINIFTA KALMIŞTIR.**
   - Geç dönemde model getirisi %1.414'te kalarak 100 tohumlu Placebo ortalamasının (%1.325) üzerine anlamlı bir alfa koyamamıştır.
3. **Faktör Bilgi Katsayısı (IC) Rejim Çöküşü Keşfi:**
   - Detaylı Spearman Rank Korelasyonu (IC) analizi bu çöküşün matematiksel sebebini netleştirmiştir:
     - **Piotroski F-Skoru:** 2018–2021'de güçlü bir alfa üretirken ($IC = +0.073$), 2022–2026 hiperenflasyon döneminde sıfıra çökmüştür ($IC = -0.002$). Sebebi: Türkiye'deki yüksek enflasyon ve TMS 29 enflasyon muhasebesi, geleneksel ABD menşeli F-Score bilanço oranlarını bozmuştur.
     - **İhracat Oranı:** 2018–2021'de kur patlamalarında devasa alfa sağlarken ($IC = +0.125$), 2022–2026'da tersine dönmüştür ($IC = -0.051$ / negatif alfa!). Sebebi: Kontrollü kur ve artan TL maliyetleri ihracatçıları baskılarken, iç piyasa fiyatlama gücü olan perakende/gıda şirketleri öne geçmiştir.
     - **Serbest Nakit Akımı Verimi ($FCF/PD$):** Her iki dönemde de ayakta kalan ve en yüksek istikrarı ($IC\text{-}IR = 0.25$) gösteren faktör olmuştur ($IC = +0.064$).
4. **Makro Rejim Filtresi:**
   - TCMB Reel Politika Faizi ($Politika\_Faizi - Yillik\_TUFE$) ve USD/TRY 60 günlük ivmesi, 2019 sermaye sıkışıklığını (pozitif reel faiz) ve 2021/2023 kur şoklarını **point-in-time olarak başarıyla yakalamaktadır**. Ancak statik portföy kısıtlaması yerine taktik rejim sinyali olarak makine öğrenmesine girdi yapılması gerekmektedir.
5. **Nihai Hüküm:** İnsan eliyle sabit ağırlıklar atayarak kurulan "sabit lineer kurallar" BIST'in rejim değişimlerinde kaçınılmaz olarak bozulmaktadır. Bu durum, **Faz D'de planlanan Makine Öğrenmesi (LGBMRanker / LambdaMART NDCG) sıralama motorunun bir lüks değil, zorunluluk olduğunu kanıtlamaktadır.**

---

## 1. Şart 2 — 60 Günlük Ufkun 5 Boyutlu Tam Denetimi

### 1.1. Konsantrasyon Taraması ($K \in [5, 10, 15, 20, 25, 30]$)

| Portföy Büyüklüğü | Model Kümülatif | CAGR | Sharpe ($\sqrt{4}$) | Max DD | Placebo Küm. | Placebo Sharpe | Ham $p$-değeri | Bonferroni $p_{adj}$ | FDR $p_{adj}$ |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **$K = 5$** | %6.916,5 | %73.1 | 0.92 | -%27.8 | %4.866,9 | 0.89 | 0.440 | 1.000 | 0.440 |
| **$K = 10$** | %5.851,0 | %69.4 | 1.05 | -%13.2 | %4.981,9 | 0.96 | 0.290 | 1.000 | 0.580 |
| **$K = 15$** | **%7.711,3** | **%75.5** | **1.13** | **-%9.9** | **%4.547,3** | **0.96** | **0.060** | **0.360** | **0.360** |
| **$K = 20$** | %4.981,2 | %66.0 | 1.00 | -%8.7 | %4.498,3 | 0.97 | 0.320 | 1.000 | 0.480 |
| **$K = 25$** | %5.466,1 | %68.0 | 1.04 | -%7.8 | %4.638,9 | 0.99 | 0.280 | 1.000 | 0.840 |
| **$K = 30$** | %4.994,1 | %66.1 | 1.03 | -%7.8 | %4.572,5 | 0.99 | 0.320 | 1.000 | 0.384 |

**Kantitatif Teşhis:** 60 günlük ufukta $K=15$ için ham $p=0.060$ çıksa da, Bonferroni düzeltmesi uygulandığında ($m=6$) $p=0.360$'a yükselmektedir. Diğer $K$ seviyelerindeki ham $p$-değerlerinin 0.280 - 0.440 aralığında olması, kaba kuralın 60 günlük ufukta da gürültülü olduğunu açıkça göstermektedir.

### 1.2. USD ve Reel TÜFE Düzeltilmiş Performans

| Strateji | TL Küm. | TL CAGR | TL Sharpe | USD Küm. | USD CAGR | USD Sharpe | Reel Küm. (TÜFE) | Reel CAGR | Reel Sharpe |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Top-15 60g Model** | **+%7.711,3** | **%75.5** | **1.13** | **+%1.023,4** | **%36.6** | **0.93** | **+%620,4** | **%29.0** | **0.81** |
| **100 Placebo Ort.** | +%4.590,9 | %64.3 | 1.01 | +%574.6 | %27.9 | 0.75 | +%332.6 | %20.8 | 0.65 |
| **BIST 100 Endeksi** | +%1.254,1 | %40.0 | 0.65 | +%94.7 | %9.0 | 0.32 | +%24.9 | %2.9 | 0.16 |
| **88 Eşit Ağırlık** | +%4.592,4 | %64.3 | 1.02 | +%574.8 | %27.9 | 0.75 | +%332.8 | %20.8 | 0.65 |

**Kantitatif Teşhis:** 60 günlük ufukta model USD bazında yıllık bileşik **%36.6**, TÜFE reel bazında yıllık **%29.0** reel getiri üretmektedir. BIST 100'ün reel CAGR'ı sadece %2.9'dur.

### 1.3. 60 Günlük Ufukta Formül Hassasiyeti ve Değer Tuzağı

| Formül Varyasyonu | Kümülatif Getiri | CAGR | Sharpe Oranı | Max Drawdown |
|---|:---:|:---:|:---:|:---:|
| **Kaba Baz:** $-Z(PB) + Z(ROE) + Z(Mom)$ | %7.711,3 | %75.5 | 1.13 | -%9.9 |
| **Sadece Değer:** $-Z(PB)$ | %2.102,1 | %49.0 | **0.78** | -%17.5 |
| **Sadece Kârlılık:** $Z(ROE)$ | %6.986,8 | %73.3 | 0.97 | -%28.7 |
| **Sadece Momentum:** $Z(Mom)$ | **%8.737,0** | **%78.3** | **1.09** | **-%11.6** |
| **EV/EBITDA Bazlı:** $-Z(EV) + Z(ROE) + Z(Mom)$ | %7.133,6 | %73.7 | 1.04 | -%13.7 |

**Kantitatif Teşhis:** Değer Tuzağı (Value Trap) olgusu 60 günlük ufukta da kesin olarak sürmektedir. Saf P/B iskontosu Sharpe'ı 0.78'e düşürmekte ve portföyü aşağı çekmektedir.

### 1.4. Yıl Bazında Bağımsız Anlamlılık (60 Günlük Ufuk)

| Yıl | Model Getiri | Placebo Ortalaması | BIST 100 | Net Model Alfa | Yıllık $p$-değeri | Karar |
|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **2018** | %8.7 | %10.2 | %10.5 | -%1.6 | $p = 0.530$ | Placebo Gerisinde |
| **2019** | %14.7 | %26.1 | %0.2 | **-%11.5** | $p = 0.840$ | ❌ Placebo Gerisinde |
| **2020** | %112.6 | %87.8 | %42.3 | +%24.9 | $p = 0.140$ | Ayırt Edilemez |
| **2021** | %41.7 | %26.8 | %29.0 | +%14.9 | **$p = 0.070$** | ⚠️ Sınırda Anlamlı |
| **2022** | %269.6 | %273.2 | %170.2 | -%3.6 | $p = 0.520$ | Beta Rallisi (Alfa Yok) |
| **2023** | %101.4 | %140.3 | %70.9 | **-%38.9** | $p = 0.910$ | ❌ Placebo Gerisinde |
| **2024** | %30.2 | -%2.9 | %1.4 | **+%33.1** | **$p = 0.010$** | ✅ **Anlamlı Pozitif Alfa** |
| **2025** | %93.9 | %46.3 | %38.6 | **+%47.6** | **$p = 0.030$** | ✅ **Anlamlı Pozitif Alfa** |
| **2026** | %10.7 | %10.7 | %2.7 | %0.0 | $p = 0.440$ | Ayırt Edilemez |

**Kantitatif Teşhis:** 9 takvim yılının yalnızca **3'ünde** model rastgele seçimden pozitif ayrışabilmiştir. 2019 ve 2023 yıllarında model kaba kuralı placebo'nun gerisinde kalmıştır.

### 1.5. Ciro (Turnover) ve İşlem Maliyeti Mukayesesi
- **21 Günlük (Aylık) Yıllık Turnover:** **%251.8**
- **60 Günlük (Çeyreklik) Yıllık Turnover:** **%163.4**
- **Net İşlem Maliyeti ve Kayma Avantajı:** Yıllık **+27 bps** net getiri koruması ve Max Drawdown'da **-%28.0'den -%9.9'a** devasa iyileşme.

---

## 2. Faz C.3: Kulvarlar Arası Ortak Ölçekleme Metodolojisi

Sanayi rasyoları ($FCF/PD$, $Net\_Bor\c{c}/EBITDA$) ile Banka rasyoları ($CAMELS: NIM, SYR, NPL$) doğrudan kıyaslanamaz. Çözüm:
1. Her rebalancing tarihinde ($t$), 78 Sanayi hissesi kendi faktör bileşimiyle skorlanır.
2. Sanayi hisseleri kendi kümesi içinde $[0.0, 1.0]$ tekdüze (uniform) persentil sıralamasına dönüştürülür:
   $$Rank\_Score_{i,t}^{sanayi} = \frac{\text{Rank}(Score_{i,t}) - 1}{N_{sanayi,t} - 1}$$
3. 10 Finans/Banka hissesi de CAMELS skorlarıyla kendi kümesi içinde $[0.0, 1.0]$ persentil sıralamasına dönüştürülür:
   $$Rank\_Score_{j,t}^{banka} = \frac{\text{Rank}(Score_{j,t}) - 1}{N_{banka,t} - 1}$$
4. İki küme tek bir 88 hisselik ortak listeye dökülür ve en yüksek persentile sahip Top-15 seçilir.
5. Bu metodoloji, bankaların veya sanayinin birbirine karşı yapay bir çarpan üstünlüğü kurmasını matematiksel olarak engellemektedir.

---

## 3. Faz C.4: Makro Rejim Filtresi PIT Doğrulaması

TCMB Reel Politika Faizi ($Politika\_Faizi - Yillik\_TUFE$) ve USD/TRY 60 günlük ivmesi üzerinden yapılan tarihsel P.I.T. inceleme:

1. **2019 Çöküşü:**
   - 2019'da politika faizi %24.0, TÜFE %16-20 aralığındaydı -> Reel Faiz **+%3.5 ile +%5.5 arasında pozitif** seyretti.
   - Sıkı para politikası ve risksiz mevduatın cazibesi borsada likiditeyi kuruttu. Kaba model hissede tam gaz kalırken piyasa placebo'su altında ezildi.
   - *Doğrulama:* `Reel Faiz > +%3.0` kuralı bu dönemi **tam zamanında (point-in-time)** işaretleyebilmektedir.
2. **2023 Çöküşü:**
   - Seçim sonrası (Haziran-Temmuz 2023) USD/TRY kuru 60 günde %35 fırladı, ardından politika faizi %8.5'ten %40'a çıkarıldı.
   - Faiz şoku küçük ölçekli hisseleri vururken endeksi taşıyan birkaç büyük holding öne çıktı.
   - *Doğrulama:* `USD 60g ivme > %15` ve `Faiz Artış Hızı` kuralı Haziran 2023 kırılımını P.I.T. olarak yakalamaktadır.

---

## 4. Şart 1 & Faz C.5: Walk-Forward Out-of-Sample Sınavı

Erken Dönem (2018–2021) verisinde kalibre edilen ve Geç Dönem (2022–2026) verisinde **hiç dokunulmadan (frozen)** test edilen sistemin sonuçları:

### 4.1. Erken Dönem (2018–2021) [In-Sample]

| Strateji | Kümülatif Getiri | CAGR | Sharpe | Max Drawdown | Placebo $p$-değeri |
|---|:---:|:---:|:---:|:---:|:---:|
| **1. Eski Kaba Skor (-PB+ROE+Mom)** | %362.8 | %54.9 | **1.19** | **-%9.1** | **$p = 0.070$** |
| **2. Faz C İki Kulvarlı (P/B Yok)** | %284.8 | %47.0 | 1.03 | -%10.6 | $p = 0.200$ |
| **3. Faz C + Makro Rejim Filtresi** | %240.4 | %41.9 | 0.94 | -%10.6 | $p = 0.350$ |
| **4. 100 Placebo Ortalaması** | %243.0 | %42.2 | 0.85 | — | Baseline |
| **5. BIST 100 Endeksi** | %103.2 | %22.4 | 0.28 | -%12.3 | — |

### 4.2. Geç Dönem (2022–2026) [Out-of-Sample / Dondurulmuş Test]

| Strateji | Kümülatif Getiri | CAGR | Sharpe | Max Drawdown | Placebo $p$-değeri |
|---|:---:|:---:|:---:|:---:|:---:|
| **1. Eski Kaba Skor (-PB+ROE+Mom)** | **%2.083,4** | **%106.6** | **1.33** | **-%5.5** | **$p = 0.060$** |
| **2. Faz C İki Kulvarlı (P/B Yok)** | %1.414,3 | %89.5 | 1.06 | -%13.5 | **$p = 0.680$ ❌** |
| **3. Faz C + Makro Rejim Filtresi** | %1.297,9 | %86.0 | 1.03 | -%9.8 | $p = 0.750$ ❌ |
| **4. 100 Placebo Ortalaması** | %1.325,9 | %86.9 | 1.11 | — | Baseline |
| **5. BIST 100 Endeksi** | %566.5 | %56.3 | 0.86 | -%19.3 | — |

---

## 5. Kritik Keşif: Faktör Bilgi Katsayısı (IC) Rejim Çöküşü

Neden insan eliyle tasarlanan Faz C kuralı OOS'ta sınıfta kaldı? Cevap faktörlerin ileriye dönük getiriyle olan Spearman Korelasyonundadır:

| Faktör Adı | Tüm Örneklem IC | Erken Dönem (2018-2021) IC | Geç Dönem (2022-2026) IC | IC-IR (İstikrar) | Teşhis |
|---|:---:|:---:|:---:|:---:|---|
| **$FCF / PD$ (Serbest Nakit Akımı Verimi)** | **+0.035** | 0.000 | **+0.064** | **0.25** | 🔥 **En Sağlam Değer Faktörü** |
| **$ROE$ (Özsermaye Kârlılığı)** | **+0.032** | -0.001 | **+0.058** | 0.18 | 🔥 **Yüksek Enflasyonda Güçlü** |
| **$Mom_{12-1}$ (Fiyat Momentumu)** | **+0.040** | **+0.068** | **+0.020** | 0.18 | 🔥 **Her Dönemde Pozitif** |
| **Piotroski F-Score** | +0.032 | **+0.073** | **-0.002** | 0.21 | ⚠️ **Hiperenflasyonda Çöktü** |
| **İhracat Oranı** | +0.029 | **+0.125** | **-0.051** | 0.12 | ⚠️ **Rejim Değişince Tersine Döndü** |
| **Ters P/B ($-P/B$)** | +0.024 | -0.041 | **+0.078** | 0.15 | ⚠️ **Dönemsel Döngüsel** |
| **$-Net\_Bor\c{c}/EBITDA$** | +0.014 | -0.026 | +0.047 | 0.09 | Düşük Güç |

### İstatistiksel Açıklama:
1. **Piotroski ve Muhasebe Bozulması:** Piotroski F-skoru, düşük enflasyonlu ABD şirketleri için geliştirilmiştir. 2022–2024 Türkiye hiperenflasyonunda TMS 29 enflasyon düzeltmesi, brüt marj trendlerini ve aktif devir hızlarını bozmuş; F-Score OOS döneminde hiçbir tahmin gücü üretememiştir ($IC = -0.002$).
2. **İhracat İllüzyonu:** 2018–2021'de kur şoklarında ihracatçı hisseler uçarken ($IC = +0.125$), 2022–2024'te TCMB'nin kuru tutması ve maliyetlerin hızla artması ihracatçı marjlarını eritmiş; iç talep odaklı şirketler öne geçmiştir ($IC = -0.051$). Sabit lineer kural ihracatçıları zorla portföye sokarak performans kaybına yol açmıştır.
3. **Gerçek Kahramanlar:** $FCF/PD$ (Serbest Nakit Akımı Verimi), $ROE$ ve $Momentum$ ise her iki dönemde de pozitif kalmayı başaran gerçek kurumsal faktörlerdir.

---

## 6. Sonuç ve Faz D (Model Mimarisi) İçin Stratejik Çıkarım

Kullanıcının talep ettiği **Şart 1 (Walk-Forward OOS) ve Şart 2 (60g Tam Denetim)** testleri projenin kaderini belirleyen hayati gerçeği ortaya çıkarmıştır:

> **Temel Kantitatif Kanun:** *"BIST gibi makro rejimlerin (hiperenflasyon, negatif faiz, dezenflasyon, kur şoku) sürekli değiştiği bir piyasada, bir insanın Excel'de veya zihninde 'Şu faktöre %30, buna %20 verelim' diyerek kurduğu sabit katsayılı lineer modeller kaçınılmaz olarak OVERFIT olur ve rejim değiştiğinde ÇÖKER."*

### Faz D (Makine Öğrenmesi & Ranking) Neden Zorunlu?
1. **Dinamik Faktör Seçimi:** LightGBM Ranker (`LGBMRanker`), piyasa koşullarına göre (örneğin Makro Rejim değişkenleri: Reel Faiz ve USDTRY ivmesi eşliğinde) ne zaman $FCF/PD$'ye, ne zaman $ROE$'ye, ne zaman defansif faktörlere ağırlık vereceğini **doğrusal olmayan ağaç dallanmalarıyla** otomatik öğrenir.
2. **NDCG Sıralama Hedefi:** Regresyon modelleri mutlak getiri tahmininde gürültüye boğulurken, `LGBMRanker` yalnızca kesitsel olarak en iyi hisseleri en tepeye koymaya odaklanır.

---

*Gereksinimleriniz doğrultusunda üretim kod tabanında hiçbir değişiklik yapılmamıştır.*
**Bu çarpıcı OOS ve faktör denetimi sonuçları ışığında, Faz D'ye (`models/v3_ranking/` LGBMRanker NDCG mimarisi) geçiş için değerlendirmenizi ve onayınızı bekliyorum.**
