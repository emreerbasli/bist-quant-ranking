import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

url = "https://paratic.com/borsa-istanbulda-3-hisseye-vbts-tedbiri/"
r = requests.get(url, headers=headers, timeout=10)
print("VBTS Article Status:", r.status_code)
if r.status_code == 200:
    soup = BeautifulSoup(r.text, 'html.parser')
    for p in soup.find_all('p'):
        print(p.get_text().strip())
