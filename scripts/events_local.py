#!/usr/bin/env python3
"""
Weekly events scraper — runs on your Mac.
Scrapes Meetup for events in Tel Aviv, Jerusalem, Netanya and sends to server.

Run manually:
  python3 scripts/events_local.py

Force regenerate:
  python3 scripts/events_local.py --force
"""

import httpx
import json
import sys
from playwright.sync_api import sync_playwright

SERVER_URL = "https://alia-channel.com/api/scrape/events/manual"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

CITIES = [
    {"name": "Tel Aviv", "url": "https://www.meetup.com/find/events/?allMeetups=true&userFreeform=Tel+Aviv%2C+Israel&radius=25"},
    {"name": "Jerusalem", "url": "https://www.meetup.com/find/events/?allMeetups=true&userFreeform=Jerusalem%2C+Israel&radius=25"},
    {"name": "Netanya", "url": "https://www.meetup.com/find/events/?allMeetups=true&userFreeform=Netanya%2C+Israel&radius=25"},
]


def scrape_meetup_city(page, city: dict) -> list[dict]:
    print(f"[meetup] Loading {city['name']}...")
    events = []

    try:
        page.goto(city["url"], wait_until="commit", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(5000)
    page.evaluate("window.scrollBy(0, 800)")
    page.wait_for_timeout(2000)

    raw = page.evaluate("""() => {
        const results = [];
        const seen = new Set();

        // Try event cards
        const selectors = [
            '[data-testid="event-card"]',
            '[data-element-name="event-card"]',
            'a[href*="/events/"]',
            '[class*="eventCard"]',
            '[class*="event-card"]',
        ];

        for (const sel of selectors) {
            document.querySelectorAll(sel).forEach(card => {
                const title = card.querySelector('h2, h3, [class*="title"], [class*="name"]');
                const date = card.querySelector('time, [class*="date"], [class*="time"]');
                const link = card.closest('a') || card.querySelector('a');
                const titleText = title ? title.innerText.trim() : card.innerText.split('\\n')[0].trim();
                const dateText = date ? (date.getAttribute('datetime') || date.innerText.trim()) : '';
                const href = link ? link.href : '';

                if (titleText && titleText.length > 3 && !seen.has(titleText)) {
                    seen.add(titleText);
                    results.push({ title: titleText, date: dateText, url: href });
                }
            });
            if (results.length >= 10) break;
        }
        return results.slice(0, 15);
    }""")

    for e in raw:
        if e.get("title"):
            events.append({
                "name": e["title"],
                "date": e.get("date", ""),
                "url": e.get("url", ""),
                "city": city["name"],
            })

    print(f"[meetup] {city['name']}: {len(events)} events found")
    for e in events[:3]:
        print(f"  → {e['name'][:80]}")
    return events


def scrape_secret_telaviv(page) -> list[dict]:
    print("[secret_tlv] Loading https://www.secrettelaviv.com/tickets/...")
    events = []
    try:
        page.goto("https://www.secrettelaviv.com/tickets/", wait_until="domcontentloaded", timeout=25000)
    except Exception:
        pass
    page.wait_for_timeout(10000)
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 600)")
        page.wait_for_timeout(800)

    import re
    html = page.content()

    # Event links look like /tickets/some-event-name/ — not categories or pagination
    matches = re.findall(
        r'href=["\x27](https://www\.secrettelaviv\.com/tickets/[^"\x27#?]+)["\x27][^>]*>([^<]{3,100})',
        html
    )
    seen = set()
    for url, text in matches:
        url = url.rstrip("/")
        text = text.strip()
        if (url not in seen
                and "/categories/" not in url
                and "/page/" not in url
                and url != "https://www.secrettelaviv.com/tickets"
                and text):
            seen.add(url)
            events.append({"name": text, "date": "", "url": url,
                           "city": "Tel Aviv", "source": "Secret Tel Aviv"})

    print(f"[secret_tlv] Found {len(events)} events")
    for e in events[:5]:
        print(f"  → {e['name'][:80]} | {e['url']}")
    return events


def scrape_eventbrite(page) -> list[dict]:
    print("[eventbrite] Loading Israel events...")
    events = []
    try:
        page.goto("https://www.eventbrite.com/d/israel/events/", wait_until="domcontentloaded", timeout=25000)
    except Exception:
        pass
    page.wait_for_timeout(8000)
    for _ in range(4):
        page.evaluate("window.scrollBy(0, 800)")
        page.wait_for_timeout(800)

    raw = page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="eventbrite.com/e/"]').forEach(a => {
            const href = a.href.split('?')[0];
            const card = a.closest('article') || a.closest('[class*="card"]') || a.closest('li') || a;
            const titleEl = card.querySelector('h2, h3, [class*="title"], [class*="name"]') || a;
            const title = titleEl.innerText.trim().split('\\n')[0].trim();
            const dateEl = card.querySelector('time, [class*="date"], [class*="when"], p');
            const date = dateEl ? dateEl.innerText.trim() : '';
            if (title && title.length > 3 && !seen.has(href)) {
                seen.add(href);
                results.push({ title, url: href, date });
            }
        });
        return results.slice(0, 20);
    }""")

    for e in raw:
        if e.get("title"):
            events.append({
                "name": e["title"],
                "date": e.get("date", ""),
                "url": e.get("url", ""),
                "city": "Israel",
                "source": "Eventbrite",
            })

    print(f"[eventbrite] Found {len(events)} events")
    for e in events[:3]:
        print(f"  → {e['name'][:80]}")
    return events


def scrape_telaviv_municipality(page) -> list[dict]:
    print("[tlv_city] Loading Tel Aviv municipality events...")
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
        print(f"[tlv_city] API parse error: {e}")
        return []

    for item in (api_data if isinstance(api_data, list) else [])[:25]:
        fields = item.get("Fields") or []
        title = _get_field(fields, "Title")
        if not title or len(title) < 3:
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

    print(f"[tlv_city] Found {len(events)} events")
    for e in events[:3]:
        print(f"  → {e['name'][:80]}")
    return events


def run():
    debug = "--debug" in sys.argv
    force = "--force" in sys.argv
    print("=== Alia Events Scraper ===")

    all_events = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        ctx_opts = dict(
            user_agent=HEADERS["User-Agent"],
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )

        for city in CITIES:
            try:
                context = browser.new_context(**ctx_opts)
                events = scrape_meetup_city(context.new_page(), city)
                all_events.extend(events)
                context.close()
            except Exception as e:
                print(f"[meetup] {city['name']} failed: {e}")

        try:
            context = browser.new_context(**ctx_opts)
            all_events.extend(scrape_secret_telaviv(context.new_page()))
            context.close()
        except Exception as e:
            print(f"[secret_tlv] Failed: {e}")

        try:
            context = browser.new_context(**ctx_opts)
            all_events.extend(scrape_eventbrite(context.new_page()))
            context.close()
        except Exception as e:
            print(f"[eventbrite] Failed: {e}")

        browser.close()

    # Deduplicate by name across cities
    seen_names = set()
    unique_events = []
    for e in all_events:
        if e["name"] not in seen_names:
            seen_names.add(e["name"])
            unique_events.append(e)
    all_events = unique_events

    print(f"\n[send] Total unique events: {len(all_events)}")
    if not all_events:
        print("[send] No events found, aborting.")
        return

    print("[send] Sending to server...")
    payload = {"events": all_events, "force": force}

    with httpx.Client(timeout=60) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        result = resp.json()

    print(f"[done] {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    run()
