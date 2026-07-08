import os
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import anthropic
from db.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)
client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class ContestCreate(BaseModel):
    title: str
    content_fr: str
    content_ru: Optional[str] = None  # if None, Claude translates from FR
    auto_translate: bool = True


class ContestUpdate(BaseModel):
    title: Optional[str] = None
    content_fr: Optional[str] = None
    content_ru: Optional[str] = None
    status: Optional[str] = None


@router.post("")
async def create_contest(body: ContestCreate):
    """Create a contest/giveaway manually. Optionally auto-translate FR → RU."""
    content_ru = body.content_ru

    if not content_ru and body.auto_translate:
        try:
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": f"""Traduis ce message en russe pour des olim en Israël.
Garde le même ton, les emojis, et les liens.
Ne traduis pas les noms propres, marques, ou liens.

Message français :
{body.content_fr}

Réponds uniquement avec la traduction."""}],
            )
            content_ru = response.content[0].text.strip()
        except Exception as e:
            logger.error(f"[contests] Translation failed: {e}")
            content_ru = body.content_fr  # fallback to FR

    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO contests (title, content_fr, content_ru, created_at) VALUES (?, ?, ?, ?)",
            (body.title, body.content_fr, content_ru, datetime.utcnow().isoformat()),
        )
        await db.commit()
        contest_id = cursor.lastrowid

    return {"ok": True, "contest_id": contest_id, "translated": body.auto_translate and not body.content_ru}


@router.get("")
async def list_contests(limit: int = 20):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, title, content_fr, content_ru, status, sent_wa_fr, sent_wa_ru, created_at FROM contests ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.patch("/{contest_id}")
async def update_contest(contest_id: int, update: ContestUpdate):
    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = contest_id
    async with get_db() as db:
        await db.execute(f"UPDATE contests SET {set_clause} WHERE id = :id", fields)
        await db.commit()
    return {"ok": True}


@router.delete("/{contest_id}")
async def delete_contest(contest_id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM contests WHERE id = ?", (contest_id,))
        await db.commit()
    return {"ok": True}
