import asyncio
import hashlib
import logging
from datetime import datetime

import feedparser
import httpx

from db.database import get_db
from scrapers.sources import SOURCES

logger = logging.getLogger(__name__)


def _make_guid(source_name: str, url: str) -> str:
    """Stable unique ID for deduplication."""
    return hashlib.sha256(f"{source_name}:{url}".encode()).hexdigest()


def _parse_feed(raw: str, source: dict) -> list[dict]:
    feed = feedparser.parse(raw)
    articles = []

    for entry in feed.entries:
        url = entry.get("link", "")
        if not url:
            continue

        guid = _make_guid(source["name"], url)
        title = entry.get("title", "").strip()
        content = (
            entry.get("summary", "")
            or entry.get("content", [{}])[0].get("value", "")
        ).strip()

        articles.append({
            "guid": guid,
            "source": source["name"],
            "language": source["language"],
            "url": url,
            "title_raw": title,
            "content_raw": content,
        })

    return articles


async def _fetch_feed(client: httpx.AsyncClient, source: dict) -> list[dict]:
    try:
        response = await client.get(source["url"], timeout=15)
        response.raise_for_status()
        return _parse_feed(response.text, source)
    except Exception as e:
        logger.error(f"[scraper] Failed to fetch {source['name']}: {e}")
        return []


async def _save_new_articles(articles: list[dict]) -> int:
    """Insert articles, skip duplicates. Returns count of new articles."""
    saved = 0
    async with await get_db() as db:
        for article in articles:
            try:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO articles
                        (guid, source, language, url, title_raw, content_raw)
                    VALUES
                        (:guid, :source, :language, :url, :title_raw, :content_raw)
                    """,
                    article,
                )
                if db.total_changes > 0:
                    saved += 1
            except Exception as e:
                logger.error(f"[scraper] DB insert error for {article['url']}: {e}")
        await db.commit()
    return saved


async def run_scraper() -> dict:
    """Fetch all RSS sources and store new articles. Returns summary."""
    logger.info("[scraper] Starting RSS scrape...")
    start = datetime.utcnow()

    async with httpx.AsyncClient(
        headers={"User-Agent": "AL.IA Channel Bot/1.0"},
        follow_redirects=True,
    ) as client:
        tasks = [_fetch_feed(client, source) for source in SOURCES]
        results = await asyncio.gather(*tasks)

    all_articles = [article for batch in results for article in batch]
    new_count = await _save_new_articles(all_articles)

    duration = (datetime.utcnow() - start).seconds
    summary = {
        "fetched": len(all_articles),
        "new": new_count,
        "duplicates": len(all_articles) - new_count,
        "duration_seconds": duration,
        "sources": len(SOURCES),
    }
    logger.info(f"[scraper] Done: {summary}")
    return summary
