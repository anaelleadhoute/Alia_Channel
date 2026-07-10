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
from datetime import datetime
from playwright.sync_api import sync_playwright

KARAMEL_URL = "https://www.karamel.co.il/%D7%90%D7%98%D7%A8%D7%A7%D7%A6%D7%99%D7%95%D7%AA_%D7%9C%D7%99%D7%9C%D7%93%D7%99%D7%9D_%D7%91%D7%9E%D7%A8%D7%9B%D7%96.asp"

SKIP_KARAMEL = {
    "English", "Русский", "יום הולדת", "יום הולדת לבנים", "יום הולדת לבנות",
    "יום הולדת למבוגרים", "רעיונות ליום הולדת", "מקומות", "בת מצווה",
    "יום הולדת ספא", "יום הולדת נסיכות", "יום הולדת כדורגל",
}

SERVER_URL = "https://alia-channel.com/api/scrape/events-kids/manual"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

KIDS_KEYWORDS = [
    "ילדים", "ילדות", "לילדים", "משחקייה", "משפחות", "למשפחות",
    "קרקס", "יוגה להורים", "סדנת התפתח", "פעוטות", "תינוקות",
    "kids", "children", "family",
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
        web_id = _get_field(fields, "WebID")
        list_id = _get_field(fields, "ListID")
        item_id = _get_field(fields, "ListItemID")
        url = f"https://www.tel-aviv.gov.il/Pages/MainItemPage.aspx?WebID={web_id}&ListID={list_id}&ItemID={item_id}" if web_id and list_id and item_id else "https://www.tel-aviv.gov.il/Visitors/Events/Pages/Events.aspx"

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


def scrape_karamel_activity(page) -> dict | None:
    print("[karamel] Loading activity ideas...")
    try:
        page.goto(KARAMEL_URL, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(3000)

    activities = page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        document.querySelectorAll('a[href]').forEach(a => {
            const text = a.innerText.trim();
            const href = a.href;
            if (text.length > 3 && text.length < 40 && href.includes('karamel.co.il') && !seen.has(text)) {
                seen.add(text);
                results.push({ name: text, url: href });
            }
        });
        return results;
    }""")

    # Filter out nav/birthday items
    skip = {
        "English", "Русский", "יום הולדת", "יום הולדת לבנים", "יום הולדת לבנות",
        "יום הולדת למבוגרים", "רעיונות ליום הולדת", "מקומות", "בת מצווה",
        "יום הולדת ספא", "יום הולדת נסיכות", "יום הולדת כדורגל", "הפעלות לימי הולדת",
    }
    activities = [a for a in activities if a["name"] not in skip and "הולדת" not in a["name"]]

    if not activities:
        print("[karamel] No activities found")
        return None

    # Pick deterministically by week number so it rotates weekly
    week_num = int(datetime.utcnow().strftime("%W"))
    pick = activities[week_num % len(activities)]
    print(f"[karamel] Activity of the week: {pick['name']} | {pick['url']}")
    return {
        "name": pick["name"],
        "date": "",
        "url": pick["url"],
        "city": "Centre d'Israël",
        "source": "Karamel",
        "activity_idea": True,
    }


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

        try:
            context = browser.new_context(**ctx_opts)
            activity = scrape_karamel_activity(context.new_page())
            if activity:
                events.append(activity)
            context.close()
        except Exception as e:
            print(f"[karamel] Failed: {e}")

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
