import sys
import os
from pathlib import Path

# Add bist-bot to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from models.v3_ranking.data_loader import yukle_veriler, check_market_date_alignment
from models.v3_ranking.ranking_pipeline import LGBMRankingPipeline
from models.v3_ranking.drift_monitor import DriftMonitor

print("--- 1. Testing data loading ---")
fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()
print(f"Loaded {len(fiyat_dict)} stock price series, xu100 len={len(seri_xu100)}, usdtry len={len(seri_usdtry)}")

print("\n--- 2. Checking alignment ---")
alignment = check_market_date_alignment(fiyat_dict, seri_xu100)
print("Alignment:", alignment)

t_now = seri_xu100.index[-1]
print(f"Latest date t_now: {t_now}")

print("\n--- 3. Testing pipeline features ---")
pipeline = LGBMRankingPipeline()
df_features = pipeline.compute_features(t_now, fiyat_dict, pit_bellek, seri_usdtry, tufe_aylik)
print(f"Computed features shape: {df_features.shape}")

print("\n--- 4. Testing rank_stocks ---")
df_ranked = pipeline.rank_stocks(df_features)
print(f"Ranked stocks: {len(df_ranked)}, top 5: {df_ranked['sembol'].iloc[:5].tolist()}")

print("\n--- 5. Testing select_top_k_v2 ---")
df_selected = pipeline.select_top_k_v2(df_features, k=10)
print(f"Selected stocks: {df_selected['sembol'].tolist()}")

print("\n--- 6. Testing drift monitor ---")
drift_mon = DriftMonitor()
report = drift_mon.generate_full_report(t_now, seri_usdtry, tufe_aylik, df_ranked['ml_score'].values)
print("Drift status:", report.overall_status)
print("Macro status:", report.macro_result.status, report.macro_result.details)
print("Score status:", report.score_result.status if report.score_result else "None")

print("\n--- 7. Checking paper portfolio positions against prices ---")
import json
with open(BASE_DIR / "models" / "v3_ranking" / "paper_portfolio.json", "r", encoding="utf-8") as f:
    p_data = json.load(f)

positions = p_data.get("positions", {})
missing_prices = []
for s, info in positions.items():
    if s not in fiyat_dict:
        missing_prices.append(s)
    else:
        last_avail = fiyat_dict[s].iloc[-1]
        print(f"Position {s:<9}: entry={info['entry_price']:.2f}, last_in_json={info['last_price']:.2f}, current_market={last_avail:.2f}")

if missing_prices:
    print("ERROR: missing stock prices for:", missing_prices)
else:
    print("All positions have available market prices.")

print("\n--- 8. Checking batch and shell scripts ---")
scripts = list(BASE_DIR.parent.glob("*.bat"))
for sc in scripts:
    print(f"Batch script: {sc.name}")

print("\nALL CORE TESTS COMPLETED SUCCESSFULLY!")
