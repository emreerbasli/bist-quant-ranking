import requests
import json
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}

try:
    r = requests.get('https://www.kap.org.tr/tr/sirket-bilgileri/ozet/5221-pasifik-eurasia-lojistik-dis-ticaret-a-s', headers=headers, timeout=15)
    print("Ozet status:", r.status_code)
    with open('bist-bot/scripts/kap_paseu_page.html', 'w', encoding='utf-8') as f:
        f.write(r.text)
    
    # search for memberOid in text
    matches = re.findall(r'mkkMemberOid[^,\&;\"\']+', r.text)
    print("mkkMemberOid matches:", matches[:5])
    
    # search for api links
    apis = re.findall(r'/tr/api/[^\"\'\s]+', r.text)
    print("APIs found:", list(set(apis))[:10])

except Exception as e:
    print("Error:", e)
