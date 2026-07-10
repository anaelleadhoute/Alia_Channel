from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.database import get_db
from processors.digest_processor import generate_daily_digest

router = APIRouter()


class DigestUpdate(BaseModel):
    status: Optional[str] = None
    content_fr: Optional[str] = None
    content_ru: Optional[str] = None


@router.patch("/{digest_id}")
async def update_digest(digest_id: int, update: DigestUpdate):
    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = digest_id
    async with get_db() as db:
        await db.execute(f"UPDATE digests SET {set_clause} WHERE id = :id", fields)
        await db.commit()
    return {"ok": True}


@router.post("/generate")
async def generate_digest():
    """Generate today's news digest in FR + RU from scraped articles."""
    return await generate_daily_digest()


@router.post("/generate/force")
async def generate_digest_force():
    """Force-regenerate today's digest even if one already exists."""
    return await generate_daily_digest(force=True)


@router.get("")
async def list_digests(limit: int = 10):
    """List recent digests."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, digest_date, content_fr, content_ru,
                   article_count, status, sent_wa_fr, sent_wa_ru, generated_at
            FROM digests
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]
