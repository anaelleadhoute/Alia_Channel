from fastapi import APIRouter, HTTPException
from db.database import get_db
from processors.faq_processor import generate_weekly_faq

router = APIRouter()


@router.post("/generate")
async def generate_faq():
    """Generate this week's FAQ in FR + RU."""
    return await generate_weekly_faq()


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
