from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.database import get_db
from processors.faq_processor import generate_weekly_faq

router = APIRouter()


@router.post("/generate")
async def generate_faq(force: bool = False):
    """Generate this week's FAQ in FR + RU and auto-publish if enabled."""
    from api.routes.scrape import _is_auto_publish, _auto_publish_item
    result = await generate_weekly_faq(force=force)
    if result.get("status") == "ok" and result.get("faq_id"):
        auto = await _is_auto_publish("faq")
        if auto:
            await _auto_publish_item("faqs", "id", result["faq_id"])
            result["auto_published"] = True
    return result


@router.post("/generate/force")
async def generate_faq_force():
    """Force-regenerate this week's FAQ."""
    return await generate_weekly_faq(force=True)


class FaqUpdate(BaseModel):
    status: Optional[str] = None
    content_fr: Optional[str] = None
    content_ru: Optional[str] = None


@router.patch("/{faq_id}")
async def update_faq(faq_id: int, update: FaqUpdate):
    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = faq_id
    async with get_db() as db:
        await db.execute(f"UPDATE faqs SET {set_clause} WHERE id = :id", fields)
        await db.commit()
    return {"ok": True}


@router.get("")
async def list_faqs(limit: int = 10):
    """List recent FAQs."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, week, content_fr, content_ru,
                   status, sent_wa_fr, sent_wa_ru, generated_at
            FROM faqs
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]
