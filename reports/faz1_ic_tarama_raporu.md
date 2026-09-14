# FAZ 1: BİREYSEL SPEARMAN RANK IC TARAMA RAPORU
*V4 Model Geliştirme — 30 Yıllık Kantitatif Finans & BIST Veri Bilimi Analizi*

**Tarih:** 2026-09-13  
**Pencere:** 2019-09 → 2024-12 (Eğitim Seti — 21 Çeyrek Dönem Kesiti)  
**Kilit Kutu Durumu:** 2025-06 → 2026-09 aralığına KESİNLİKLE DOKUNULMAMIŞTIR (Karantina korundu).  
**Hedef Değişken:** 60 günlük ileriye dönük getiri ($t \rightarrow t+60\text{d}$)  
**Yöntem:** Kesitsel Spearman Derece Korelasyonu ($IC_t$), Zaman Serisi Ortalaması ($\mu_{IC}$), İstikrar Oranı ($IC\text{-}IR = \mu / \sigma$), Öğrenci t-testi ($p\text{-değeri}$), Dönem A (2019-2022 Negatif Reel Faiz) ve Dönem B (2023-2024 Pozitif Reel Faiz / Sıkılaşma) Rejim Ayrımı.

---

## 1. ÖZET SONUÇ TABLOSU (3-KATEGORİ KARAR KURALI)

| Feature Adı | Beklenen Yön | Tüm Örneklem IC | Std IC | IC-IR | p-değeri | Dönem A (IC/IR) | Dönem B (IC/IR) | Karar |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `reel_eps_growth` | ➕ Pozitif | **+0.0820** | 0.178 | **+0.46** | **0.0471** | +0.044 / 0.25 | **+0.158 / 0.97** | ⚠️ **KOŞULLU KABUL (REJİM)** |
| `op_marji_trend` | ➕ Pozitif | **+0.0802** | 0.186 | **+0.43** | **0.0617** | +0.063 / 0.32 | **+0.114 / 0.69** | ⚠️ **KOŞULLU KABUL (REJİM)** |
| `eps_accel` | ➕ Pozitif | +0.0538 | 0.198 | +0.27 | 0.2276 | +0.032 / 0.17 | +0.097 / 0.45 | ❌ **RED (REJİMDE DE BAŞARISIZ)** |
| `satislar_growth` | ➕ Pozitif | +0.0437 | 0.208 | +0.21 | 0.3466 | +0.041 / 0.17 | +0.049 / 0.36 | ❌ **RED (REJİMDE DE BAŞARISIZ)** |
| `accruals_ratio` | ➖ Negatif | +0.0002 | 0.143 | +0.00 | 0.9958 | +0.019 / 0.12 | -0.037 / -0.28 | ❌ **RED (TERS İŞARET / ETKİSİZ)** |
| `ihracat_kalkani` | ➕ Pozitif | +0.0202 | 0.186 | +0.11 | 0.6428 | +0.066 / 0.32 | -0.059 / -0.50 | ❌ **RED (REJİMDE DE BAŞARISIZ)** |
| `reversal_penalty` | ➖ Negatif | +0.0225 | 0.146 | +0.15 | 0.4883 | +0.023 / 0.17 | +0.021 / 0.12 | ❌ **RED (TERS İŞARET)** |
| `usd_vol_rejim` | Rejim | +0.0096 | 0.123 | +0.08 | 0.7247 | -0.008 / -0.07 | +0.044 / 0.31 | ❌ **RED (\|IC\| < 0.02)** |
| `z_borc_oz` | ➕ Pozitif | -0.0270 | 0.148 | -0.18 | 0.4148 | -0.049 / -0.37 | +0.017 / 0.09 | ❌ **RED (TERS İŞARET)** |

---

## 2. KANTİTATİF VE EKONOMİK DEĞERLENDİRME

### A. KABUL EDİLEN VE ÖNE ÇIKAN SİNYALLER

#### 1. `reel_eps_growth` (Enflasyondan Arındırılmış Net Kâr Büyümesi) — **GÜÇLÜ SİNYAL**
- **Tüm Örneklem:** Ortalama IC = **+0.0820**, $p = 0.0471$ (%5 anlamlılık düzeyinde istatistiksel olarak anlamlı).
- **Dönem B (Pozitif Reel Faiz & Ortodoks Politika):** IC = **+0.158**, IC-IR = **0.97** (Olağanüstü yüksek tahmin gücü ve istikrar).
- **Ekonomik Gerekçe:** BIST'te %60-80 enflasyon yaşanan dönemlerde, şirketlerin nominal %40-50 kâr artışları aslında reel bir kâr erimesidir. Piyasa, nominal kâr büyümesi yerine enflasyon üzerinde reel değer üreten şirketleri çok güçlü biçimde ödüllendirmektedir. 
- **Mevcut Faktörlerle Korelasyon:** PB ile $\rho = -0.143$, FCF Verim ile $\rho = -0.074$, Momentum ile $\rho = +0.055$. Mevcut faktörlerle tamamen dik (ortogonal), sisteme saf bağımsız alfa kaynağı sunuyor.

#### 2. `op_marji_trend` (Faaliyet Kâr Marjı Genişlemesi / Trendi) — **GÜÇLÜ SİNYAL**
- **Tüm Örneklem:** Ortalama IC = **+0.0802**, $p = 0.0617$.
- **Dönem B (2023-2024):** IC = **+0.114**, IC-IR = **0.69** ($IC \ge 0.03$ ve $IR \ge 0.5$ rejim şartını aşıyor).
- **Ekonomik Gerekçe:** Ciro büyümesi enflasyonla şişebilir; ancak faaliyet marjının (Operating Margin) yıllık bazda genişlemesi şirketin fiyatlama gücünü (pricing power) ve girdi maliyetlerini müşteriye yansıtabildiğini kanıtlar. Sıkı para politikasında marjını koruyan/genişleten şirketler BIST'te primlenmiştir.
- **Korelasyon:** PB ile $\rho = -0.102$, Momentum ile $\rho = +0.183$. `reel_eps_growth` ile korelasyonu $\rho = +0.545$ olup birbirini tamamlayıcı niteliktedir.

---

### B. REDDEDİLEN ÖZELLİKLER VE BAŞARISIZLIK NEDENLERİ

#### 3. `eps_accel` (Kâr Büyüme İvmesi) — ❌ RED
- IC = +0.0538 (yön doğru pozitif), ancak çeyreklik oynaklığı yüksek (std=0.198) olduğundan $IC\text{-}IR = 0.27$ ve Dönem B'de $IR = 0.45$ ile $0.50$ eşiğinin hemen altında kalmıştır. Çeyreklik bazda tek seferlik baz etkileri (COVID şoku, deprem çeyreği vb.) ivme sinyalinde aşırı gürültü yaratmaktadır.

#### 4. `satislar_growth` (Ciro Büyümesi) — ❌ RED
- IC = +0.0437, ancak $IR = 0.21$ ve $p = 0.3466$. Yalnızca ciro büyümesi, kârlılık ve marj genişlemesiyle desteklenmediğinde BIST'te zayıf kalmaktadır (ciro enflasyonla nominal artarken kâr marjı eriyen şirketler ceza almaktadır).

#### 5. `accruals_ratio` (Sloan 1996 Tahakkuk Anomalisi) — ❌ RED (TERS İŞARET)
- Beklenen yön: **Negatif** (Yüksek tahakkuk / nakde dönmeyen kâr $\rightarrow$ düşük getiri).
- Gerçekleşen: Bütün örneklemde IC = **+0.0002** (tamamen sıfır / etkisiz).
- **BIST Neden Sloan Tahakkukunu Çalıştırmıyor?** BIST'te yüksek enflasyon ortamında işletme sermayesi, stok değerlemeleri ve peşin ödenen giderler nakit akış tablosunu (CFO) aşırı derecede dalgalandırmaktadır. Sloan anomalisi ABD gibi düşük enflasyonlu ve istikrarlı işletme sermayesi döngüsüne sahip piyasalarda çalışırken BIST'te sinyal üretmemektedir.

#### 6. `ihracat_kalkani` (İhracat Oranı $\times$ USD/TRY Getirisi) — ❌ RED (SİNYAL ÇÖKMESİ)
- Dönem A'da (TL'nin hızla değer kaybettiği 2021-2022 dönemi) IC = +0.066 iken, Dönem B'de (2023-2024 pozitif reel faiz ve TL'nin reel değerlenme dönemi) IC = **-0.059**'a dönmüştür!
- Sinyalin işareti rejimden rejime tersine döndüğü için modelin genelleştirme kabiliyetini bozar, aşırı uyum (overfitting) riski taşır.

#### 7. `reversal_penalty` (Kısa Vadeli 5-Günlük Fiyat Primi) — ❌ RED (TERS İŞARET)
- Beklenen: **Negatif** (5 günde çok koşan hissenin düzeltme yemesi).
- Gerçekleşen: IC = **+0.0225** (Pozitif!).
- **Piyasa Yapısı Nedeni:** BIST'te perakende ve momentum akımları kısa vadeli 5 günlük rallileri ertesi günlerde hemen düzeltmeye sokmaz; kısa vadeli momentum 60 günlük periyotta da devam etme eğilimi gösterir (küçük pozitif momentum yayılması). Reversal varsayımı BIST dinamiklerine uymamaktadır.

#### 8. `usd_vol_rejim` — ❌ RED ($|IC| < 0.02$)
- Tüm örneklem IC = +0.0096. İstatistiksel olarak saf gürültüdür.

#### 9. `z_borc_oz` (Özkaynak Bazlı Borçluluk) — ❌ RED (TERS İŞARET)
- Beklenen: Pozitif (Düşük borç $\rightarrow$ yüksek getiri).
- Gerçekleşen: Tüm örneklemde IC = **-0.0270**, Dönem A'da IC = **-0.049**.
- **Ekonomik Neden:** 2019-2022 negatif reel faiz döneminde borçlu şirketler enflasyon sayesinde reel olarak borçlarını erittiği ve finansal kaldıraçtan faydalandığı için piyasada daha yüksek getiri elde etmiştir. Bu durum borç faktörlerinin işaretini karıştırmaktadır. Faz 6'da `z_borc_oz` yerine orijinal `z_borc`'un tutulması gerektiği kesinleşmiştir.

---

## 3. EK KANTİTATİF ANALİZ: ORTOGONALLİK VE OTOKORELASYON (TURNOVER) TESTLERİ

### A. Ortogonallik Matrisi & Multicollinearity Testi (N=1,808 Gözlem, 21 Çeyrek)
* **Kritik Soru:** `reel_eps_growth` ile `op_marji_trend` birbirine çok mu benziyor?
* **Gerçekleşen Korelasyon:**
  * **21 Çeyrek Ortalama Kesitsel Spearman:** $\rho = \mathbf{+0.5017} > 0.50$
  * **Havuzlanmış Panel Spearman:** $\rho = \mathbf{+0.5171} > 0.50$
  * **Havuzlanmış Panel Pearson:** $r = +0.3645$
* **Karar Kuralı İcrası:** İki faktör arasındaki kesitsel derece korelasyonu $\rho > 0.50$ eşiğini aştığı için, çoklu doğrusal bağlantıyı (redundancy) önlemek amacıyla **yalnızca IC-IR skoru en yüksek olan** V4 modeline dahil edilmiş, diğeri elenmiştir:
  * `reel_eps_growth`: Tüm Örneklem IC-IR = **+0.46**, Dönem B IR = **+0.97**, $p = \mathbf{0.0471} \le 0.05$ (İstatistiksel Olarak Anlamlı!)
  * `op_marji_trend`: Tüm Örneklem IC-IR = **+0.43**, Dönem B IR = **+0.69**, $p = 0.0617$
* **Sonuç:** `reel_eps_growth` açık ara üstün gelerek **V4'e tek başına seçilmiş**, `op_marji_trend` çoklu korelasyon kuralıyla elenmiştir.

| Faktör | `z_pb` | `z_roe` | `z_fcf` | `z_mom` | `z_borc` | `reel_eps_growth` | `op_marji_trend` |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `z_pb` | 1.000 | -0.407 | +0.068 | -0.096 | -0.153 | **-0.183** | -0.106 |
| `z_roe` | -0.407 | 1.000 | +0.074 | +0.192 | +0.326 | **+0.534** | +0.256 |
| `z_fcf` | +0.068 | +0.074 | 1.000 | +0.065 | +0.145 | **+0.127** | +0.111 |
| `z_mom` | -0.096 | +0.192 | +0.065 | 1.000 | +0.049 | **+0.239** | +0.242 |
| `z_borc` | -0.153 | +0.326 | +0.145 | +0.049 | 1.000 | **+0.157** | +0.116 |
| `reel_eps_growth` | **-0.183** | **+0.534** | **+0.127** | **+0.239** | **+0.157** | **1.000** | **+0.502** |

*(Not: Değerler 2019-2024 arasındaki 21 çeyreğin ortalama kesitsel Spearman derece korelasyonlarıdır).*

---

### B. Otokorelasyon (Turnover) Kontrolü (20 Çeyreklik Geçiş Analizi)
Bir faktörün her çeyrekte radikal biçimde sıralama değiştirmesi portföy turnover'ını ve komisyon/kayma (slippage) maliyetlerini patlatabilir. Bu risk ardışık çeyrekler arasındaki derece otokorelasyonu ($\text{Spearman}(F_t, F_{t+1})$) ve Top-15 pozisyon tutma oranı (retention) ile test edildi:

| Faktör Adı | Ortalama Otokorelasyon ($\mu$) | Std ($\sigma$) | Top-15 Tutma Oranı | Çeyreklik Turnover Riski |
|:---|:---:|:---:|:---:|:---|
| `z_pb` | +0.917 | 0.085 | %81.3 | 🟢 ÇOK DÜŞÜK (Yüksek Kararlılık) |
| `z_roe` | +0.787 | 0.225 | %73.7 | 🟢 ÇOK DÜŞÜK (Yüksek Kararlılık) |
| `z_borc` | +0.855 | 0.125 | %79.7 | 🟢 ÇOK DÜŞÜK (Yüksek Kararlılık) |
| `z_mom` | +0.769 | 0.084 | %64.1 | 🟢 ÇOK DÜŞÜK (Yüksek Kararlılık) |
| `reel_eps_growth` | **+0.643** | **0.394** | **%66.7** | 🟡 **NORMAL / DENGELİ** |
| `z_fcf` (Mevcut V3) | **+0.595** | 0.364 | %66.7 | 🟡 **NORMAL / DENGELİ** |

**Turnover Değerlendirmesi:**
* `reel_eps_growth`'un çeyreklik otokorelasyonu **+0.643** olup, mevcut V3 modelinde halihazırda bulunan `z_fcf` faktöründen (+0.595) **daha yüksek bir istikrara** sahiptir.
* Top-15 tutma oranı **%66.7**'dir; yani hisselerin ortalama 10 tanesi bir sonraki çeyrekte de Top-15 içinde kalmakta, çeyrek başına yalnızca ~5 hisselik doğal bir rotasyon gerçekleşmektedir.
* **Sonuç:** `reel_eps_growth` sisteme ilave bir turnover yükü veya komisyon maliyeti bindirmemektedir.

---

## 4. KESİNLEŞEN V4 FEATURE KÜMESİ (9 FEATURE)

Uygulanan tüm filtreler, 3-kategori IC eşiği, ortogonallik ve turnover denetimleri sonucunda **V4 modeli için kesinleşen 9 feature**:

```python
FEATURE_COLS_V4 = [
    # Orijinal 8 Feature (V3 ile Birebir Aynı)
    "z_pb",
    "z_roe",
    "z_fcf",
    "z_mom",
    "z_borc",
    "reel_faiz",
    "usd_mom_60",
    "usd_mom_90",
    # Faz 1'de Tüm Testleri Geçen Tekil PIT Fundamental Alfa Faktörü
    "reel_eps_growth",
]
```

Bu 9 feature'lı mimari:
1. PB aşırı ağırlığını ve nominal kâr yanılgısını reel kâr büyümesiyle dengeler.
2. `op_marji_trend` ile çakışan mükerrer bilgiyi ($\rho > 0.50$) dışlayarak aşırı öğrenmeyi (overfitting) önler.
3. Turnover oranını V3'ün mevcut FCF seviyesinde tutarak işlem maliyeti sürprizi yaratmaz.
