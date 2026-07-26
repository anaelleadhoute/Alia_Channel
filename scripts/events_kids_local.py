#!/usr/bin/env python3
"""
Kids attraction scraper — runs on Mac weekly.
Picks one Karamel attraction per week (rotating) and sends to server.

crontab: 0 9 * * 0 python3 /Users/anaelleadhoute/Desktop/Alia_Community/scripts/events_kids_local.py
"""

import sys
import json
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

SERVER_URL = "https://alia-channel.com/api/scrape/events-kids/manual"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
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


def run():
    force = "--force" in sys.argv
    week_num = datetime.utcnow().isocalendar()[1]
    pick = KARAMEL_ACTIVITIES[week_num % len(KARAMEL_ACTIVITIES)]
    print(f"[karamel] Week {week_num} — {pick['name']} | {pick['url']}")

    description = ""
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20) as client:
            resp = client.get(pick["url"])
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
        print(f"[karamel] Description: {description[:80]}...")
    except Exception as e:
        print(f"[karamel] Could not fetch description: {e}")

    activity = {
        "name": pick["name"],
        "url": pick["url"],
        "source": "Karamel",
        "activity_idea": True,
        "description": description,
    }

    payload = {"events": [activity], "force": force}
    with httpx.Client(timeout=30) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        print(f"[done] {resp.json()}")


if __name__ == "__main__":
    run()
