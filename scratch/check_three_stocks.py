import os, json, sys
sys.path.insert(0, os.path.abspath("."))
import pandas as pd

# 1. paper_portfolio_v4.json kontrolü
v4_port_file = "models/v4_ranking/paper_portfolio_v4.json"
with open(v4_port_file, "r", encoding="utf-8") as f:
    v4_port = json.load(f)

v4_positions = v4_port.get("positions", {})
targets = ["ALKIM.IS", "KCAER.IS", "OSMEN.IS"]

print("=== 1. paper_portfolio_v4.json KONTROLÜ ===")
for t in targets:
    in_port = t in v4_positions
    print(f"  - {t}: Portföyde {'VAR' if in_port else 'YOK'}")

# 2. latest_ranking_cache_v4.parquet kontrolü
cache_file = "models/v4_ranking/latest_ranking_cache_v4.parquet"
if os.path.exists(cache_file):
    df_cache = pd.read_parquet(cache_file)
    print("\n=== 2. latest_ranking_cache_v4.parquet SKORLARI ===")
    for t in targets:
        sub = df_cache[df_cache["sembol"] == t]
        if not sub.empty:
            r = sub.iloc[0]
            print(f"  - {t}: Sıra (Rank) = {r.get('rank')}, Skor = {r.get('ml_score', 0):.4f}, Desil = {r.get('decile')}, Bilanço Yaşı = {r.get('data_age_days')} gün, Bilanço Uyarı = {r.get('bilanco_uyari')}")
        else:
            print(f"  - {t}: Cache tablosunda bulunamadı!")

# 3. Bilanço tazelik ve forward-fill durumu
print("\n=== 3. BİLANÇO DOSYASI (fundamentals) KONTROLÜ ===")
for t in targets:
    stem = t.replace(".IS", "_IS")
    p_file = f"data/fundamentals/{stem}.parquet"
    if os.path.exists(p_file):
        df_p = pd.read_parquet(p_file)
        last_row = df_p.iloc[-1]
        print(f"  - {t}: Dosya VAR ({len(df_p)} çeyrek), Son Çeyrek = {last_row.get('ceyrek')}, Geçerlilik = {last_row.get('gecerlilik_tarihi')}")
    else:
        print(f"  - {t}: Dosya YOK ({p_file})")

# Check config universe
import config as cfg
print("\n=== 4. config.HISSELER EVRENİ KONTROLÜ ===")
for t in targets:
    in_universe = t in cfg.HISSELER
    print(f"  - {t}: 88 hisselik evrende {'VAR' if in_universe else 'YOK'}")
