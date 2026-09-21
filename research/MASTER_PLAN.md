# BIST kantitatif hisse seçimi — araştırma uygulama planı

Revizyon: 2026-09-17. Durum: Uygulama öncesi plan. Bu revizyon deney veya eğitim başlatmaz.

## 1. Amaç ve değişmez sınırlar

Amaç, doğrulanabilir veriyle farklı rejimlerde maliyet sonrasında sürdürülebilir hisse seçimi katkısı sağlayan model + portföy yaklaşımını bulmaktır. En yüksek geçmiş Sharpe/CAGR tek başına başarı değildir. V3'ün yenilmesi zorunlu sonuç değildir; hiçbir yeni aday yeterli bulunmayabilir.

- V3: FROZEN INCUMBENT BENCHMARK. Feature, target, model veya K tercihlerinin optimal olduğu varsayılmaz.
- V4 Raw: REJECTED. Aynı ham yaklaşım yeniden açılmaz.
- V4.1: PROMISING RESEARCH / SHADOW REFERENCE. Production champion değildir.
- 2025-06 → 2026-09 dönemi görülmüştür; yalnızca descriptive historical robustness için kullanılır. Feature, target, model, K, eşik veya ensemble ağırlığı seçiminde kullanılmaz.
- Daha eski dönemler de önceki araştırmalarda görülmüştür. Yeni walk-forward bu araştırma geçmişini silmez; historical research evidence olarak raporlanır.
- Temiz ileri dönem kanıtı, aday/config dondurulduktan ve zaman damgalı sinyaller kaydedildikten sonra başlar. Takvimde yeni dönem olması yeterli değildir.

Yeni kod, config, model ve raporlar `research/` altında tutulur. Production V3, feature pipeline, Telegram, scheduler, sinyaller, cache ve paper portföyler değiştirilmez. Yeni provider/API/paket ihtiyacı gerekçesi, alternatifleri ve kapsamıyla raporlanır; otomatik kurulum veya entegrasyon yapılmaz.

Çalışma başında üretim dosyalarının ve kullanılan verinin hash manifesti alınır. Import yan etkileri incelenir; çalışma sonunda korunacak dosyalar karşılaştırılır. Mevcut kullanıcı değişiklikleri korunur.

## 2. Veri kanıtı: önceki denetimin sınırları

EXP-A-001 başlangıç taramasıdır; tamamlanmış Phase A değildir:

- 88 fiyat dosyasının PASS olması esas olarak sütun/duplicate kontrolüdür; fiyat doğruluğu ve PIT sertifikası değildir.
- 36.021 tarih yokluğu halka arz öncesini de sayar; gerçek veri kaybı olarak sunulamaz.
- 1.787 sıfır/negatif hacimli bar ve beş mutlak %50 üzeri getiri incelenecek bayraklardır; otomatik silinmez.
- 2.646 kaydın sabit açıklama takvimine oturması gerçek KAP yayın zamanının doğrulanmadığını gösterir.
- Macro loader'daki eksik ay için %2 TÜFE varsayımı gerçek veri sayılmaz.
- Tarihsel evren, delist, corporate action ve vintage kaynaklarının kapsamı envanterle kesinleştirilir; mevcut denetimdeki sabit metinler kapsamlı arama kanıtı sayılmaz.

Kararlar alan × hisse × dönem düzeyinde verilir:

| Statü | Kullanım |
|---|---|
| VERIFIED | Kaynak, ekonomik tanım ve geçmiş erişilebilirlik doğrulanmış kapsamda karar deneyi |
| PROXY / UNVERIFIED | Keşif ve duyarlılık; doğrulanmış alpha/production uygunluğu iddiası yok |
| INVALID | Girdiden çıkar; neden ve coverage etkisini kaydet |
| MISSING | Eksikliği koru; veri uydurma; kayıtlı eksik veri politikasını uygula |

Doğrulanmış alt kümelerle ilerlenebilir. Alt küme seçiminin yanlılığı ayrıca raporlanır. Olumlu proxy sonuç VERIFIED statüsü kazandırmaz. Veri yokluğu hipotezin yanlış olduğunu kanıtlamaz; INVESTIGATE kararı gerektirir.

## 3. Faz sırası

A–L isimleri korunur; G doğrulama altyapısı başlangıca alınır ve tüm araştırmayı kapsar.

**A → işlem/hedef sözleşmesi + G altyapısı → B → iç doğrulamada C–D–E–F → G dış değerlendirme → H → I → J → gerekirse K → L.**

Her faz sonunda CONTINUE / KILL / INVESTIGATE, kanıtı ve sıradaki izin verilen çalışma kaydedilir.

## Phase A — Veri, leakage ve muhasebe

Başlangıçta PROJECT_MEMORY.md, IMPLEMENTATION_LOG.md, bağımsız audit, V3/V4 karşılaştırması, V3/V4/V4.1 eğitim/inference, feature, backtest, loader ve paper kodları tam okunur. Okuma manifesti ve geçmiş deney envanteri oluşturulur. Bulunamayan belge açıkça kaydedilir; başka rapor aynı belge sayılmaz.

Kontroller:

1. Fiyat: adjusted/unadjusted ayrımı, split/bedelsiz/temettü, OHLC tutarlılığı, NaN/inf, duplicate, sıfır hacim, stale ticker, aşırı getiri. Düzeltmeler kaynakla kanıtlanır.
2. Takvim: gerçek seans günleri; halka arz öncesi, işlem durması ve gerçek veri boşluğu ayrılır. İlk mevcut bar resmi IPO tarihi sayılmaz.
3. Fundamental: gerçek bildirim zamanı, ilk yayımlanan değer, restatement/vintage, dönem sonu ve erişilebilirlik tarihi ayrımı. Açıklama saati yoksa ihtiyatlı icra politikası.
4. Muhasebe: tek çeyrek/YTD/TTM ayrımı; eksik çeyrek varken satır indeksinden YoY üretmeme; banka/sanayi tanımları; TFRS29, yeniden sunulmuş karşılaştırmalar ve çift enflasyon düzeltmesi riski.
5. Değerleme: tarihsel sermaye/piyasa değeri ve corporate action uyumu. Builder'daki son sermaye × geçmiş fiyat fallback'inin etkisi ölçülür. Sinyal tarihindeki fiyat ve o anda bilinen finansallar kullanılır; eski çarpan güncel ucuzluk sayılmaz.
6. Universe: tarihsel uygunluk, IPO/delist, işlem durumu ve sektör. Yalnız bugünkü evren varsa genelleme sınırı açıkça yazılır.
7. Macro: kaynak, referans dönem, yayın tarihi ve revizyon. Kaynaksız sabit değer/fallback yok. Macro gerektirmeyen adaylar ayrıca ilerleyebilir.
8. Likidite: geçmiş ADV, turnover, zero-return ve spread proxy kapsamı. Adjusted fiyat × hacmin geçmiş TL ciroyu bozup bozmadığı doğrulanır.

Çıktı: veri sözlüğü, provenance/coverage matrisi, sorun listesi, onarım seçenekleri, VERIFIED/PROXY alt kümeler ve yeni kaynak gereksinimleri. Geçiş: karar deneyine yalnızca doğrulanmış kapsam girer. Sorunlu alan INVESTIGATE olurken bağımsız geçerli alan CONTINUE olabilir.

## Başlangıç sözleşmesi — İşlem, target ve günlük simülasyon

Performans görülmeden sürümlenmiş config hazırlanır:

- Sinyal kapanış sonrası; tüm girdiler o anda erişilebilir olmalı. Temel icra sonraki seansın uygulanabilir fiyatıdır. Open verisinin düzeltme uyumu doğrulanamazsa alternatif önceden kaydedilir.
- Prediction horizon: H ∈ {20, 40, 60} işlem seansı araştırılabilir; 60 seans optimal kabul edilmez. Horizon seçimi yalnız inner temporal validation içinde yapılır; outer sonuçlardan seçilmez.
- Her observation ve H için dinamik label contract: `signal_date`, `entry_date`, `label_start`, `label_end`, `H trading sessions`. `label_start` girişteki getiri ölçüm başlangıcını, `label_end` H seanslık ölçüm bitişini belirtir; takvim ve sayım uç noktaları kesin tanımlanır. Leakage kontrolünde kullanılan `label_end_date`, bu observation'ın gerçek `label_end` tarihidir.
- V3'ün yaklaşık üç takvim aylık target'ı `LEGACY_V3_TARGET` olarak korunur; yeni 60-trading-session target ile aynı şey sayılmaz.
- Prediction horizon tahmin edilen getiri aralığıdır; rebalance frequency portföyün yeniden değerlendirilme sıklığıdır; holding period pozisyonun elde tutulma süresidir. Ayrı config alanlarıdır: 40 günlük target otomatik olarak 40 günlük forced holding veya rebalance anlamına gelmez.
- Mevcut asgari 60 işlem seanslık holding kuralı ayrı portföy kısıtı olarak korunur; optimal prediction horizon iddiası taşımaz. Horizon karşılaştırmasında holding ve rebalance kuralları sabit tutulur; bu düzeltme holding/rotation optimizasyonu açmaz. Takvim çeyreği asgari holding süresini garanti etmez.
- Evren yalnız sinyal anındaki bilgiyle kurulur. İleri getirisi bulunan hisselerden geçmiş evren oluşturulmaz.
- Eksik fiyat, işlem durması, delist, gerçekleşmeyen emir ve nakit politikası yazılır; pozisyonlar kaybolmaz, getiri sessizce sıfır sayılmaz.
- Gerçekleşmiş PnL kırpılmaz. Eğitim label clipping'i ayrı config ve sensitivity testidir.
- Ortak ilk portföy eşit ağırlık Top-10; K=10 kontrol tercihidir, optimal varsayılmaz. Alpha ile production risk kuralları ayrı analiz edilir. Tradability/likidite baştan uygulanır.
- Ücret: alım/satım işlem nominali üzerinden tek yön 0/30/50/100 bps; ilk giriş, ağırlık düzeltme, çıkış ve terminal tasfiye politikası belirtilir.
- NAV: günlük değerleme, nakit ve corporate action muhasebesi. Adjusted toplam getiri kullanılırsa temettü ikinci kez eklenmez.
- Sermaye senaryoları ve emir/ADV tavanı kapasite sonuçlarından önce kaydedilir; sermaye belirtilmeden kapasite hükmü verilmez.

## Phase G — Baştan itibaren temporal validation

Random split yok. Expanding outer walk-forward ve geçmiş veride inner walk-forward kullanılır. Fold tarihleri, minimum eğitim/kesit büyüklüğü ve uygunluk koşulları veri kapsamına göre, performans görülmeden kaydedilir.

- Feature/target/prediction horizon/model/hiperparametre ve gerektiğinde K seçimi inner fold'larda yapılır. Outer dönem seçilmiş prosedürü değerlendirir; horizon seçimine geri beslenmez.
- Purge sabit 60 gün değildir: her observation'ın gerçek `label_end_date` bilgisine göre eğitim label'ının ilgili inner validation veya outer test sınırına taşması kontrol edilir ve sızan observation'lar çıkarılır. Embargo ihtiyacı bölme yapısına göre gerekçelendirilir.
- Öğrenilen imputation/scaling/winsorization/selection yalnız training'de fit edilir. Sinyal gününün bilinen kesitindeki rank/sector dönüşümleri geleceğe bakmadan hesaplanır; öğrenilen parametrelerle karıştırılmaz.
- Incremental IC residualization katsayıları training'de öğrenilir; validation target'ı fit için kullanılmaz.
- Outer sonuçları gördükten sonra tasarım değiştirmek yeni denemedir; clean test diye yeniden sunulmaz. Eski lockbox seçim döngüsünün dışındadır.
- Ek günlük/haftalık örnekler bağımsız piyasa sayısı değildir; yapılandırılmış H ufkundaki örtüşen etiketlerin bağımlılığı korunur.

Doğrulama testleri: her H için gerçek label bitişine dayalı sınır sızıntısı, gelecek veri eklenince geçmiş feature değişmemesi, evrenin ileri veri varlığına bağlı olmaması, maliyet muhasebesi, H seanslık label sayımı ile ayrı holding kuralının kontrolü ve günlük NAV tutarlılığı. Çıktı: fold manifesti, test sonuçları ve ortak evaluator. Bu kapı geçmeden performans yarışı başlamaz.

## Phase B — Ortak baseline'lar

Altı referans: BIST100; investable universe equal-weight; basit 12–1 momentum; value/quality bileşimi; V3; V4.1.

- Aynı veri erişimi, execution, tarih, maliyet ve NAV sözleşmesi. Veri eksiği olan baseline N/A ve gerekçesiyle raporlanır.
- BIST100 fiyat endeksi ile toplam getirili hisseler arasındaki fark belirtilir; mümkünse eşdeğer getiri türü kullanılır.
- Frozen artifact'in eğitim geçmişindeki sonucu OOS değildir. Frozen davranış incelemesi ve her fold'da yeniden eğitilen V3/V4.1 yaklaşımı ayrı raporlanır. Refit yalnız research dosyalarına yazılır.
- Refit eski mimari seçiminin araştırma yanlılığını ortadan kaldırmaz. Bugünkü evren kullanılıyorsa equal-weight da tüm tarihsel BIST'i temsil etmez.

Geçiş: sonuçlar yeniden üretilebilir olmalı ve ML'nin ek katkısının ölçüleceği basit referanslar görünür olmalı.

## Phase C — Kontrollü target araştırması

İlk target-horizon araştırması yalnız `raw return ranking × H ∈ {20, 40, 60}` ile sınırlıdır. Ortak feature/model ve sabit holding/rebalance kurallarıyla karşılaştırılır. Umut veren horizon(lar) yalnız inner temporal validation içinde belirlenir; outer sonuçlar seçim için kullanılmaz.

EXP-TGT-001 sonucunda global horizon sabitlenmemiştir (`GLOBAL HORIZON = NOT FIXED`). Aday set `H ∈ {20, 40, 60}` olarak kalır. Bundan sonraki target/model prosedürlerinde horizon ilgili adayın kendi inner temporal validation'ında seçilen bir prosedür parametresidir; outer fold yalnız seçilmiş prosedürü değerlendirir. EXP-TGT-001B ile yeni bir global horizon araması açılmaz. EXP-TGT-001'in sonucu yalnız “sabit ridge ve üç basit price predictor control altında global horizon winner bulunmadı” şeklinde yorumlanır; tek başına herhangi bir horizon'ın veya price-only alpha'nın genel reddi değildir.

İkinci adımda yalnız inner validation'da umut veren horizon(lar) üzerinde raw, sector-relative, geçmişte tahmin edilmiş beta ile market/sector residual ve geçmiş volatiliteyle ölçeklenmiş target türleri araştırılır. Tüm horizon × target × model kombinasyonlarından full Cartesian grid açılmaz.

Aynı kesitte ortak BIST/evren getirisini çıkarmak rank/desil sıralamasını değiştirmez. Eşdeğer ranking etiketleri ayrı deney sayılmaz. Regression için ham/BIST-excess/universe-relative farklı öğrenme problemleri olabilir; yalnız gerekçeli karşılaştırmalar açılır.

Beta/risk ölçeği geçmişten hesaplanır. Küçük sektör fallback'i önceden belirlenir. Ortak feature/model kontrolüyle başlanır; yalnız anlamlı target × model etkileşimleri açılır. Outer ve eski lockbox'tan target veya horizon seçilmez.

## Phase D — Ekonomik feature factory

İlk dalga yaklaşık 15–25 kaliteli temsil adayı; her raw × transform kombinasyonu yok. Veri yetersizse sayı doldurulmaz.

| Aile | Öncelikli hipotezler |
|---|---|
| Quality | ROE/ROA ve değişimleri; veri uygunsa ROIC; marj iyileşmesi/istikrar |
| Cash flow | CFO/assets, güvenli payda politikasıyla cash conversion, FCF yield ve süreklilik |
| Balance sheet | Borç yükü değişimi, net borç trendi, varsa interest coverage ve kısa vade baskısı |
| Earnings | Doğru dönem tanımıyla büyüme sürekliliği; sektör göreli temsil; marj+büyüme iyileşmesi |
| Value | Sinyal tarihindeki PIT değerleme; quality × value; negatif payda politikası |
| Momentum | 3/6/12 ay, kısa dönemi atlama, tutarlılık, sektör/residual momentum |
| Risk | Downside/idiosyncratic volatilite ve bilanço istikrarı; önce predictive factor |
| Liquidity | ADV, Amihud, zero-return ve hacim istikrarı; uygulama etkisinden ayrıştırma |

Her aday: mekanizma, formül, beklenen yön, veri alanları/PIT, banka uygunluğu, missingness, transform ve eski denemeden fark. Eksik veri sıfır ekonomik değer sayılmaz. Aynı aralıkta ortak USD dönüşümü momentum rank'ini değiştirmeyebilir; eşdeğer temsiller bağımsız bilgi sayılmaz.

## Phase E — Feature seçimi ve incremental bilgi

Tarih kesiti bazında Rank IC mean/median/std, ICIR (frekans/yıllıklandırma açıklamasıyla), positive oranı; fold/sektör/rejim tutarlılığı, missingness, outlier sensitivity, Pearson/rank correlation, incremental IC ve turnover etkisi ölçülür.

Korelasyon tek başına otomatik red değildir; ek bilgi ve istikrarla birlikte yorumlanır. Büyük kesit/tek dönem etkisi ayrıca incelenir. Eşikler ilgili sonuçlar açılmadan kaydedilir, sonra gevşetilmez. Hedef 4–8 bilgi ailesi olabilir; kanıt yoksa daha azıyla devam edilir.

## Phase F — Kademeli model araştırması

Başlangıç: eşit ağırlıklı faktör composite → regularized linear → LightGBM regression → LightGBM LambdaMART. LightGBM ranking ile LambdaMART ayrı aile sayılmaz.

Setler: quality/value; buna earnings; buna momentum; en iyi non-redundant set. Coverage farkları raporlanır; daha kolay alt evren model üstünlüğü sayılmaz. Önce sensible defaults, sonra finalistlerde küçük coarse grid ve önceden belirli seed'ler. Mevcut paketler envanterlenir; XGBoost/CatBoost yalnız zaten mevcutsa ve gerekçe oluşursa eklenir. Neural network için bağımsız örnek sayısı ve öğrenme eğrisi desteği gerekir.

Rank IC, incremental katkı, NDCG@K (tie politikasıyla), top-decile spread ve ortak Top-K net sonuçları esas alınır; RMSE yardımcıdır. Analitik long-short spread, short uygulanabilirliği kanıtlanmadan işlem stratejisi diye sunulmaz.

## Phase H — Portföy, maliyet ve kapasite

Alpha özellik/model ayarları sabitlendikten sonra K=5/10/15/20 inner zaman doğrulamasında karşılaştırılır. Outer sonuçlardan K seçilmez. Eşit ağırlık temel kuraldır.

Turnover drift etmiş gerçek ağırlıklardan hesaplanır; kalan hisselerin yeniden dengelenmesi ve giriş/çıkışlar dahil edilir. Tek yön işlem toplamı ile yarım-L1 tanımı ayrılır. 0/30/50/100 bps, cost drag, değişen isim sayısı, pozisyon/ADV, sermaye senaryoları, dolum gecikmesi ve likit alt evren sonuçları raporlanır. VIP likidite muafiyeti araştırma varsayılanı olmaz.

## Phase I — Stress, ablation ve istatistik

Yalnız finalistlerde cost ×2, baz icraya ek bir seans gecikme, ranking/feature noise, missing fundamental, liquidity constraint, winsorization ve küçük hyperparameter perturbation, seed dağılımı.

One-feature-out ve family-out; tek yıl/çeyrek/sektör/hisse çıkarma; veri yeterliyse en iyi üç yılı çıkarma. Kalan örneklemin küçüklüğü belirtilir. Sector/year/stock/top-3 PnL hem mutlak hem aktif katkıyla değerlendirilir; net toplam sıfıra yakınken katkı yüzdeleri yanıltıcı olabilir.

Rejimler performans görülmeden tanımlanır. Macro doğrulanamıyorsa geçmiş fiyat tabanlı bull/weak/FX-stress kullanılabilir; enflasyon/faiz rejimi diye sunulmaz.

Paired karşılaştırma aynı dönem farklarından yapılır. Multi-period block bootstrap blok uzunluğu etiket örtüşmesi/bağımlılıkla gerekçelendirilir ve makul alternatiflerde sınanır. Bootstrap sayısı bağımsız piyasa sayısı değildir. Tüm denemeler sayılır; geçmiş sayı bilinmiyorsa alt sınır olarak raporlanır. Deflated Sharpe gibi ölçüler varsayımlarıyla yardımcıdır; veri hatalarını gidermez, tek onay kapısı olmaz.

## Phase J — Pareto finalist kararı

Tek model puanı yok. RETURN, RISK, ALPHA, STABILITY, COST, COMPLEXITY ve veri güvenilirliği birlikte sunulur. En fazla 2–3 finalist hedeflenir; zorla doldurulmaz.

Dayanaklar: basit baseline'a net katkı, incremental bilgi, fold/rejim istikrarı, makul günlük risk/kapasite, sınırlı jackpot ve feature bağımlılığı. Risk sınırı, asgari ekonomik katkı ve kapasite eşikleri sonuçlar görülmeden sözleşmeye eklenir. V3'ü korumak veya yeni adayı seçmek için değişmez. Sonuç NO QUALIFIED CANDIDATE olabilir.

## Phase K — Koşullu ensemble

Yalnız bağımsız katkısı gösterilmiş ve ranking'leri farklı finalistlerde rank average. Weighted rank inner validation desteğiyle; stacking ilk tercih değil. Farklı seed tek başına ayrı alpha kaynağı değildir. Ek net katkı maliyet/karmaşıklıkla birlikte değerlendirilir; eski lockbox'tan ağırlık seçilmez.

## Phase L — Freeze ve clean forward

Model/data/config/code hash, eğitim penceresi, feature şeması, preprocessing, target, risk/işlem kuralları, seed ve tekrar üretim komutu dondurulur. Statü BEST HISTORICAL RESEARCH CANDIDATE olur.

Shadow kayıtları ayrı konumda zaman damgalı sinyal, veri/işlem hatası ve gerçekleşmeyen emirlerle tutulur. Mevcut paper sistemi resetlenmez; operasyonel bağlantı değişiklikleri ayrıca onay gerektirir.

Forward değerlendirme takvimi freeze öncesi belirlenir: tamamlanmış yapılandırılmış-horizon cohort sayısı (completed configured-horizon cohorts), karşılaşılan rejimler, paired benchmark farkları, uygulama hataları, ücret/kayma ve kapasite. Örtüşen cohort'lar bağımsız sayılmaz. X ay geçmesi tek başına doğrulama değildir; gerekli kanıt belirsizlik ve ekonomik katkıya bağlıdır. Production promotion otomatik değildir.

## 4. Yeniden açılmayacak yaklaşımlar

Individual stop-loss grid; TP/SL dynamic exit; 20-day rotation; Piotroski + export ratio; SMA200; inverse-volatility weighting; Core-Satellite tactical tilt; aynı V5-Neutral + DART; reel_peg V6; raw reel_eps_growth V4 Raw.

Reddedilen `20-day rotation`, her 20 işlem gününde portföyü zorunlu ve yüksek turnover ile yenileme yaklaşımıdır; `20-day prediction horizon` değildir. 20 günlük target araştırılabilir; 20 günlük forced rotation tekrar açılmaz.

Diğer geçmiş red'lerde önce eski formül/veri/validation okunur. Yeni deney ancak ekonomik temsil veya veri/metodoloji düzeltmesi bakımından açık farkla açılır; önceki red ve yeni gerekçe kaydedilir.

## 5. Dalga bütçesi ve deney defteri

Dalga 1: veri kapılarından geçen 15–25 temsil, sınırlı target ve altı baseline. Dalga 2: seçilmiş az sayıda set × dört başlangıç model ailesi. Dalga 3: yalnız finalistlerde robustness/portföy/kapasite. Tam Cartesian grid yok.

Kesin deney listesi ve compute bütçesi dalga öncesi kaydedilir. Sonradan yeni hipotez yeni versiyon/gerekçeyle eklenir. ID'ler EXP-DATA/TGT/FTR/MDL/PORT/ROB; mevcut EXP-A-001 korunur. Ufak deneylere yeni model version adı verilmez.

Her kayıt: ID, hypothesis, önceki denemeden fark, data kapsam/statü/hash, features, target, model, preprocessing, train/inner/outer tarihler, seed, config/code/model hash, holding/K/sermaye/portfolio rules, cost modeli, sonuç artefact'leri, eksik metrik, karar/neden. FAILED run'lar da tutulur. Geçmiş kayıt değiştirilmez; düzeltme ayrı kayıt olur.

## 6. Dalga raporu sözleşmesi

- Executive summary: 5–10 bulgu ve kanıt düzeyi.
- Data quality: PIT/vintage, survivorship, corporate actions, missingness, liquidity/coverage.
- Altı baseline; target sonuçları; feature IC/ICIR/incremental IC/correlation/stability ve elenen fikirler.
- Tüm ciddi modeller, her walk-forward fold; frozen/refit ayrımı.
- Gross/net cumulative return, CAGR, Sharpe, Sortino, Calmar, DAILY MaxDD, quarterly MaxDD, recovery, worst month/quarter, hit rate. Risksiz getiri, frekans ve yıllıklandırma belirtilir.
- BIST/universe excess, USD return, active-return information ratio ve tanımlı regresyon alpha'sı; basit benchmark farkı regression alpha sayılmaz.
- Turnover, 30/50/100 bps, cost drag, değişen isimler, kapasite ve fill varsayımları.
- Regime, sector/year/stock concentration, ablation, seed/noise/delay/parameter stress.
- Deneme sayısı, seçim yanlılığı, belirsizlik; finalistlerin güç/zayıflık/riskleri ve öneri.

Eksik metrik N/A + neden. Test çalışmadıysa PASS yok. Küçük örneklem ve aşırı kesin p-değerleri başarı kanıtı diye sunulmaz.

## 7. İlk uygulama paketi

1. Tam okuma manifesti, geçmiş red envanteri ve production hash manifesti.
2. EXP-A-001 kapsam düzeltmesi: IPO/işlem durması/missingness ayrımı, fiyat PASS anlamı, macro/evren kanıt envanteri; eski ledger kararına append-only düzeltme.
3. Fundamental muhasebe/vintage/sermaye audit ve alan × hisse × dönem coverage matrisi.
4. Yerel kaynaklarla onarım seçenekleri ve yeni kaynak gerektirenler. Otomatik kurulum/entegrasyon yok.
5. İşlem/label sözleşmesi, fold tasarımı, deney/eşik/sermaye config'ini sonuçlardan önce kaydetme.
6. Geçerli kapsamda G altyapısını doğrulama ve B baseline dalgası. Veri yetmeyen referanslar gerekçeli N/A.

İlk teslim: düzeltilmiş veri raporu + kaynak/onarım matrisi + validation sözleşmesi + mümkün baseline sonuçları. Model başarısı ilanı veya production değişikliği değildir.

## 8. Metodoloji referansları

- [Nested model selection](https://scikit-learn.org/1.5/auto_examples/model_selection/plot_nested_cross_validation_iris.html): zaman sırasını koruyan inner/outer fold'lara uyarlanacak; örnekteki random CV aynen kullanılmayacak.
- [Bailey–López de Prado, Deflated Sharpe Ratio](https://doi.org/10.2139/ssrn.2460551): seçim yanlılığına yardımcı değerlendirme; veri doğruluğu ve clean forward yerine geçmez.
