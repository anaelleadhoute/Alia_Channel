#!/usr/bin/env python3
"""
Batch scraper — fills the content queue with weeks of pre-generated content.

Usage:
    python3 scripts/batch_scrape.py                   # all categories
    python3 scripts/batch_scrape.py --category guide  # one category
    python3 scripts/batch_scrape.py --dry-run         # print what would be scraped

Targets:
    guide       — 50 weeks from Kol Zchut (general terms)
    droits      — 50 weeks from Kol Zchut (eligibility terms)
    prestataire — up to 50 weeks from Midrag (rotates through cities/services)
    kids        — 18 weeks from Karamel (one per link)
    pharma      — 1 item per run from Super-Pharm promotions (AI picks the most
                  relevant one). Must run from a non-Israeli-datacenter IP —
                  blocked (HTTP 492) from the production server.
"""

import argparse
import re
import sys
import time
import urllib.parse
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

SERVER_URL = "https://alia-channel.com/api/queue/add"
MAX_WEEKS = 50


def _load_admin_key() -> str:
    """Read ADMIN_API_KEY from the repo-root .env (required by the backend's auth middleware)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("ADMIN_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


ADMIN_API_KEY = _load_admin_key()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}

# ── Guide terms (Kol Zchut general) ──────────────────────────────────────────
GUIDE_TERMS = [
    "עולים חדשים", "סל קליטה", "תעודת עולה", "משרד הקליטה",
    "דיור", "שכר דירה", "סיוע בשכר דירה", "משכנתא",
    "בריאות", "קופת חולים", "ביטוח בריאות", "תרופות",
    "ילדים", "קצבת ילדים", "גן ילדים", "חופשת לידה", "דמי לידה",
    "עבודה", "דמי אבטלה", "זכויות עובד", "חופשה שנתית",
    "קצבת זקנה", "ביטוח לאומי", "קצבת נכות", "פנסיה",
    "מס הכנסה", "מס רכוש", "החזר מס", "ביטוח לאומי עצמאי",
    "רב-קו", "תחבורה ציבורית", "הנחה בתחבורה",
    "בנק", "חשבון בנק", "כרטיס אשראי",
    "רישיון נהיגה", "ביטוח רכב", "טסט לרכב",
    "מינהל מקרקעי ישראל", "מס שבח", "הסכם שכירות",
    "לשכת גיוס", "שירות מילואים", "פטור מגיוס",
    "אזרחות ישראלית", "דרכון ישראלי", "תעודת זהות",
    "שכר מינימום", "חופשת מחלה", "פיצויי פיטורין",
    "קצבת אבטלה", "ביטוח אבטלה", "הכשרה מקצועית",
][:MAX_WEEKS]

# ── Droits terms (Kol Zchut eligibility) ─────────────────────────────────────
DROITS_TERMS = [
    "זכויות עולים חדשים", "מענק עלייה", "סל קליטה", "הטבות מס לעולים",
    "פטור ממס לעולים", "סיוע לדיור לעולים", "זכאות לדיור", "תעודת עולה",
    "זכאות למשכנתא", "סיוע בשכר דירה",
    "זכאות לקצבת זקנה", "גמלת סיעוד", "קצבת שאירים",
    "זכאות לביטוח בריאות", "זכות לתרופות", "זכות לרופא מומחה",
    "זכאות לקצבת ילדים", "זכאות לדמי לידה", "זכאות לגן ילדים חינם",
    "זכויות עובדים", "זכאות לדמי אבטלה", "פיצויי פיטורין",
    "דמי מחלה", "זכאות לקצבת נכות",
    "הטבות ביטוח לאומי", "זכאות לדיור ציבורי", "זכאות להלוואה",
    "זכאות למלגה", "זכאות לסבסוד גן", "זכאות לנסיעות חינם",
    "זכאות לכסא גלגלים", "זכאות לשיקום", "זכאות לתוספת נכות",
    "עולה מבוגר זכויות", "זכאות לשכר לימוד", "זכאות להכשרה",
    "זכאות לייעוץ משפטי", "זכאות לביטוח חיים", "זכאות לדיור חינם",
    "גמלת ניידות", "קצבת שירותים מיוחדים", "תוספת ותק",
    "זכאות לחשמל מוזל", "זכאות לארנונה מוזלת", "זכאות לפטור ממסים",
    "זכאות לתוכנית טיפולית", "הטבות לנכים", "זכאות לרכב",
    "זכויות בפנסיה", "זכות לחופשה שנתית",
][:MAX_WEEKS]

# ── Karamel kids activities ───────────────────────────────────────────────────
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

# ── Midrag category URLs (user-provided, Tel Aviv / Netanya / Jerusalem / Haifa / Holon-Bat Yam / Ashdod) ──
MIDRAG_URLS = [
    ("https://www.midrag.co.il/Search/Results?serviceId=102&cityId=900", "נתניה"),
    ("https://www.midrag.co.il/Search/Results?ntla=5I21Y06M88D0W7AD48IO76W3H5919H77891402", "תל אביב"),
    ("https://www.midrag.co.il/Search/Results?ntla=QO2FYN67T8YZG6Z56OYE77N80611378GMD6H58", "ירושלים"),
    ("https://www.midrag.co.il/Search/Results?ntla=152NGC63B7N6594078T757O5F8241E4OQ935Y2", "ירושלים"),
    ("https://www.midrag.co.il/Search/Results?ntla=N56LHX9329TP58W560647", "תל אביב"),
    ("https://www.midrag.co.il/Search/Results?ntla=ZN7C2105U243N7IU6LE28", "נתניה"),
    ("https://www.midrag.co.il/Search/Results?ntla=VO7A1N3ZB3F188DR8K5D7GL4F038", "תל אביב"),
    ("https://www.midrag.co.il/Search/Results?ntla=1C24N46V57B9E8KL6DAS75883RN185160G4847", "חיפה"),
    ("https://www.midrag.co.il/Search/Results?serviceId=119&cityId=237", "חולון-בת ים"),
    ("https://www.midrag.co.il/Search/Results?serviceId=206&cityId=121&areaId=5", "אשדוד"),
]

SUPER_PHARM_URL = "https://shop.super-pharm.co.il/promotions"

TARGET_CITIES = {
    "תל אביב", "תל-אביב",
    "נתניה", "נתניה-עיר ימים",
    "ירושלים",
    "חיפה",
    "חולון", "בת ים", "חולון-בת ים",
    "אשדוד",
}


def extract_kolzchut_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()
    main = soup.find("div", class_="mw-parser-output") or soup.find("main") or soup.body
    return main.get_text(separator="\n", strip=True)[:4000] if main else ""


def post_to_queue(category: str, source_url: str, payload: dict, dry_run: bool) -> bool:
    if dry_run:
        print(f"  [DRY RUN] Would add {category}: {source_url or payload.get('name', '')}")
        return True
    try:
        resp = httpx.post(
            SERVER_URL,
            json={"category": category, "source_url": source_url, "raw_payload": payload, "generate_now": True},
            headers={"X-Admin-Key": ADMIN_API_KEY},
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"  ✓ Queued #{result['queue_order']} (id={result['id']})")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def scrape_kolzchut(term: str, client: httpx.Client) -> tuple[str, str] | None:
    try:
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
        content = extract_kolzchut_text(page.text)
        return url, content if content else None
    except Exception as e:
        print(f"  ✗ Kol Zchut error for '{term}': {e}")
        return None


def batch_guide(dry_run: bool):
    print(f"\n=== GUIDE — {len(GUIDE_TERMS)} topics ===")
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for i, term in enumerate(GUIDE_TERMS):
            print(f"[{i+1}/{len(GUIDE_TERMS)}] {term}")
            result = scrape_kolzchut(term, client)
            if result:
                url, content = result
                post_to_queue("guide", url, {"url": url, "content": content}, dry_run)
            else:
                print(f"  ✗ Skipped (no content)")
            time.sleep(2)


def batch_droits(dry_run: bool):
    print(f"\n=== DROITS — {len(DROITS_TERMS)} topics ===")
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for i, term in enumerate(DROITS_TERMS):
            print(f"[{i+1}/{len(DROITS_TERMS)}] {term}")
            result = scrape_kolzchut(term, client)
            if result:
                url, content = result
                post_to_queue("droits", url, {"url": url, "content": content}, dry_run)
            else:
                print(f"  ✗ Skipped (no content)")
            time.sleep(2)


def batch_kids(dry_run: bool):
    print(f"\n=== KIDS — {len(KARAMEL_ACTIVITIES)} activities ===")
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20) as client:
        for i, activity in enumerate(KARAMEL_ACTIVITIES):
            print(f"[{i+1}/{len(KARAMEL_ACTIVITIES)}] {activity['name']}")
            description = ""
            try:
                resp = client.get(activity["url"])
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                meta = soup.find("meta", attrs={"name": "description"})
                if meta and meta.get("content") and len(meta["content"]) > 20:
                    description = meta["content"][:300]
                else:
                    for p in soup.find_all("p"):
                        t = p.get_text(strip=True)
                        if len(t) > 40:
                            description = t[:300]
                            break
            except Exception as e:
                print(f"  ✗ Could not fetch: {e}")

            post_to_queue("kids", activity["url"], {
                "name": activity["name"],
                "description": description,
                "url": activity["url"],
            }, dry_run)
            time.sleep(1.5)


def batch_prestataire(dry_run: bool):
    # Need playwright for Midrag — check if available
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n=== PRESTATAIRE — skipped (playwright not installed) ===")
        print("  Install with: pip install playwright && playwright install chromium")
        return

    import re

    def parse_providers(text: str, title: str):
        cat_match = re.match(r'^(.+?)\s*\|', title)
        category = cat_match.group(1).strip() if cat_match else ""
        city_match = re.search(r'ב([א-ת ]+?)\s*[\|$]', title)
        city = city_match.group(1).strip() if city_match else "תל אביב"
        parts = text.split("דירוג כללי")
        providers = []
        for idx2, part in enumerate(parts[1:], 1):
            prev = parts[idx2 - 1].strip().split('\n')
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
                    "satisfaction": int(satisfaction_match.group(1)) if satisfaction_match else 0,
                })
        return category, city, providers

    weeks_per_category = MAX_WEEKS // len(MIDRAG_URLS) + 1
    print(f"\n=== PRESTATAIRE — {min(MAX_WEEKS, len(MIDRAG_URLS) * weeks_per_category)} items ===")

    count = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=HEADERS["User-Agent"],
            extra_http_headers={"Accept-Language": "he-IL,he;q=0.9"},
        )
        for repeat in range(weeks_per_category):
            for idx, (url, city_hint) in enumerate(MIDRAG_URLS):
                if count >= MAX_WEEKS:
                    break
                print(f"[{count+1}/{MAX_WEEKS}] Midrag category {idx} (round {repeat+1})")
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(2000)
                    text = page.evaluate("() => document.body.innerText")
                    title = page.evaluate("() => document.title")
                    links = page.evaluate("""() => {
                        const anchors = Array.from(document.querySelectorAll('a[href*="/SpCard/Sp/"]'));
                        return [...new Set(anchors.map(a => a.href))];
                    }""")
                    category, city, providers = parse_providers(text, title)
                    # Skip providers not in target cities
                    if city not in TARGET_CITIES:
                        city = city_hint  # fall back to URL hint city
                    if city not in TARGET_CITIES:
                        print(f"  ✗ Skipped — city '{city}' not in target cities")
                        continue
                    if providers:
                        top = providers[0]
                        profile_url = links[0] if links else url
                        payload = {
                            "name": top["name"],
                            "category": category,
                            "city": city,
                            "rating": top["rating"],
                            "reviews": top["reviews"],
                            "satisfaction": top["satisfaction"],
                            "url": profile_url,
                        }
                        post_to_queue("prestataire", profile_url, payload, dry_run)
                        count += 1
                    else:
                        print("  ✗ No providers found")
                except Exception as e:
                    print(f"  ✗ Error: {e}")
                time.sleep(3)
            if count >= MAX_WEEKS:
                break
        browser.close()


def batch_pharma(dry_run: bool):
    """Scrape Super-Pharm's promotions page. Must run from a non-Israeli-datacenter
    IP — the site returns HTTP 492 (WAF block) when hit from the production server."""
    print("\n=== PHARMA — Super-Pharm promotions ===")
    try:
        resp = httpx.get(SUPER_PHARM_URL, headers=HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ Error fetching Super-Pharm: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    seen = set()
    promotions = []
    for it in soup.find_all("a", attrs={"data-promotion-id": True}):
        pid = it.get("data-promotion-id")
        if pid in seen:
            continue
        seen.add(pid)
        title = (it.get("data-promotion-title") or "").strip()
        price_m = re.search(r"[\d.]+", it.get("data-promotion-details") or "")
        price = price_m.group(0) if price_m else None
        valid_m = re.search(r"בתוקף עד ([\d.]+)", it.get_text(" ", strip=True))
        valid_until = valid_m.group(1) if valid_m else None
        if title and price:
            promotions.append({"title": title, "price": price, "valid_until": valid_until})

    if not promotions:
        print("  ✗ No promotions found")
        return

    print(f"  Found {len(promotions)} promotions")
    promotions_text = "\n".join(
        f"- {p['title']} — {p['price']} ₪" + (f" (valable jusqu'au {p['valid_until']})" if p["valid_until"] else "")
        for p in promotions
    )
    post_to_queue("pharma", SUPER_PHARM_URL, {"promotions_text": promotions_text}, dry_run)


def main():
    parser = argparse.ArgumentParser(description="Batch scrape content into the queue")
    parser.add_argument("--category", choices=["guide", "droits", "prestataire", "kids", "pharma"], help="Only scrape this category")
    parser.add_argument("--dry-run", action="store_true", help="Print without posting to server")
    args = parser.parse_args()

    cats = [args.category] if args.category else ["guide", "droits", "kids", "prestataire", "pharma"]

    print(f"Starting batch scrape: {', '.join(cats)}")
    if args.dry_run:
        print("DRY RUN — nothing will be sent to server\n")

    for cat in cats:
        if cat == "guide":
            batch_guide(args.dry_run)
        elif cat == "droits":
            batch_droits(args.dry_run)
        elif cat == "kids":
            batch_kids(args.dry_run)
        elif cat == "prestataire":
            batch_prestataire(args.dry_run)
        elif cat == "pharma":
            batch_pharma(args.dry_run)

    print("\n=== Batch scrape complete ===")


if __name__ == "__main__":
    main()
