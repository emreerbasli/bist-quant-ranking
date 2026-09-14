import requests
from bs4 import BeautifulSoup
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

urls = [
    'https://www.kap.org.tr/tr/sirket-bilgileri/bildirimler/5221-pasifik-eurasia-lojistik-dis-ticaret-a-s',
    'https://www.kap.org.tr/tr/sirket-bilgileri/tum-bildirimler/5221-pasifik-eurasia-lojistik-dis-ticaret-a-s'
]

for url in urls:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(url, "-> Status:", r.status_code)
        if r.status_code == 200:
            with open('bist-bot/scripts/kap_bildirimler.html', 'w', encoding='utf-8') as f:
                f.write(r.text)
            soup = BeautifulSoup(r.text, 'html.parser')
            print("Title:", soup.title.string if soup.title else "")
            # search for disclosure titles or items
            # find all text with dates like 2024, 2025, 2026, or Ağustos, Eylül
            for tag in soup.find_all(['p', 'div', 'span', 'a']):
                t = tag.get_text().strip()
                if any(k in t for k in ['Özel Durum', 'Sermaye', 'Pay', 'Finansal Rapor', 'Ortaklık', 'Açıklama']):
                    if len(t) < 150:
                        print("Found text:", t)
    except Exception as e:
        print("Error fetching:", url, e)
