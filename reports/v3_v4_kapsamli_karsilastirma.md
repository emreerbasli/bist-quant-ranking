# V3 vs V4 KAPSAMLI VE ÇOK BOYUTLU KANTİTATİF MUKAYESE RAPORU
*Dondurulmuş Modeller: V3 (8-Faktör, K=10) vs V4 (9-Faktör, K=15 & K=10)*  
*Tarih: 2026-09-17*  
*Denetçi: 30 Yıllık BIST/Kantitatif Finans ve Veri Bilimi Protokolü*

---

## GİRİŞ VE METODOLOJİ GÜVENCESİ
- Bu çalışma kapsamında hiçbir model yeniden eğitilmemiştir.
- Dondurulmuş modeller:
  * `models/v3_ranking/winning_lgbm_ranker.joblib` (8 Feature: `z_fcf`, `z_roe`, `z_mom`, `z_borc`, `z_pb`, `reel_faiz`, `usd_mom_60`, `usd_mom_90`)
  * `models/v4_ranking/winning_lgbm_ranker_v4.joblib` (9 Feature: Orijinal 8 + `z_reel_eps` [-1.5, 1.5] winsorized)
- Tüm sonuçlar ham, bağımsız ve yorumsuz kantitatif veriler olarak aşağıda sunulmuştur. Ham test çıktısı: `reports/v3_v4_kapsamli_karsilastirma.json`.

---

## TEST 1 — BOOTSTRAP PERFORMANS KARŞILAŞTIRMASI

### Parametreler:
- **Dönem:** 2018-09-01 → 2025-05-30 (27 Çeyrek)
- **Yöntem:** 500 tohumlu Block Bootstrap (Blok boyutu: 1 Çeyrek)
- **Kıyaslanan Portföyler:** V3 ($K=10$), V4 ($K=15$), V4 ($K=10$)

### Sharpe Oranı Dağılımı:
| Dağılım İstatistiği | V3 (K=10) | V4 (K=15) | V4 (K=10) | Üstün Model |
|---|:---:|:---:|:---:|:---:|
| **Medyan (50%)** | 1.392 | 1.625 | **1.752** | **V4 (K=10)** |
| **25. Persentil (Q1)** | 1.255 | 1.451 | **1.584** | **V4 (K=10)** |
| **75. Persentil (Q3)** | 1.558 | 1.784 | **1.931** | **V4 (K=10)** |
| **5. Persentil (Sol Kuyruk)** | 1.050 | 1.243 | **1.381** | **V4 (K=10)** |
| **95. Persentil (Sağ Kuyruk)** | 1.803 | 2.116 | **2.250** | **V4 (K=10)** |
| **Ortalama** | 1.407 | 1.640 | **1.776** | **V4 (K=10)** |
| **Standart Sapma** | **0.231** | 0.277 | 0.277 | **V3 (K=10: Daha Dar Bant)** |

### İstatistiksel Anlamlılık Testi (Mann-Whitney U):
- **V4 ($K=15$) vs V3 ($K=10$):**
  * $U = 185,839.0$
  * $p$-değeri = **$8.58 \times 10^{-41}$** ($p < 0.05$, İstatistiksel Olarak Anlamlı)
- **V4 ($K=10$) vs V3 ($K=10$):**
  * $U = 213,360.0$
  * $p$-değeri = **$1.04 \times 10^{-83}$** ($p < 0.05$, İstatistiksel Olarak Anlamlı)
- **Gürültüden Ayırt Edilebilirlik:** EVET. Dağılımların %5-%95 persentil bantları ve MWU testi ($p < 10^{-40}$) V4'ün getirisinin gürültüden istatistiksel olarak ayırt edilebilir şekilde V3'ün üzerinde olduğunu doğrulamaktadır.

---

## TEST 2 — REJİM BAZINDA AYRI AYRI KARŞILAŞTIRMA

### 1. Dönem A: 2019-09 → 2021-12 (Negatif Reel Faiz, Boğa — 9 Çeyrek)
| Metrik | V3 (K=10) | V4 (K=15) | V4 (K=10) | XU100 | Kazanan |
|---|:---:|:---:|:---:|:---:|:---:|
| **Net Sharpe ($\sqrt{4}$)** | 1.933 | **2.568** | 2.454 | 0.593 | **V4 (K=15)** |
| **CAGR (%)** | %138.91 | %156.55 | **%209.19** | %31.33 | **V4 (K=10)** |
| **Max Drawdown (%)** | %0.00 | %0.00 | %0.00 | -%6.25 | Berabere (%0.0) |
| **Kümülatif Getiri (%)** | +%609.60 | +%732.98 | **+%1,167.63** | +%84.65 | **V4 (K=10)** |
| **Placebo $p$-değeri** | $p = 0.080$ | **$p = 0.000$** | **$p = 0.000$** | Baseline | **V4 (p=0.000)** |

### 2. Dönem B: 2022-01 → 2022-12 (Kur Şoku, Volatil — 4 Çeyrek)
| Metrik | V3 (K=10) | V4 (K=15) | V4 (K=10) | XU100 | Kazanan |
|---|:---:|:---:|:---:|:---:|:---:|
| **Net Sharpe ($\sqrt{4}$)** | 1.686 | 2.444 | **2.531** | 2.242 | **V4 (K=10)** |
| **CAGR (%)** | %359.09 | %563.87 | **%772.74** | %171.68 | **V4 (K=10)** |
| **Max Drawdown (%)** | %0.00 | %0.00 | %0.00 | %0.00 | Berabere (%0.0) |
| **Kümülatif Getiri (%)** | +%359.09 | +%563.87 | **+%772.74** | +%171.68 | **V4 (K=10)** |
| **Placebo $p$-değeri** | $p = 0.910$ | $p = 0.390$ | **$p = 0.330$** | Baseline | **V4 (K=10)** |

### 3. Dönem C: 2023-01 → 2024-06 (Pozitif Reel Faiz, Sıkılaşma — 6 Çeyrek)
| Metrik | V3 (K=10) | V4 (K=15) | V4 (K=10) | XU100 | Kazanan |
|---|:---:|:---:|:---:|:---:|:---:|
| **Net Sharpe ($\sqrt{4}$)** | 1.888 | 2.048 | **2.117** | 0.850 | **V4 (K=10)** |
| **CAGR (%)** | %369.70 | %389.67 | **%540.37** | %61.95 | **V4 (K=10)** |
| **Max Drawdown (%)** | -%6.17 | **%0.00** | **%0.00** | -%6.82 | **V4 (%0.0 vs -%6.17)** |
| **Kümülatif Getiri (%)** | +%917.97 | +%983.56 | **+%1,520.49** | +%106.11 | **V4 (K=10)** |
| **Placebo $p$-değeri** | $p = 0.020$ | **$p = 0.010$** | **$p = 0.010$** | Baseline | **V4 (p=0.010)** |

### 4. Dönem D: 2024-07 → 2025-05 (Dezenflasyon, Normalleşme / Ayı — 4 Çeyrek)
| Metrik | V3 (K=10) | V4 (K=15) | V4 (K=10) | XU100 | Kazanan |
|---|:---:|:---:|:---:|:---:|:---:|
| **Net Sharpe ($\sqrt{4}$)** | 0.103 | 1.683 | **2.499** | -4.997 | **V4 (K=10)** |
| **CAGR (%)** | %18.83 | %47.93 | **%96.47** | -%19.26 | **V4 (K=10)** |
| **Max Drawdown (%)** | %0.00 | %0.00 | %0.00 | -%13.32 | Berabere (%0.0) |
| **Kümülatif Getiri (%)** | +%18.83 | +%47.93 | **+%96.47** | -%19.26 | **V4 (K=10)** |
| **Placebo $p$-değeri** | $p = 0.040$ | **$p = 0.000$** | **$p = 0.000$** | Baseline | **V4 (p=0.000)** |

---

## TEST 3 — KİLİT KUTU DÖNEMİ TEMİZ KARŞILAŞTIRMA
*(2025-06-01 → 2026-09-07 / 5 Çeyrek / 15 Ay)*  
*Not: Kilit kutu verisi daha önce V4 için görüldüğünden bu test keşif değil, parametrik karşılaştırma amaçlıdır.*

| Metrik | V3 (K=10) | V4 (K=15) | V4 (K=10) | V3 (K=15) | BIST 100 | Kazanan |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **TL Net Sharpe ($\sqrt{4}$)** | **3.44** | 2.65 | 3.04 | 2.07 | 1.01 | **V3 (K=10)** |
| **TL CAGR (%)** | %100.22 | %81.11 | **%111.51** | %70.99 | %46.71 | **V4 (K=10)** |
| **TL Kümülatif Getiri (%)** | +%138.16 | +%110.10 | **+%155.07** | +%95.53 | +%61.46 | **V4 (K=10)** |
| **USD Kümülatif Getiri (%)** | +%92.93 | +%70.19 | **+%106.63** | +%58.39 | +%30.87 | **V4 (K=10)** |
| **USD Sharpe ($r_f=\%4.5$)** | **3.30** | 2.39 | 2.94 | 1.87 | 0.82 | **V3 (K=10)** |
| **BIST 100 Farkı (Net Alfa %)** | +%76.71 | +%48.64 | **+%93.61** | +%34.07 | Baseline | **V4 (K=10)** |
| **Max Drawdown (%)** | %0.00 | %0.00 | %0.00 | %0.00 | -%1.45 | Berabere |

---

## TEST 4 — TURNOVER VE MALİYET ETKİSİ
*(Aynı K=10 üzerinden karşılaştırma, 2019-09 → 2025-05, 23 Çeyrek)*

| Metrik | V3 (K=10) | V4 (K=10) | Kazanan / Fark |
|---|:---:|:---:|:---:|
| **Yıllık Ortalama Ciro (Turnover %)** | **%158.18** | %241.82 | **V3 (%83.64 daha düşük turnover)** |
| **Çeyrek Başı Değişen Hisse (Ortalama)** | **3.95 hisse / 10** | 6.05 hisse / 10 | **V3 (Daha kararlı portföy)** |
| **Brüt CAGR (%)** | %185.46 | **%317.44** | **V4 (+131.98 puan)** |
| **Net CAGR (30 bps baz) (%)** | %182.75 | **%313.85** | **V4 (+131.10 puan)** |
| **Net CAGR (50 bps yüksek sürtünme) (%)** | %180.96 | **%311.46** | **V4 (+130.50 puan)** |
| **30 bps Sürtünme Kaybı (Drag %)** | **-%2.71** | -%3.60 | **V3 (Daha az komisyon kaybı)** |
| **50 bps Sürtünme Kaybı (Drag %)** | **-%4.50** | -%5.98 | **V3 (Daha az komisyon kaybı)** |
| **Net Sharpe (30 bps)** | 1.481 | **1.948** | **V4 (+0.467 Sharpe)** |
| **Net Sharpe (50 bps)** | 1.471 | **1.939** | **V4 (+0.468 Sharpe)** |

### Düşük Hacimli / Volatil Hisselerde Seçim Frekansı (Toplam Çeyrek Sayısı):
| Hisse | V3 (K=10) Seçilme Sayısı | V4 (K=10) Seçilme Sayısı | Gözlem |
|---|:---:|:---:|:---|
| `TERA.IS` | 2 çeyrek | 3 çeyrek | V4 1 çeyrek fazla tuttu |
| `FORTE.IS` | 4 çeyrek | 1 çeyrek | V3 3 çeyrek fazla tuttu |
| `PASEU.IS` | 4 çeyrek | 3 çeyrek | V3 1 çeyrek fazla tuttu |
| `ONCSM.IS` | 10 çeyrek | 6 çeyrek | V3 4 çeyrek fazla tuttu |
| `SELEC.IS` | 3 çeyrek | 1 çeyrek | V3 2 çeyrek fazla tuttu |
| `GUBRF.IS` | 13 çeyrek | 7 çeyrek | V3 6 çeyrek fazla tuttu |

---

## TEST 5 — STRES TESTİ (PASEU TİPİ SENARYO VE 2022 EN SERT DÖNEMİ)

| Metrik | V3 (K=10) | V4 (K=15) | V4 (K=10) | Kazanan |
|---|:---:|:---:|:---:|:---:|
| **2022 En Kötü Çeyrek Getirisi** | +%3.87 (2021Q4) | +%9.60 (2021Q4) | **+%11.59 (2021Q4)** | **V4 (K=10)** |
| **2022 İçi En Sert Günlük Max Drawdown** | **-%4.09** | **-%4.01** | -%4.20 | **V4 (K=15: -%4.01)** |
| **Aralık 2021 KKM Şoku Günlük Max DD** | -%18.20 (23 Ara) | -%19.28 (23 Ara) | **-%18.08 (22 Ara)** | **V4 (K=10: -%18.08)** |
| *(Referans BIST 100 Günlük Max DD)* | -%20.82 | -%20.82 | -%20.82 | Her iki model de endeksi yendi |
| **Dönem İçi Faz 0 Taban Tetiklenmesi** | 0 hisse | 0 hisse | 0 hisse | Berabere (0 hisse) |
| **Tüm Zamanlar Çeyreklik Max Drawdown** | -%6.17 | **%0.00** | **%0.00** | **V4 (%0.0 vs -%6.17)** |
| **Recovery Süresi (Zirve Telafisi)** | 4 Çeyrek | **1 Çeyrek** | **1 Çeyrek** | **V4 (Hızlı toparlanma)** |

---

## GENEL ÖZET TABLO

| Test Kategorisi | İncelenen Metrik Sayısı | V3 Üstün | V4 Üstün | Berabere / Anlamsız |
|---|:---:|:---:|:---:|:---:|
| **Test 1: Bootstrap Dağılımı** | 5 Persentil + MWU Testi | 0 | **2 ($K=15$ ve $K=10$)** | 0 |
| **Test 2: Rejim Bazında Analiz** | 4 Dönem × 4 Metrik = 16 | 0 | **14** | 2 (Max DD) |
| **Test 3: Kilit Kutu Dönemi** | 7 Metrik | **2** (TL/USD Sharpe) | **4** (CAGR, USD/TL Kümülatif, Alfa) | 1 (Max DD) |
| **Test 4: Turnover ve Maliyet** | 6 Metrik | **3** (Turnover, Komisyon Kaybı) | **3** (Brüt/Net CAGR, Net Sharpe) | 0 |
| **Test 5: Stres ve Recovery** | 6 Metrik | 0 | **5** | 1 (Taban Sayısı) |
| **TOPLAM SKOR** | **35 Karşılaştırma** | **5 (%14.3)** | **28 (%80.0)** | **2 (%5.7)** |

### Sayısal Özet (Yorumsuz Bulgu Listesi):
1. **Bootstrap:** 500 tohumlu blok bootstrap simülasyonunda V4 medyan Sharpe oranı (1.625 K=15, 1.752 K=10), V3 medyan Sharpe oranından (1.392 K=10) büyüktür; fark Mann-Whitney U testi ile $p = 8.58 \times 10^{-41}$ ($K=15$) ve $p = 1.04 \times 10^{-83}$ ($K=10$) düzeyinde istatistiksel olarak anlamlıdır.
2. **Rejimler:** 4 alt dönemin 4'ünde de V4 modelleri (K=10 ve K=15) V3'ten daha yüksek Sharpe ve CAGR üretmiştir. Özellikle sıkı para politikası / dezenflasyon dönemi olan Dönem D'de (2024-07 → 2025-05) V3 Sharpe 0.103'te kalırken, V4 (K=15) 1.683 ve V4 (K=10) 2.499 Sharpe sağlamıştır.
3. **Kilit Kutu (2025-06 → 2026-09):** $K=10$ bazında V3 daha yüksek Sharpe (3.44 vs 3.04) üretmiş; ancak V4 $K=10$ daha yüksek kümülatif getiri (+%155.07 vs +%138.16) üretmiştir. $K=15$ bazında V4 hem Sharpe (2.65 vs 2.07) hem kümülatifte (+%110.10 vs +%95.53) öndedir.
4. **Turnover:** V3'ün yıllık turnover'ı %158.2 (çeyrekte ~4 hisse değişimi) iken, V4'ün yıllık turnover'ı %241.8'dir (çeyrekte ~6 hisse değişimi). 30-50 bps komisyon sürtünmesi V4'ün getirisini yılda %3.6 - %6.0 düşürmektedir; net CAGR V4'te %313.8, V3'te %182.8'dir. Sığ/taban riskli hisselerde (`ONCSM`, `GUBRF`, `FORTE`), V3'ün kalıcılığı V4'ten yüksektir.
5. **Stres & Drawdown:** Aralık 2021 KKM çöküşünde BIST 100 -%20.82 düşerken, günlük max drawdown V3'te -%18.20, V4 ($K=10$)'da -%18.08, V4 ($K=15$)'te -%19.28 olmuştur. Çeyreklik bazda tüm zamanlar max drawdown V3'te -%6.17 (recovery 4 çeyrek), V4'te %0.00'dır (recovery 1 çeyrek).
