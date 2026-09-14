import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

urls = [
    "https://www.borsagundem.com.tr/haber/mkk-acikladi-4-hissede-pay-sahipligi-oranlari-degisti-1808620", # approximate, let's search borsagundem
]

# Let's search borsagundem for PASEU articles in late August / September 2026
try:
    r = requests.get('https://www.borsagundem.com.tr/arama?q=PASEU', headers=headers, timeout=10)
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        if '/haber/' in a['href']:
            print(a['href'], a.get_text().strip())
except Exception as e:
    print("Error:", e)
