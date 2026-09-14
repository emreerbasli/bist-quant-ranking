import requests
from bs4 import BeautifulSoup
import urllib.parse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

queries = [
    'PASEU "pay sahipliği oranları değişti" borsagundem',
    'PASEU fiili dolaşımdaki pay oranı 2026',
    'PASEU "VBTS" 2026',
    'PASEU ortak satışı 2026'
]

for q in queries:
    url = f"https://www.bing.com/search?q={urllib.parse.quote(q)}"
    r = requests.get(url, headers=headers, timeout=10)
    print(f"Bing status for '{q}': {r.status_code}")
    soup = BeautifulSoup(r.text, 'html.parser')
    results = soup.find_all('li', class_='b_algo')
    print(f"Found {len(results)} results")
    for res in results[:3]:
        title = res.find('h2')
        snippet = res.find('div', class_='b_caption')
        print("Title:", title.get_text() if title else "")
        print("Snippet:", snippet.get_text() if snippet else "")
        print("-" * 30)
