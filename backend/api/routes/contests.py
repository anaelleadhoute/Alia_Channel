import csv
import io
import os
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
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


# ── Contest form submissions ──────────────────────────────────────────────────

class SubmissionCreate(BaseModel):
    full_name: str
    contact: str
    time_in_israel: str
    interests: List[str]
    discovery: str
    best_opinion: Optional[str] = ""


@router.post("/submit")
async def submit_contest(body: SubmissionCreate):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO contest_submissions
               (full_name, contact, time_in_israel, interests, discovery, best_opinion)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (body.full_name, body.contact, body.time_in_israel,
             ", ".join(body.interests), body.discovery, body.best_opinion),
        )
        await db.commit()
    return {"ok": True}


@router.get("/submissions")
async def list_submissions():
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM contest_submissions ORDER BY submitted_at DESC"
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.get("/submissions/export")
async def export_submissions_csv():
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM contest_submissions ORDER BY submitted_at ASC"
        )
        rows = await cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Prénom & Nom", "Contact", "Temps en Israël",
                     "Centres d'intérêt", "Découverte", "Avis", "Date"])
    for r in rows:
        r = dict(r)
        writer.writerow([r["id"], r["full_name"], r["contact"], r["time_in_israel"],
                         r["interests"], r["discovery"], r["best_opinion"], r["submitted_at"]])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=concours.csv"},
    )
