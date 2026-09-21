# EXP-DATA-009 — Macro Provenance, Release-Timing & PIT Audit

## 1. Executive Summary

**MACRO = EXCLUDE.** Yerel politika faizi ve TÜFE serilerinde yayın tarihi, kullanılabilirlik tarihi, vintage ve revizyon soyu yoktur; TÜFE eksiklerinde kod `%2.0` üretmektedir. Bu karar fiyat-only ve recovered-exact fundamental araştırmasını bloklamaz.

## 2. Macro Source Inventory

Envanter `EXP-DATA-009_macro_inventory.csv` içindedir; seri bazlı PIT niteliği kayıtlıdır.

## 3. Policy Rate

Politika faizi V3/V4 içinde statik listedir; son kayıt 2026-01-01'dir. Tarihler etkinlik/yayın ayrımını, kaynak kanıtını veya vintage'i taşımaz. Tarihe göre ffill mantığı ekonomik olarak mümkün olsa da bu metadata olmadan PIT-safe değildir: **NO / INVALID**.

## 4. CPI / TÜFE

TÜFE statik sözlüktedir; yayın tarihi ve revision bilgisi yoktur. Audit tarihinde ileri tarihli sözlük ayı bulunmadı; ancak `tufe_aylik.get(m, 2.0)` eksik ayları gerçek gözlem değil `%2` ile tamamlar. Araştırmada fallback kullanılamaz: **NO / INVALID**.

## 5. USDTRY

`TRY_X.parquet` 2018-01-01–2026-09-15, 2,266 satır, null/duplicate yoktur. BIST işlem günlerinde doğrudan olmayan üç tarih ffill ile taşınır. Kodda `<= t` kesiti vardır; ancak yfinance ham serisi yayın/vintage/zaman damgası taşımadığından yalnız **PARTIAL / PROXY_DATE_ONLY**'dır.

## 6. Real Rate

Formül politika faizi eksi geriye dönük 12 aylık bileşik TÜFE'dir. CPI seçimi gün eşiğine dayanır, resmi yayın `available_from` alanına değil. Her iki girdi de güvenli olmadığından **NO / INVALID**.

## 7. TFRS29 / Inflation Interaction

V4 real EPS net kârı ayrıca CPI ile deflate eder. EXP-DATA-006/007'nin TFRS29 bulguları ile birlikte **DOUBLE-ADJUSTMENT RISK**; V4 çalıştırılmadı.

## 8. Release-Timing Contract

Her gözlem için zorunlu alanlar: `observation_period`, `publication_date`, `available_from`, `value`, `source`, `revision_status`, `pit_quality`. Saat yoksa yayın tarihi sonrası ilk işlem seansı konservatif `available_from` olur. Mevcut rate/CPI bu alanları karşılamaz.

## 9. Series-Level Readiness

Policy rate NO; CPI NO; USDTRY PARTIAL; real rate NO; inflation-adjusted real EPS NO.

## 10. Overall MACRO Gate

**EXCLUDE.** İlk araştırma dalgasında makro-türetilmiş feature/target/model kullanılmayacaktır.

## 11. External Data Needs

Gelecekte yeniden açılırsa kaynak bazında yayın takvimi, ilk-yayın/vintage ve revizyon soyuyla TCMB/TÜİK arşivi gerekir. Bu deney yeni sağlayıcı veya entegrasyon açmadı.

## 12. Tests

Unit testleri geleceğe yayın kullanmama, fabricated fallback reddi, statik seri tazeliği, FX hizalama, real-rate zamanlama ve üretim hash'ini denetler.

## 13. Production Integrity

Production değişikliği yoktur; korunan dosya hash kontrolü bu deney sonunda çalıştırılacaktır.

## 14. MASTER_PLAN’e göre SINGLE NEXT BEST ACTION

Makroyu dışarıda bırakarak MASTER_PLAN'daki sonraki data/foundation paketine geçmek; macro yeni veri deneyi yalnız plan açıkça gerektirirse veya model seçimini değiştirecek yeni hata bulunursa açılmalıdır.
