import logging
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from db.database import get_db
from scrapers.sources import KOL_ZCHUT_BASE_URL, KOL_ZCHUT_PAGES

logger = logging.getLogger(__name__)


def _current_week() -> str:
    return datetime.utcnow().strftime("%Y-W%W")


def _scrape_page(html: str, url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Remove nav, header, footer, sidebars
    for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()

    main = soup.find("div", class_="mw-parser-output") or soup.find("main") or soup.body
    return main.get_text(separator="\n", strip=True)[:4000] if main else ""


async def run_kolzchut_scraper() -> dict:
    """Scrape one Kol Zchut page per week and store raw content."""
    week = _current_week()

    async with get_db() as db:
        existing = await db.execute(
            "SELECT id FROM tips WHERE week = ?", (week,)
        )
        if await existing.fetchone():
            logger.info(f"[kolzchut] Tip for {week} already exists, skipping.")
            return {"status": "skipped", "week": week}

    # Rotate page each week
    week_number = int(datetime.utcnow().strftime("%W"))
    page_path = KOL_ZCHUT_PAGES[week_number % len(KOL_ZCHUT_PAGES)]
    url = KOL_ZCHUT_BASE_URL + page_path

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "AL.IA Channel Bot/1.0"},
            follow_redirects=True,
        ) as client:
            response = await client.get(url, timeout=20)
            response.raise_for_status()

        content = _scrape_page(response.text, url)

        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO tips (source_url, week, content_fr, content_ru)
                VALUES (?, ?, NULL, NULL)
                """,
                (url, week),
            )
            await db.commit()

        logger.info(f"[kolzchut] Scraped {url} for week {week}")
        return {"status": "ok", "week": week, "url": url, "content_length": len(content)}

    except Exception as e:
        logger.error(f"[kolzchut] Failed to scrape {url}: {e}")
        return {"status": "error", "error": str(e)}
