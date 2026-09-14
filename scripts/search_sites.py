import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 1. Search borsagundem
try:
    r = requests.get('https://www.borsagundem.com.tr/arama?q=PASEU', headers=headers, timeout=10)
    print("Borsagundem status:", r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a'):
        href = a.get('href', '')
        text = a.get_text().strip()
        if 'PASEU' in text or 'paseu' in href or 'Pasifik' in text:
            print("BG Link:", href, text)
except Exception as e:
    print("BG err:", e)

# 2. Search paratic
try:
    r = requests.get('https://paratic.com/?s=PASEU', headers=headers, timeout=10)
    print("\nParatic status:", r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a'):
        href = a.get('href', '')
        text = a.get_text().strip()
        if 'PASEU' in text or 'tedbir' in text.lower() or 'Pasifik' in text:
            print("Paratic Link:", href, text)
except Exception as e:
    print("Paratic err:", e)
