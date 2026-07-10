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
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

SHELANU_URL = "https://shelanu-kids.com/whats-on"
IPO_URL = "https://www.ipo.co.il/serie/%d7%94%d7%a4%d7%99%d7%9c%d7%94%d7%a8%d7%9e%d7%95%d7%a0%d7%99%d7%aa-%d7%9c%d7%99%d7%9c%d7%93%d7%99%d7%9d-%d7%94%d7%a2%d7%95%d7%a0%d7%94-%d7%94-90/"

HE_MONTHS = {
    "ינואר": 1, "פברואר": 2, "מרץ": 3, "אפריל": 4, "מאי": 5, "יוני": 6,
    "יולי": 7, "אוגוסט": 8, "אוג׳": 8, "ספטמבר": 9, "ספט׳": 9,
    "אוקטובר": 10, "אוק׳": 10, "נובמבר": 11, "נוב׳": 11,
    "דצמבר": 12, "דצמ׳": 12,
}

KARAMEL_ACTIVITIES = [
    {"name": "טקטיקס",                              "url": "https://www.karamel.co.il/%D7%98%D7%A7%D7%98%D7%99%D7%A7%D7%A1.asp?cat=715&tag=726"},
    {"name": "החוויה בגבעה - גבעת ברנר",            "url": "https://www.karamel.co.il/%D7%94%D7%97%D7%95%D7%95%D7%94_%D7%91%D7%92%D7%91%D7%A2%D7%94_-_%D7%92%D7%91%D7%A2%D7%AA_%D7%91%D7%A8%D7%A0%D7%A8.asp?cat=715&tag=726"},
    {"name": "פליי פארק רעננה",                     "url": "https://www.karamel.co.il/%D7%A4%D7%9C%D7%99%D7%99_%D7%A4%D7%90%D7%A8%D7%A7_%D7%A8%D7%A2%D7%A0%D7%A0%D7%94.asp?cat=715&tag=726"},
    {"name": "NINJA PRO",                            "url": "https://www.karamel.co.il/NINJA_PRO.asp?cat=715&tag=726"},
    {"name": "אי גיימפ ראשון לציון",                "url": "https://www.karamel.co.il/%D7%90%D7%99%D7%99_%D7%92%D7%90%D7%99%D7%9E%D7%A4_%D7%A8%D7%90%D7%A9%D7%95%D7%9F_%D7%9C%D7%A6%D7%99%D7%95%D7%9F.asp?cat=715&tag=726"},
    {"name": "אי גיימפ פתח תקווה",                  "url": "https://www.karamel.co.il/%D7%90%D7%99%D7%99_%D7%92%D7%90%D7%9E%D7%A4_%D7%A4%D7%AA%D7%97_%D7%AA%D7%A7%D7%95%D7%95%D7%94.asp?cat=715&tag=726"},
    {"name": "גיימפיקס",                            "url": "https://www.karamel.co.il/%D7%92%D7%90%D7%9E%D7%A4%D7%99%D7%A7%D7%A1.asp"},
    {"name": "תות בכפר",                            "url": "https://www.karamel.co.il/%D7%AA%D7%95%D7%AA_%D7%91%D7%9B%D7%A4%D7%A8.asp?cat=715&tag=727"},
    {"name": "לונה פארק",                           "url": "https://www.karamel.co.il/%D7%9C%D7%95%D7%A0%D7%94_%D7%A4%D7%90%D7%A8%D7%A7.asp?cat=715&tag=727"},
    {"name": "מיני ישראל",                          "url": "https://www.karamel.co.il/%D7%9E%D7%99%D7%A0%D7%99_%D7%99%D7%A9%D7%A8%D7%90%D7%9C.asp?cat=715&tag=727"},
    {"name": "קיפצובה",                             "url": "https://www.karamel.co.il/%D7%A7%D7%99%D7%A4%D7%A6%D7%95%D7%91%D7%94.asp?cat=682&tag=718"},
    {"name": "מוזיאון המדע על בלומפילד ירושלים",    "url": "https://www.karamel.co.il/%D7%9E%D7%95%D7%96%D7%99%D7%90%D7%95%D7%9F_%D7%94%D7%9E%D7%93%D7%A2_%D7%A2%D7%A9_%D7%91%D7%9C%D7%95%D7%9E%D7%A4%D7%99%D7%9C%D7%93_%D7%99%D7%A8%D7%95%D7%A9%D7%9C%D7%99%D7%9D.asp?cat=682&tag=718"},
    {"name": "אקווריום ישראל",                      "url": "https://www.karamel.co.il/%D7%90%D7%A7%D7%95%D7%95%D7%A8%D7%99%D7%95%D7%9D_%D7%99%D7%A9%D7%A8%D7%90%D7%9C.asp?cat=682&tag=718"},
    {"name": "מימדיון",                             "url": "https://www.karamel.co.il/%D7%9E%D7%99%D7%9E%D7%93%D7%99%D7%95%D7%9F.asp?cat=722"},
    {"name": "חוות הפסיפלורה",                      "url": "https://www.karamel.co.il/%D7%97%D7%95%D7%95%D7%AA_%D7%94%D7%A4%D7%A1%D7%99%D7%A4%D7%9C%D7%95%D7%A8%D7%94.asp?cat=722"},
    {"name": "נאון מיני גולף",                      "url": "https://www.karamel.co.il/%D7%A0%D7%90%D7%95%D7%9F_%D7%9E%D7%99%D7%A0%D7%99_%D7%92%D7%95%D7%9C%D7%A3.asp?cat=682"},
    {"name": "2 גאמפ כפר סבא",                     "url": "https://www.karamel.co.il/2_%D7%92%D7%90%D7%9E%D7%A4_%D7%9B%D7%A4%D7%A8_%D7%A1%D7%91%D7%90.asp?cat=682"},
    {"name": "מדעטק חיפה",                          "url": "https://www.karamel.co.il/%D7%9E%D7%93%D7%A2%D7%98%D7%A7_%D7%97%D7%99%D7%A4%D7%94.asp?cat=682&tag=719"},
]

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


def scrape_shelanu(page) -> list[dict]:
    print("[shelanu] Loading children's theater shows...")
    try:
        page.goto(SHELANU_URL, wait_until="networkidle", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(2000)

    raw = page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        document.querySelectorAll('a[href*="/repertoire/"]').forEach(infoLink => {
            let container = infoLink.parentElement;
            for (let i = 0; i < 8; i++) {
                if (!container) break;
                const lines = container.innerText.trim().split('\\n').map(l => l.trim()).filter(l => l);
                if (lines.length >= 7) break;
                container = container.parentElement;
            }
            if (!container) return;
            const lines = container.innerText.trim().split('\\n').map(l => l.trim()).filter(l => l);
            if (lines.length < 7) return;
            const key = lines[0] + lines[1] + lines[5] + lines[6];
            if (seen.has(key)) return;
            seen.add(key);
            results.push({ lines, url: infoLink.href });
        });
        return results;
    }""")

    now = datetime.now()
    cutoff = now + timedelta(days=7)
    year = now.year
    events = []

    for item in raw:
        lines = item["lines"]
        if len(lines) < 7:
            continue
        try:
            day = int(lines[0])
            month = HE_MONTHS.get(lines[1])
            if not month:
                continue
            event_date = datetime(year, month, day)
            # Handle year wrap
            if event_date < now - timedelta(days=1):
                event_date = datetime(year + 1, month, day)
            if event_date > cutoff:
                continue
        except Exception:
            continue

        title = lines[5] if len(lines) > 5 else ""
        location = lines[6] if len(lines) > 6 else ""
        city = location.split("|")[0].strip() if "|" in location else location

        events.append({
            "name": title,
            "date": event_date.strftime("%Y-%m-%d") + f" {lines[3]}",
            "url": item["url"],
            "city": city,
            "source": "HaTeatron Shelanu",
        })

    print(f"[shelanu] Found {len(events)} shows in next 14 days")
    for e in events[:5]:
        print(f"  → {e['name']} | {e['date']} | {e['city']}")
    return events


def scrape_ipo_kids(page) -> dict | None:
    print("[ipo] Loading IPO children's concerts...")
    try:
        page.goto(IPO_URL, wait_until="networkidle", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(2000)

    text = page.evaluate("() => document.body.innerText")
    now = datetime.now()

    # Parse "DD.MM.YY" dates from text
    import re
    concerts = []
    # Each concert block: date line like "11.11.26", then title a few lines later
    blocks = re.split(r'קונצרט מס\' \d+', text)
    for block in blocks[1:]:
        date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', block)
        if not date_match:
            continue
        try:
            day, month, year_short = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
            year = 2000 + year_short
            concert_date = datetime(year, month, day)
        except Exception:
            continue
        if concert_date < now:
            continue
        # Title is the first non-empty, non-date line after the date
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        title = ""
        for line in lines:
            if re.match(r'\d{2}\.\d{2}\.\d{2}', line):
                continue
            if re.match(r'יום|תל אביב|17:30', line):
                continue
            if len(line) > 5:
                title = line
                break
        if title:
            concerts.append({"date": concert_date, "title": title})

    if not concerts:
        print("[ipo] No upcoming concerts found")
        return None

    # Pick the soonest upcoming concert
    concerts.sort(key=lambda c: c["date"])
    next_concert = concerts[0]
    date_str = next_concert["date"].strftime("%d.%m.%Y")
    print(f"[ipo] Next concert: {next_concert['title']} | {date_str}")

    return {
        "name": next_concert["title"],
        "date": date_str,
        "url": IPO_URL,
        "city": "Tel Aviv",
        "source": "Philharmonie Israélienne",
        "upcoming_highlight": True,
    }


def scrape_karamel_activity(page) -> dict | None:
    week_num = int(datetime.utcnow().strftime("%W"))
    pick = KARAMEL_ACTIVITIES[week_num % len(KARAMEL_ACTIVITIES)]
    print(f"[karamel] Activity of the week: {pick['name']} | {pick['url']}")

    description = ""
    try:
        page.goto(pick["url"], wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
        description = page.evaluate("""() => {
            const selectors = ['.description', '.content', '.about', 'p'];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    const t = el.innerText.trim();
                    if (t.length > 40) return t.slice(0, 300);
                }
            }
            return '';
        }""")
    except Exception as e:
        print(f"[karamel] Could not scrape description: {e}")

    return {
        "name": pick["name"],
        "date": "",
        "url": pick["url"],
        "city": "Centre d'Israël",
        "source": "Karamel",
        "activity_idea": True,
        "description": description,
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
            shelanu = scrape_shelanu(context.new_page())
            events.extend(shelanu)
            context.close()
        except Exception as e:
            print(f"[shelanu] Failed: {e}")

        try:
            context = browser.new_context(**ctx_opts)
            ipo = scrape_ipo_kids(context.new_page())
            if ipo:
                events.append(ipo)
            context.close()
        except Exception as e:
            print(f"[ipo] Failed: {e}")

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
