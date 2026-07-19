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
        digest_id = digest_result.get("digest_id")

        # If digest already existed (skipped), check for unsent pending digest today
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

    return {"scrape": scrape_result, "ai": ai_result, "digest": digest_result, "auto_published": auto}


@router.post("/telegram-deals")
async def scrape_telegram_deals():
    """Scrape Telegram deal channels and process new deals with AI. Auto-publishes if enabled."""
    scrape_result = await run_telegram_scraper()
    ai_result = await process_pending_deals()

    auto = await _is_auto_publish()
    best_id = None
    if ai_result.get("deal_ids"):
        best_id = await pick_best_deal(ai_result["deal_ids"])
        if auto and best_id:
            await _auto_publish_item("deals", "id", best_id)

    return {"scrape": scrape_result, "ai": ai_result, "best_deal_id": best_id, "auto_published": best_id}


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
    """Store raw Kol Zchut content from Mac scraper (no generation)."""
    import json
    week = datetime.utcnow().strftime("%Y-W%W")
    async with get_db() as db:
        existing = await db.execute("SELECT id FROM tips WHERE week = ?", (week,))
        row = await existing.fetchone()
        if row:
            await db.execute(
                "UPDATE tips SET source_url = ?, raw_payload = ? WHERE week = ?",
                (body.url, json.dumps({"url": body.url, "content": body.content}), week),
            )
        else:
            await db.execute(
                "INSERT INTO tips (source_url, week, raw_payload) VALUES (?, ?, ?)",
                (body.url, week, json.dumps({"url": body.url, "content": body.content})),
            )
        await db.commit()
    return {"status": "stored", "week": week}


@router.post("/tips/generate")
async def generate_tip():
    """Generate FR+RU tip from stored raw payload and auto-publish."""
    week = datetime.utcnow().strftime("%Y-W%W")
    import json
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, source_url, raw_payload FROM tips WHERE week = ? AND ai_processed_at IS NULL",
            (week,)
        )
        row = await cursor.fetchone()
    if not row:
        return {"status": "skipped", "reason": "no stored tip for this week or already generated"}

    payload = json.loads(row["raw_payload"] or "{}")
    result = await process_tip(row["id"], payload.get("url", row["source_url"]), payload.get("content", ""))

    auto = await _is_auto_publish()
    if auto and result:
        await _auto_publish_item("tips", "id", row["id"])

    return {"status": "ok" if result else "error", "tip_id": row["id"], "week": week, "auto_published": auto}


@router.post("/rights/manual")
async def manual_rights(body: ManualTip):
    """Store raw Kol Zchut rights content from Mac scraper (no generation)."""
    import json
    week = datetime.utcnow().strftime("%Y-W%W")
    async with get_db() as db:
        existing = await db.execute("SELECT id FROM weekly_rights WHERE week = ?", (week,))
        row = await existing.fetchone()
        if row:
            await db.execute(
                "UPDATE weekly_rights SET source_url=?, raw_payload=? WHERE week=?",
                (body.url, json.dumps({"url": body.url, "content": body.content}), week),
            )
        else:
            await db.execute(
                "INSERT INTO weekly_rights (week, source_url, raw_payload) VALUES (?,?,?)",
                (week, body.url, json.dumps({"url": body.url, "content": body.content})),
            )
        await db.commit()
    return {"status": "stored", "week": week}


@router.post("/rights/generate")
async def generate_rights():
    """Generate FR+RU rights content from stored raw payload and auto-publish."""
    from processors.rights_processor import generate_weekly_rights
    result = await generate_weekly_rights()
    auto = await _is_auto_publish()
    if auto and result.get("weekly_rights_id") and result.get("status") == "generated":
        try:
            await _auto_publish_item("weekly_rights", "id", result["weekly_rights_id"])
            result["auto_published"] = True
        except Exception as e:
            result["auto_publish_error"] = str(e)
    return result



class PrestatairePayload(BaseModel):
    data: dict
    force: bool = False


@router.post("/prestataire/manual")
async def scrape_prestataire_manual(body: PrestatairePayload):
    """Store raw prestataire data from Mac scraper (no generation)."""
    import json
    week = datetime.utcnow().strftime("%Y-W%W")
    async with get_db() as db:
        if body.force:
            await db.execute("DELETE FROM weekly_prestataire WHERE week = ?", (week,))
        await db.execute(
            "INSERT OR REPLACE INTO weekly_prestataire (week, data_json, raw_payload) VALUES (?, ?, ?)",
            (week, json.dumps(body.data, ensure_ascii=False), json.dumps(body.data, ensure_ascii=False)),
        )
        await db.commit()
    return {"status": "stored", "week": week}


@router.post("/prestataire/generate")
async def generate_prestataire():
    """Generate FR+RU content from stored raw payload and auto-publish."""
    from processors.prestataire_processor import generate_weekly_prestataire
    result = await generate_weekly_prestataire()
    auto = await _is_auto_publish()
    if auto and result.get("prestataire_id") and result.get("status") == "generated":
        try:
            await _auto_publish_item("weekly_prestataire", "id", result["prestataire_id"])
            result["auto_published"] = True
        except Exception as e:
            result["auto_published"] = False
            result["auto_publish_error"] = str(e)
    return result


class EventsPayload(BaseModel):
    events: list[dict] = []
    force: bool = False


@router.post("/events-kids/manual")
async def scrape_events_kids_manual(body: EventsPayload):
    """Store raw kids events from Mac scraper (no generation)."""
    import json
    week = datetime.utcnow().strftime("%Y-W%W")
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO weekly_events_kids (week, raw_payload) VALUES (?, ?)",
            (week, json.dumps(body.events, ensure_ascii=False)),
        )
        await db.commit()
    return {"status": "stored", "week": week, "events_count": len(body.events)}


@router.post("/events-kids/generate")
async def generate_events_kids():
    """Generate FR+RU kids events content from stored raw payload and auto-publish."""
    from processors.events_kids_processor import generate_weekly_kids_events
    result = await generate_weekly_kids_events()
    auto = await _is_auto_publish()
    if auto and result.get("weekly_event_kids_id") and result.get("status") == "generated":
        try:
            await _auto_publish_item("weekly_events_kids", "id", result["weekly_event_kids_id"])
            result["auto_published"] = True
        except Exception as e:
            result["auto_published"] = False
            result["auto_publish_error"] = str(e)
    return result


@router.post("/cleanup")
async def cleanup():
    """Delete sent articles older than 30 days and rejected older than 7 days."""
    return await run_cleanup()
