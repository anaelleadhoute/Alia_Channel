#!/usr/bin/env python3
"""
Droits Alia local scraper — runs on Mac every Tuesday.
Scrapes Kol Zchut with eligibility-focused terms.

crontab: 0 9 * * 2 python3 /Users/anaelleadhoute/Desktop/Alia_Community/scripts/droits_local.py
"""

import httpx
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime

SERVER_URL = "https://alia-channel.com/api/scrape/rights/manual"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}

# Eligibility-focused terms
RIGHTS_TERMS = [
    # Aides financières
    "זכאות לדיור", "סיוע בשכר דירה", "מענק עלייה", "סל קליטה",
    # Bituah Leumi — éligibilité
    "זכאות לקצבת ילדים", "זכאות לדמי לידה", "זכאות לדמי אבטלה",
    "זכאות לקצבת נכות", "זכאות לקצבת זקנה",
    # Santé — droits
    "זכאות לביטוח בריאות", "זכות לתרופות", "זכות לרופא מומחה",
    # Travail — droits
    "זכויות עובד זר", "זכויות עובדים", "פיצויי פיטורין", "דמי מחלה",
    # Olim — droits spécifiques
    "הטבות מס לעולים", "פטור ממס לעולים", "זכויות עולים חדשים",
    # Logement
    "זכאות למשכנתא", "סיוע לדיור לעולים",
    # Famille
    "קצבת שאירים", "גמלת סיעוד", "זכאות לגן ילדים חינם",
]


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()
    main = soup.find("div", class_="mw-parser-output") or soup.find("main") or soup.body
    return main.get_text(separator="\n", strip=True)[:4000] if main else ""


def run():
    week_number = int(datetime.now().strftime("%W"))
    term = RIGHTS_TERMS[week_number % len(RIGHTS_TERMS)]
    print(f"[droits] Week {week_number} — searching: {term}")

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        resp = client.get(
            "https://www.kolzchut.org.il/w/api.php",
            params={"action": "query", "list": "search", "srsearch": term, "format": "json", "srlimit": 1},
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search", [])
        if not hits:
            print(f"[droits] No results for '{term}'")
            return

        title = hits[0]["title"]
        url = f"https://www.kolzchut.org.il/he/{urllib.parse.quote(title)}"
        print(f"[droits] Fetching: {url}")

        page = client.get(url, timeout=20)
        page.raise_for_status()
        content = extract_text(page.text)
        if not content:
            print("[droits] Empty content, aborting.")
            return

        print(f"[droits] Content length: {len(content)} chars")
        server_resp = client.post(SERVER_URL, json={"url": url, "content": content}, timeout=30)
        server_resp.raise_for_status()
        print(f"[droits] Sent to server: {server_resp.json()}")


if __name__ == "__main__":
    run()
