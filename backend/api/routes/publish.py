import os
import httpx
from fastapi import APIRouter, HTTPException
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
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


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
