# Kilit Kutu (Lockbox) Sözleşmesi ve Resmi Kanıt Tutanağı
*Model Güvenilirlik Belgesi — models/v3_ranking Arşivi*

Bu doküman, `models/v3_ranking/winning_lgbm_ranker.joblib` modelinin hangi bilimsel sözleşme altında, hangi kilit kutu verisi üzerinde ve hangi sonuçlarla onaylandığının **değiştirilemez resmi kanıtıdır**.

---

## 1. Sözleşme Şartları (Test Öncesi İmzalanan Taahhüt)

- **Kilit Kutu Dönemi:** `2025-06-01` $\rightarrow$ `2026-09-07` (Son 5 Çeyrek / 15 Ay)
- **Karantina Kuralı:** Model yalnızca `2018-09-01` ile `2025-05-31` arasında eğitilmiştir. Kilit kutu verisi eğitim, hiperparametre arama ve cross-validation süreçlerinde %100 gizlenmiştir.
- **Tek Seferlik Test Şartı:** Kasa tek bir kez açılacak; başarısızlık durumunda ikinci bir deneme yapılmayacak, proje durdurulacaktır.

---

## 2. Dört Resmi Kriter ve Gerçekleşen Sonuçlar

| Kriter | Tanım | Önceden Belirlenen Eşik | Gerçekleşen Değer | Karar |
|:---:|:---|:---:|:---:|:---:|
| **1** | **İstatistiksel Anlamlılık** | $p < 0.10$ | **$p = 0.030$** ($K=10$'da **$p = 0.000$**) | ✅ **GEÇTİ** |
| **2** | **Ekonomik Sharpe Primi** | $\Delta Sharpe \ge +0.20$ | $\Delta Sharpe = 2.09 - 0.77 = \mathbf{+1.32}$ | ✅ **GEÇTİ** |
| **3** | **Piyasa Üstünlüğü** | $R_{model} > R_{XU100}$ | Model: **+%95.9** vs BIST: **+%61.4** ($\Delta = +\%34.5$) | ✅ **GEÇTİ** |
| **4** | **K=10/15/20 Tutarlılığı** | Tüm K'larda Model > Placebo | K=10 ($p=0.000$), K=15 ($p=0.030$), K=20 ($p=0.060$) | ✅ **GEÇTİ** |

---

## 3. Ayrıntılı Kilit Kutu Performansı ($K=10, 15, 20$)

| Strateji | K | Kümülatif Getiri | CAGR | Sharpe Oranı ($\sqrt{4}$) | Max Drawdown | Placebo $p$-değeri |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Dondurulmuş LGBMRanker** | **$K=10$** | **+%137,3** | **%99.6** | **3.41** | **%0.0** | **$p = 0.000$** |
| Bağlamsal Kaba Skor | $K=10$ | +%117,4 | %86.1 | 1.53 | -%4.4 | $p = 0.060$ |
| 100 Tohum Placebo Ortalaması | $K=10$ | +%53,1 | %40.6 | 0.71 | — | Baseline |
| **Dondurulmuş LGBMRanker** | **$K=15$** | **+%95,9** | **%71.3** | **2.09** | **%0.0** | **$p = 0.030$** |
| Bağlamsal Kaba Skor | $K=15$ | +%105,8 | %78.1 | 1.66 | -%1.7 | $p = 0.040$ |
| 100 Tohum Placebo Ortalaması | $K=15$ | +%54,8 | %41.8 | 0.77 | — | Baseline |
| **Dondurulmuş LGBMRanker** | **$K=20$** | **+%86,8** | **%64.8** | **1.69** | **-%1.0** | **$p = 0.060$** |
| Bağlamsal Kaba Skor | $K=20$ | +%113,5 | %83.4 | 2.21 | %0.0 | $p = 0.000$ |
| 100 Tohum Placebo Ortalaması | $K=20$ | +%55,4 | %42.3 | 0.82 | — | Baseline |
| **BIST 100 Endeksi (Kıstas)** | — | +%61,4 | %46.7 | 1.01 | -%1.4 | Market |

---

## 4. Çeyreklik Kırılım Tablosu ($K=15$)

| Kilit Kutu Çeyreği | Dondurulmuş LGBM | Bağlamsal Kaba Skor | 100 Placebo Ortalaması | BIST 100 Endeksi | LGBM Net Çeyreklik Alfa |
|:---|:---:|:---:|:---:|:---:|:---:|
| **2025Q2** | +%24.67 | **+%37.44** | +%29.33 | +%25.21 | -%0.54 |
| **2025Q3** | +%2.18 | +%13.38 | -%4.21 | -%1.45 | **+%3.63** |
| **2025Q4** | +%15.49 | +%21.35 | +%15.63 | +%23.40 | -%7.91 |
| **2026Q1** | **+%24.31** | +%10.74 | +%10.57 | +%2.68 | **+%21.63** 🔥 |
| **2026Q2 (Güncel)** | **+%7.12** | -%1.72 | -%3.65 | +%3.24 | **+%3.88** 🔥 |

---

## 5. Kayıtlara Geçen Kurumsal Şerhler (Caveats)

1. **Örneklem Sınırı ($n=5$):** Kilit kutu örneklemi küçüktür; Sharpe oranları geniş güven aralıkları içerir. 2025Q2 genel bir beta rallisidir.
2. **ML'in Gerçek Katma Değeri:** K=20'de basit formül p=0.000 ile daha güçlüydü. LGBMRanker'ın asıl üstünlüğü %0.0 Drawdown ve 2026 faiz şokundaki dayanıklılığıdır.
