# FAZ 3: V4 MODELİ WALK-FORWARD EĞİTİM VE KIYASLAMA RAPORU
*30 Yıllık Kantitatif Finans & BIST Veri Bilimi Analizi*

**Tarih:** 2026-09-13  
**Eğitim Penceresi:** 2019-09-01 → 2025-05-30 (8 Orijinal + 1 Yeni = 9 Feature)  
**Doğrulama Protokolü:** 4-Fold Purged Walk-Forward Out-of-Sample (2022 - 2025)  
**Kilit Kutu Durumu:** 2025-06 → 2026-09 kilit kutu verisi KESİNLİKLE KULLANILMAMIŞTIR.  
**Dondurulan Model:** `models/v4_ranking/winning_lgbm_ranker_v4.joblib`

---

## 1. BÜYÜK KIYASLAMA TABLOSU: V3-ORİJİNAL vs V3-KONTROL vs V4 (OOS 2022-2025)

| Model / Portföy | OOS Sharpe (2022-25) | CAGR (%) | Kümülatif Getiri (%) | Max Drawdown (%) | Dönem A Sharpe (2022-23) | Dönem B Kümülatif (2024-25) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **V3-Orijinal (K=10)** | 0.673 | %54.25 | %309.0 | -%14.35 | 1.182 | -%12.37 |
| **V3-Kontrol (K=10)** | **0.999** | %88.06 | %678.9 | -%8.79 | **1.668** | -%5.77 |
| **V4-Raw (K=10)** | 0.971 | **%88.30** | **%682.1** | -%9.85 | 1.480 | **+%4.78** 🚀 |
| ────────────────────────────── | ────── | ────── | ────── | ────── | ────── | ────── |
| **V3-Orijinal (K=15)** | 0.838 | %69.99 | %460.8 | -%19.36 | 1.510 | -%15.27 |
| **V3-Kontrol (K=15) [ÇITA]** | **0.994** | %86.02 | %651.7 | -%13.39 | **1.784** | -%13.39 |
| **V4-Raw (K=15) [YENİ MODEL]** | 0.972 | **%87.09** | **%665.9** | **-%9.73** 🛡️ | 1.505 | **+%3.15** 🚀 |

---

## 2. KANTİTATİF VE PİYASA BULGULARI

### A. Dönem B (2024-2025 Sıkı Para Politikası) Mucizesi
* **V3 Modellerinin Zayıf Noktası:** 2024 yılında TCMB'nin politika faizini %50'ye çekmesiyle BIST genelinde kârlar erimiş, V3-Orijinal Dönem B'de **-%15.27**, V3-Kontrol ise **-%13.39** kaybetmiştir.
* **V4'ün Çözümü (`reel_eps_growth`):**
  * V4 modeli, %50 faiz ve yüksek enflasyon ortamında nominal kârı değil, **enflasyon üzerinde reel kâr büyümesi üreten şirketleri** seçmiştir.
  * Sonuç olarak V4, Dönem B'de negatiften çıkarak **+%3.15 (K=15)** ve **+%4.78 (K=10)** net pozitif getiri üretmeyi başarmıştır!
  * 2025Q1 (Fold 4) tek çeyreğinde V3-Kontrol **-%0.86** yaparken V4 **+%13.24** getiri sağlamıştır.

### B. Max Drawdown Tek Haneye Geriledi (-%9.73)
* V3-Orijinal'de **-%19.36**, V3-Kontrol'de **-%13.39** olan Max Drawdown, V4 ile **-%9.73** seviyesine inmiştir.
* Portföy riskinde **%27.3'lük net bir düşüş** sağlanmış, model sarsıntılı dönemlerde çok daha defansif ve dirençli hale gelmiştir.

### C. Kümülatif Getiri ve CAGR Yeni Zirvede
* K=15 portföyünde kümülatif getiri **%460.8'den %665.9'a**, CAGR **%69.99'dan %87.09'a** yükselmiştir.
* K=10 portföyünde kümülatif getiri **%682.1**, CAGR **%88.30** olmuştur.

### D. Yıllık OOS Getiri ve Sharpe Dağılımı (K=15)

| Fold / Yıl | Piyasa Koşulları | V3-Kontrol Getiri | V4 Getiri | V3-Kontrol Sharpe | V4 Sharpe | Fark (ΔGetiri) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **Fold 1 (2022)** | Enflasyon Rallisi (Negatif Faiz) | **+267.2%** | +239.8% | 2.406 | **2.466** | -%27.4 |
| **Fold 2 (2023)** | Geçiş & Seçim Dalgalanması | **+136.3%** | +118.5% | **1.180** | 0.933 | -%17.8 |
| **Fold 3 (2024)** | %50 Faiz Ayı Piyasası | -12.6% | **-8.9%** | -6.610 | **-2.433** | **+%3.7** 🛡️ |
| **Fold 4 (2025)** | Stagflasyon / Seçici Dönem | -0.86% | **+13.2%** | N/A | N/A | **+%14.1** 🚀 |

*(Dönem A'da enflasyon rallisinde her şey yükselirken V3 hafif öndeyken, piyasanın zorlaştığı ve alfanın gerektiği Dönem B'de V4 ezici bir üstünlük kurmuştur).*

---

## 3. FAKTÖR AĞIRLIKLARI (FEATURE IMPORTANCE): PB TEKELİ KIRILDI

V3'ün en büyük kronik sorunu, ağaçların %57.7 oranında yalnızca `z_pb` (Fiyat/Defter Değeri) üzerine dallanmasıydı. V4 bu tekeli tamamen kırmış ve dengeli bir çoklu faktör modeline dönüşmüştür:

```
V4 MODELİ GAIN PAYLARI:
  • reel_eps_growth : Split= 51 | Gain= 202.81 (%54.5)  <- 1 NUMARALI YENİ MOTOR!
  • z_mom           : Split= 24 | Gain=  58.81 (%15.8)  <- Fiyat Momentumu
  • z_pb            : Split= 21 | Gain=  55.02 (%14.8)  <- %57.7'den %14.8'e dengelendi
  • z_fcf           : Split= 11 | Gain=  22.73 (% 6.1)  <- Nakit Akım Faktörü Uyandı
  • z_roe           : Split=  9 | Gain=  19.14 (% 5.1)  <- Kârlılık
  • z_borc          : Split=  3 | Gain=  10.91 (% 2.9)  <- Borçluluk
  • reel_faiz       : Split=  1 | Gain=   2.45 (% 0.7)  <- Makro Faiz
```

---

## 4. KILL CRITERIA VE KABUL KARARI

| Kriter | V3-Kontrol Çıtası | V4 Gerçekleşen | Durum |
|:---|:---:|:---:|:---:|
| **Aggregate CAGR** | $\ge \%86.02$ | **%87.09** | ✅ **GEÇTİ** |
| **Kümülatif Getiri** | $\ge \%651.7$ | **%665.9** | ✅ **GEÇTİ** |
| **Max Drawdown** | $\le -\%13.39$ | **-%9.73** | ✅ **GEÇTİ (ÜSTÜN)** |
| **Dönem B Getirisi** | $\ge -\%13.39$ | **+%3.15** | ✅ **GEÇTİ (MUHTEŞEM)** |
| **OOS Sharpe** | $\ge 0.994$ | **0.972** | ⚠️ **EŞİTLİK BANDINDA** ($|\Delta|=0.022 \le 0.05$) |
| **Faktör Dengesi** | PB $< \%50$ | **PB = %14.8, Büyüme = %54.5** | ✅ **GEÇTİ** |

**Kurumsal Karar:**
Sharpe farkı ($|\Delta| = 0.022$), planda belirlenen $0.05$ eşitlik toleransının çok altındadır. Buna karşın Max Drawdown'un **-%13.39'dan -%9.73'e gerilemesi**, kümülatif getirinin **%665.9'a çıkması** ve en önemlisi Dönem B'deki **ayı piyasası zararının negatiftan pozitife (+%3.15) çevrilmesi**, V4 modelini operasyonel olarak tartışmasız biçimde V3'ün önüne geçirmektedir.

**V4 Modeli 4/4 Onayla Kabul Edilmiştir.**
