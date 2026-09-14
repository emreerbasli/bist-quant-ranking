import base64
import re
import requests

def decode_google_news_url(source_url):
    try:
        url_part = source_url.split("articles/")[1].split("?")[0]
        # base64 decode
        # Pad url_part if needed
        padding = len(url_part) % 4
        if padding:
            url_part += '=' * (4 - padding)
        decoded = base64.urlsafe_b64decode(url_part.encode('utf-8'))
        # find url in bytes
        match = re.search(rb'https?://[^\x00-\x1f\x7f-\xff]+', decoded)
        if match:
            return match.group(0).decode('utf-8', errors='ignore')
    except Exception as e:
        return str(e)
    return None

test_links = [
    "https://news.google.com/rss/articles/CBMibEFVX3lxTE5hYjZpbE91MDhhcHZGWXRYcFVpRjk5RHJlb2E4TXVLTnh5cmh0ajc0b0VpN2l1cWE0ZHlRU2h1WVhCdTN0blRMSXNMTm1rRnBhVFZxNFM2UHZmQUZfMGdLUEpaaXZ1RzBNUG1aNA?oc=5",
    "https://news.google.com/rss/articles/CBMijAFBVV95cUxPekRWZzd1TFRxTFhWc0swemtLbFliODhaS1pqRV82Y2J1YTVock5tdndpZjhZTjFodGttWkRRcEpfdVE3RTFwdndwb0FLQWNsWjN1TGM5MFB4RlhybUZiSTlWTUxEYVpiajRGWnREaXNteTZFWXVGalFuSnJkM0lTU3YzeS1KZk9rMU9PNA?oc=5",
    "https://news.google.com/rss/articles/CBMilgFBVV95cUxNc0kybW9JR1IwN0hHU19QYno0N0M1XzhZWHNScmNmTDVpUVg4eEhkQ0Nsak1mSlI3bTBvb3UxbUk2cTFqMjM3Tl9GMVdOWU5UWi1qVDN1ZjRMNmdhOXRlOEtnMUx0LUhfeXlRMndka2F5MTBLbDB5QUNMeVpTZlpFaVZOX0k2T005TzVlN3lPUl9HLVNDZmc?oc=5"
]

for l in test_links:
    real = decode_google_news_url(l)
    print("Decoded URL:", real)
