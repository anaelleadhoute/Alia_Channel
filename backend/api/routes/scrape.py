from fastapi import APIRouter
from pydantic import BaseModel
from scrapers.rss_scraper import run_scraper
from scrapers.kolzchut_scraper import run_kolzchut_scraper
from processors.ai_processor import process_pending_articles
from processors.tip_processor import process_pending_tips, process_tip
from db.database import get_db
from db.cleanup import run_cleanup
from datetime import datetime

router = APIRouter()


@router.post("/news")
async def scrape_news():
    """Fetch all RSS sources and process new articles with AI."""
    scrape_result = await run_scraper()
    ai_result = await process_pending_articles()
    return {"scrape": scrape_result, "ai": ai_result}


@router.post("/tips")
async def scrape_tips():
    """Scrape Kol Zchut and process tip with AI."""
    scrape_result = await run_kolzchut_scraper()
    ai_result = await process_pending_tips()
    return {"scrape": scrape_result, "ai": ai_result}


@router.post("/reset-ai")
async def reset_ai():
    """Reset AI processing status so all articles get reprocessed."""
    async with get_db() as db:
        await db.execute("UPDATE articles SET ai_processed_at = NULL")
        await db.commit()
    return {"ok": True}


class ManualTip(BaseModel):
    url: str
    content: str


@router.post("/tips/manual")
async def manual_tip(body: ManualTip):
    """Receive Kol Zchut content from local Mac scraper and process with AI."""
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        existing = await db.execute("SELECT id FROM tips WHERE week = ?", (week,))
        if await existing.fetchone():
            return {"status": "skipped", "reason": "tip already exists for this week"}

        cursor = await db.execute(
            "INSERT INTO tips (source_url, week) VALUES (?, ?)",
            (body.url, week),
        )
        await db.commit()
        tip_id = cursor.lastrowid

    result = await process_tip(tip_id, body.url, body.content)
    return {"status": "ok" if result else "error", "tip_id": tip_id, "week": week}


@router.post("/cleanup")
async def cleanup():
    """Delete sent articles older than 30 days and rejected older than 7 days."""
    return await run_cleanup()
