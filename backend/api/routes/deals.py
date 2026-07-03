from fastapi import APIRouter
from db.database import get_db

router = APIRouter()


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
                       status, scraped_at
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
                       status, scraped_at
                FROM deals
                WHERE is_relevant = 1
                ORDER BY relevance_score DESC, scraped_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]
