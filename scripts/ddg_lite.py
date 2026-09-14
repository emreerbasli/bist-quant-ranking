import requests
from bs4 import BeautifulSoup
import urllib.parse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# DDG lite:
q = urllib.parse.quote("PASEU MKK pay sahipliği oranı 31 Ağustos 2026")
url = f"https://lite.duckduckgo.com/lite/"
r = requests.post(url, data={'q': 'PASEU MKK pay sahipliği oranı'}, headers=headers)
print("DDG lite status:", r.status_code)
soup = BeautifulSoup(r.text, 'html.parser')
for a in soup.find_all('a', class_='result-link'):
    print(a['href'], a.get_text())
for snippet in soup.find_all('td', class_='result-snippet'):
    print("Snippet:", snippet.get_text().strip())
    print("-" * 30)
