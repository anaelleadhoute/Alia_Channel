#!/usr/bin/env python3
"""
Prestataire of the week scraper — runs on your Mac.
Picks one category randomly by week, scrapes top provider from Midrag.

Run manually:
  python3 scripts/prestataire_local.py
  python3 scripts/prestataire_local.py --force
"""

import httpx
import json
import re
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright

SERVER_URL = "https://alia-channel.com/api/scrape/prestataire/manual"

MIDRAG_URLS = [
    "https://www.midrag.co.il/Search/Results?ntla=ON2C5Q5QY1S096Y802VK6458Y5Q9282ZLK0440",  # רואי חשבון
    "https://www.midrag.co.il/Search/Results?ntla=5I61Y02M82D0W5AD28IO06W7H5919H87890403",  # סוכן ביטוח
    "https://www.midrag.co.il/Search/Results?ntla=1K1U4H6Z69EEV6379055168876A1J900Q24RM3",  # רופאי שיניים
    "https://www.midrag.co.il/Search/Results?ntla=VO7A1N3ZB3F188DR8K5D7GL4F038",            # חשמלאי
    "https://www.midrag.co.il/Search/Results?ntla=1E53958037M8264464RJ4X800YR4098",          # אינסטלטור
    "https://www.midrag.co.il/Search/Results?ntla=N56LHX9329TP58W560647",                    # הובלות
    "https://www.midrag.co.il/Search/Results?ntla=5I21Y06M88D0W7AD48IO76W3H5919H77891402",  # שיפוצניק
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
}


def parse_providers(text: str, title: str) -> tuple[str, str, list[dict]]:
    cat_match = re.match(r'^(.+?)\s*\|', title)
    category = cat_match.group(1).strip() if cat_match else ""

    city_match = re.search(r'ב([א-ת ]+?)\s*[\|$]', title)
    city = city_match.group(1).strip() if city_match else "תל אביב"

    parts = text.split("דירוג כללי")
    providers = []
    for i, part in enumerate(parts[1:], 1):
        prev = parts[i - 1].strip().split('\n')
        name = ""
        for line in reversed(prev):
            line = line.strip()
            if 2 <= len(line) <= 25 and re.match(r'^[א-ת\s"\'.-]+$', line):
                name = line
                break

        rating_match = re.search(r'^\s*(\d+\.\d+)', part)
        reviews_match = re.search(r'חוות דעת\s*\n?\s*(\d+)', part)
        satisfaction_match = re.search(r'(\d+)%\s*מאוד מרוצים', part)

        if rating_match and name:
            providers.append({
                "name": name,
                "rating": float(rating_match.group(1)),
                "reviews": int(reviews_match.group(1)) if reviews_match else 0,
                "satisfaction": int(satisfaction_match.group(1)) if satisfaction_match else None,
            })

    return category, city, providers


def _get_next_url() -> tuple[str, int]:
    """Ask server for last used category index and return the next one."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get("https://alia-channel.com/api/scrape/prestataire/last-index")
            if resp.status_code == 200:
                last_index = resp.json().get("last_index", -1)
                next_index = (last_index + 1) % len(MIDRAG_URLS)
                return MIDRAG_URLS[next_index], next_index
    except Exception:
        pass
    week_num = int(datetime.now().strftime("%W"))
    idx = week_num % len(MIDRAG_URLS)
    return MIDRAG_URLS[idx], idx


def scrape_prestataire(page) -> dict | None:
    url, idx = _get_next_url()
    print(f"[midrag] Category index {idx} → {url}")

    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(2000)

    text = page.evaluate("() => document.body.innerText")
    title = page.evaluate("() => document.title")
    category, city, providers = parse_providers(text, title)

    if not providers:
        print("[midrag] No providers found")
        return None

    # Pick the top provider (highest rated = first in list)
    top = providers[0]
    print(f"[midrag] Top provider: {top['name']} | {category} | ⭐ {top['rating']} | {top['reviews']} avis")

    return {
        "name": top["name"],
        "category": category,
        "city": city,
        "rating": top["rating"],
        "reviews": top["reviews"],
        "satisfaction": top["satisfaction"],
        "url": url,
        "category_index": idx,
        "all_providers": providers[:5],
    }


def run():
    force = "--force" in sys.argv
    print("=== Alia Prestataire Scraper ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=HEADERS["User-Agent"],
            extra_http_headers={"Accept-Language": "he-IL,he;q=0.9"},
        )
        data = scrape_prestataire(page)
        browser.close()

    if not data:
        print("[send] Nothing scraped, aborting.")
        return

    payload = {"data": data, "force": force}
    print(f"\n[send] Sending to server...")
    with httpx.Client(timeout=60) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        result = resp.json()

    print(f"[done] {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    run()
