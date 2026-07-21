from fastapi import APIRouter
from pydantic import BaseModel
from scrapers.rss_scraper import run_scraper
from scrapers.kolzchut_scraper import run_kolzchut_scraper
from scrapers.telegram_scraper import run_telegram_scraper
from processors.deal_processor import process_pending_deals, pick_best_deal
from processors.ai_processor import process_pending_articles
from processors.tip_processor import process_pending_tips, process_tip
from processors.digest_processor import generate_daily_digest
from db.database import get_db
from db.cleanup import run_cleanup
from datetime import datetime

router = APIRouter()


async def _is_auto_publish(category: str = "") -> bool:
    async with get_db() as db:
        if category:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?", (f"auto_publish_{category}",)
            )
            row = await cursor.fetchone()
            if row:
                return row["value"] == "true"
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
    """Fetch all RSS sources, generate digest and send immediately."""
    scrape_result = await run_scraper()
    ai_result = await process_pending_articles()
    digest_result = await generate_daily_digest()

    digest_id = digest_result.get("digest_id")
    if not digest_id and digest_result.get("status") == "skipped":
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT id FROM digests WHERE digest_date = ? AND sent_wa_fr = 0 AND sent_wa_ru = 0",
                (today,)
            )
            pending = await cursor.fetchone()
            if pending:
                digest_id = pending["id"]

    if digest_id:
        await _auto_publish_item("digests", "id", digest_id)

    return {"scrape": scrape_result, "ai": ai_result, "digest": digest_result, "auto_published": bool(digest_id)}


@router.post("/telegram-deals")
async def scrape_telegram_deals():
    """Scrape Telegram deal channels and process new deals with AI. Auto-publishes if enabled."""
    scrape_result = await run_telegram_scraper()
    ai_result = await process_pending_deals()

    best_id = None
    if ai_result.get("deal_ids"):
        best_id = await pick_best_deal(ai_result["deal_ids"])
        if best_id:
            await _auto_publish_item("deals", "id", best_id)

    return {"scrape": scrape_result, "ai": ai_result, "best_deal_id": best_id, "auto_published": bool(best_id)}


@router.post("/tips")
async def scrape_tips():
    """Scrape Kol Zchut and store raw payload (no generation)."""
    scrape_result = await run_kolzchut_scraper()
    return {"scrape": scrape_result}


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
    """Store raw Kol Zchut content from Mac scraper and immediately generate FR+RU."""
    import json
    week = datetime.utcnow().strftime("%Y-W%U")
    async with get_db() as db:
        existing = await db.execute("SELECT id FROM tips WHERE week = ?", (week,))
        row = await existing.fetchone()
        if row:
            await db.execute(
                "UPDATE tips SET source_url = ?, raw_payload = ?, ai_processed_at = NULL WHERE week = ?",
                (body.url, json.dumps({"url": body.url, "content": body.content}), week),
            )
        else:
            await db.execute(
                "INSERT INTO tips (source_url, week, raw_payload) VALUES (?, ?, ?)",
                (body.url, week, json.dumps({"url": body.url, "content": body.content})),
            )
        await db.commit()

    # Immediately generate FR+RU
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM tips WHERE week = ? AND ai_processed_at IS NULL", (week,)
        )
        tip_row = await cursor.fetchone()
    if tip_row:
        await process_tip(tip_row["id"], body.url, body.content)

    return {"status": "generated", "week": week}


@router.post("/tips/generate")
async def generate_tip(force: bool = False):
    """Generate FR+RU tip from stored raw payload and auto-publish."""
    week = datetime.utcnow().strftime("%Y-W%U")
    import json
    async with get_db() as db:
        if force:
            await db.execute(
                "UPDATE tips SET ai_processed_at=NULL, sent_wa_fr=0, sent_wa_ru=0 WHERE week=?", (week,)
            )
            await db.commit()
        cursor = await db.execute(
            "SELECT id, source_url, raw_payload FROM tips WHERE week = ? AND ai_processed_at IS NULL",
            (week,)
        )
        row = await cursor.fetchone()
    if not row:
        return {"status": "skipped", "reason": "no stored tip for this week or already generated"}

    payload = json.loads(row["raw_payload"] or "{}")
    result = await process_tip(row["id"], payload.get("url", row["source_url"]), payload.get("content", ""))
    return {"status": "ok" if result else "error", "tip_id": row["id"], "week": week}


@router.post("/rights/manual")
async def manual_rights(body: ManualTip):
    """Store raw Kol Zchut rights content from Mac scraper and immediately generate FR+RU."""
    import json
    from processors.rights_processor import generate_weekly_rights
    week = datetime.utcnow().strftime("%Y-W%U")
    async with get_db() as db:
        existing = await db.execute("SELECT id FROM weekly_rights WHERE week = ?", (week,))
        row = await existing.fetchone()
        if row:
            await db.execute(
                "UPDATE weekly_rights SET source_url=?, raw_payload=?, content_fr=NULL, content_ru=NULL WHERE week=?",
                (body.url, json.dumps({"url": body.url, "content": body.content}), week),
            )
        else:
            await db.execute(
                "INSERT INTO weekly_rights (week, source_url, raw_payload) VALUES (?,?,?)",
                (week, body.url, json.dumps({"url": body.url, "content": body.content})),
            )
        await db.commit()

    result = await generate_weekly_rights()
    return {"status": "generated", "week": week, "result": result}


@router.post("/rights/generate")
async def generate_rights(force: bool = False):
    """Generate FR+RU rights content from stored raw payload and auto-publish."""
    from processors.rights_processor import generate_weekly_rights
    return await generate_weekly_rights(force=force)



class PrestatairePayload(BaseModel):
    data: dict
    force: bool = False


@router.get("/prestataire/last-index")
async def get_prestataire_last_index():
    """Return the category_index stored in the most recent weekly_prestataire entry."""
    import json
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT raw_payload FROM weekly_prestataire ORDER BY created_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
    if row and row[0]:
        data = json.loads(row[0])
        return {"last_index": data.get("category_index", -1)}
    return {"last_index": -1}


@router.post("/prestataire/manual")
async def scrape_prestataire_manual(body: PrestatairePayload):
    """Store raw prestataire data from Mac scraper and immediately generate FR+RU."""
    import json
    from processors.prestataire_processor import generate_weekly_prestataire
    week = datetime.utcnow().strftime("%Y-W%U")
    async with get_db() as db:
        if body.force:
            await db.execute("DELETE FROM weekly_prestataire WHERE week = ?", (week,))
        await db.execute(
            "INSERT OR REPLACE INTO weekly_prestataire (week, data_json, raw_payload) VALUES (?, ?, ?)",
            (week, json.dumps(body.data, ensure_ascii=False), json.dumps(body.data, ensure_ascii=False)),
        )
        await db.commit()

    result = await generate_weekly_prestataire(force=body.force, data=body.data)
    return {"status": "generated", "week": week, "result": result}


@router.post("/prestataire/generate")
async def generate_prestataire(force: bool = False):
    """Generate FR+RU content from stored raw payload and auto-publish."""
    from processors.prestataire_processor import generate_weekly_prestataire
    return await generate_weekly_prestataire(force=force)


class EventsPayload(BaseModel):
    events: list[dict] = []
    force: bool = False


@router.post("/events-kids/manual")
async def scrape_events_kids_manual(body: EventsPayload):
    """Store raw kids events from Mac scraper and immediately generate FR+RU."""
    import json
    from processors.events_kids_processor import generate_weekly_kids_events
    week = datetime.utcnow().strftime("%Y-W%U")
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO weekly_events_kids (week, raw_payload) VALUES (?, ?)",
            (week, json.dumps(body.events, ensure_ascii=False)),
        )
        await db.commit()

    result = await generate_weekly_kids_events(force=body.force, raw_events=body.events)
    return {"status": "generated", "week": week, "events_count": len(body.events), "result": result}


@router.post("/events-kids/generate")
async def generate_events_kids(force: bool = False):
    """Generate FR+RU kids events content from stored raw payload and auto-publish."""
    from processors.events_kids_processor import generate_weekly_kids_events
    return await generate_weekly_kids_events(force=force)


@router.post("/cleanup")
async def cleanup():
    """Delete sent articles older than 30 days and rejected older than 7 days."""
    return await run_cleanup()
