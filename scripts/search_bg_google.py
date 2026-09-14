import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Let's search borsagundem via google using html parsing
url = "https://www.google.com/search?q=site:borsagundem.com.tr+PASEU+31+A%C4%9Fustos+2026"
r = requests.get(url, headers=headers, timeout=10)
print("Google status:", r.status_code)
if r.status_code == 200:
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        if 'borsagundem.com.tr' in a['href']:
            print("Link:", a['href'])
