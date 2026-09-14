import pandas as pd
import numpy as np

df = pd.read_parquet('bist-bot/data/raw/PASEU_IS.parquet')

# Calculate indicators
df['daily_ret'] = df['close'].pct_change() * 100
df['vol_ma20'] = df['volume'].rolling(20).mean()
df['vol_std20'] = df['volume'].rolling(20).std()
df['vol_zscore'] = (df['volume'] - df['vol_ma20']) / df['vol_std20']
df['vol_ratio'] = df['volume'] / df['vol_ma20']
df['vol_tl'] = df['volume'] * df['close'] / 1e6 # Million TL turnover

pd.set_option('display.max_columns', 15)
pd.set_option('display.width', 150)
last15 = df.tail(15)

print("=== PASEU.IS PARQUET SON 15 GÜNLÜK DETAYLI HACİM VE FİYAT TABLOSU ===")
output_cols = ['open', 'high', 'low', 'close', 'daily_ret', 'volume', 'vol_ma20', 'vol_ratio', 'vol_zscore', 'vol_tl']
res = last15[output_cols].copy()
res['volume_lot'] = res['volume'].apply(lambda x: f"{x:,.0f}")
res['vol_ma20_lot'] = res['vol_ma20'].apply(lambda x: f"{x:,.0f}")
res['vol_tl_str'] = res['vol_tl'].apply(lambda x: f"{x:,.1f} M TL")
res['vol_ratio_str'] = res['vol_ratio'].apply(lambda x: f"{x:.2f}x")
res['vol_z_str'] = res['vol_zscore'].apply(lambda x: f"{x:+.2f}")
res['ret_str'] = res['daily_ret'].apply(lambda x: f"{x:+.2f}%")

print(res[['close', 'ret_str', 'volume_lot', 'vol_ma20_lot', 'vol_ratio_str', 'vol_z_str', 'vol_tl_str']])

print("\n--- İSTATİSTİKSEL ÖZET (SON 15 GÜN) ---")
print(f"Hacim Ortalaması (Son 15 Gün): {last15['volume'].mean():,.0f} lot")
print(f"Tüm Tarihsel Hacim Ortalaması: {df['volume'].mean():,.0f} lot")
print(f"En Yüksek Hacim: {last15['volume'].max():,.0f} lot ({last15['volume'].idxmax().strftime('%Y-%m-%d')})")
print(f"En Düşük Hacim: {last15['volume'].min():,.0f} lot ({last15['volume'].idxmin().strftime('%Y-%m-%d')})")
