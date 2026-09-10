# BIST Telegram Sinyal Botu — Uçtan Uca Proje Planı (v2)

Bu plan, veri toplamadan canlı sinyale kadar tüm süreci sıralı, kontrol edilebilir adımlara böler. Her fazın sonunda "bu faz bitti mi?" diye kontrol edebileceğin somut bir çıktı (deliverable) vardır. **v2 güncellemesiyle** timeout label stratejisi, işlem skoru tanımı, hiperparametre optimizasyonu, paper trading bitiş kriterleri, KAP erişim güvenilirliği, platform kararı ve retraining süreci netleştirilmiştir.

---

## FAZ 0 — Kurulum ve Kapsam (1-2 gün)

**Amaç:** Neyi, hangi hisselerde, hangi zaman diliminde yapacağını ve hangi piyasa davranışından avantaj (edge) aradığını netleştirmek.

### 0.1 Evren ve strateji

- [ ] Evren belirle: İlk aşamada 15-30 likit BIST hissesi (THYAO, TUPRS, DOAS, ASELS, KCHOL, BIMAS, EREGL, SAHOL, ISCTR, MGROS, TERA, FORTE vb.) — az hisseyle başla, sistemi doğrula, sonra genişlet
- [ ] **Likidite notu:** MGROS büyük/likit bir hisse, sorun yok. TERA ve FORTE ise THYAO/TUPRS gibi devlere göre daha düşük hacimli — bu ikisi için backtest'te slippage payını (Faz 5) daha yüksek tutmak gerekir (örn. %0.1-0.3 yerine %0.3-0.5), yoksa gerçek işlemde sinyal fiyatına yakın giriş yapamayabilirsin
- [ ] **Hisse evreni genişleme kriteri:** İlk 15-20 hisse ile en az 8 hafta paper trading (Faz 6) tamamlanmadan ve win rate/backtest sapma kriteri sağlanmadan evreni genişletme. Genişleme adımı: +5-10 hisse, yeni hisseler için Faz 1-3 tekrar.
- [ ] Zaman dilimi: Günlük mum (1D) ile başla. Intraday (saatlik/15dk) çok daha zor ve gürültülü, sonraki faz
- [ ] **Strateji hipotezi:** İlk sürümün amacı kısa vadeli **momentum + göreceli güç + hacim teyidi** kombinasyonunun BIST hisselerinde pozitif beklenen değer üretip üretmediğini test etmek olsun. Feature sayısı bu hipotezin önüne geçmesin.
- [ ] **ML rolü:** Model doğrudan "yarın fiyat kaç olacak?" tahmini yapmayacak; belirli bir girişten sonra **üst bariyere alt bariyerden önce ulaşma olasılığını** tahmin edecek.
- [ ] **Baseline zorunluluğu:** ML modeli, Buy&Hold ve basit teknik stratejileri (ör. momentum / MA / RSI tabanlı) geçmeden "edge var" kabul edilmeyecek.

### 0.2 Platform ve altyapı kararı

- [ ] **Çalışma platformu:** Sistem günlük olarak 18:10 sonrası çalışacak. Lokal PC güvenilir değil (uyku modu, güncelleme, kesinti). **Tercih: küçük bir VPS** (Hetzner CX11 ~3 EUR/ay, DigitalOcean Droplet 4 USD/ay) veya ücretsiz seçenek olarak Railway/Render. Lokal kullanılacaksa Windows Task Scheduler + `pythonw.exe` ile `apscheduler`.
  - VPS: `crontab -e` → `45 18 * * 1-5 /path/venv/bin/python /path/bot/run_daily.py`
  - Windows: Task Scheduler → Tetikleyici: Her iş günü 18:45, Eylem: `pythonw.exe run_daily.py`
  - Python içi (platform bağımsız): `APScheduler` kütüphanesi
  - **Neden 18:45 ve 18:10 değil?** BIST 18:10'da kapanır ancak uzlaşma (settlement) fiyatlarının yfinance ve diğer API'lere yansıması gecikebilir. 18:10'da çekilen veri eksik mum veya yanlış hacim (bir önceki günle birleşmiş) getirebilir. 18:45-19:00 arası veri stabilitesi çok daha yüksektir.

### 0.3 Ortam kurulumu

- [ ] Python 3.11+, virtualenv, aşağıdaki kütüphaneler:
  ```
  # Veri
  yfinance, pandas, numpy, pyarrow, fastparquet, requests, beautifulsoup4, lxml

  # Feature engineering
  pandas-ta, scipy

  # Model
  lightgbm, scikit-learn, imbalanced-learn, optuna

  # Görselleştirme ve raporlama
  matplotlib, plotly, seaborn, shap

  # Bot ve zamanlama
  python-telegram-bot, apscheduler, python-dotenv

  # Yardımcı
  tqdm, joblib, loguru
  ```

- [ ] **Güvenlik:** Tüm hassas bilgiler (Telegram token, API anahtarları) `.env` dosyasında saklanacak, asla `config.py` veya kaynak koda yazılmayacak. `.env` `.gitignore`'a eklenecek.
  ```python
  # config.py — sadece şablonu burada, değerler .env'den
  from dotenv import load_dotenv
  import os
  load_dotenv()
  TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
  ADMIN_CHAT_ID  = os.getenv("ADMIN_CHAT_ID")
  ```

### 0.4 Proje klasör yapısı

```
bist-bot/
  data/
    raw/          # ham OHLCV parquet
    features/     # feature-engineered parquet
    labeled/      # etiketli veri parquet
  features/       # feature engineering scriptleri
  models/
    v1/           # ilk ensemble (3 kalibre model)
    v2/           # yeniden eğitim sonrası
    aktif/        # symlink/junction ile aktif modele işaret
  backtest/       # trading engine, risk kuralları, raporlar
  bot/            # telegram, KAP filtresi, health check, sinyal skoru
  notebooks/      # keşifsel analiz (Jupyter)
  logs/           # günlük çalışma logları
  .env            # gizli bilgiler (gitignore'da)
  config.py       # hisse listesi, sabit parametreler (token yok)
  run_daily.py    # ana giriş noktası (her gün 18:10 sonrası çalışır)
  requirements.txt
```

**Çıktı:** Çalışan Python ortamı + hisse evreni listesi + platform kararı + `.env` şablonu.

---

## FAZ 1 — Veri Toplama ve Temizleme (2-4 gün)

**Amaç:** Güvenilir, boşluksuz, doğru hizalanmış tarihsel veri.

1. `yfinance` ile OHLCV çek (`.IS` uzantılı: `THYAO.IS`, `TUPRS.IS`)
2. **XU100 endeks verisini de ayrı çek** — göreceli güç hesaplaması için şart (`XU100.IS`)
3. **USDTRY verisini çek** (`TRY=X`) — kur hassasiyeti feature'ı için
4. **Sektörel endeks verilerini çek** — hisseyi ana endeksle değil kendi rakipleriyle kıyaslamak için:
   - `XULAS.IS` (Ulaştırma) — THYAO, PGSUS vb.
   - `XUMOT.IS` (Motorlu Araçlar) — DOAS, TOASO vb.
   - `XBANK.IS` (Bankacılık) — ISCTR, AKBNK vb.
   - `XHOLD.IS` (Holding) — KCHOL, SAHOL vb.
   - Evrende hangi hisse hangi sektörde → `config.py`'da `HISSE_SEKTOR` sözlüğü tutulacak
5. **VIX Endeksini çek** (`^VIX`) — küresel korku/panik göstergesi. Makro risk filtresi (Faz 2.4 ve 5.0.1) için şart.
6. Veri kalite kontrolü:
   - [ ] Eksik günler (tatil, halka arz öncesi) için forward-fill değil, **düşür**
   - [ ] Split/bölünme ayarlamalarını kontrol et. `yfinance` genelde otomatik ayarlar ama BIST'te bazen hatalı olabilir — özellikle 2018-2021 dönemi için bilinen sorunlu hisseler manuel spot-check yapılmalı. **Doğrulama yöntemi:** İsYatırım veya Matriks'ten indirilen ham fiyatla karşılaştır; %1'den fazla sapma olan noktaları işaretle.
   - [ ] Aşırı düşük hacimli günleri (işlem askıya alma vb.) işaretle, bunları etiketleme/backtest'te ayrı tut
5. Tüm veriyi tarih index'i ile hizalayıp `data/raw/` altında parquet olarak sakla

**Kritik nokta:** Her hisse + XU100 + USDTRY verisi **aynı tarih index'ine** oturmalı. Hizalama hatası tüm modeli baştan bozar.

**Survivorship bias (hayatta kalma yanlılığı) uyarısı:** Şu an seçtiğimiz evren bugün var olan, başarılı, likit hisseler. Geçmiş test döneminde (2018-2024) borsadan çıkmış, küçülmüş veya işlem hacmini kaybetmiş hisseler evrene dahil değil — bu durum backtest sonuçlarını **olduğundan iyimser** gösterebilir. Backtest raporunda bu sınırlama not düşülmeli ve sonuçlar **iyimser bir üst sınır** olarak yorumlanmalı.

**Çıktı:** `data/raw/{ticker}.parquet` dosyaları, kalite raporu (eksik gün sayısı, tarih aralığı, split kontrol raporu).

---

## FAZ 2 — Feature Engineering (3-5 gün)

**Amaç:** Modelin "göreceği" bağlamı üretmek. Sızıntısız, mantıklı, aşırı olmayan bir feature seti.

### 2.1 Teknik indikatörler (`pandas-ta`)
- Momentum: RSI(14), Stokastik, MACD (line + histogram)
- Volatilite: ATR(14), Bollinger Bant genişliği ve fiyatın banda göre konumu
- Hacim: OBV, MFI, hacmin 20 günlük ortalamaya oranı

### 2.2 BIST'e özgü feature'lar
- Göreceli güç (XU100): `hisse_getiri(5g) - XU100_getiri(5g)` ve `hisse_getiri(20g) - XU100_getiri(20g)`
- **Sektörel Göreceli Güç:** `hisse_getiri(5g) - kendi_sektor_getiri(5g)` — hissenin kendi sektörüne kıyasla ne kadar iyi/kötü performans gösterdiği
  ```python
  # Örnek: THYAO için XULAS ile kıyaslama
  df['sektor_relatif_guc_5g'] = (
      hisse['close'].pct_change(5) - sektor_endeks['close'].pct_change(5)
  )
  ```
  Bu feature, XU100 göreceli gücünden daha ince bir bilgi taşır: piyasa geneli iyi ama hissenin sektörü kötüyse bu erken uyarıdır.
- **Hacim Şoku (Spike) — Binary Feature:**
  ```python
  df['hacim_soku'] = (df['volume'] > df['volume'].rolling(20).mean() * 3).astype(int)
  ```
  Günlük hacim 20 günlük ortalamanın 3 katını aşıyorsa `1`, değilse `0`. Ağaç tabanlı modeller (LightGBM, RandomForest) bu tür keskin kırılımları çok iyi yakalar. Büyük hacim şoku genellikle kurumsal hareket, KAP haberi veya momentum kırılımıyla örtüşür.
- USDTRY 5 ve 20 günlük değişim yüzdesi
- Zaman feature'ları: haftanın günü, ayın ilk/son 3 günü

### 2.3 Bilanço/KAP Etkinlik Takvimi (İlk Sürüme Dahil — Opsiyonel DEĞİL)

**Neden ilk sürüme dahil:** Bir hissenin bilanço öncesinde/sonrasında davranışı teknik sinyallerden bağımsız olarak değişir. Bu feature olmadan model, event-driven momentumun en öngörülebilir kısmını kaçırır.

- [ ] KAP takviminden veya manuel olarak tutulan bir `events.csv`'den bilanço/temettü tarihleri okunacak
- [ ] Feature: `gun_fark_bilanco` — pozisyon açılış tarihinin en yakın bilanço tarihine uzaklığı (gün olarak, negatif = öncesi, pozitif = sonrası)
- [ ] Feature: `bilanco_penceresi` — bilanço tarihinden ±5 iş günü içinde mi? (binary)
- [ ] İlk sürümde `events.csv` manuel olarak tutulabilir; sonradan KAP API ile otomatikleştirilebilir

### 2.4 XU100 Piyasa Rejimi Filtresi (üst düzey kapı)

XU100 için ayrı, basit bir rejim sınıflandırması:

| Rejim | Tanım |
|---|---|
| Güçlü Yükseliş | XU100, 50 günlük ortalamanın %2+ üstünde |
| Yatay | Dar bantta, net yön yok |
| Güçlü Düşüş | XU100, 50 günlük ortalamanın %2+ altında |
| Yüksek Oynaklık/Panik | XU100 ATR z-score > 2 (kriz/şok anı) |

```python
def piyasa_rejimi(xu100_df):
    ma50 = xu100_df['close'].rolling(50).mean()
    fiyat_ma_farki = (xu100_df['close'] - ma50) / ma50
    atr = xu100_df['atr']
    atr_zscore = (atr - atr.rolling(100).mean()) / atr.rolling(100).std()

    if atr_zscore.iloc[-1] > 2:
        return "PANIK"
    elif fiyat_ma_farki.iloc[-1] > 0.02:
        return "GUCLU_YUKSELIS"
    elif fiyat_ma_farki.iloc[-1] < -0.02:
        return "GUCLU_DUSUS"
    else:
        return "YATAY"
```

**Sinyal eşiğine entegrasyon (Faz 7):**
- Güçlü Yükseliş / Yatay → eşik %70
- Güçlü Düşüş → eşik %80+
- Panik → sinyal üretimi durur, bilgi mesajı gider

### 2.4.1 VIX Makro Risk Filtresi (FAZ 2.4'e bağlı, FAZ 5.0.1'de uygulanır)

**Neden:** XU100 piyasa rejimi BIST'in kendi durumunu izler ama küresel şokları (Pandemi, SVB iflası, jeopolitik kriz) gecikmeli yakalar. VIX bu durumları çok daha erken sinyal verir.

```python
def vix_makro_filtresi(vix_df):
    """
    VIX'in son 3 günlük değişimi:
    - %20'den fazla artış → küresel panik başlıyor
    - Aktif pozisyonlara dikkat, yeni pozisyon açmaktan kaçın
    """
    vix_degisim_3g = vix_df['close'].pct_change(3).iloc[-1]
    if vix_degisim_3g > 0.20:
        return "KURESEL_PANIK"  # işlem skorundan 20 puan düş
    elif vix_degisim_3g > 0.10:
        return "ARTIS_UYARISI"  # işlem skorundan 10 puan düş
    else:
        return "NORMAL"
```

**İşlem skoru entegrasyonu (FAZ 5.0.1):**
- VIX NORMAL → skor değişmez
- VIX ARTIS_UYARISI → işlem skorundan 10 puan düş
- VIX KURESEL_PANIK → işlem skorundan 20 puan düş veya sinyal üretimini tamamen durdur (XU100 PANIK eşiğiyle birleşirse kesinlikle durdur)

Bu kural 2020 Pandemi düşüşü, 2022 küresel şoklar gibi BIST'in değil dışarısının kötü olduğu dönemlerde botu korur.

**Çıktı:** `features/piyasa_rejimi.py` (VIX filtresi de bu modüle eklenecek)

### 2.5 Sızıntı kontrolü (ZORUNLU adım)
- [ ] Her indikatör hesaplanırken **sadece o ana kadarki kapanmış mumlar** kullanılıyor mu?
- [ ] Hiçbir feature, "gelecekteki" bilgiyi içermiyor
- [ ] Normalizasyon/scaling varsa, bunu **sadece train setinde fit et**, test setine sadece transform uygula

**Çıktı:** `data/features/{ticker}.parquet` — 15-25 feature kolonu + orijinal OHLCV.

---

## FAZ 3 — Etiketleme: Triple Barrier Method + Gerçekçi Execution (2-3 gün)

**Amaç:** Modelin gerçekten trade edilebilir bir senaryoyu öğrenmesini sağlamak.

### 3.1 Bariyerler
- Üst bariyer: ATR tabanlı; `+k1 x ATR(14)` — ilk aday k1 = 1.5
- Alt bariyer: ATR tabanlı; `-k2 x ATR(14)` — ilk aday k2 = 1.0 (asimetrik: kazanç/kayıp oranı 1.5:1)
- Zaman bariyeri: 5 işlem günü
- Sabit +%4 / -%2 yapısı yalnızca baseline olarak tutulmalı; nihai sistem bunları otomatik optimize ederek seçmemeli.

### 3.2 Bariyer kontrolü OHLC ile yapılmalı
- Gelecek günlerin **High/Low** değerleri kullanılarak TP/SL temasları kontrol edilmeli.
- Aynı mumda hem TP hem SL dokunulursa: **konservatif varsayımla SL önce olmuş kabul edilmeli**. Bu varsayımın win rate üzerindeki etkisi ayrıca ölçülmeli ve raporlanmalı.
- Sinyal gününün kapanışı entry olarak kullanılmamalı; gerçekçi execution T+1 açılış üzerinden kurgulanmalı.

### 3.3 Etiket stratejisi — SABİT KARAR (v2)

**Timeout label kararı:** Bu karar tüm model metriklerini ve eşiklerini etkiler. Değerlendirilen seçenekler:

| Seçenek | Açıklama | Avantaj | Dezavantaj |
|---|---|---|---|
| **(a) Binary: timeout = 0** SEÇILDI | Zaman bariyeri doldu = kayıp | Basit, anlaşılır | Nötr pozisyonlar kayıp sayılır |
| (b) Üçlü sınıf: timeout = 2 | Ayrı nötr sınıf | Daha bilgilendirici | Çok sınıflı model karmaşık, eşik ayarı zor |
| (c) Timeout'ları çıkar | Sadece TP/SL ile biten pozisyonlar | Temiz veri | Örneklem azalır, seçim yanlılığı riski |

**Seçim gerekçesi:** Binary (timeout=0) modeli "emin olmadığında tahmin yapma" yönünde teşvik eder. Yüksek güven eşiği araması canlı sistemde pozitif yan etki.

**Etiketleme mantığı:**
- Üst bariyere önce değerse → `1` (başarılı işlem)
- Alt bariyere önce değerse → `0` (başarısız işlem)
- Hiçbiri tetiklenmeden zaman bariyeri dolarsa → `0` (zaman kaybı = kayıp kabul)

### 3.4 Sınıf dengesi
- `1/0` dağılımı raporlanmalı; hedef: %35-55 arası `1` oranı
- %20 altında `1` oranı → bariyerleri yeniden ayarla

**Çıktı:** `data/labeled/{ticker}.parquet` — feature'lar + label + entry_price + upper_barrier + lower_barrier + horizon kolonu.

---

## FAZ 3.5 — Etiket Kalite Denetimi (0.5-1 gün) — YENİ FAZ

**Amaç:** Model eğitmeden önce etiketlerin sağlıklı, mantıklı ve tutarlı olduğunu doğrulamak.

- [ ] **Etiket dağılımı histogramı:** Tüm hisseler için birleşik 0/1 dağılımı
- [ ] **Hisse bazında etiket dağılımı:** Bazı hisseler çok az `1` üretiyorsa neden? (bariyer çok dar mı, hisse çok volatil mi?)
- [ ] **Zaman bazlı etiket dağılımı:** 2018 vs 2022 vs 2024 dönemleri için ayrı ayrı bak — rejim değişimi görülüyor mu?
- [ ] **ATR bariyer büyüklüklerinin hisse bazında dağılımı:** Bariyerler makul mı?
- [ ] **Entry-exit grafiği:** Rastgele 20-30 örnek pozisyonu fiyat grafiği üzerinde görselleştir — gözle kontrol et
- [ ] **Sızıntı son kontrolü:** İlk 10 feature'ı manuel incele, gelecek tarihli veri var mı?

**Geçiş kriteri:** Bu kontrolü geçemeyen hisseler Faz 4'e sokulmaz, etiketleme parametreleri yeniden ayarlanır.

**Çıktı:** `notebooks/label_quality_check.ipynb` — etiket kalite raporu ve görselleştirmeler.

---

## FAZ 4 — Model Eğitimi (Ensemble + Kalibrasyon + Sızıntısız Doğrulama) (6-9 gün)

**Amaç:** Tek bir modelin kararına değil, birbirini çapraz kontrol eden bir model topluluğunun **kalibre edilmiş** olasılığına dayanan bir karar mekanizması kurmak.

### 4.1 Veri bölme — ASLA rastgele K-Fold kullanma
- **Walk-Forward Validation**: Zamanı kaydırarak defalarca eğit-test et
  ```
  Pencere 1: Eğit [2018-2021] → Test [2021 Q1]
  Pencere 2: Eğit [2018-2021 Q1] → Test [2021 Q2]
  ... (zaman ilerledikçe kaydır)
  ```
- **Purged Walk-Forward + Embargo:** Bariyerler ileriye baktığı için overlapping label dönemleri train/test arasında purge edilmeli; başlangıçta en az 5 günlük embargo.
- **Nested zaman serisi doğrulaması:** Kalibrasyon standart rastgele CV ile değil, yalnızca geçmiş veriden geleceğe doğru ilerleyen zaman sıralı calibration split ile yapılmalı.

### 4.2 Hiperparametre Optimizasyonu — YENİ (v2)

Sabit parametrelerle devam etmek overfitting veya underfitting riskini yükseltir. **Walk-forward inner-loop'ta** Optuna ile Bayesian search yapılmalı:

```python
import optuna

def objective(trial, X_train, y_train, X_val, y_val):
    params = {
        'n_estimators': trial.suggest_int('n_estimators', 100, 500),
        'max_depth': trial.suggest_int('max_depth', 3, 7),
        'min_child_samples': trial.suggest_int('min_child_samples', 20, 100),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1, log=True),
        'subsample': trial.suggest_float('subsample', 0.6, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
        'scale_pos_weight': ratio
    }
    model = lgb.LGBMClassifier(**params)
    model.fit(X_train, y_train)
    return roc_auc_score(y_val, model.predict_proba(X_val)[:, 1])

study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=50)
best_params = study.best_params
```

**Kurallar:**
- Optimizasyon yalnızca **train/validation** verisinde — dış test seti parametrelere hiç dokunmayacak
- Her walk-forward penceresi için ayrı optimizasyon (parametreler zaman içinde değişebilir)
- LogisticRegression için `C`, RandomForest için `max_depth` ve `min_samples_leaf` da optimize edilecek

### 4.3 Ensemble model kurulumu (üç model)

```python
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

# Parametreler 4.2'den gelecek
lgbm = lgb.LGBMClassifier(**best_params_lgbm)
logreg = LogisticRegression(C=best_C, class_weight="balanced", max_iter=1000)
rf = RandomForestClassifier(**best_params_rf, class_weight="balanced")
```

**Kalibrasyon:**
- Zaman sıralı calibration split ile yapılmalı; rastgele CV kullanılmamalı
- Calibration set boyutu: **minimum 500 örnek**
  - >= 500 örnek → `method='isotonic'`
  - < 500 örnek → `method='sigmoid'` (Platt scaling — fallback)
- Uygulama: train → calibration → validation/test

**Neden kalibrasyon şart?** LightGBM'in "%82 olasılık" dediği senaryolar kalibrasyonsuzsa tarihsel olarak %60 başarı oranına sahip olabilir — Telegram'daki güven yüzdesinin yalan söylemesi demek.

### 4.4 Fikir birliği (consensus) kuralı

```python
p_lgbm = calibrated_lgbm.predict_proba(X)[:, 1]
p_logreg = calibrated_logreg.predict_proba(X)[:, 1]
p_rf = calibrated_rf.predict_proba(X)[:, 1]

consensus_std = np.std([p_lgbm, p_logreg, p_rf], axis=0)
final_prob = np.mean([p_lgbm, p_logreg, p_rf], axis=0)

sinyal_gecerli = (final_prob > 0.70) & (consensus_std < 0.10)
```

Modeller çelişiyorsa (biri %80 biri %35 diyor) → bot susar.

### 4.5 Meta-labeling (opsiyonel, ileri seviye)

Birinci katman "AL var mı yok mu" desin, ikinci model bu karara "ne kadar güvenilmeli" sorusuna cevap versin. İlk sürümde atlanabilir.

### 4.6 Feature selection

- [ ] Otomatik "en alttaki %20-30'u at" kuralını doğrudan canlı sisteme koyma
- [ ] Tüm feature seti ile SHAP-seçilmiş feature setini **tamamen out-of-sample** karşılaştır
- [ ] Seçim kararı yalnızca train/validation sonuçlarına dayanmalı
- [ ] **Production notu:** SHAP hesabı maliyetlidir. Günlük sinyal üretiminde SHAP devre dışı; **haftalık** raporlamada çalıştır.

### 4.7 Model doğrulama

- [ ] Her walk-forward penceresinde **AUC, PR-AUC, Precision, Recall, Brier Score** kaydet
- [ ] SHAP değerleriyle feature önemini kontrol et
- [ ] Son 3-6 ayı **hiç eğitime sokmadan** kör test olarak ayır
- [ ] Kalibrasyon grafiği çiz (reliability diagram) — ideal: 45 derecelik çizgiye yakın
- [ ] **Baseline karşılaştırması:** Buy&Hold + en az 2 basit teknik strateji ile karşılaştır
- [ ] **Ek metrikler:** Profit Factor, Expectancy, turnover ve exposure raporla

**Çıktı:** `models/ensemble_v1/` (üç kalibre model), walk-forward performans raporu, SHAP grafiği, kalibrasyon grafiği.

---

## FAZ 5 — Trading Engine + Backtest (Gerçekçi Simülasyon) (5-7 gün)

**Amaç:** Model çıktısını gerçek bir işlem kararına çevirmek.

### 5.0 Trading karar katmanı

`Model Probability → Expected Value → KAP Risk Check → Candidate Ranking → Portfolio Constraints → Position Sizing → Entry/Exit Plan`

- [ ] Probability threshold tek başına yeterli kabul edilmeyecek
- [ ] Expected value maliyetler dahil düşünülmeli
- [ ] Aynı anda gelen sinyaller arasında rank/select yapılmalı
- [ ] Asgari model olasılığı + asgari risk/ödül + uygun market regime birlikte aranmalı

### 5.0.1 İşlem Skoru Hesabı — YENİ, TANIMLI (v2)

Telegram mesajlarındaki "İşlem skoru: 86/100" değeri aşağıdaki formülle hesaplanır:

```python
def islem_skoru_hesapla(model_olasiligi, risk_odul, hacim_teyidi,
                        goreceli_guc, kap_riski, rejim):
    """
    Her bileşen 0-100 arası normalize edilir, sonra ağırlıklı ortalama alınır.
    Ağırlıklar mantıksal olarak belirlenmiş, backtest edilerek seçilmemiştir
    (overfit riski önlemek için).
    """
    # 1. Model olasılığı (%40 ağırlık) — 0.5→0, 1.0→100
    skor_model = max(0, (model_olasiligi - 0.5) / 0.5) * 100

    # 2. Risk/ödül oranı (%20 ağırlık) — 1:1→50, 2:1→100, <1:1→0
    skor_ro = min(100, max(0, (risk_odul - 1.0) / 1.0 * 100))

    # 3. Hacim teyidi (%15 ağırlık) — >1.5x→100, <0.8x→0
    skor_hacim = min(100, max(0, (hacim_teyidi - 0.8) / 0.7 * 100))

    # 4. Göreceli güç (%15 ağırlık) — +%3→100, -%3→0
    skor_rsguc = min(100, max(0, (goreceli_guc + 3) / 6 * 100))

    # 5. KAP riski (%10 ağırlık)
    kap_puanlar = {'dusuk': 100, 'orta': 50, 'yuksek': 0}
    skor_kap = kap_puanlar.get(kap_riski, 50)

    skor = (skor_model * 0.40 + skor_ro * 0.20 + skor_hacim * 0.15 +
            skor_rsguc * 0.15 + skor_kap * 0.10)

    # Panik rejiminde tavan skor 40
    if rejim == 'PANIK':
        skor = min(40, skor)

    # VIX makro filtresi cezası
    vix_durum = vix_makro_filtresi(vix_df)
    if vix_durum == 'KURESEL_PANIK':
        skor = max(0, skor - 20)
    elif vix_durum == 'ARTIS_UYARISI':
        skor = max(0, skor - 10)

    return round(skor)
```

**Dosya:** `bot/sinyal_skoru.py`

### 5.0.2 Entry

- Sinyal T gününün kapanışından sonra üretilir, execution T+1 açılışında
- **Gap stres eşiği (sabit, backtest öncesinde belirlendi):**
  - T+1 açılış, T kapanışına göre **ATR'nin %75'inden fazla** sapma → işlemi atla
  - Mutlak eşik: **%4'ten büyük gap** → işlemi atla
  - Eşik aşılma sıklığı backtest'te ayrıca raporlanmalı

```python
# YANLIŞ: giris_fiyati = sinyal_gunu['close']
# DOGRU:
giris_fiyati = df.loc[sinyal_tarihi + 1, 'open']
gap_yuzde = abs(giris_fiyati - sinyal_gunu['close']) / sinyal_gunu['close']
if gap_yuzde > 0.04:
    islem_atla()
```

**Emir Tipi Kuralı — KRİTİK (v2 ekleme):**

T+1 sabah açılışında **asla Piyasa (Serbest) Emri kullanılmayacak.**

> **Neden:** BIST sabah açılışları sığdır. Piyasa emri gönderilirse, düşük hacimli hisselerde (FORTE, TERA vb.) tahtayı tek başına çizip sistemin backtest fiyatının %2-3 üzerinden maliyetlenebilirsin — bu işleme girmeden backtest kârını yok eder.

**Kural:** Limit emir, tahmini giriş fiyatının en fazla **+%0.5** üzerine. Emir 09:55'e kadar gerçekleşmezse iptal et, o gün pozisyon açılmaz.

Telegram mesajına eklenecek standart uyarı satırı:
```
⚠️ EMİR: Limit emir kullanınız (max. giriş +%0.5 üzeri). 09:55'e kadar gerçekleşmezse iptal.
```

Backtest'te bu kural şu şekilde simüle edilmeli:
```python
# Limit emir simülasyonu: T+1 gün içinde hiçbir zaman
# sinyal_kapanis * 1.005'in altına inmediyse → işlem gerçekleşmedi
limit_fiyat = sinyal_gunu['close'] * 1.005
if df.loc[sinyal_tarihi + 1, 'low'] > limit_fiyat:
    islem_atla()  # limit dolmadı
else:
    giris_fiyati = limit_fiyat  # limit doldu
```

### 5.0.3 Exit Engine

Her pozisyon için açıkça tanımlanmış kurallar:

| Kural | Detay |
|---|---|
| Hard stop | ATR tabanlı: `-k2 x ATR(14)` — FAZ 3 ile tutarlı |
| Profit target | `+k1 x ATR(14)` |
| Time stop | 5 işlem günü |
| Trailing stop | Opsiyonel — FAZ 8'de eklenebilir |
| Model sinyali bozulması | final_prob < 0.40 VE consensus_std > 0.15 → erken çıkış |
| Panik rejimi | Panik anında açık pozisyon: stop ATR x 0.5'e çekilir; yeni pozisyon açılmaz |
| **Split/Temettü maskeleme** | Pozisyon açıkken hissede split veya temettü gerçekleştiyse → o hisse için 5 iş günü boyunca yeni sinyal üretme, mevcut indikatörleri güvenilmez say |

**Temettü / Bedelsiz Sonrası İndikatör Maskeleme Kuralı (v2 ekleme):**

> **Neden:** yfinance geçmiş fiyatı geriye dönük düzeltse bile, hareketli ortalamalar ve MACD gibi indikatörler temettü/split öncesi ve sonrasındaki fiyat boşluğunu "sert bir düşüş trendi" gibi algılar. Bu hatalı sinyal bozulması yaratır.

```python
def split_temettü_maskele(df, ticker, kurumsal_aksiyonlar):
    """
    kurumsal_aksiyonlar: yfinance'ten gelen Dividends + Splits verisi
    """
    son_aksiyonlar = kurumsal_aksiyonlar[
        kurumsal_aksiyonlar.index >= (pd.Timestamp.now() - pd.Timedelta(days=7))
    ]
    if len(son_aksiyonlar) > 0:
        # Son aksiyon tarihinden itibaren 5 iş günü sinyal üretme
        maskeleme_bitis = son_aksiyonlar.index[-1] + pd.offsets.BDay(5)
        if pd.Timestamp.now() <= maskeleme_bitis:
            return True  # maskele
    return False
```

Bu kural hem backtest'te (geçmiş split/temettü tarihleri için) hem canlı sistemde uygulanmalı. Maskeleme aktifken Telegram'a: "⏸ {TICKER}: Kurumsal aksiyon sonrası 5 gün bekleme süresi aktif" notu gider.

**Exit kuralları backtest sonucu görüldükten sonra değiştirilmeyecek; önce belirlenmeli.**

### 5.0.4 Position Sizing — Risk Bazlı

```python
def pozisyon_boyutu(portfolio_degeri, max_risk_yuzde=0.005,
                    stop_mesafesi=None, giris_fiyati=None, max_agirlik=0.20):
    risk_tutari = portfolio_degeri * max_risk_yuzde
    adet = risk_tutari / stop_mesafesi
    nominal = adet * giris_fiyati
    max_nominal = portfolio_degeri * max_agirlik
    if nominal > max_nominal:
        adet = max_nominal / giris_fiyati
    return adet
```

- Başlangıç: `max_risk_yuzde = 0.005` (%0.5 per işlem)
- Maksimum nominal ağırlık: %20

### 5.0.5 Portfolio Selector

- Model olasılığına göre adayları sırala
- Expected value ve risk/ödül oranını dikkate al
- Rolling 20/60 günlük return correlation kontrol et (>0.7 ise aynı sektörden say)
- Sektör başına maksimum 2 pozisyon
- Maksimum eşzamanlı pozisyon: 4-5
- Portfolio heat (toplam stop riski) <= portföy %3

### 5.1 Maliyet ve execution varsayımları

- [ ] **Komisyon:** Gerçek aracı kurum oranı config'den; stres senaryosu için %50 daha yüksek de test et
- [ ] **Slippage:** Hisse bazlı — THYAO/TUPRS: %0.1-0.2, TERA/FORTE: %0.3-0.5
- [ ] **Spread:** Tahmini %0.05-0.15 maliyete ekle
- [ ] **Rejim bazlı test:** 2020 tepe/çöküş, 2022 enflasyon rallisi, 2023-24 yatay dönem ayrı raporla

### 5.2 Benchmark ve robustness testleri

- [ ] BIST100 Buy&Hold ile karşılaştır
- [ ] En az 2 basit baseline stratejiyle karşılaştır
- [ ] Bull / bear / sideways / panic dönemlerinde ayrı raporla
- [ ] Parametre hassasiyeti testi
- [ ] Hisse evreninin küçük değişikliklerine karşı robustness kontrolü
- [ ] Maliyetleri iyimser ve stres seviyesinde iki senaryoda test et

### 5.3 Portföy Risk Yönetimi

BIST hisseleri birbiriyle yüksek korelasyonlu — özellikle aynı sektörde.

- [ ] Maksimum eşzamanlı pozisyon: 4-5
- [ ] Sektör başına maksimum 2 pozisyon
- [ ] Risk bazlı sizing + maksimum nominal ağırlık (%20)
- [ ] Portfolio heat <= portföy %3

**Çıktı:** `backtest/trading_engine.py` + `backtest/risk_kurallari.py`

Raporlanacak metrikler:
- Toplam getiri, Sharpe, Sortino, maksimum drawdown
- Win rate, ortalama kazanç/kayıp oranı
- İşlem sayısı (çok az → istatistiksel güven düşük)
- Expectancy, Profit Factor, CAGR, Benchmark farkı
- Turnover, toplam işlem maliyeti, time in market / net exposure
- En kötü ardışık kayıp serisi, ortalama pozisyon süresi
- Gap stres testi ve rejim bazlı ayrıştırma

**Çıktı:** `backtest/rapor_v1.html`

**Karar noktası:** Backtest tatmin edici değilse Faz 2-4'e geri dön.

---

## FAZ 5.5 — Otomatik Doğrulama ve Hata Tespiti (Self-Validation) (3-4 gün)

**Amaç:** Sistem canlıdayken "sessizce yanlış" çalışmaya başlarsa bunu kendi kendine fark edip sana haber vermesi.

### 5.5.1 Veri kalite kontrolü (her çalışmadan önce)

```python
def veri_saglik_kontrolu(df, ticker):
    hatalar = []
    if df.isnull().sum().sum() > 0:
        hatalar.append("Eksik değer tespit edildi")
    if (pd.Timestamp.now() - df.index[-1]).days > 3:
        hatalar.append("Veri güncel değil, son mum 3+ gün eski")
    if df['volume'].iloc[-1] == 0:
        hatalar.append("Hacim sıfır — işlem askıda olabilir")
    if df['close'].iloc[-1] <= 0:
        hatalar.append("Geçersiz fiyat verisi")
    if abs(df['close'].pct_change().iloc[-1]) > 0.20:
        hatalar.append("Günlük %20+ değişim — split veya hatalı veri olabilir")
    return hatalar
```

### 5.5.2 Feature drift tespiti (PSI)

```python
def psi_hesapla(beklenen, gozlemlenen, bucket_sayisi=10):
    """
    PSI < 0.1: stabil | 0.1-0.25: orta risk | > 0.25: ciddi kayma
    Küçük örneklerde (n<200) adaptive binning kullanılmalı.
    """
    if len(gozlemlenen) < 200:
        buckets = pd.qcut(beklenen, q=min(5, bucket_sayisi), duplicates='drop')
    else:
        buckets = pd.cut(beklenen, bins=bucket_sayisi)
    # PSI hesaplama...
```

### 5.5.3 Tahmin dağılımı izleme

- Normalde 2-3 hisse %70+ alıyorsa, birden 15+ alıyorsa → şüpheli
- 30+ gün sinyalsizse → kontrol tetiklensin

### 5.5.4 Kod seviyesinde hata yönetimi

```python
try:
    calistir_gunluk_analiz()
except Exception as e:
    telegram_admin_mesaji(f"HATA: {str(e)}\nSistem durdu, kontrol gerekiyor.")
    logging.error(e, exc_info=True)
```

Her gün (sinyal olsun olmasın) "sistem çalıştı" onay mesajı gönderilmeli.

**Çıktı:** `bot/health_check.py`

---

## FAZ 5.7 — KAP Haber Filtresi (3-4 gün)

**Amaç:** Teknik model "AL" dediğinde, arkasında olumsuz bir gelişme olup olmadığını kontrol etmek.

### 5.7.0 KAP Erişim Güvenilirlik Testi — YENİ (v2)

KAP'ın resmi public API veya stabil RSS garantisi yoktur.

- [ ] FAZ başında KAP RSS/API endpoint'ini manuel test et (3-5 gün boyunca izle)
- [ ] Rate limiting ve bot bloklamasını simüle et
- [ ] **Fallback kaynaklar:** İsYatırım haber akışı, Bloomberg HT RSS, Mynet Borsa
- [ ] Başarısız erişimde: "KAP verisi alınamadı, filtre atlandı" logu + admin uyarısı; sinyal iptal edilmez
- [ ] **Retry mekanizması:** exponential backoff (1s → 2s → 4s → 8s → vazgeç)

```python
def kap_verisi_cek(ticker, retry_max=4):
    for attempt in range(retry_max):
        try:
            return _kap_request(ticker)
        except Exception as e:
            time.sleep(2 ** attempt)
    logging.error(f"{ticker} KAP verisi alınamadı, filtre atlandı")
    return None
```

### 5.7.1 Kaynak: KAP
- Son 2 işlem günü içindeki bildirimleri hisse bazlı çek

### 5.7.2 Sınıflandırma (kural + LLM opsiyonel)
- **Anahtar kelime taraması:** "zarar", "dava", "ceza", "SPK incelemesi", "yönetim kurulu istifası" → işaretle
- **LLM (opsiyonel katman):** Belirsiz bildirimler için kısa prompt ile sınıflandırma
- Temel işlev LLM olmadan da çalışmalı; botun sinyal üretimi ücretli API'ye bağımlı olmamalı

### 5.7.3 Sinyale entegrasyon

Olumsuz bildirim varsa sinyali iptal etmiyoruz — Telegram'a "DİKKAT" notu ile gönderiyoruz, son karar kullanıcıda.

### 5.7.4 Telegram mesaj standardı

Tüm kullanıcı mesajları Türkçe. Örnek:
```
🟢 GÜÇLÜ AL ADAYI — THYAO

Model olasılığı: %82
İşlem skoru: 86/100
Piyasa rejimi: 🟢 Güçlü Yükseliş
Göreceli güç (XU100): +2,8%
Göreceli güç (Sektör): +1,4%
Hacim teyidi: ✅  Hacim Şoku: ✅
KAP riski: 🟢 Düşük
VIX Durumu: 🟢 Normal

Tahmini giriş: 285,50 TL
Stop: 279,80 TL (-2,0%)
Hedef 1: 297,00 TL (+4,0%)
Hedef 2: 303,00 TL (+6,1%)
Risk / Getiri: 1:2,0

Önerilen pozisyon: 18.500 TL
Portföy riski: %0,50
Beklenen taşıma süresi: 2-5 işlem günü

⚠️ EMİR: Limit emir kullanınız (max. giriş +%0,5 üzeri).
09:55'e kadar gerçekleşmezse emri iptal edin.

Bu mesaj yatırım tavsiyesi değildir. Bot otomatik emir göndermez; son karar kullanıcıya aittir.
```

**Çıktı:** `bot/kap_filter.py` + `bot/telegram_messages_tr.py` + `bot/sinyal_skoru.py`

---

## FAZ 6 — Paper Trading (4-8 hafta)

**Amaç:** Backtest ile gerçek piyasa arasındaki farkı gerçek parayı riske atmadan görmek.

- [ ] Modeli her gün kapanıştan sonra çalıştır, sinyalleri "TEST" etiketiyle Telegram'a gönder
- [ ] Gerçek fiyat hareketleriyle karşılaştır
- [ ] Paper trading sonuçlarını haftalık raporla

### 6.1 Paper Trading Bitiş Kriterleri — YENİ, SOMUT (v2)

**Tüm** kriterlerin sağlanması gerekir. Herhangi biri sağlanmazsa Faz 4'e geri dön:

| Kriter | Eşik | Açıklama |
|---|---|---|
| Minimum sinyal sayısı | **>= 30 tamamlanmış sinyal** | İstatistiksel güven için minimum örneklem |
| Win rate sapması | **<= %15 fark** | Backtest win rate ile paper trading farkı |
| Kalibrasyon kayması | **Brier Score <= backtest + 0.05** | Güven tahminleri ne kadar doğru? |
| Veri drift uyarısı | **Son 4 haftada <= 2 uyarı** | PSI > 0.25 uyarı sayısı |
| KAP filtresi çalışma oranı | **>= %90 başarılı sorgu** | KAP erişim güvenilirliği |
| Sistem kararlılığı | **>= 30 gün kesintisiz** | Kritik hata veya çökme olmadan |

**Ek kural:** Win rate %20+ sapma veya 5+ kritik çökme → otomatik durdur.

**Çıktı:** Paper trading log'u, backtest karşılaştırma raporu, bitiş kriteri kontrol tablosu.

---

## FAZ 7 — Telegram Entegrasyonu ve Canlıya Alım (2-3 gün)

**Amaç:** Doğrulanmış sistemi otomatik hale getirmek.

1. `python-telegram-bot` ile bot oluştur (BotFather'dan token al)
2. **Platform kararı — netleştirildi (v2):**
   ```
   VPS (Önerilen): crontab -e
   45 18 * * 1-5 /path/venv/bin/python /path/bot/run_daily.py

   Windows lokal: Task Scheduler
   Tetikleyici: Her iş günü 18:45
   Eylem: pythonw.exe C:\bist-bot\run_daily.py
   Not: PC'nin açık ve uyumamış olması gerekir

   Python içi (platform bağımsız): APScheduler
   scheduler.add_job(calistir_gunluk, 'cron',
                     day_of_week='mon-fri', hour=18, minute=45)
   ```
   **Neden 18:45?** Settlement fiyatlarının yfinance'e yansıması 18:10'da tamamlanmamış olabilir. 18:45'te çekilen veri çok daha stabiltir.
3. Sinyal üretiminden önce Faz 2.4 XU100 piyasa rejimi kontrol edilir
4. Telegram güvenliği: Token `.env`'de, `.env` `.gitignore`'da
5. Onay mekanizması: Bot otomatik emir vermesin (en az ilk 3-6 ay), sadece bilgilendirsin

**Çıktı:** Canlı, günlük çalışan, Türkçe mesaj gönderen, otomatik emir vermeyen Telegram botu.

---

## FAZ 8 — İzleme, Drift Takibi ve Yeniden Eğitim (Sürekli)

### 8.1 Rutin izleme

- [ ] PSI ve tahmin dağılımı raporlarını **haftalık** gözden geçir
- [ ] Model performansını **aylık** takip et
- [ ] Gerçekleşen sinyallerin başarı oranını her ay backtest beklentisiyle karşılaştır

### 8.2 Yeniden eğitim (Retraining) süreci — netleştirildi (v2)

**Ne zaman yeniden eğit?**

| Tetikleyici | Açıklama |
|---|---|
| Rutin: 3-6 ayda bir | Takvimsel yeniden eğitim |
| Drift: PSI > 0.25 | Feature dağılımı ciddi kaymış |
| Performans: Canlı win rate backtest'ten %15+ sapma | Model artık çalışmıyor |
| Acil: 2 haftada 3+ kritik hata | Altyapı sorunu |
| Rejim değişimi: Büyük makro şok sonrası | Faiz, seçim, küresel kriz |

**Nasıl yeniden eğit?**

```
1. Kayan pencere yaklaşımı:
   Eğitim: son 5 yıl (çok eski dönem piyasa yapısı farklı)
   Validation: son 1 yıl
2. Faz 3 (etiketleme) → Faz 4 (eğitim) tam döngüsü
3. Yeni model v(n+1) olarak kaydet: models/v2/, models/v3/
4. Karşılaştırma: eski vs yeni — aynı out-of-sample dönemde
   (yeni model eskisini %5+ geçmiyorsa canlıya alma)
5. Kısa paper trading (2-3 hafta) → canlıya al
```

**Model versiyonlama:**
- Her model `models/v{N}/` altında saklanır
- `models/aktif/` → junction ile aktif modele işaret eder
- Eski modeller silinmez — en az 3 versiyon tarihsel karşılaştırma için tutulur

### 8.3 Evreni genişletme

- [ ] Yeni hisse ekleme için her seferinde Faz 1-3 tekrar et
- [ ] Model Faz 4'te yeni hisseyi dahil ederek yeniden eğitilmeli
- [ ] "Hızlıca ekleyip canlıya alma" dürtüsüne kapılma

---

## FAZ 9 — Basit Streamlit Arayüzü (FAZ 8 Sonrası) — YENİ

**Amaç:** Botun ürettiği sinyalleri, açık pozisyonları ve hisse takip listesini kullanıcı dostu, sade ve görsel bir web arayüzünden izlemek ve yönetmek.

### 9.1 Hisse Yönetimi Ekranı
- SQLite veya `config/tickers.json` üzerinden takip edilen hisse evrenini (TICKERS) dinamik yönetme
- Yeni hisse ekleme / çıkarma / aktif-pasif durumu değiştirme
- Hisselerin sektör ve likidite etiketlerini tek tıkla güncelleme

### 9.2 Hızlı Analiz Ekranı
- Seçilen hissenin Plotly interaktif mum grafiği (Candlestick)
- Üzerine eklenmiş dinamik ATR bantları, TP/SL seviyeleri ve hacim barları
- Anlık model olasılığı, piyasa rejimi ve 0-100 arası **İşlem Skoru** gösterge kartı

### 9.3 Portföy & Pozisyon Takibi
- Açık işlemlerin anlık kâr/zarar (% ve TL) durumu
- Giriş fiyatı, TP1, TP2, Stop-Loss ve elde tutma günü (Time barrier kalan gün) takip tablosu
- Geçmiş işlem günlüğü (trade log) ve kümülatif getiri grafiği

**Not:** Bu fazın kodlaması FAZ 8 (canlı izleme ve retraining) tamamlandıktan sonra en son adımda yapılacaktır.

---

## Zaman Çizelgesi Özeti

| Faz | Süre | Kümülatif |
|---|---|---|
| 0 — Kurulum + platform kararı | 1-2 gün | ~2 gün |
| 1 — Veri toplama + split kontrolü | 2-4 gün | ~6 gün |
| 2 — Feature engineering (bilanço dahil) | 3-5 gün | ~11 gün |
| 3 — Etiketleme (timeout kararı dahil) | 2-3 gün | ~14 gün |
| 3.5 — Etiket kalite denetimi (YENİ) | 0.5-1 gün | ~15 gün |
| 4 — Model eğitimi + Optuna + nested validation | 6-9 gün | ~24 gün |
| 5 — Trading engine + backtest + portfolio | 5-7 gün | ~31 gün |
| 5.5 — Otomatik doğrulama / hata tespiti | 3-4 gün | ~35 gün |
| 5.7 — KAP haber filtresi + erişim testi | 3-4 gün | ~39 gün |
| 6 — Paper trading (bitiş kriteri ile) | 4-8 hafta | ~2.5-3.5 ay |
| 7 — Telegram canlı + platform kurulumu | 2-3 gün | ~2.5-3.5 ay |
| 8 — İzleme + drift + retraining (sürekli) | Sürekli | — |
| 9 — Basit Streamlit arayüzü | 2-3 gün | En son |

Gerçekçi toplam: **paper trading dahil yaklaşık 3-5 ay**. Faz 6'yı veya 5.5'i atlamak en sık yapılan ve en pahalıya patlayan hatadır.

---

## Bir Sonraki Adım — Kodlama Öncelik Sırası

Bu planda en kritik parçalar:
1. **OHLC tabanlı Triple Barrier + ATR dinamik bariyer motoru** (FAZ 3)
2. **Purged Walk-Forward + Optuna + zaman sıralı calibration motoru** (FAZ 4)
3. **Trading Engine:** entry/exit + gap kontrolü + risk-based sizing + portfolio selector (FAZ 5)
4. **İşlem skoru hesabı:** `bot/sinyal_skoru.py` (FAZ 5.0.1)
5. FAZ 0-1 veri altyapısı + kalite kontrolü

**İlk kodlama sırası:**
```
Faz 1 veri → Faz 2 feature → Faz 3 label → Faz 3.5 kalite denetimi
→ Faz 4 model → Faz 5 trading engine → Faz 5.5 health check
→ Faz 5.7 KAP filtresi → Faz 6 paper trading → Faz 7 telegram canlı
→ Faz 8 izleme & drift → Faz 9 Streamlit arayüzü
```

---

*Plan v2.2 — Son güncelleme: 2026-08-30*

*v2 değişiklikleri: Timeout label stratejisi sabitlendi (FAZ 3), FAZ 3.5 etiket kalite denetimi eklendi (YENİ FAZ), hiperparametre optimizasyonu Optuna ile eklendi (FAZ 4.2), kalibrasyon minimum örneklem eşiği belirlendi (FAZ 4.3), işlem skoru formülle tanımlandı (FAZ 5.0.1), gap stres eşiği somutlaştırıldı (FAZ 5.0.2), exit engine model sinyal kuralı netleştirildi (FAZ 5.0.3), KAP erişim güvenilirlik testi eklendi (FAZ 5.7.0), paper trading bitiş kriterleri somutlaştırıldı (FAZ 6.1), platform kararı netleştirildi (FAZ 0.2 + FAZ 7), kütüphane listesi güncellendi (FAZ 0.3), bilanço takvimi opsiyonellikten çıkarıldı (FAZ 2.3), retraining süreci ve versiyonlama belgelendi (FAZ 8.2).*

*v2.1 değişiklikleri (2026-08-30): Cron zamanı 18:10 → 18:45 olarak güncellendi — settlement gecikmesi nedeniyle (FAZ 0.2, FAZ 7), sektörel endeks + VIX veri çekimi eklendi (FAZ 1), sektörel göreceli güç feature eklendi (FAZ 2.2), hacim şoku binary feature eklendi (FAZ 2.2), VIX makro risk filtresi ve işlem skoru cezası eklendi (FAZ 2.4.1 + FAZ 5.0.1), split/temettü sonrası indikatör maskeleme kuralı eklendi (FAZ 5.0.3), limit emir kuralı ve Telegram uyarı satırı eklendi (FAZ 5.0.2), güncel Telegram mesaj standardı güncellendi (FAZ 5.7.4).*

*v2.2 değişiklikleri (2026-08-30): FAZ 9 — Basit Streamlit Arayüzü (Hisse yönetimi, Hızlı analiz ve Portföy takibi) eklendi.*
