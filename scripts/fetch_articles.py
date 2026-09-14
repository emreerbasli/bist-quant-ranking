import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

session = requests.Session()
session.headers.update(headers)

links = [
    ("VBTS Tedbiri", "https://news.google.com/rss/articles/CBMibEFVX3lxTE5hYjZpbE91MDhhcHZGWXRYcFVpRjk5RHJlb2E4TXVLTnh5cmh0ajc0b0VpN2l1cWE0ZHlRU2h1WVhCdTN0blRMSXNMTm1rRnBhVFZxNFM2UHZmQUZfMGdLUEpaaXZ1RzBNUG1aNA?oc=5"),
    ("MKK Pay Sahipligi 31 Aug", "https://news.google.com/rss/articles/CBMijAFBVV95cUxPekRWZzd1TFRxTFhWc0swemtLbFliODhaS1pqRV82Y2J1YTVock5tdndpZjhZTjFodGttWkRRcEpfdVE3RTFwdndwb0FLQWNsWjN1TGM5MFB4RlhybUZiSTlWTUxEYVpiajRGWnREaXNteTZFWXVGalFuSnJkM0lTU3YzeS1KZk9rMU9PNA?oc=5"),
    ("Fiili Dolasim 08 Sep", "https://news.google.com/rss/articles/CBMilgFBVV95cUxNc0kybW9JR1IwN0hHU19QYno0N0M1XzhZWHNScmNmTDVpUVg4eEhkQ0Nsak1mSlI3bTBvb3UxbUk2cTFqMjM3Tl9GMVdOWU5UWi1qVDN1ZjRMNmdhOXRlOEtnMUx0LUhfeXlRMndka2F5MTBLbDB5QUNMeVpTZlpFaVZOX0k2T005TzVlN3lPUl9HLVNDZmc?oc=5"),
    ("KAP Fiili Dolasim Yeni Safak", "https://news.google.com/rss/articles/CBMi8AFBVV95cUxNaFdiSW16c2ExdEJ5Z0Q2bmJsQVBDQ2lxbERWOGNrNDNTUmktYTRQbzN6ODVqZ1VGb0JyOVZ1TVhsQVp4MnZmN2pvNTRRbHF0M3BWcU16bUNRQmdVWjZPWTM3aU9xOTRYUFpQXzdDODMzWDJWOWRRSlVKUTB4SmJrU2tyX0U3S0JYQUlsVW1rTW5wTnlNMkJQMnlUd011ZTJLVmdXamV1TnVrSmZpeHloY1pNdDJnMFRiZUdERXBnTzB1YzRTMjY5Y1pPQ2ZMeXRHZHNzZ25iYlVjMkdWZU91UmVBcUZEVjFkb252RXV1Vlg?oc=5"),
    ("Tera Pusula Fon 09 Sep", "https://news.google.com/rss/articles/CBMijgFBVV95cUxPaVVkM0pWXzFNblo5OGFleGc5ZklFbm1PZUJReUttemxNS180RjZyMEgtMnZTRUJLckt5N1BVU25xVVpMVEtMamVOU0NrcWlkUXItTU5HMVlRQUJXXzJmWUtSZ0F0bXk4UFg3U1ExdldwVjRMWHBmdTVvbzk0TFV2SjFrN1ZYRGM0NHNQdTl3?oc=5"),
]

for label, url in links:
    print(f"\n{'='*20} {label} {'='*20}")
    try:
        r = session.get(url, timeout=12, allow_redirects=True)
        soup = BeautifulSoup(r.text, 'html.parser')
        # print title and first 1000 chars of body
        print("Final URL:", r.url)
        print("Page Title:", soup.title.string if soup.title else "")
        paragraphs = [p.get_text().strip() for p in soup.find_all(['p', 'div']) if len(p.get_text().strip()) > 40]
        for p in paragraphs[:8]:
            if any(k in p for k in ['PASEU', 'Pasifik', 'tedbir', 'kredili', 'brüt', 'fiili dolaşım', 'MKK', 'pay']):
                print(">>", p[:300])
    except Exception as e:
        print("Fetch err:", e)
