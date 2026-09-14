"""
scratch/test_v32_full_verification.py
Tam V3.2 uçtan uca doğrulama testi.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from models.v3_ranking.data_loader import yukle_veriler
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline
from models.v3_ranking.paper_trader import PaperTrader
import config as cfg

print("=" * 80)
print("BIST V3.2 TAM UÇTAN UCA DOĞRULAMA TESTİ")
print("=" * 80)

# 1. Verileri Yükle
print("\n[1/4] Piyasa ve PIT Bilanço Verileri Yükleniyor...")
fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
t_now = seri_xu100.index[-1]
print(f"  -> En son veri tarihi: {t_now.strftime('%Y-%m-%d')}")
print(f"  -> Yüklenen hisse sayısı: {len(fiyat_dict)}")

# 2. Ranking Pipeline Test
print("\n[2/4] LGBMRankingPipeline Özellik ve Sıralama Testi...")
pipeline = LGBMRankingPipeline()
df_features = pipeline.compute_features(t_now, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)

assert "data_age_days" in df_features.columns, "HATA: data_age_days sütunu compute_features içinde bulunamadı!"
print(f"  -> compute_features tamamlandı: {len(df_features)} hisse.")
print(f"  -> data_age_days min: {df_features['data_age_days'].min()} gün, max: {df_features['data_age_days'].max()} gün.")

df_ranked = pipeline.rank_stocks(df_features)
assert "data_age_days" in df_ranked.columns, "HATA: data_age_days rank_stocks çıktısında korunmadı!"
print(f"  -> rank_stocks tamamlandı: {len(df_ranked)} hisse sıralandı.")

# select_top_k_v2 testi
top_10_df = pipeline.select_top_k_v2(df_features, k=10)
assert "sektor_v2" in top_10_df.columns, "HATA: sektor_v2 bulunamadı!"
assert "data_age_days" in top_10_df.columns, "HATA: data_age_days top_10_df içinde yok!"
assert "bilanco_uyari" in top_10_df.columns, "HATA: bilanco_uyari bulunamadı!"
print("  -> select_top_k_v2 başarıyla çalıştı. Seçilen 10 hisse:")
for idx, r in top_10_df.iterrows():
    uyari_str = "[ESKI]" if r["bilanco_uyari"] else "[Taze]"
    print(f"     {r['rank']:>2}. {r['sembol']:<9} | Sektor: {r['sektor_v2']:<18} | Hacim: {r['avg_tl_hacim_m']:>6.1f}M TL | Bilanco: {int(r['data_age_days'])} gun ({uyari_str})")

# 3. Paper Trader Simülasyonu
print("\n[3/4] PaperTrader V3.2 İcra ve Takip Testi...")
import tempfile
temp_dir = Path(tempfile.mkdtemp())
p_file = temp_dir / "paper_portfolio.json"
l_file = temp_dir / "paper_trading_log.csv"

# Canlı portföyden kopyalayarak başla
import shutil
live_p_file = ROOT / "models" / "v3_ranking" / "paper_portfolio.json"
shutil.copy(live_p_file, p_file)

trader = PaperTrader(portfolio_file=p_file, log_file=l_file)
top_10_syms = top_10_df["sembol"].tolist()
current_prices = {s: float(fiyat_dict[s].iloc[-1]) for s in top_10_syms if s in fiyat_dict}
for s in trader.portfolio_state["positions"]:
    if s in fiyat_dict and s not in current_prices:
        current_prices[s] = float(fiyat_dict[s].iloc[-1])

res = trader.execute_check(
    t=t_now,
    top_k_ranked=top_10_syms,
    current_prices=current_prices,
    current_xu100_price=float(seri_xu100.iloc[-1]),
    seri_usdtry=seri_usdtry,
    tufe_aylik=tufe_aylik,
    days_elapsed=3,  # 2026-09-07'den 2026-09-10'a 3 gün
    send_telegram=False
)


# Kontroller
pos = trader.portfolio_state["positions"]
for s, inf in pos.items():
    assert "personal_peak_price" in inf, f"HATA: {s} için personal_peak_price yok!"
    assert "peak_drawdown_pct" in inf, f"HATA: {s} için peak_drawdown_pct yok!"
    assert "days_held" in inf, f"HATA: {s} için days_held yok!"

assert "cikis_takvimi" in res, "HATA: res içinde cikis_takvimi yok!"
print("  -> execute_check başarıyla icra edildi.")
print(f"  -> 60-Gün Çıkış Takvimi çıktısı mevcut: {len(res['cikis_takvimi'].splitlines())} satır.")
print(f"  -> Bireysel peak DD uyarı sayısı: {len(res.get('uyari_hisseler', []))}")

# 4. CSV Log Sütun Doğrulaması
print("\n[4/4] CSV Log Sütun Doğrulaması...")
df_log = pd.read_csv(l_file)
required_cols = [
    "tarih", "portfoy_listesi", "degisiklik", "model_getiri_yuzde",
    "bist100_getiri_yuzde", "alfa", "drift_durumu", "makro_ozet",
    "dd_kesici_aktif", "portfoy_zirve_getiri",
    "max_hisse_dd_pct", "min_gun_kalan", "uyari_hisseler"
]
for col in required_cols:
    assert col in df_log.columns, f"HATA: {col} CSV logunda bulunamadı!"
print(f"  -> CSV log sütunları eksiksiz: {len(df_log.columns)} sütun doğrulandı.")

print("\n" + "=" * 80)
print("[OK] TUM V3.2 TESTLERI BASARIYLA GECTI!")
print("=" * 80)
