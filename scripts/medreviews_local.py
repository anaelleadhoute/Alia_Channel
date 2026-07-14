#!/usr/bin/env python3
"""
MedReviews local scraper — runs on Mac, scrapes FR + RU doctors and sends to server.
Run manually or add to crontab (e.g. monthly).

Setup:
  pip3 install httpx beautifulsoup4
"""

import httpx, json, math
from bs4 import BeautifulSoup

SERVER_URL = "https://alia-channel.com/api/doctors/import"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}

SOURCES = {
    "fr": "https://www.medreviews.co.il/search/all?lang=fr",
    "ru": "https://www.medreviews.co.il/search/all?lang=ru",
}

SPECIALTIES_TRANSLATE = {
    "אורטופדיה": "Orthopédie / Ортопедия",
    "עור ומין": "Dermatologie / Дерматология",
    "ילדים": "Pédiatrie / Педиатрия",
    "גינקולוגיה": "Gynécologie / Гинекология",
    "עיניים": "Ophtalmologie / Офтальмология",
    "רפואה פנימית": "Médecine interne / Терапия",
    "קרדיולוגיה": "Cardiologie / Кардиология",
    "נוירולוגיה": "Neurologie / Неврология",
    "אף אוזן גרון": "ORL / ЛОР",
    "פסיכיאטריה": "Psychiatrie / Психиатрия",
    "אנדוקרינולוגיה": "Endocrinologie / Эндокринология",
    "גסטרואנטרולוגיה": "Gastro-entérologie / Гастроэнтерология",
    "כירורגיה": "Chirurgie / Хирургия",
    "אורולוגיה": "Urologie / Урология",
    "ריאות": "Pneumologie / Пульмонология",
    "אונקולוגיה": "Oncologie / Онкология",
    "רפואה אסתטית": "Médecine esthétique / Эстетическая медицина",
    "שיניים": "Dentiste / Стоматология",
    "פיזיותרפיה": "Kinésithérapie / Физиотерапия",
}


def extract_doctors(html: str, lang: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    doctors = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            for item in data.get("@graph", []):
                if item.get("@type") == "ItemList":
                    for entry in item.get("itemListElement", []):
                        doc = entry.get("item", {})
                        specialties_he = doc.get("knowsAbout", [])
                        doctors.append({
                            "name_he": doc.get("name", ""),
                            "phone": doc.get("telephone", ""),
                            "city_he": doc.get("address", {}).get("addressLocality", ""),
                            "url": doc.get("url", ""),
                            "specialties_he": specialties_he,
                            "specialty_translated": SPECIALTIES_TRANSLATE.get(specialties_he[0], specialties_he[0]) if specialties_he else "",
                            "language": lang,
                            "source": "medreviews",
                        })
        except Exception:
            pass
    return doctors


def scrape_lang(client: httpx.Client, lang: str, base_url: str) -> list[dict]:
    all_doctors = []

    # First page to get total count
    r = client.get(base_url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    total = 0
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            for item in data.get("@graph", []):
                if item.get("@type") == "ItemList":
                    total = item.get("numberOfItems", 0)
        except Exception:
            pass

    all_doctors.extend(extract_doctors(r.text, lang))
    pages = math.ceil(total / 15)
    print(f"[medreviews] {lang}: {total} doctors, {pages} pages")

    for page in range(2, pages + 1):
        url = f"{base_url}&page={page}"
        r = client.get(url, timeout=20)
        r.raise_for_status()
        docs = extract_doctors(r.text, lang)
        all_doctors.extend(docs)
        print(f"[medreviews] {lang} page {page}/{pages}: {len(docs)} doctors")

    return all_doctors


def run():
    all_doctors = []
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for lang, url in SOURCES.items():
            docs = scrape_lang(client, lang, url)
            all_doctors.extend(docs)

    print(f"\n[medreviews] Total: {len(all_doctors)} doctors (FR + RU)")

    # Send to server
    with httpx.Client(headers=HEADERS) as client:
        resp = client.post(SERVER_URL, json={"doctors": all_doctors}, timeout=60)
        resp.raise_for_status()
        print(f"[medreviews] Server response: {resp.json()}")


if __name__ == "__main__":
    run()
