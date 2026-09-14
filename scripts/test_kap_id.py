import requests
import re
import json

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

r = requests.get('https://www.kap.org.tr/tr/Bildirim/1647691', headers=headers)
chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', r.text)
combined = ''.join(chunks).replace('\\"', '"').replace('\\\\', '\\')
print("Reconstructed length:", len(combined))

# find all table cells or strings
words = re.findall(r'\"([^\"]*PASEU[^\"]*)\"', combined)
print("PASEU occurrences:", list(set(words))[:10])

for m in re.finditer(r'([^\"\{\}\[\]]{10,PASEU.{10,100})', combined):
    pass

# search for text around PASEU
idx = 0
while True:
    pos = combined.find('PASEU', idx)
    if pos == -1:
        break
    print("Context around PASEU:", combined[max(0, pos-100):min(len(combined), pos+150)])
    print("-" * 40)
    idx = pos + 5
