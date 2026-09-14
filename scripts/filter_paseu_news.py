import requests
from bs4 import BeautifulSoup
import urllib.parse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Fetch all items from Google News RSS
url = "https://news.google.com/rss/search?q=PASEU&hl=tr&gl=TR&ceid=TR:tr"
r = requests.get(url, headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'xml')
items = soup.find_all('item')
print(f"Total items for PASEU: {len(items)}")

for i, item in enumerate(items):
    title = item.title.text
    date = item.pubDate.text
    # filter for August and September 2026 (or 2024 if applicable)
    if any(m in date for m in ['Aug 2026', 'Sep 2026', 'Aug 2024', 'Sep 2024']):
        print(f"[{date}] {title}")
        print(f"Link: {item.link.text}")
        print("-" * 50)
