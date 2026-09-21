# BIST Quant: Gölge Mimari & Karar Destek Sistemi

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Machine Learning](https://img.shields.io/badge/ML-LightGBM%20&%20LambdaMART-success.svg)](https://lightgbm.readthedocs.io/)
[![UI](https://img.shields.io/badge/Dashboard-Streamlit%20Bloomberg%20Grid-red.svg)](https://streamlit.io/)
[![Market](https://img.shields.io/badge/Market-Borsa%20Istanbul%20(BIST%2088)-orange.svg)](https://www.borsaistanbul.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Production Status](https://img.shields.io/badge/Production-RC--LGBMR--001%20Live-brightgreen.svg)](#)

> ⚠️ **YASAL UYARI VE KURUMSAL SINIRLAR:**  
> Bu yazılım; Borsa İstanbul pay piyasasında işlem gören hisse senetleri için geliştirilmiş **kantitatif bir araştırma, simülasyon ve Karar Destek Sistemidir (Decision Support System - DSS)**.  
> Sistem **kesinlikle otomatik emir iletmez, canlı sermaye yönetmez ve hiçbir aracı kurum API'sine doğrudan bağlı değildir**.  

---

## 📌 Sistem Özeti

BIST Quant, geleneksel fiyat tahmini algoritmalarının aksine **Kesitsel Sıralama (Learning-to-Rank)** ve **İleri Yönlü Gölge Altyapı (Forward Shadow Infrastructure)** prensipleriyle çalışan kurumsal düzeyde bir sistemdir.

Son **EXP-MODEL-001** testlerinden geçen Şampiyon modeller:
1. 🥇 **RC-LGBMR-001 (LightGBM Regression):** Birincil Yürütücü Model.
2. 🥈 **RC-LAMBDAMART-001 (LambdaMART):** İkincil Model.

---

## 🏗️ Sistem Mimarisi ve Uçtan Uca Akış

Sistem, geleneksel monolitik yapıyı terk ederek, araştırma ve üretimi tamamen izole eden **"Shadow System"** mimarisi üzerinde çalışır:

```mermaid
graph TD
    %% 1. Veri Katmanı
    subgraph S1 ["1. Veri Boru Hattı"]
        A1["BIST Kapanış Verileri"] --> A3["Fiyat ve Hacim Düzeltmeleri"]
        A2["KAP Haberleri & VBTS"] --> A3
    end

    %% 2. Araştırma ve Olay Katmanı
    subgraph S2 ["2. Gölge Araştırma Ortamı (Shadow Research)"]
        B1["RC-LGBMR-001 Motoru"]
        B2["RC-LAMBDAMART-001 Motoru"]
        A3 --> B1
        A3 --> B2
        B1 --> C1["COMMITTED Event (JSONL)"]
        B2 --> C1
    end

    %% 3. Risk ve Çıkış Motoru
    subgraph S3 ["3. Risk Motoru & Karar Destek"]
        C1 --> D1{"Shadow Reader"}
        D1 --> E1["Faz-0 Veto Filtresi (10 Günde 5 Taban Vb.)"]
        D1 --> E2["Katman 4 Veri Tazelik Kapısı"]
        E1 --> F1["Final 15 Hisselik Eşit Ağırlıklı Portföy"]
        E2 --> F1
    end

    %% 4. İletişim Arayüzü
    subgraph S4 ["4. Arayüz & Raporlama"]
        direction LR
        F1 --> G1["📱 Telegram Botu (K/Z Raporu)"]
        F1 --> G2["🌐 Streamlit Terminali (Hisse Röntgeni)"]
    end
```

### 🧬 Şampiyon Modeller

- **RC-LGBMR-001 (Primary):** `max_depth: 4`, `num_leaves: 15` gibi parametrelerle donatılmış, aşırı uyum (overfitting) riskini ortadan kaldıran sığ regresyon mimarisi.
- **RC-LAMBDAMART-001 (Secondary):** İkili kıyas (pairwise) algoritmalarıyla hisseleri birbirleriyle doğrudan rekabet ettirerek en güçlülerini tepeye taşıyan sıralama modeli.
- **Sıfır Geleceğe Bakma Hatası (Zero Lookahead Bias):** Modeller sadece Point-in-Time (PIT) veriler üzerinden katı kilit kutu (lockbox) protokolleriyle eğitilir. 

---

## 🛡️ Güvenlik ve Risk Yönetimi

- **Katman 4 Tazelik Kapısı:** Son fiyat veya makro veriler $\ge 2$ gün bayatsa, sistem otomatik kilitlenir.
- **Faz-0 (PASEU) Doktrini:** Son 10 işlem gününde 5 defa taban çeken hisseler doğrudan veto edilir.
- **%25 Devre Kesici:** Portföy tarihi tepesinden %25 gerilerse sistem tamamen nakde geçer.
- **Lockbox (Kilit Kutu) Testi:** Yeni modeller 15 aylık out-of-sample kilit kutuda Sharpe oranı, p-değeri ve piyasa getirisi hedeflerini aşamazsa direkt elenir.

---

## 🌐 Streamlit Terminali (Bloomberg Grid)

`python main.py panel` komutuyla açılan yönetim terminali 5 sekmeden oluşur:

1. **💼 Canlı Portföy:** 15 hissenin güncel durumu ve kâr/zararı.
2. **🏆 Otonom Model Sıralaması:** RC-LGBMR-001 ve RC-LAMBDAMART-001 sonuçlarının karşılaştırmalı tablosu.
3. **🛡️ Sistem Sağlığı & Drift Radarı:** Tazelik kapısı ve NaN taraması.
4. **👤 Gerçek Portföyüm:** Otonom sistemden %100 izole kişisel portföy yönetimi.
5. **🔍 Hisse Röntgeni (Stock X-Ray 2.0):** Seçilen hissenin model sırası, BIST 100 görece alfası ve risk profillerini detaylandıran klinik panel.

---

## ⚙️ Hızlı Kurulum

```bash
git clone https://github.com/emreerbasli/bist-quant-ranking.git
cd bist-quant-ranking

# Sanal ortamı kur ve aktifleştir
python -m venv venv
venv\Scripts\activate

# Gerekli kütüphaneleri yükle
pip install -r requirements.txt
```

Merkezi konsol komutları (`python main.py`):
* `panel`: Streamlit Yönetim Panelini açar.
* `guncelle`: Günlük BIST kapanış verilerini çeker.
* `kontrol`: Gölge sinyalleri tarar ve Telegram'a rapor atar.
* `dogrula`: Veri bütünlüğünü denetler.

---

## 🛑 Reddedilen Yaklaşımlar (Kurumsal Hafıza)

| Fikir | Test | Sonuç |
|:---|:---|:---|
| **Sabit Stop-Loss (TP/SL)** | 25 farklı marj denemesi | Piyasa oynaklığı nedeniyle "silkeleme" kurbanı oldu, Sharpe çöktü. |
| **Aylık Rotasyon** | 20 günde bir kurulum | Yıllık turnover %400'ü aştı, komisyon/spread maliyetleri alfanın tamamını sildi. |
| **Canlı Broker API** | Aracı kuruma otomatik emir | Regülasyon ve piyasa makas boşlukları nedeniyle iptal edildi. |
