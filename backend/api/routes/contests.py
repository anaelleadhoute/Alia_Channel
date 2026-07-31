import csv
import html
import io
import re
import os
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import anthropic
from db.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)
client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[àâä]', 'a', text)
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[îï]', 'i', text)
    text = re.sub(r'[ôö]', 'o', text)
    text = re.sub(r'[ùûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')[:50]


# ── Contest management ────────────────────────────────────────────────────────

class ContestCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    slug: Optional[str] = None


class ContestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    slug: Optional[str] = None
    status: Optional[str] = None


@router.post("")
async def create_contest(body: ContestCreate):
    slug = body.slug or _slugify(body.title)
    async with get_db() as db:
        # ensure unique slug
        existing = await db.execute("SELECT id FROM contests WHERE slug = ?", (slug,))
        if await existing.fetchone():
            slug = f"{slug}-{datetime.utcnow().strftime('%m%d%H%M')}"
        cursor = await db.execute(
            "INSERT INTO contests (title, description, slug, created_at) VALUES (?, ?, ?, ?)",
            (body.title, body.description, slug, datetime.utcnow().isoformat()),
        )
        await db.commit()
        contest_id = cursor.lastrowid
    return {"ok": True, "contest_id": contest_id, "slug": slug, "url": f"/concours/{slug}"}


@router.get("")
async def list_contests(limit: int = 50):
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT c.id, c.title, c.description, c.slug, c.status, c.created_at,
               (SELECT COUNT(*) FROM contest_submissions WHERE contest_id = c.id) as submissions
               FROM contests c ORDER BY c.created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


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


# ── Public form page ──────────────────────────────────────────────────────────

@router.get("/form/{slug}", response_class=HTMLResponse)
async def contest_form(slug: str, lang: str = "fr"):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, title, description FROM contests WHERE slug = ?", (slug,)
        )
        contest = await cursor.fetchone()
    if not contest:
        raise HTTPException(status_code=404, detail="Concours introuvable")
    contest = dict(contest)

    template = "/app/static/concours-ru.html" if lang == "ru" else "/app/static/concours.html"
    with open(template, "r") as f:
        page = f.read()

    default_desc = "Заполни анкету для участия!" if lang == "ru" else "Remplis ce formulaire pour participer !"
    page = page.replace("{{CONTEST_TITLE}}", html.escape(contest["title"]))
    page = page.replace("{{CONTEST_DESCRIPTION}}", html.escape(contest["description"] or default_desc))
    page = page.replace("{{CONTEST_ID}}", str(contest["id"]))
    return HTMLResponse(page)


# ── Submissions ───────────────────────────────────────────────────────────────

class SubmissionCreate(BaseModel):
    contest_id: int
    first_name: str
    last_name: str
    phone: str
    email: str
    time_in_israel: str
    interests: List[str]
    discovery: str


@router.post("/submit")
async def submit_contest(body: SubmissionCreate):
    async with get_db() as db:
        existing = await db.execute("SELECT id FROM contests WHERE id = ?", (body.contest_id,))
        if not await existing.fetchone():
            raise HTTPException(status_code=404, detail="Concours introuvable")
        dup = await db.execute(
            "SELECT id FROM contest_submissions WHERE contest_id = ? AND (phone = ? OR email = ?)",
            (body.contest_id, body.phone, body.email)
        )
        if await dup.fetchone():
            raise HTTPException(status_code=409, detail="Ce numéro ou cet email a déjà participé à ce concours.")
        await db.execute(
            """INSERT INTO contest_submissions
               (contest_id, first_name, last_name, phone, email, time_in_israel, interests, discovery)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (body.contest_id, body.first_name, body.last_name, body.phone, body.email,
             body.time_in_israel, ", ".join(body.interests), body.discovery),
        )
        await db.commit()
    return {"ok": True}


@router.get("/{contest_id}/submissions")
async def list_submissions(contest_id: int):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM contest_submissions WHERE contest_id = ? ORDER BY submitted_at DESC",
            (contest_id,)
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.get("/{contest_id}/submissions/export")
async def export_submissions_csv(contest_id: int):
    async with get_db() as db:
        contest = dict((await (await db.execute("SELECT title FROM contests WHERE id = ?", (contest_id,))).fetchone()) or {})
        cursor = await db.execute(
            "SELECT * FROM contest_submissions WHERE contest_id = ? ORDER BY submitted_at ASC",
            (contest_id,)
        )
        rows = await cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Prénom", "Nom", "Téléphone", "Email", "Temps en Israël",
                     "Centres d'intérêt", "Découverte", "Date"])
    for r in rows:
        r = dict(r)
        writer.writerow([r["id"], r.get("first_name",""), r.get("last_name",""),
                         r.get("phone",""), r.get("email",""), r["time_in_israel"],
                         r["interests"], r["discovery"], r["submitted_at"]])

    output.seek(0)
    filename = f"concours-{contest_id}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
