import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

urls = [
    "https://tr.investing.com/equities/pasifik-eurasia-lojistik-dis-ticaret-as-news",
    "https://tr.investing.com/equities/pasifik-eurasia-lojistik-dis-ticaret-as-commentary",
    "https://finans.mynet.com/borsa/hisseler/paseu-pasifik-eurasia-lojistik/kap-haberleri/"
]

for url in urls:
    print(f"\n--- Fetching: {url} ---")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print("Status:", r.status_code)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            print("Title:", soup.title.string if soup.title else "")
            # Find news headlines or comments
            articles = soup.find_all(['article', 'li', 'div', 'p'])
            found = 0
            for a in articles:
                txt = a.get_text().strip()
                if ('PASEU' in txt or 'Pasifik' in txt or 'taban' in txt.lower() or 'tedbir' in txt.lower() or 'düşüş' in txt.lower()) and 20 < len(txt) < 300:
                    print(">>", txt.replace('\n', ' '))
                    found += 1
                    if found > 6:
                        break
    except Exception as e:
        print("Err:", e)
