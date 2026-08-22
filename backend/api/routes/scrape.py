from fastapi import APIRouter
from scrapers.rss_scraper import run_scraper
from scrapers.telegram_scraper import run_telegram_scraper
from processors.deal_processor import process_pending_deals, pick_best_deal, discard_deals
from processors.ai_processor import process_pending_articles
from processors.digest_processor import generate_daily_digest
from db.database import get_db
from db.cleanup import run_cleanup

router = APIRouter()


@router.post("/news")
async def scrape_news(force: bool = False):
    scrape_result = await run_scraper()
    ai_result = await process_pending_articles()
    digest_result = await generate_daily_digest(force=force)
    return {"scrape": scrape_result, "ai": ai_result, "digest": digest_result}


@router.post("/telegram-deals")
async def scrape_telegram_deals(force: bool = False):
    scrape_result = await run_telegram_scraper(force=force)
    ai_result = await process_pending_deals()
    best_id = None
    if ai_result.get("deal_ids"):
        best_id = await pick_best_deal(ai_result["deal_ids"])
        runner_ups = [d for d in ai_result["deal_ids"] if d != best_id]
        await discard_deals(runner_ups)
    return {"scrape": scrape_result, "ai": ai_result, "best_deal_id": best_id}


@router.post("/reset-ai")
async def reset_ai():
    async with get_db() as db:
        await db.execute("UPDATE articles SET ai_processed_at = NULL")
        await db.commit()
    return {"ok": True}


@router.post("/cleanup")
async def cleanup():
    return await run_cleanup()
