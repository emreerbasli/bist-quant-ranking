# 🚀 BIST Quant: Shadow Execution & Karar Destek Sistemi (RC Serisi)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Machine Learning](https://img.shields.io/badge/ML-LightGBM%20&%20LambdaMART-success.svg)](https://lightgbm.readthedocs.io/)
[![UI](https://img.shields.io/badge/Dashboard-Streamlit%20Modern%20Bloomberg%20Grid-red.svg)](https://streamlit.io/)
[![Market](https://img.shields.io/badge/Market-Borsa%20Istanbul%20(BIST%2088)-orange.svg)](https://www.borsaistanbul.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Production Status](https://img.shields.io/badge/Production-RC--LGBMR--001%20Live-brightgreen.svg)](#)

> ⚠️ **YASAL UYARI VE KURUMSAL SINIRLAR (İHLAL EDİLEMEZ):**  
> Bu yazılım; Borsa İstanbul pay piyasasında işlem gören hisse senetleri için geliştirilmiş **kantitatif bir araştırma, simülasyon ve Karar Destek Sistemidir (Decision Support System - DSS)**.  
> Sistem **kesinlikle otomatik emir iletmez, canlı sermaye yönetmez ve hiçbir aracı kurum API'sine doğrudan bağlı değildir**.  
> Türkiye Sermaye Piyasası Kurulu (SPK) lisanssız portföy yöneticiliği mevzuatına %100 uyumlu olarak tasarlanmıştır.

---

## 📌 Yönetici Özeti (Executive Summary)

BIST Quant, geleneksel nominal fiyat tahmini algoritmalarının aksine **Kesitsel Sıralama (Learning-to-Rank)** ve **İleri Yönlü Gölge Altyapı (Forward Shadow Infrastructure)** prensipleriyle çalışan, kurumsal düzeyde bir Karar Destek Sistemidir.

Geliştirilen en son **EXP-MODEL-001** kontrollü mimari araştırmaları (101 tam regresyon ve smoke test) sonucunda sistem, katı *Out-of-Sample* ve *Kilit Kutu (Lockbox)* protokollerini aşan iki yeni nesil şampiyon Release Candidate (RC) modele emanet edilmiştir:
1. 🥇 **RC-LGBMR-001 (LightGBM Regression):** Birincil Yürütücü Model.
2. 🥈 **RC-LAMBDAMART-001 (LambdaMART):** İkincil (Karşılaştırma) Model.

---

## 🏗️ Yeni Nesil Mimari: İleri Yönlü Gölge (Shadow) Altyapı

Eski monolitik (V3/V4) tasarımlar terk edilmiş, kurumsal fonlardaki gibi **%100 Araştırma / Üretim İzolasyonu** prensibine dayalı "Shadow System" kurulmuştur:

1. **Bağımsız Araştırma Ortamı (`research/`):** Model keşfi, hiperparametre optimizasyonu, target/horizon seçimi "nested validation" (iç içe doğrulama) ile sadece burada gerçekleşir. Üretim koduna asla sızmaz.
2. **Sinyal ve Olay (Event) Sürüşü:** Geliştirilen modellerin kesitsel (cross-section) sıralama sonuçları `research/forward_infrastructure/events/` dizinine bir sözleşme (JSONL) olarak basılır.
3. **Kusursuz İzolasyon (Shadow Reader):** Streamlit Web Terminali ve Telegram botu, sadece `COMMITTED` durumundaki `OFFICIAL_CLEAN_FORWARD` olayları okur. Üretim paneli hiçbir modelin iç hesaplamasına bağlı değildir.
4. **Çift Motorlu İcra:** Her gün iki farklı mimarinin (LGBM Regression ve LambdaMART) kararları eşzamanlı ve risksiz şekilde izlenebilir.

---

## 🧬 Şampiyon Modeller (RC-LGBMR-001 & RC-LAMBDAMART-001)

4 farklı mimari (Factor Composite, Ridge, LGBM_Regression, LambdaMART) arasında yapılan zorlu testler (EXP-MODEL-001) sonucunda karar ağacı tabanlı modeller zaferle çıkmıştır.

* **RC-LGBMR-001 (Primary):** `max_depth: 4`, `num_leaves: 15` gibi parametrelerle donatılmış, aşırı uyum (overfitting) tuzağına düşmeyen kararlı regression mimarisi.
* **RC-LAMBDAMART-001 (Secondary):** Arama motorlarının kullandığı pairwise (ikili kıyas) algoritmalarıyla BIST 88 evrenindeki hisseleri birbirleriyle doğrudan dövüştürerek en güçlülerini tepeye (`NDCG` maksimizasyonu) taşıyan sıralama modeli.
* **Sıfır Geleceğe Bakma Hatası (Zero Lookahead Bias):** Modeller sadece Point-in-Time (PIT) veriler ve katı tasfiye (purge) mekanizmaları üzerinden eğitilir. 

---

## 🛡️ Kantitatif Güvenlik Kalkanları

Sistem, bir fon yöneticisinin reflekslerini otonomlaştıran savunma hatlarına sahiptir:
- **Katman 4 Tazelik Kapısı (Kill-Switch):** BIST takvimine göre son fiyat verisi veya makro veriler $\ge 2$ gün bayatsa, sistem otomatik kilitlenir ve işlem (rebalance) durdurulur.
- **Faz-0 (PASEU Doktrini) & Ardışık Taban Vetosu:** Son 10 işlem gününde 5 defa taban çeken veya ciddi çöküş yaşayan hisseler, model skoru ne olursa olsun **doğrudan veto edilir** ve listeye giremez.
- **%25 Portföy Devre Kesicisi:** Otonom portföy, tarihi tepe noktasından (Max Drawdown) %25 gerilerse, sistem acil "Risk-Off" moduna geçer.
- **Kilit Kutu (Lockbox) Protokolü:** Geliştirilen modeller, hiçbir koşulda 15 aylık test dönemini (out-of-sample) hileli geçemez. Hedef Sharpe oranını, p-değerini ve piyasa getirisini aşamayan her model **acımasızca imha edilir.** (Bkz: `FIRST_WORK_PACKAGE_REPORT.md`)

---

## 🌐 Streamlit Terminali: Modern Bloomberg Grid

`python main.py panel` komutuyla açılan yerel terminal, tamamen Shadow System sinyalleriyle uyumlu hale getirilmiştir:

1. **💼 Canlı Portföy:** 15 hissenin güncel durumu, 60 günlük kilit süresi takibi ve anlık zarar/kâr durumu.
2. **🏆 Otonom Model Sıralaması:** RC-LGBMR-001 ve RC-LAMBDAMART-001 kararlarının interaktif tablosu. Top-10 hisseleri belirginleştirilir.
3. **🛡️ Sistem Sağlığı & Drift Radarı:** Tazelik kapısı, NaN değer taraması, veri bütünlüğü.
4. **👤 Gerçek Portföyüm (İzole Cüzdan):** Sistemden bağımsız olarak kullanıcının kendi maliyetlerini takip ettiği salt-okunur kişisel ajanda.
5. **🔍 Hisse Röntgeni (Stock X-Ray 2.0):** Seçtiğiniz bir hisseyi cerrahi masaya yatıran Bloomberg tarzı grid:
   - **Sol Blok:** Model Sırası (Shadow Rank), Otonom Puan, Sektörel Yön.
   - **Sağ Blok:** 3 Katmanlı İnteraktif Plotly Grafiği (Mum, Hacim, RSI, Alış Çizgisi), BIST 100 Görece Alfa ve Faz-0 Risk Durumu.
   - **Özet:** Tek Tıkla Kopyalanabilir Markdown Check-Up Raporu.

---

## ⚙️ Kurulum & Merkezi Konsol

### 1. Kurulum (Python 3.11+)
```bash
git clone https://github.com/emreerbasli/bist-quant-ranking.git
cd bist-quant-ranking

# Sanal ortamı kur ve aktifleştir
python -m venv venv
venv\Scripts\activate

# Bağımlılıkları yükle
pip install -r requirements.txt
```

### 2. Merkezi Konsol Komutları (`python main.py`)
Tüm operasyonlar kök dizinden tek komutla yönetilir:

* 🌐 **`python main.py panel`** → Streamlit Yönetim Panelini açar (`http://localhost:8501`).
* 📥 **`python main.py guncelle`** → BIST kapanış verilerini ve KAP arşivini çeker.
* ⚡ **`python main.py kontrol`** → Shadow modellerin sinyallerini tarar, paper trading'i günceller ve Telegram'a rapor atar.
* 🛡️ **`python main.py dogrula`** → Veri bütünlüğü ve "bulaşma" (data leakage) denetimini yapar.
* ⏰ **`python main.py oto`** → Arka plan zamanlanmış otomasyon servisini başlatır.
* 🏛️ **`python main.py`** → İnteraktif ana menüyü ekrana basar.

---

## 🛑 Test Edilip Reddedilen Fikirler (Kurumsal Tabular)

Bilimsel araştırma sürecinde test edilip, istatistiksel alfa yaratmadığı anlaşıldığı için **kod tabanına girmesi KESİN OLARAK yasaklanan** metotlar:

| Yasaklanan Fikir | Nasıl Test Edildi? | Sonuç ve Red Gerekçesi |
|:---|:---|:---|
| **Bireysel Stop-Loss (TP/SL)** | 25 farklı SL (%-5 ila %-15) testi | Sharpe çöktü. BIST hisselerindeki %7 silkeleme manipülasyonlarına kurban gitti. |
| **Aylık Rotasyon (H=20g)** | Portföyü her 20 günde bir kurma | Yıllık turnover %400'ü aştı, komisyon/spread maliyetleri alfanın tamamını sildi. |
| **V5 (Neutral/DART Mimari)** | Hedef nötralizasyonu ve faktör saçılımı | Takip hatasını azalttı ancak benchmark'a aşırı yaklaşarak aktif alfayı (IR) sıfırladı. |
| **V6 (Monotonic Constraints)** | Parametrelere katı yön kuralları konuldu | Model esnekliği bozuldu, Max DD arttı ve getiri düştü. |
| **Canlı Broker API** | Aracı kuruma emir iletme | Regülasyon ve piyasa makas boşlukları nedeniyle kalıcı olarak iptal edildi. |

---

## 📜 Lisans

Bu proje [MIT Lisansı](LICENSE) altında korunmaktadır.  
Arka plan araştırma logları, "Lockbox" sözleşmeleri ve kantitatif tatbikat raporları için `research/results/` dizinindeki MD ve JSON raporlarını inceleyebilirsiniz.
