from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.database import get_db

router = APIRouter()


class TipUpdate(BaseModel):
    status: Optional[str] = None
    content_fr: Optional[str] = None
    content_ru: Optional[str] = None
    send_at: Optional[str] = None


@router.get("")
async def list_tips(status: str = "all"):
    async with get_db() as db:
        if status == "all":
            cursor = await db.execute(
                """
                SELECT id, source_url, week, content_fr, content_ru,
                       status, send_at, sent_wa_fr, sent_wa_ru, scraped_at, ai_processed_at
                FROM tips
                ORDER BY scraped_at DESC
                """
            )
        else:
            cursor = await db.execute(
                """
                SELECT id, source_url, week, content_fr, content_ru,
                       status, send_at, sent_wa_fr, sent_wa_ru, scraped_at, ai_processed_at
                FROM tips
                WHERE status = ?
                ORDER BY scraped_at DESC
                """,
                (status,),
            )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.patch("/{tip_id}")
async def update_tip(tip_id: int, update: TipUpdate):
    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = tip_id

    async with get_db() as db:
        await db.execute(
            f"UPDATE tips SET {set_clause} WHERE id = :id", fields
        )
        await db.commit()

    return {"ok": True}
