import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import httpx
from bs4 import BeautifulSoup

from db.database import get_db
from scrapers.sources import SOURCES

logger = logging.getLogger(__name__)


def _make_guid(source_name: str, url: str) -> str:
    """Stable unique ID for deduplication."""
    return hashlib.sha256(f"{source_name}:{url}".encode()).hexdigest()


def _parse_published(entry) -> str | None:
    """Extract ISO publication date from a feedparser entry, or None."""
    if entry.get("published_parsed"):
        try:
            return datetime.utcfromtimestamp(mktime(entry["published_parsed"])).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return None


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
            "published_at": _parse_published(entry),
        })

    return articles


async def _fetch_article_published_at(client: httpx.AsyncClient, url: str) -> str | None:
    """JPost article pages carry a JSON-LD datePublished field even though the tag/
    category listing page doesn't show any date — fetch it so the age cutoff applies."""
    try:
        response = await client.get(url, timeout=10)
        response.raise_for_status()
        match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', response.text)
        if match:
            dt = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.error(f"[scraper] Failed to fetch published date for {url}: {e}")
    return None


async def _parse_html_page(client: httpx.AsyncClient, raw: str, source: dict) -> list[dict]:
    """Server-rendered category/tag page with no RSS feed — pull headline links directly.
    Looks for h3/h4 tags whose child <a> points at an article page, matching the site's
    card layout (works for JPost tag pages like /middle-east/iran-news)."""
    soup = BeautifulSoup(raw, "html.parser")
    candidates = []
    seen = set()

    for heading in soup.find_all(["h3", "h4"]):
        link = heading.find("a", href=True)
        if not link or "/article-" not in link["href"]:
            continue
        href = link["href"]
        if href in seen:
            continue
        seen.add(href)

        url = href if href.startswith("http") else f"{source['base_url']}{href}"
        title = heading.get_text(strip=True)
        if not title:
            continue

        summary = ""
        card = heading.find_parent(["article", "div"])
        if card:
            p = card.find("p")
            if p:
                summary = p.get_text(strip=True)

        candidates.append({"url": url, "title": title, "summary": summary})

    published_dates = await asyncio.gather(
        *[_fetch_article_published_at(client, c["url"]) for c in candidates]
    )

    articles = []
    for candidate, published_at in zip(candidates, published_dates):
        articles.append({
            "guid": _make_guid(source["name"], candidate["url"]),
            "source": source["name"],
            "language": source["language"],
            "url": candidate["url"],
            "title_raw": candidate["title"],
            "content_raw": candidate["summary"],
            "published_at": published_at,
        })

    return articles


async def _fetch_feed(client: httpx.AsyncClient, source: dict) -> list[dict]:
    try:
        response = await client.get(source["url"], timeout=15)
        response.raise_for_status()
        if source.get("type") == "html":
            return await _parse_html_page(client, response.text, source)
        return _parse_feed(response.text, source)
    except Exception as e:
        logger.error(f"[scraper] Failed to fetch {source['name']}: {e}")
        return []


async def _save_new_articles(articles: list[dict]) -> int:
    """Insert articles, skip duplicates and articles older than 2 days. Returns count of new articles."""
    cutoff = datetime.utcnow() - timedelta(days=1)
    saved = 0
    async with get_db() as db:
        for article in articles:
            pub = article.get("published_at")
            if pub:
                try:
                    pub_dt = datetime.strptime(pub, "%Y-%m-%d %H:%M:%S")
                    if pub_dt < cutoff:
                        continue
                except Exception:
                    pass
            try:
                cursor = await db.execute(
                    """
                    INSERT OR IGNORE INTO articles
                        (guid, source, language, url, title_raw, content_raw, published_at)
                    VALUES
                        (:guid, :source, :language, :url, :title_raw, :content_raw, :published_at)
                    """,
                    article,
                )
                if cursor.rowcount > 0:
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
