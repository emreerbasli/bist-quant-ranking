import pandas as pd

paseu = pd.read_parquet('bist-bot/data/raw/PASEU_IS.parquet')
xu100 = pd.read_parquet('bist-bot/data/raw/XU100_IS.parquet')
xusin = pd.read_parquet('bist-bot/data/raw/XUSIN_IS.parquet')

df = pd.DataFrame({
    'PASEU_Close': paseu['close'],
    'PASEU_Vol': paseu['volume'],
    'XU100_Close': xu100['close'],
    'XUSIN_Close': xusin['close']
}).dropna()

tail_df = df.loc['2026-08-15':]
print(tail_df)

print("\n--- PERFORMANCE COMPARISON: PEAK TO 2026-09-07 ---")
ret_period = (tail_df.loc['2026-09-07', ['PASEU_Close', 'XU100_Close', 'XUSIN_Close']] / 
              tail_df.loc['2026-08-28', ['PASEU_Close', 'XU100_Close', 'XUSIN_Close']] - 1) * 100
for k, v in ret_period.items():
    print(f"{k}: {v:.2f}%")

print("\n--- PERFORMANCE OVER FULL 15-DAY PERIOD (2026-08-18 to 2026-09-07) ---")
ret_full = (tail_df.loc['2026-09-07', ['PASEU_Close', 'XU100_Close', 'XUSIN_Close']] / 
            tail_df.loc['2026-08-18', ['PASEU_Close', 'XU100_Close', 'XUSIN_Close']] - 1) * 100
for k, v in ret_full.items():
    print(f"{k}: {v:.2f}%")
