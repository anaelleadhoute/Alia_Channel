import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal
from db.database import get_db
from datetime import datetime

router = APIRouter()

WHAPI_TOKEN = os.getenv("WHAPI_TOKEN")
WHAPI_GROUP_FR = os.getenv("WHAPI_GROUP_FR")
WHAPI_GROUP_RU = os.getenv("WHAPI_GROUP_RU")
WHAPI_URL = "https://gate.whapi.cloud/messages/text"


async def _send_whatsapp(group_id: str, text: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{WHAPI_URL}?token={WHAPI_TOKEN}",
            json={"to": group_id, "body": text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


class ManualMessage(BaseModel):
    text: str
    audience: Literal["fr", "ru", "both"] = "both"


@router.post("/manual")
async def publish_manual(msg: ManualMessage):
    """Send a custom text message to FR and/or RU WhatsApp groups."""
    results = {}
    if msg.audience in ("fr", "both"):
        await _send_whatsapp(WHAPI_GROUP_FR, msg.text)
        results["fr"] = "sent"
    if msg.audience in ("ru", "both"):
        await _send_whatsapp(WHAPI_GROUP_RU, msg.text)
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
        await _send_whatsapp(WHAPI_GROUP_FR, digest["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE digests SET sent_wa_fr = 1 WHERE id = ?", (digest_id,)
            )
            await db.commit()

    if digest.get("content_ru") and not digest.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, digest["content_ru"])
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
        await _send_whatsapp(WHAPI_GROUP_FR, tip["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE tips SET sent_wa_fr = 1 WHERE id = ?", (tip_id,)
            )
            await db.commit()

    if tip.get("content_ru") and not tip.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, tip["content_ru"])
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
        await _send_whatsapp(WHAPI_GROUP_FR, faq["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE faqs SET sent_wa_fr = 1 WHERE id = ?", (faq_id,)
            )
            await db.commit()

    if faq.get("content_ru") and not faq.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, faq["content_ru"])
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


@router.post("/weekly-deal/{weekly_deal_id}")
async def publish_weekly_deal(weekly_deal_id: int):
    """Publish the weekly supermarket deal to WhatsApp FR and RU groups."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM weekly_deals WHERE id = ?", (weekly_deal_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Weekly deal not found")
    deal = dict(row)
    results = {}
    if deal.get("content_fr") and not deal.get("sent_wa_fr"):
        await _send_whatsapp(WHAPI_GROUP_FR, deal["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_deals SET sent_wa_fr = 1 WHERE id = ?", (weekly_deal_id,))
            await db.commit()
    if deal.get("content_ru") and not deal.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, deal["content_ru"])
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_deals SET sent_wa_ru = 1 WHERE id = ?", (weekly_deal_id,))
            await db.commit()
    return {"ok": True, "weekly_deal_id": weekly_deal_id, "sent": results}


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
        await _send_whatsapp(WHAPI_GROUP_FR, item["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_prestataire SET sent_wa_fr = 1 WHERE id = ?", (record_id,))
            await db.commit()
    if item.get("content_ru") and not item.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, item["content_ru"])
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
        await _send_whatsapp(WHAPI_GROUP_FR, item["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_events_kids SET sent_wa_fr = 1 WHERE id = ?", (event_id,))
            await db.commit()
    if item.get("content_ru") and not item.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, item["content_ru"])
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
        await _send_whatsapp(WHAPI_GROUP_FR, item["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_rights SET sent_wa_fr = 1 WHERE id = ?", (record_id,))
            await db.commit()
    if item.get("content_ru") and not item.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, item["content_ru"])
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
        await _send_whatsapp(WHAPI_GROUP_FR, item["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute("UPDATE weekly_doctor SET sent_wa_fr = 1 WHERE id = ?", (record_id,))
            await db.commit()
    if item.get("content_ru") and not item.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, item["content_ru"])
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
        await _send_whatsapp(WHAPI_GROUP_FR, deal["content_fr"])
        results["fr"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE deals SET sent_wa_fr = 1 WHERE id = ?", (deal_id,)
            )
            await db.commit()

    if audience in ("ru", "both") and deal.get("content_ru") and not deal.get("sent_wa_ru"):
        await _send_whatsapp(WHAPI_GROUP_RU, deal["content_ru"])
        results["ru"] = "sent"
        async with get_db() as db:
            await db.execute(
                "UPDATE deals SET sent_wa_ru = 1 WHERE id = ?", (deal_id,)
            )
            await db.commit()

    return {"ok": True, "deal_id": deal_id, "sent": results}
