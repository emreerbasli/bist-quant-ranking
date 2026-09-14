import requests
from bs4 import BeautifulSoup
import urllib.parse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 1. Check Yahoo Finance news content
try:
    import yfinance as yf
    t = yf.Ticker('PASEU.IS')
    print("Yahoo Finance info summary:")
    # print sector and industry
    print("Sector:", t.info.get('sector'))
    print("Industry:", t.info.get('industry'))
    print("Long Name:", t.info.get('longBusinessSummary')[:200] if t.info.get('longBusinessSummary') else "None")
except Exception as e:
    print("YF info error:", e)

# 2. Check RSS feeds or search
url = "https://news.google.com/rss/search?q=PASEU+KAP&hl=tr&gl=TR&ceid=TR:tr"
try:
    r = requests.get(url, headers=headers, timeout=10)
    print("\nGoogle News RSS Status:", r.status_code)
    soup = BeautifulSoup(r.text, 'xml')
    items = soup.find_all('item')
    print("Items found:", len(items))
    for item in items[:10]:
        print("Title:", item.title.text)
        print("Date:", item.pubDate.text)
        print("Link:", item.link.text)
        print("-" * 30)
except Exception as e:
    print("RSS error:", e)
