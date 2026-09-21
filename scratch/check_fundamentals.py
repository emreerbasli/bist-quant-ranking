import os, glob
import pandas as pd

files = glob.glob('data/fundamentals/*.parquet')
print(f'Total fundamental parquet files: {len(files)}')

records = []
for f in sorted(files):
    ticker = os.path.basename(f).replace('.parquet', '').replace('_IS', '.IS')
    try:
        df = pd.read_parquet(f)
        count = len(df)
        quarters = df['ceyrek'].tolist() if 'ceyrek' in df.columns else []
        last_q = quarters[-1] if quarters else 'None'
        records.append({
            'ticker': ticker,
            'count': count,
            'last_q': last_q,
            'last_date': df['gecerlilik_tarihi'].iloc[-1] if 'gecerlilik_tarihi' in df.columns else 'None',
            'quarters': quarters[-4:]
        })
    except Exception as e:
        records.append({'ticker': ticker, 'count': 0, 'last_q': f'ERROR: {e}', 'last_date': 'None', 'quarters': []})

df_res = pd.DataFrame(records)
print(f"Toplam hisse: {len(df_res)}")

# 1) 88 hissenin tamamında en az son 4 çeyrek bilanço var mı?
missing_4q = df_res[df_res['count'] < 4]
print(f"\n1) En az son 4 çeyrek bilançosu OLMAYAN hisse sayısı: {len(missing_4q)}")
if len(missing_4q) > 0:
    for _, r in missing_4q.iterrows():
        print(f"   {r['ticker']}: toplam {r['count']} çeyrek var.")
else:
    print("   -> 88 hissenin TAMAMINDA en az son 4 çeyrek bilanço MEVCUT! (Minimum çeyrek sayısı: %d)" % df_res['count'].min())

# 2) Hangi hisselerde eksik çeyrek var (En güncel 2026Q2 olmayanlar)?
print('\nSon çeyrek dağılımı:')
print(df_res['last_q'].value_counts())

not_2026q2 = df_res[df_res['last_q'] != '2026Q2']
print(f"\n2) En son çeyreği 2026Q2 OLMAYAN hisseler ({len(not_2026q2)} adet):")
for _, r in not_2026q2.iterrows():
    print(f"   - {r['ticker']}: Son Çeyrek = {r['last_q']}, Son Geçerlilik Tarihi = {r['last_date']}, Toplam = {r['count']}")
