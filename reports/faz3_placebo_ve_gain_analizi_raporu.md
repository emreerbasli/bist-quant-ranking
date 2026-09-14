# FAZ 3 EK PROTOKOL: 100-TOHUMLU PLACEBO TESTİ VE GAIN YOĞUNLAŞMA RAPORU
*30 Yıllık Kantitatif Finans & BIST Veri Bilimi Disipliniyle*

**Tarih:** 2026-09-14  
**Doğrulama Havuzu:** 4-Fold Purged Walk-Forward Out-of-Sample (2022-2025, 13 Çeyrek)  
**Tohum Sayısı:** 100 Rastgele Portföy Tohumu (`SEED=42`)  
**İncelenen Modeller:** V4-Raw (9 Feature) ve V3-Kontrol (8 Feature)  

---

## 1. 100-TOHUMLU PLACEBO TEST SONUÇLARI (OOS 2022-2025)

| Model | $K$ | Model Sharpe | Placebo Ort. Sharpe | Placebo %95 Sharpe | Placebo Maks. Sharpe | Empirik $p$-değeri | Sözleşme Eşiği | Durum |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **V3-Kontrol** | 10 | 0.999 | 1.115 | 1.453 | 1.639 | **$p = 0.700$** | $p \le 0.10$ | ❌ **AŞILAMADI** |
| **V4-Raw** | 10 | 0.971 | 1.115 | 1.453 | 1.639 | **$p = 0.730$** | $p \le 0.10$ | ❌ **AŞILAMADI** |
| ──────────── | ── | ───── | ───── | ───── | ───── | ─────────── | ─────────── | ────────── |
| **V3-Kontrol** | 15 | 0.994 | 1.146 | 1.436 | 1.601 | **$p = 0.810$** | $p \le 0.05$ | ❌ **AŞILAMADI** |
| **V4-Raw** | 15 | 0.972 | 1.146 | 1.436 | 1.601 | **$p = 0.840$** | $p \le 0.05$ | ❌ **AŞILAMADI** |
| ──────────── | ── | ───── | ───── | ───── | ───── | ─────────── | ─────────── | ────────── |
| **V3-Kontrol** | 20 | 0.980 | 1.155 | 1.359 | 1.520 | **$p = 0.910$** | $p \le 0.10$ | ❌ **AŞILAMADI** |
| **V4-Raw** | 20 | 0.841 | 1.155 | 1.359 | 1.520 | **$p = 0.990$** | $p \le 0.10$ | ❌ **AŞILAMADI** |

---

## 2. KANTİTATİF TEŞHİS: NEDEN HER İKİ MODEL DE OOS PLACEBO'DAN GEÇEMEDİ?

Bu sonuç ilk bakışta şaşırtıcı görünse de, 30 yıllık BIST piyasa mekanizması incelendiğinde son derece mantıklı ve matematiksel bir gerçeği ortaya koymaktadır:

### A. 2022-2023 "Enflasyon Tsunamisi" Beta Yanılgısı
* 2022 yılında 88 hisselik BIST evreninin ortalama getirisi **+%279.6**, 2023 yılında ise **+%134.9** olmuştur.
* 88 hisse arasından rastgele 15 hisse çeken 100 Placebo sepeti, hisse bazlı idiyosenkratik riskleri çeşitlendirerek piyasanın bu devasa makro beta dalgasına binmiştir.
* Bu iki yıllık rallide rastgele sepetlerin oynaklığı düşmüş ve Placebo ortalama Sharpe oranı yapay olarak **1.146** gibi aşırı yüksek bir seviyeye çıkmıştır.
* `reports/faz_c_dogrulama_raporu.md` Tablo 1.4'te de açıkça görüldüğü üzere, V3 modeli de 2022 yılında **$p = 0.520$**, 2023 yılında ise **$p = 0.910$** ile Placebo'nun gerisinde kalmıştı.

### B. V3 Daha Önce Kilit Kutuda Nasıl $p = 0.030$ Almıştı?
* `reports/kilit_kutu_denetim_tutanagi.md` incelendiğinde; V3 modelinin $p=0.030$ aldığı Placebo testi 2022-2025 Walk-Forward'ında değil; **2025-06 $\rightarrow$ 2026-09** arasındaki son 5 çeyrekte (piyasanın durulduğu ve ayrıştığı dönemde) yapılmıştı. 
* O dönemde Placebo Sharpe'ı **0.77**'ye gerilerken, model **2.09** Sharpe ile Placebo'yu ezmişti ($p = 0.030$).
* **Fakat sözleşme kuralı gereğince:** Eğer test dönemi 2022-2025 Walk-Forward havuzunun tamamı olarak alınırsa, ne V3 ne de V4 bu testi aggregate bazda geçememektedir.

---

## 3. %54.5'LİK GAIN YOĞUNLAŞMASI VE OVERFITTING İNCELEMESİ

Ağaç iç yapısı ve düğüm derinliği analiz edildiğinde (`booster.dump_model()`):

### A. Düğüm Derinliği Dağılımı
* **Kök Düğüm (Derinlik 0):** 60 ağacın **45 tanesinde (%75)** ilk bölünme kararı doğrudan `reel_eps_growth` ile verilmektedir.
* **Alt Düğüm (Derinlik 1):** Kökten sonra ağaçlar en çok `z_mom` (16 kez), `z_pb` (11 kez) ve `z_fcf` (6 kez) ile etkileşime girmektedir.

### B. Kantitatif Yorum: Yeni Bir Tekel mi Doğdu?
1. **P/B Tekeli Yıkıldı:** V3'teki %57.7'lik tek taraflı değerleme bağımlılığı %14.8'e inmiştir.
2. **Reel Büyüme Tekeli Oluştu:** Ancak ağaçların kök düğümlerinin %75'inin tek bir değişkene bağlanması, modelin BIST'te yalnızca "enflasyon üzeri kâr büyütenler" eksenine aşırı odaklanmasına yol açmıştır.
3. **Piyasa Riski:** 2024 ve 2025 gibi sıkı para politikası döneminde bu odak muazzam bir kalkan oluşturup zararı kara çevirmişken (+%3.15 getiri, -%9.73 Max DD); 2022 gibi enflasyon rallisi döneminde aşırı defansif kalarak modelin piyasa getirisinin gerisinde kalmasına neden olmuştur (%239.8 vs %267.2).
