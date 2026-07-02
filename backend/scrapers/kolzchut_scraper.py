import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from db.database import get_db

logger = logging.getLogger(__name__)

SEARCH_TERMS = ["עולים חדשים", "דיור", "בריאות", "עבודה"]
SEARCH_URL = "https://www.kolzchut.org.il/w/he/index.php"


def _current_week() -> str:
    return datetime.utcnow().strftime("%Y-W%W")


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()
    main = soup.find("div", class_="mw-parser-output") or soup.find("main") or soup.body
    return main.get_text(separator="\n", strip=True)[:4000] if main else ""


async def run_kolzchut_scraper() -> dict:
    """Search Kol Zchut and scrape the first result page."""
    week = _current_week()

    async with get_db() as db:
        existing = await db.execute(
            "SELECT id FROM tips WHERE week = ?", (week,)
        )
        if await existing.fetchone():
            logger.info(f"[kolzchut] Tip for {week} already exists, skipping.")
            return {"status": "skipped", "week": week}

    # Rotate search term each week
    week_number = int(datetime.utcnow().strftime("%W"))
    term = SEARCH_TERMS[week_number % len(SEARCH_TERMS)]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
        "Referer": "https://www.kolzchut.org.il/",
    }

    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            # Step 1 — search
            search_resp = await client.get(
                SEARCH_URL,
                params={"search": term, "action": "opensearch"},
                timeout=20,
            )
            search_resp.raise_for_status()
            results = search_resp.json()

            # results = [query, [titles], [descriptions], [urls]]
            urls = results[3] if len(results) > 3 else []
            if not urls:
                return {"status": "error", "error": f"No results for '{term}'"}

            target_url = urls[0]

            # Step 2 — fetch the article page
            page_resp = await client.get(target_url, timeout=20)
            page_resp.raise_for_status()
            content = _extract_text(page_resp.text)

        async with get_db() as db:
            cursor = await db.execute(
                "INSERT INTO tips (source_url, week) VALUES (?, ?)",
                (target_url, week),
            )
            await db.commit()
            tip_id = cursor.lastrowid

        logger.info(f"[kolzchut] Scraped '{term}' → {target_url}")
        return {"status": "ok", "week": week, "url": target_url, "tip_id": tip_id, "term": term}

    except Exception as e:
        logger.error(f"[kolzchut] Failed: {e}")
        return {"status": "error", "error": str(e)}
