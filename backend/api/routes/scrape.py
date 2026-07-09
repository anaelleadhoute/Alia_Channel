from fastapi import APIRouter
from pydantic import BaseModel
from scrapers.rss_scraper import run_scraper
from scrapers.kolzchut_scraper import run_kolzchut_scraper
from scrapers.telegram_scraper import run_telegram_scraper
from processors.deal_processor import process_pending_deals
from processors.ai_processor import process_pending_articles
from processors.tip_processor import process_pending_tips, process_tip
from processors.digest_processor import generate_daily_digest
from db.database import get_db
from db.cleanup import run_cleanup
from datetime import datetime

router = APIRouter()


async def _is_auto_publish() -> bool:
    async with get_db() as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'auto_publish'")
        row = await cursor.fetchone()
    return row and row["value"] == "true"


async def _auto_publish_item(table: str, id_col: str, item_id: int, audience: str = "both"):
    """Auto-publish a single item if auto_publish is enabled."""
    from api.routes.publish import _send_whatsapp
    import os
    WHAPI_GROUP_FR = os.getenv("WHAPI_GROUP_FR")
    WHAPI_GROUP_RU = os.getenv("WHAPI_GROUP_RU")

    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT content_fr, content_ru, sent_wa_fr, sent_wa_ru FROM {table} WHERE {id_col} = ?",
            (item_id,)
        )
        row = await cursor.fetchone()
    if not row:
        return

    updates = []
    if audience in ("fr", "both") and row["content_fr"] and not row["sent_wa_fr"]:
        await _send_whatsapp(WHAPI_GROUP_FR, row["content_fr"])
        updates.append("sent_wa_fr = 1")
    if audience in ("ru", "both") and row["content_ru"] and not row["sent_wa_ru"]:
        await _send_whatsapp(WHAPI_GROUP_RU, row["content_ru"])
        updates.append("sent_wa_ru = 1")

    if updates:
        async with get_db() as db:
            await db.execute(
                f"UPDATE {table} SET {', '.join(updates)} WHERE {id_col} = ?", (item_id,)
            )
            await db.commit()


@router.post("/news")
async def scrape_news():
    """Fetch all RSS sources and process new articles with AI. Auto-publishes digest if enabled."""
    scrape_result = await run_scraper()
    ai_result = await process_pending_articles()

    auto = await _is_auto_publish()
    digest_result = None
    if auto:
        digest_result = await generate_daily_digest()
        if digest_result.get("digest_id"):
            await _auto_publish_item("digests", "id", digest_result["digest_id"])

    return {"scrape": scrape_result, "ai": ai_result, "digest": digest_result, "auto_published": auto}


@router.post("/tips")
async def scrape_tips():
    """Scrape Kol Zchut and process tip with AI. Auto-publishes if enabled."""
    scrape_result = await run_kolzchut_scraper()
    ai_result = await process_pending_tips()

    auto = await _is_auto_publish()
    if auto and ai_result.get("tip_ids"):
        for tip_id in ai_result["tip_ids"]:
            await _auto_publish_item("tips", "id", tip_id)

    return {"scrape": scrape_result, "ai": ai_result, "auto_published": auto}


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

    auto = await _is_auto_publish()
    if auto and result:
        await _auto_publish_item("tips", "id", tip_id)

    return {"status": "ok" if result else "error", "tip_id": tip_id, "week": week, "auto_published": auto}


@router.post("/deals")
async def scrape_deals():
    """Scrape all 3 supermarkets and generate the weekly combined deal message."""
    from processors.weekly_deal_processor import generate_weekly_deals
    result = await generate_weekly_deals()

    auto = await _is_auto_publish()
    if auto and result.get("weekly_deal_id") and result.get("status") == "generated":
        await _auto_publish_item("weekly_deals", "id", result["weekly_deal_id"])
        result["auto_published"] = True

    return result


class SupermarketPayload(BaseModel):
    shufersal: list[dict] = []
    rami_levy: list[dict] = []
    carrefour: list[dict] = []
    force: bool = False  # regenerate even if this week already exists


@router.post("/supermarkets/manual")
async def scrape_supermarkets_manual(body: SupermarketPayload):
    """Receive pre-scraped supermarket items from local Mac scraper and generate weekly deal."""
    from processors.weekly_deal_processor import generate_weekly_deals
    from datetime import datetime

    week = datetime.utcnow().strftime("%Y-W%W")

    if body.force:
        async with get_db() as db:
            await db.execute("DELETE FROM weekly_deals WHERE week = ?", (week,))
            await db.commit()

    raw_data = {
        "shufersal": body.shufersal,
        "rami_levy": body.rami_levy,
        "carrefour": body.carrefour,
    }

    result = await generate_weekly_deals(raw_data=raw_data)

    auto = await _is_auto_publish()
    if auto and result.get("weekly_deal_id") and result.get("status") == "generated":
        try:
            await _auto_publish_item("weekly_deals", "id", result["weekly_deal_id"])
            result["auto_published"] = True
        except Exception as e:
            result["auto_published"] = False
            result["auto_publish_error"] = str(e)

    return result


@router.post("/cleanup")
async def cleanup():
    """Delete sent articles older than 30 days and rejected older than 7 days."""
    return await run_cleanup()
