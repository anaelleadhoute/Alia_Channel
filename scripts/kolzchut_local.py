#!/usr/bin/env python3
"""
Guide Alia local scraper — runs on your Mac every Tuesday.
Rotates between Kol Zchut, Bituah Leumi, and Gov.il sources.
"""

import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import urllib.parse

SERVER_URL = "https://alia-channel.com/api/scrape/tips/manual"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}

# Rotate sources by week
SOURCES = [
    {
        "name": "kolzchut",
        "search_terms": ["עולים חדשים", "ביטוח לאומי", "דיור", "עבודה", "בריאות", "ילדים"],
    },
    {
        "name": "btl",
        "urls": [
            "https://www.btl.gov.il/benefits/Immigrants/Pages/default.aspx",
            "https://www.btl.gov.il/benefits/Maternity/Pages/default.aspx",
            "https://www.btl.gov.il/benefits/Child/Pages/default.aspx",
            "https://www.btl.gov.il/benefits/unemployment/Pages/default.aspx",
        ],
    },
    {
        "name": "gov",
        "urls": [
            "https://www.gov.il/he/departments/topics/aliya",
            "https://www.gov.il/he/departments/topics/health",
        ],
    },
]


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()
    main = (
        soup.find("div", class_="mw-parser-output")
        or soup.find("main")
        or soup.find("div", class_="content")
        or soup.body
    )
    return main.get_text(separator="\n", strip=True)[:4000] if main else ""


def scrape_kolzchut(client: httpx.Client, week_number: int) -> tuple[str, str] | None:
    terms = SOURCES[0]["search_terms"]
    term = terms[week_number % len(terms)]
    print(f"[guide] Kol Zchut — searching: {term}")

    resp = client.get(
        "https://www.kolzchut.org.il/w/api.php",
        params={"action": "query", "list": "search", "srsearch": term, "format": "json", "srlimit": 1},
        timeout=20,
    )
    resp.raise_for_status()
    hits = resp.json().get("query", {}).get("search", [])
    if not hits:
        return None

    title = hits[0]["title"]
    url = f"https://www.kolzchut.org.il/he/{urllib.parse.quote(title)}"
    page = client.get(url, timeout=20)
    page.raise_for_status()
    content = extract_text(page.text)
    return (url, content) if content else None


def scrape_url(client: httpx.Client, url: str) -> tuple[str, str] | None:
    print(f"[guide] Fetching: {url}")
    try:
        resp = client.get(url, timeout=20)
        resp.raise_for_status()
        content = extract_text(resp.text)
        return (url, content) if content else None
    except Exception as e:
        print(f"[guide] Error fetching {url}: {e}")
        return None


def run():
    week_number = int(datetime.now().strftime("%W"))
    source_idx = week_number % len(SOURCES)
    source = SOURCES[source_idx]

    print(f"[guide] Week {week_number} — source: {source['name']}")

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        result = None

        if source["name"] == "kolzchut":
            result = scrape_kolzchut(client, week_number)
        else:
            for url in source["urls"]:
                result = scrape_url(client, url)
                if result:
                    break

        if not result:
            # Fallback to Kol Zchut
            print("[guide] Falling back to Kol Zchut")
            result = scrape_kolzchut(client, week_number)

        if not result:
            print("[guide] No content found, aborting.")
            return

        url, content = result
        server_resp = client.post(
            SERVER_URL,
            json={"url": url, "content": content},
            timeout=30,
        )
        server_resp.raise_for_status()
        print(f"[guide] Sent to server: {server_resp.json()}")


if __name__ == "__main__":
    run()
