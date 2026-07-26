import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from db.database import get_db
from datetime import datetime, date

router = APIRouter()

WHAPI_TOKEN = os.getenv("WHAPI_TOKEN")
WHAPI_GROUP_FR = os.getenv("WHAPI_GROUP_FR")
WHAPI_GROUP_RU = os.getenv("WHAPI_GROUP_RU")
WHAPI_URL = "https://gate.whapi.cloud/messages/text"
WHAPI_IMAGE_URL = "https://gate.whapi.cloud/messages/image"
ALIA_AVATAR_URL = "https://alia-channel.com/alia_final_avatar.png"

# French avatars
ALIA_NEWS_FR_URL        = "https://alia-channel.com/alia_actualites_fr.png"
ALIA_DEALS_FR_URL       = "https://alia-channel.com/alia_bon_plans_fr.png"
ALIA_RIGHTS_FR_URL      = "https://alia-channel.com/alia_droits_fr.png"
ALIA_KIDS_FR_URL        = "https://alia-channel.com/alia_enfants_fr.png"
ALIA_GUIDE_FR_URL       = "https://alia-channel.com/alia_guide_fr.png"
ALIA_DOCTORS_FR_URL     = "https://alia-channel.com/alia_medecins_fr.png"
ALIA_PRESTATAIRE_FR_URL = "https://alia-channel.com/alia_prestataires_fr.png"
ALIA_FAQ_FR_URL         = "https://alia-channel.com/alia_questions_fr.png"

# Russian avatars
ALIA_NEWS_RU_URL        = "https://alia-channel.com/ALIA_ACTUALITE_RUSSIAN.png"
ALIA_DEALS_RU_URL       = "https://alia-channel.com/ALIA_BON_PLANS_RUSSIAN.png"
ALIA_RIGHTS_RU_URL      = "https://alia-channel.com/alia_droits_russian.png"
ALIA_KIDS_RU_URL        = "https://alia-channel.com/ALIA_ENFANTS_RUSSIAN.png"
ALIA_GUIDE_RU_URL       = "https://alia-channel.com/ALIA_GUIDE_RUSSIAN.png"
ALIA_DOCTORS_RU_URL     = "https://alia-channel.com/ALIA_MEDECINS_RUSSIAN.png"
ALIA_PRESTATAIRE_RU_URL = "https://alia-channel.com/ALIA_PRESTATAIRES_RUSSIAN.png"
ALIA_FAQ_RU_URL         = "https://alia-channel.com/ALIA_QUESTIONS_RUSSIAN.png"

TABLE_IMAGE_MAP_FR = {
    "digests":            ALIA_NEWS_FR_URL,
    "tips":               ALIA_GUIDE_FR_URL,
    "deals":              ALIA_DEALS_FR_URL,
    "weekly_doctor":      ALIA_DOCTORS_FR_URL,
    "weekly_rights":      ALIA_RIGHTS_FR_URL,
    "weekly_prestataire": ALIA_PRESTATAIRE_FR_URL,
    "weekly_events_kids": ALIA_KIDS_FR_URL,
    "faqs":               ALIA_FAQ_FR_URL,
}

TABLE_IMAGE_MAP_RU = {
    "digests":            ALIA_NEWS_RU_URL,
    "tips":               ALIA_GUIDE_RU_URL,
    "deals":              ALIA_DEALS_RU_URL,
    "weekly_doctor":      ALIA_DOCTORS_RU_URL,
    "weekly_rights":      ALIA_RIGHTS_RU_URL,
    "weekly_prestataire": ALIA_PRESTATAIRE_RU_URL,
    "weekly_events_kids": ALIA_KIDS_RU_URL,
    "faqs":               ALIA_FAQ_RU_URL,
}

# Keep backward-compat alias (used by _auto_publish_item)
TABLE_IMAGE_MAP = TABLE_IMAGE_MAP_RU


async def _send_whatsapp(group_id: str, text: str, image_url: str = ALIA_AVATAR_URL) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{WHAPI_IMAGE_URL}?token={WHAPI_TOKEN}",
            json={"to": group_id, "media": image_url, "caption": text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


class ManualMessage(BaseModel):
    text_fr: str
    text_ru: Optional[str] = None
    audience: Literal["fr", "ru", "both"] = "both"
    scheduled_at: Optional[str] = None  # ISO datetime string in IL time


class TranslateRequest(BaseModel):
    text: str


@router.post("/translate")
async def translate_to_russian(body: TranslateRequest):
    """Translate a French text to Russian using Claude."""
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": f"Traduis ce message WhatsApp du français vers le russe. Garde exactement le même format, les emojis, et les liens. Réponds uniquement avec la traduction, sans explication.\n\n{body.text}"}],
    )
    return {"text_ru": response.content[0].text.strip()}


@router.post("/manual")
async def publish_manual(msg: ManualMessage):
    """Send a custom text message to FR and/or RU WhatsApp groups, optionally scheduled."""
    from datetime import datetime
    import pytz

    if msg.scheduled_at:
        il_tz = pytz.timezone("Asia/Jerusalem")
        send_time = datetime.fromisoformat(msg.scheduled_at).replace(tzinfo=il_tz)
        now = datetime.now(il_tz)
        delay = (send_time - now).total_seconds()
        if delay > 0:
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO scheduled_manual (text_fr, text_ru, audience, send_at, sent) VALUES (?,?,?,?,0)",
                    (msg.text_fr, msg.text_ru, msg.audience, send_time.isoformat())
                )
                await db.commit()
            return {"ok": True, "scheduled": True, "send_at": send_time.isoformat()}

    results = {}
    if msg.audience in ("fr", "both") and msg.text_fr:
        await _send_whatsapp(WHAPI_GROUP_FR, msg.text_fr)
        results["fr"] = "sent"
    if msg.audience in ("ru", "both") and msg.text_ru:
        await _send_whatsapp(WHAPI_GROUP_RU, msg.text_ru)
        results["ru"] = "sent"
    return {"ok": True, "sent": results}


@router.post("/article/{article_id}")
async def publish_article(article_id: int):
    """Publish an approved article to WhatsApp FR and/or RU groups."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        )
        article = await cursor.fetchone()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    article = dict(article)
    results = {}

    if article.get("cta_fr") and not article.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, article["cta_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE articles SET sent_wa_fr = 1 WHERE id = ?", (article_id,)
            )
            await db.commit()

    if article.get("cta_ru") and not article.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, article["cta_ru"])
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE articles SET sent_wa_ru = 1 WHERE id = ?", (article_id,)
            )
            await db.commit()

    return {"ok": True, "article_id": article_id, "sent": results}


@router.post("/digest/latest")
async def publish_latest_digest():
    """Publish the most recent digest to WhatsApp FR and RU groups."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM digests ORDER BY generated_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No digest found")
    return await publish_digest(row["id"])


@router.post("/digest/{digest_id}")
async def publish_digest(digest_id: int):
    """Publish a daily news digest to WhatsApp FR and RU groups."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM digests WHERE id = ?", (digest_id,)
        )
        digest = await cursor.fetchone()

    if not digest:
        raise HTTPException(status_code=404, detail="Digest not found")

    digest = dict(digest)
    results = {}

    if digest.get("content_fr") and not digest.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, digest["content_fr"], ALIA_NEWS_FR_URL)
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE digests SET sent_wa_fr = 1 WHERE id = ?", (digest_id,)
            )
            await db.commit()

    if digest.get("content_ru") and not digest.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, digest["content_ru"], ALIA_NEWS_RU_URL)
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE digests SET sent_wa_ru = 1 WHERE id = ?", (digest_id,)
            )
            await db.commit()

    return {"ok": True, "digest_id": digest_id, "sent": results}


@router.post("/tip/{tip_id}")
async def publish_tip(tip_id: int):
    """Publish a Kol Zchut tip to WhatsApp FR and RU groups."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM tips WHERE id = ?", (tip_id,)
        )
        tip = await cursor.fetchone()

    if not tip:
        raise HTTPException(status_code=404, detail="Tip not found")

    tip = dict(tip)
    results = {}

    if tip.get("content_fr") and not tip.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, tip["content_fr"], ALIA_GUIDE_FR_URL)
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE tips SET sent_wa_fr = 1 WHERE id = ?", (tip_id,)
            )
            await db.commit()

    if tip.get("content_ru") and not tip.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, tip["content_ru"], ALIA_GUIDE_RU_URL)
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE tips SET sent_wa_ru = 1 WHERE id = ?", (tip_id,)
            )
            await db.commit()

    return {"ok": True, "tip_id": tip_id, "sent": results}


@router.post("/faq/{faq_id}")
async def publish_faq(faq_id: int):
    """Publish a weekly FAQ to WhatsApp FR and RU groups."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM faqs WHERE id = ?", (faq_id,)
        )
        faq = await cursor.fetchone()

    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    faq = dict(faq)
    results = {}

    if faq.get("content_fr") and not faq.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, faq["content_fr"], ALIA_FAQ_FR_URL)
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE faqs SET sent_wa_fr = 1 WHERE id = ?", (faq_id,)
            )
            await db.commit()

    if faq.get("content_ru") and not faq.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, faq["content_ru"], ALIA_FAQ_RU_URL)
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE faqs SET sent_wa_ru = 1 WHERE id = ?", (faq_id,)
            )
            await db.commit()

    return {"ok": True, "faq_id": faq_id, "sent": results}


@router.post("/contest/{contest_id}")
async def publish_contest(contest_id: int):
    """Publish a contest to WhatsApp FR and RU groups."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM contests WHERE id = ?", (contest_id,))
        contest = await cursor.fetchone()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")
    contest = dict(contest)
    results = {}
    if contest.get("content_fr") and not contest.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, contest["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE contests SET sent_wa_fr = 1 WHERE id = ?", (contest_id,))
            await db.commit()
    if contest.get("content_ru") and not contest.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, contest["content_ru"])
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE contests SET sent_wa_ru = 1 WHERE id = ?", (contest_id,))
            await db.commit()
    return {"ok": True, "contest_id": contest_id, "sent": results}


@router.post("/prestataire/{record_id}")
async def publish_prestataire(record_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM weekly_prestataire WHERE id = ?", (record_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Prestataire not found")
    item = dict(row)
    results = {}
    if item.get("content_fr") and not item.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, item["content_fr"], ALIA_PRESTATAIRE_FR_URL)
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_prestataire SET sent_wa_fr = 1 WHERE id = ?", (record_id,))
            await db.commit()
    if item.get("content_ru") and not item.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, item["content_ru"], ALIA_PRESTATAIRE_RU_URL)
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_prestataire SET sent_wa_ru = 1 WHERE id = ?", (record_id,))
            await db.commit()
    return {"ok": True, "prestataire_id": record_id, "sent": results}


@router.post("/weekly-event-kids/{event_id}")
async def publish_weekly_event_kids(event_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM weekly_events_kids WHERE id = ?", (event_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Weekly kids event not found")
    item = dict(row)
    results = {}
    if item.get("content_fr") and not item.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, item["content_fr"], ALIA_KIDS_FR_URL)
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_events_kids SET sent_wa_fr = 1 WHERE id = ?", (event_id,))
            await db.commit()
    if item.get("content_ru") and not item.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, item["content_ru"], ALIA_KIDS_RU_URL)
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_events_kids SET sent_wa_ru = 1 WHERE id = ?", (event_id,))
            await db.commit()
    return {"ok": True, "weekly_event_kids_id": event_id, "sent": results}


@router.post("/weekly-rights/{record_id}")
async def publish_weekly_rights(record_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM weekly_rights WHERE id = ?", (record_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Weekly rights not found")
    item = dict(row)
    results = {}
    if item.get("content_fr") and not item.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, item["content_fr"], ALIA_RIGHTS_FR_URL)
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_rights SET sent_wa_fr = 1 WHERE id = ?", (record_id,))
            await db.commit()
    if item.get("content_ru") and not item.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, item["content_ru"], ALIA_RIGHTS_RU_URL)
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_rights SET sent_wa_ru = 1 WHERE id = ?", (record_id,))
            await db.commit()
    return {"ok": True, "weekly_rights_id": record_id, "sent": results}


@router.post("/weekly-doctor/{record_id}")
async def publish_weekly_doctor(record_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM weekly_doctor WHERE id = ?", (record_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Weekly doctor not found")
    item = dict(row)
    results = {}
    if item.get("content_fr") and not item.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, item["content_fr"], ALIA_DOCTORS_FR_URL)
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_doctor SET sent_wa_fr = 1 WHERE id = ?", (record_id,))
            await db.commit()
    if item.get("content_ru") and not item.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, item["content_ru"], ALIA_DOCTORS_RU_URL)
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_doctor SET sent_wa_ru = 1 WHERE id = ?", (record_id,))
            await db.commit()
    return {"ok": True, "weekly_doctor_id": record_id, "sent": results}


@router.post("/deal/{deal_id}")
async def publish_deal(deal_id: int):
    """Publish a deal to WhatsApp FR and/or RU groups based on audience."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM deals WHERE id = ?", (deal_id,)
        )
        deal = await cursor.fetchone()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    deal = dict(deal)
    audience = deal.get("audience", "both")
    results = {}

    if audience in ("fr", "both") and deal.get("content_fr") and not deal.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, deal["content_fr"], ALIA_DEALS_FR_URL)
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE deals SET sent_wa_fr = 1 WHERE id = ?", (deal_id,)
            )
            await db.commit()

    if audience in ("ru", "both") and deal.get("content_ru") and not deal.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, deal["content_ru"], ALIA_DEALS_RU_URL)
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE deals SET sent_wa_ru = 1 WHERE id = ?", (deal_id,)
            )
            await db.commit()

    return {"ok": True, "deal_id": deal_id, "sent": results}


SEND_CATEGORY_MAP = {
    "digest":      ("digests",            "digest_date"),
    "faq":         ("faqs",               "week"),
    "tip":         ("tips",               "week"),
    "rights":      ("weekly_rights",      "week"),
    "doctor":      ("weekly_doctor",      "week"),
    "kids":        ("weekly_events_kids", "week"),
    "prestataire": ("weekly_prestataire", "week"),
    "deal":        ("deals",              None),
}


@router.post("/send-pending/{category}")
async def send_pending_category(category: str):
    """Send generated-but-not-sent item for a specific category."""
    from api.routes.scrape import _auto_publish_item

    if category not in SEND_CATEGORY_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")

    table, date_col = SEND_CATEGORY_MAP[category]
    week = f"{datetime.utcnow().isocalendar()[0]}-W{datetime.utcnow().isocalendar()[1]:02d}"
    today = date.today().strftime("%Y-%m-%d")
    date_val = today if date_col == "digest_date" else week

    async with get_db() as db:
        if date_col and date_val:
            cursor = await db.execute(
                f"SELECT id FROM {table} WHERE {date_col} = ? AND content_fr IS NOT NULL AND sent_wa_fr = 0 AND sent_wa_ru = 0",
                (date_val,)
            )
        else:
            cursor = await db.execute(
                f"SELECT id FROM {table} WHERE content_fr IS NOT NULL AND sent_wa_fr = 0 AND sent_wa_ru = 0 ORDER BY id DESC LIMIT 1"
            )
        rows = await cursor.fetchall()

    sent = 0
    for row in rows:
        await _auto_publish_item(table, "id", row["id"])
        sent += 1

    return {"status": "ok", "category": category, "sent": sent}


@router.get("/scheduled-manual")
async def list_scheduled_manual():
    """List pending scheduled manual messages."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM scheduled_manual WHERE sent = 0 ORDER BY send_at ASC"
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.delete("/scheduled-manual/{id}")
async def delete_scheduled_manual(id: int):
    """Cancel a scheduled manual message."""
    async with get_db() as db:
        await db.execute("DELETE FROM scheduled_manual WHERE id = ? AND sent = 0", (id,))
        await db.commit()
    return {"ok": True}


@router.post("/fire-scheduled-manual")
async def fire_scheduled_manual():
    """Check and send any scheduled manual messages that are due."""
    import pytz
    from datetime import datetime as dt
    il_tz = pytz.timezone("Asia/Jerusalem")
    now = dt.now(il_tz)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM scheduled_manual WHERE sent = 0 AND send_at <= ?",
            (now.isoformat(),)
        )
        rows = await cursor.fetchall()

    sent = 0
    for row in rows:
        row = dict(row)
        try:
            if row["audience"] in ("fr", "both") and row["text_fr"]:
                await _send_whatsapp(WHAPI_GROUP_FR, row["text_fr"])
            if row["audience"] in ("ru", "both") and row["text_ru"]:
                await _send_whatsapp(WHAPI_GROUP_RU, row["text_ru"])
            async with get_db() as db:
                await db.execute("UPDATE scheduled_manual SET sent = 1 WHERE id = ?", (row["id"],))
                await db.commit()
            sent += 1
        except Exception as e:
            pass

    return {"ok": True, "sent": sent}
