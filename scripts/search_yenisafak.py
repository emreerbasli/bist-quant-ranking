import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Search Yeni Safak for PASEU
url = "https://www.yenisafak.com/arama?q=PASEU"
r = requests.get(url, headers=headers, timeout=10)
print("Yeni Safak status:", r.status_code)
if r.status_code == 200:
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        if '/kap-' in a['href'] or '/ekonomi/' in a['href'] or 'PASEU' in a.get_text():
            print("YS Link:", a['href'])
            print("YS Text:", a.get_text().strip())
            print("-" * 30)
