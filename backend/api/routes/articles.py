from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from db.database import get_db

router = APIRouter()


class ArticleUpdate(BaseModel):
    status: Optional[str] = None        # approved / rejected
    title_fr: Optional[str] = None
    summary_fr: Optional[str] = None
    cta_fr: Optional[str] = None
    title_ru: Optional[str] = None
    summary_ru: Optional[str] = None
    cta_ru: Optional[str] = None
    send_at: Optional[str] = None       # ISO datetime
    channels: Optional[list[str]] = None  # wa_fr, wa_ru, ig_fr, ig_ru


@router.get("")
async def list_articles(status: str = "pending", limit: int = 50):
    """List articles filtered by status."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, source, language, url, title_raw,
                   title_fr, summary_fr, cta_fr, caption_ig_fr,
                   title_ru, summary_ru, cta_ru, caption_ig_ru,
                   score, category, status, send_at,
                   sent_wa_fr, sent_wa_ru, sent_ig_fr, sent_ig_ru,
                   scraped_at, ai_processed_at
            FROM articles
            WHERE status = ?
            ORDER BY score DESC, scraped_at DESC
            LIMIT ?
            """,
            (status, limit),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.get("/{article_id}")
async def get_article(article_id: int):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        )
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return dict(row)


@router.patch("/{article_id}")
async def update_article(article_id: int, update: ArticleUpdate):
    """Approve, reject, or edit an article."""
    fields = update.model_dump(exclude_none=True, exclude={"channels"})
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields["edited_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = article_id

    async with get_db() as db:
        await db.execute(
            f"UPDATE articles SET {set_clause} WHERE id = :id", fields
        )
        await db.commit()

    return {"ok": True, "updated": list(fields.keys())}
