#!/usr/bin/env python3
"""
Kids & family events scraper — runs on your Mac.
Scrapes Tel Aviv municipality for kids/family events and sends to server.

Run manually:
  python3 scripts/events_kids_local.py

Force regenerate:
  python3 scripts/events_kids_local.py --force
"""

import httpx
import json
import sys
from playwright.sync_api import sync_playwright

SERVER_URL = "https://alia-channel.com/api/scrape/events-kids/manual"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

KIDS_KEYWORDS = [
    "ילד", "ילדים", "ילדות", "משפח", "נוער", "בובה", "סיפור", "משחקייה",
    "קרקס", "יוגה להורים", "הצגה", "סדנת התפתח", "פעוט", "תינוק",
    "kids", "children", "family", "enfant",
]


def _is_kids_event(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in KIDS_KEYWORDS)


def scrape_telaviv_kids(page) -> list[dict]:
    print("[tlv_kids] Loading Tel Aviv municipality events...")
    events = []

    def _get_field(fields, name):
        for f in fields:
            if f.get("InternalName") == name:
                return f.get("Value") or ""
        return ""

    with page.expect_response(lambda r: "GetEvBenList" in r.url, timeout=30000) as resp_info:
        try:
            page.goto(
                "https://www.tel-aviv.gov.il/Visitors/Events/Pages/Events.aspx?AudID=1,2,7&DO=false&Free=false&Morning=false&Noon=false&Evening=false&Tickets=false&DtRng=-1",
                wait_until="domcontentloaded", timeout=25000
            )
        except Exception:
            pass

    try:
        api_data = resp_info.value.json()
    except Exception as e:
        print(f"[tlv_kids] API parse error: {e}")
        return []

    for item in (api_data if isinstance(api_data, list) else []):
        fields = item.get("Fields") or []
        title = _get_field(fields, "Title")
        if not title or len(title) < 3:
            continue
        if not _is_kids_event(title):
            continue
        date = _get_field(fields, "TlvStartDate")
        interests = _get_field(fields, "TlvFieldsOfInterests").lower()
        if "מוסיקה" in interests:
            url = "https://www.tel-aviv.gov.il/Visitors/Events/Pages/Music.aspx?IntsID=4"
        elif "תיאטרון" in interests or "מופעים" in interests:
            url = "https://www.tel-aviv.gov.il/Visitors/Events/Pages/Theater.aspx?IntsID=3"
        elif "פעילות" in interests or "outdoor" in interests:
            url = "https://www.tel-aviv.gov.il/Visitors/Events/Pages/OutdoorActivities.aspx?IntsID=1"
        else:
            url = "https://www.tel-aviv.gov.il/Visitors/Events/Pages/Events.aspx"

        events.append({
            "name": title,
            "date": date,
            "url": url,
            "city": "Tel Aviv",
            "source": "Mairie de Tel Aviv",
        })

    print(f"[tlv_kids] Found {len(events)} kids events")
    for e in events[:5]:
        print(f"  → {e['name'][:80]}")
    return events


def run():
    force = "--force" in sys.argv
    debug = "--debug" in sys.argv
    print("=== Alia Kids Events Scraper ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        ctx_opts = dict(
            user_agent=HEADERS["User-Agent"],
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        try:
            context = browser.new_context(**ctx_opts)
            events = scrape_telaviv_kids(context.new_page())
            context.close()
        except Exception as e:
            print(f"[tlv_kids] Failed: {e}")
            events = []
        browser.close()

    if not events:
        print("[send] No kids events found, aborting.")
        return

    print(f"\n[send] Sending {len(events)} kids events to server...")
    payload = {"events": events, "force": force}

    with httpx.Client(timeout=60) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        result = resp.json()

    print(f"[done] {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    run()
