import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

url = "https://www.bloomberght.com/arama?q=PASEU"
r = requests.get(url, headers=headers, timeout=10)
print("BloombergHT status:", r.status_code)
if r.status_code == 200:
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        txt = a.get_text().strip()
        if 'PASEU' in txt or 'Pasifik' in txt:
            print("Link:", a['href'])
            print("Text:", txt)
