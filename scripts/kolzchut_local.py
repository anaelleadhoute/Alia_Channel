#!/usr/bin/env python3
"""
Kol Zchut local scraper — runs on your Mac every Sunday.
Fetches Kol Zchut from your home IP and sends content to the server.

Setup:
  pip3 install httpx beautifulsoup4
  crontab -e
  Add: 0 9 * * 0 /usr/bin/python3 /Users/anaelleadhoute/Desktop/Alia_Community/scripts/kolzchut_local.py
"""

import httpx
from bs4 import BeautifulSoup
from datetime import datetime

SERVER_URL = "https://alia-channel.com/api/scrape/tips/manual"

SEARCH_TERMS = ["עולים חדשים", "דיור", "בריאות", "עבודה"]
SEARCH_URL = "https://www.kolzchut.org.il/w/he/index.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    "Referer": "https://www.kolzchut.org.il/",
}


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()
    main = soup.find("div", class_="mw-parser-output") or soup.find("main") or soup.body
    return main.get_text(separator="\n", strip=True)[:4000] if main else ""


def run():
    week_number = int(datetime.now().strftime("%W"))
    term = SEARCH_TERMS[week_number % len(SEARCH_TERMS)]

    print(f"[kolzchut] Searching for: {term}")

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        # Search
        search_resp = client.get(
            SEARCH_URL,
            params={"search": term, "action": "opensearch"},
            timeout=20,
        )
        search_resp.raise_for_status()
        results = search_resp.json()

        urls = results[3] if len(results) > 3 else []
        if not urls:
            print(f"[kolzchut] No results for '{term}'")
            return

        target_url = urls[0]
        print(f"[kolzchut] Fetching: {target_url}")

        # Fetch page
        page_resp = client.get(target_url, timeout=20)
        page_resp.raise_for_status()
        content = extract_text(page_resp.text)

        if not content:
            print("[kolzchut] Empty content, aborting.")
            return

        # Send to server
        server_resp = client.post(
            SERVER_URL,
            json={"url": target_url, "content": content},
            timeout=30,
        )
        server_resp.raise_for_status()
        print(f"[kolzchut] Sent to server: {server_resp.json()}")


if __name__ == "__main__":
    run()
