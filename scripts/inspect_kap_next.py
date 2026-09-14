import re

with open('bist-bot/scripts/kap_sorgu.html', 'r', encoding='utf-8') as f:
    text = f.read()

# find all occurrences of "http" or "api" or "disclosure"
matches = re.findall(r'https?://[a-zA-Z0-9.-]+/[^\s"\'<>]*', text)
print("Found urls:", len(matches))
for m in list(set(matches))[:20]:
    if 'kap.org.tr' in m or 'api' in m:
        print("URL:", m)

# Let's inspect the Next.js data chunks
chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', text)
print("Next.js chunks:", len(chunks))
combined = "".join(chunks).replace('\\"', '"')
# search for disclosure or bildirim in combined
for m in re.finditer(r'(bildirim[^\",]{10,80})', combined, re.I):
    print("Bildirim chunk:", m.group(1))
    if len(m.group(1)) > 0:
        break
