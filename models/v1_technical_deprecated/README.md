# models/v1_technical_deprecated
> ⚠️ **STATÜ: KULLANIM DIŞI (DEPRECATED) — SADECE ARŞİV VE REFERANS İÇİNDİR.**

Bu klasör, Point-in-Time (PIT) temel analiz reformu öncesinde kullanılan, teknik göstergelere (RSI, MACD, Bollinger vb.) dayalı eski model dosyalarını barındırmaktadır:
- `ensemble_sniper_v1.joblib`
- `ensemble_sniper_aktif_deprecated.joblib`
- `feature_importance.csv`

Bu modeller bağımsız kantitatif denetimlerde BIST'in enflasyonist ve kur şoku rejimlerinde başarısız olmuş; yerini `models/v3_ranking/` (PIT Temel Veri + Makro Rejim + LGBMRanker) mimarisine bırakmıştır. Karşılaştırma ve geriye dönük akademik referans amacıyla saklanmaktadır.
