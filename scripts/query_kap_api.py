import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json'
}

# Try different KAP search endpoints
# KAP main disclosure filter endpoint:
url = "https://www.kap.org.tr/tr/api/disclosures"
payload = {
    "stockCodes": ["PASEU"],
    "fromDate": "2026-08-20",
    "toDate": "2026-09-12"
}

try:
    print("Sending request to KAP...")
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    print("Status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        print(f"Disclosures count: {len(data)}")
        for d in data:
            print(f"[{d.get('publishDate')}] {d.get('stockCode')} | {d.get('disclosureType')} | {d.get('title')}")
            print(f"ID: {d.get('disclosureId')} | Subject: {d.get('summary')}")
            print("-" * 50)
except Exception as e:
    print("Err:", e)
