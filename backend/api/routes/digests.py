from fastapi import APIRouter
from db.database import get_db
from processors.digest_processor import generate_daily_digest

router = APIRouter()


@router.post("/generate")
async def generate_digest():
    """Generate today's news digest in FR + RU from scraped articles."""
    return await generate_daily_digest()


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
