from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.database import get_db

router = APIRouter()


class DealUpdate(BaseModel):
    status: Optional[str] = None
    content_fr: Optional[str] = None
    content_ru: Optional[str] = None


@router.patch("/{deal_id}")
async def update_deal(deal_id: int, update: DealUpdate):
    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = deal_id
    async with get_db() as db:
        await db.execute(f"UPDATE deals SET {set_clause} WHERE id = :id", fields)
        await db.commit()
    return {"ok": True}


@router.get("")
async def list_deals(category: str | None = None, limit: int = 50):
    """List relevant deals, optionally filtered by category."""
    async with get_db() as db:
        if category:
            cursor = await db.execute(
                """
                SELECT id, channel, category, relevance_score,
                       deal_product, deal_price, deal_summary_he,
                       raw_text, content_fr, content_ru,
                       audience, status, sent_wa_fr, sent_wa_ru, scraped_at
                FROM deals
                WHERE is_relevant = 1 AND category = ?
                ORDER BY relevance_score DESC, scraped_at DESC
                LIMIT ?
                """,
                (category, limit),
            )
        else:
            cursor = await db.execute(
                """
                SELECT id, channel, category, relevance_score,
                       deal_product, deal_price, deal_summary_he,
                       raw_text, content_fr, content_ru,
                       audience, status, sent_wa_fr, sent_wa_ru, scraped_at
                FROM deals
                WHERE is_relevant = 1
                ORDER BY relevance_score DESC, scraped_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]
