import re
import json

with open('bist-bot/scripts/kap_paseu_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Let's find any URLs or IDs in the html
# Specifically, let's look for member id or company id or api calls
print("Page length:", len(html))

# Let's search for mkkMemberOid or similar strings
for m in re.finditer(r'([a-zA-Z0-9_-]*(?:Member|Oid|Company|Disclos)[a-zA-Z0-9_-]*[\s:\"=]+[a-zA-Z0-9_-]{10,})', html, re.I):
    print("Match:", m.group(0)[:80])

# Let's also look for disclosure list or tables
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'html.parser')
for a in soup.find_all('a'):
    href = a.get('href', '')
    if 'bildirim' in href or 'disclos' in href:
        print("Link:", href, a.get_text().strip())
