import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Try borsagundem rss feeds
rss_urls = [
    "https://www.borsagundem.com.tr/rss",
    "https://www.borsagundem.com.tr/rss/piyasalar",
    "https://www.borsagundem.com.tr/rss/sirketler"
]

for url in rss_urls:
    try:
        r = requests.get(url, headers=headers, timeout=5)
        print(url, r.status_code)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'xml')
            for item in soup.find_all('item'):
                t = item.title.text
                if any(k in t for k in ['PASEU', 'Pasifik', 'pay', 'oran']):
                    print(">>", item.pubDate.text, t, item.link.text)
    except Exception as e:
        print("RSS err:", e)
