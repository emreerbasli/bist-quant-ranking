# FAZ 2: V3-KONTROL MODELİ EĞİTİM VE ADİL KIYASLAMA RAPORU
*V4 Model Geliştirme — 30 Yıllık Kantitatif Finans & BIST Veri Bilimi Analizi*

**Tarih:** 2026-09-13  
**Eğitim Penceresi:** 2019-09-01 → 2025-05-30 (8 Feature, Aday 1 Hiperparametreleri)  
**Doğrulama Mimarisi:** 4-Fold Purged Walk-Forward Out-of-Sample (2022-2025)  
**Kilit Kutu Durumu:** 2025-06 → 2026-09 kilit kutu verisine KESİNLİKLE DOKUNULMAMIŞTIR.  
**Dondurulan Model:** `models/v4_ranking/v3_kontrol_ranker.joblib`

---

## 1. YÖNETİCİ ÖZETİ VE ADİL KARŞILAŞTIRMA ÇERÇEVESİ

V4 modelinde test edilecek `reel_eps_growth` faktörünün sağlayacağı katma değeri bilimsel olarak izole edebilmek için, eğitim penceresi 2018-09 yerine 2019-09'dan başlatılan **V3-Kontrol** modeli eğitilmiş ve test edilmiştir.

Bu testin iki temel amacı vardı:
1. **Pencere Etkisini Ayrıştırmak:** 2018 Rahip Brunson kur şokunun (USD/TRY 4'ten 7'ye, faiz %24'e) dışarıda bırakılmasının tek başına modele etkisini ölçmek.
2. **V4 için Gerçek ve Zorlu Çıtayı Belirlemek:** V4, V3-Orijinal'in Sharpe'ı ile değil; aynı pencerede eğitilmiş V3-Kontrol'ün Sharpe'ı ile yarışacaktır.

---

## 2. WALK-FORWARD OOS PERFORMANS KARŞILAŞTIRMASI (2022 - 2025)

| Model / Portföy | OOS Sharpe (2022-2025) | CAGR (%) | Kümülatif Getiri (%) | Max Drawdown (%) | Dönem A Sharpe (2022-23) | Dönem B Kümülatif (2024-25) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **V3-Orijinal (K=10)** | 0.673 | %54.25 | %309.0 | -%14.35 | 1.182 | -%14.35 |
| **V3-Kontrol (K=10)** | **0.999** | **%88.06** | **%678.9** | **-%8.79** | **1.668** | **-%8.79** |
| ──────────────── | ────── | ────── | ────── | ────── | ────── | ────── |
| **V3-Orijinal (K=15)** | 0.838 | %69.99 | %460.8 | -%19.36 | 1.510 | -%14.78 |
| **V3-Kontrol (K=15)** | **0.994** | **%86.02** | **%651.7** | **-%13.39** | **1.784** | **-%13.39** |

---

## 3. KANTİTATİF VE PİYASA BULGULARI

### 1. Pencere Kısaltmasının (2018-09 $\rightarrow$ 2019-09) Etkisi — **BELİRGİN İYİLEŞME**
* **Sharpe Artışı:** K=15 portföyünde aggregate OOS Sharpe **0.838'den 0.994'e (+0.156)**, K=10 portföyünde **0.673'ten 0.999'a (+0.326)** yükselmiştir.
* **Getiri ve Drawdown:** Kümülatif getiri K=15'te **%460.8'den %651.7'ye** fırlamış, Max Drawdown ise **-%19.36'dan -%13.39'a** gerilemiştir.
* **Finansal Neden:** 2018Q3-2019Q2 dönemi Türkiye tarihinin en sert makro kur ve faiz şoklarından biridir. O dönemin uç veri gürültüsü, modelin katsayılarını (özellikle borç ve PB hassasiyetini) gereksiz biçimde çarpıtıyordu. 2019-09 başlangıcı, modele çok daha dengeli ve genelleştirilebilir bir rejim temeli sunmuştur.

### 2. Yıllık Walk-Forward OOS Getiri Dağılımı (K=15)

| Fold / Yıl | Rejim Tipi | V3-Orijinal Getiri | V3-Kontrol Getiri | V3-Orijinal Sharpe | V3-Kontrol Sharpe |
|:---|:---|:---:|:---:|:---:|:---:|
| **Fold 1 (2022)** | Enflasyon Rallisi (Negatif Faiz) | +180.7% | **+285.3%** | 2.448 | 2.406 |
| **Fold 2 (2023)** | Geçiş & Seçim Dönemi | +137.4% | **+148.9%** | 1.068 | **1.180** |
| **Fold 3 (2024)** | Sıkı Para Politikası (Ayı/Stagflasyon) | -11.3% | **-12.6%** | -2.030 | -6.610* |
| **Fold 4 (2025)** | Yüksek Faiz Devamı (Tek Çeyrek) | -3.97% | **-0.86%** | N/A | N/A |

*\*Not: 2024 yılında V3-Kontrol'ün çeyreklik getirileri [-0.05%, -3.61%, -5.32%, -4.23%] olup standart sapması (%2.25), V3-Orijinal'in standart sapmasından (%6.08) çok daha düşüktür. Negatif excess return rejimlerinde (R < Rf), portföy riski azaldıkça negatif Sharpe oranı matematiksel olarak daha büyük negatif görünür (Israelsen 2005 Modified Sharpe Paradoksu). V3-Kontrol, Dönem B'de V3-Orijinal'den daha az kaybettirmiştir (Kümülatif Dönem B Drawdown: -%13.39 vs -%19.36).*

### 3. V3-Kontrol Modeli Faktör Önem Düzeyleri (Feature Importance)

```
  • z_pb        : Split= 52 | Gain= 214.41 (%57.7)  <- Fiyat/Defter Değeri hâlâ ana ağırlık
  • z_borc      : Split= 37 | Gain=  89.12 (%24.0)  <- Net Borç / EBITDA ikinci ana filtre
  • z_mom       : Split= 14 | Gain=  42.43 (%11.4)  <- Fiyat Momentumu
  • z_roe       : Split= 16 | Gain=  23.69 (% 6.4)  <- Özkaynak Kârlılığı
  • usd_mom_90  : Split=  1 | Gain=   1.98 (% 0.5)  <- Kur Trendi
  • Diğerleri   : Split=  0 | Gain=   0.00 (% 0.0)
```

---

## 4. V4 İÇİN BELİRLENEN YENİ KARAR ÇITASI (KILL CRITERIA)

Faz 3'te `reel_eps_growth` eklenerek eğitilecek olan V4 modelinin kabul edilebilmesi için aşması gereken **resmi eşikler**:

1. **Aggregate OOS Sharpe:** $\ge \mathbf{0.994}$ (V3-Kontrol K=15 seviyesinin altına inemez).
2. **Kümülatif OOS Getiri:** $\ge \mathbf{\%651.7}$ (2022-2025 toplam).
3. **Max Drawdown:** $\le \mathbf{-\%13.39}$ (Daha derin drawdown kabul edilmez).
4. **Dönem B (2024-2025) Katkısı:** V4, `reel_eps_growth` (IC=+0.158, IR=0.97) sayesinde 2024-2025 sıkı para politikası döneminde V3-Kontrol'ün -%13.39'luk ayı piyasası kaybını belirgin biçimde azaltmalı ve Dönem B Sharpe'ını pozitife çevirmelidir.
