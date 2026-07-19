#!/usr/bin/env python3
"""
Guide Alia local scraper — runs on your Mac every Tuesday.
Scrapes Kol Zchut via MediaWiki API, rotates topics weekly.

Setup:
  pip3 install httpx beautifulsoup4
  crontab -e
  Add: 0 9 * * 2 python3 /Users/anaelleadhoute/Desktop/Alia_Community/scripts/kolzchut_local.py
"""

import httpx
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime

SERVER_URL = "https://alia-channel.com/api/scrape/tips/manual"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}

KOLZCHUT_TERMS = [
    # Aliya & droits des olim
    "עולים חדשים", "סל קליטה", "תעודת עולה", "משרד הקליטה",
    # Logement
    "דיור", "שכר דירה", "סיוע בשכר דירה", "משכנתא",
    # Santé
    "בריאות", "קופת חולים", "ביטוח בריאות", "תרופות",
    # Enfants & famille
    "ילדים", "קצבת ילדים", "גן ילדים", "חופשת לידה", "דמי לידה",
    # Travail
    "עבודה", "דמי אבטלה", "זכויות עובד", "חופשה שנתית",
    # Retraite & Bituah Leumi
    "קצבת זקנה", "ביטוח לאומי", "קצבת נכות", "פנסיה",
    # Impôts & finances
    "מס הכנסה", "מס רכוש", "החזר מס", "ביטוח לאומי עצמאי",
    # Transport
    "רב-קו", "תחבורה ציבורית", "הנחה בתחבורה",
]


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()
    main = soup.find("div", class_="mw-parser-output") or soup.find("main") or soup.body
    return main.get_text(separator="\n", strip=True)[:4000] if main else ""


def run():
    week_number = int(datetime.now().strftime("%U"))
    term = KOLZCHUT_TERMS[week_number % len(KOLZCHUT_TERMS)]
    print(f"[guide] Week {week_number} — searching: {term}")

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        resp = client.get(
            "https://www.kolzchut.org.il/w/api.php",
            params={"action": "query", "list": "search", "srsearch": term, "format": "json", "srlimit": 1},
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search", [])
        if not hits:
            print(f"[guide] No results for '{term}'")
            return

        title = hits[0]["title"]
        url = f"https://www.kolzchut.org.il/he/{urllib.parse.quote(title)}"
        print(f"[guide] Fetching: {url}")

        page = client.get(url, timeout=20)
        page.raise_for_status()
        content = extract_text(page.text)
        if not content:
            print("[guide] Empty content, aborting.")
            return

        print(f"[guide] Content length: {len(content)} chars")
        server_resp = client.post(SERVER_URL, json={"url": url, "content": content}, timeout=30)
        server_resp.raise_for_status()
        print(f"[guide] Sent to server: {server_resp.json()}")


if __name__ == "__main__":
    run()
