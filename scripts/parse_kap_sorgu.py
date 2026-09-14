with open('bist-bot/scripts/kap_sorgu.html', 'r', encoding='utf-8') as f:
    text = f.read()

import re
print("Length:", len(text))
# Find JS bundles or API urls
js_files = re.findall(r'src="([^"]+\.js[^"]*)"', text)
print("JS files count:", len(js_files))
for js in js_files[:5]:
    print("JS:", js)

api_endpoints = re.findall(r'["\'](/[^"\']*api[^"\']*)["\']', text)
print("API endpoints:", list(set(api_endpoints)))
