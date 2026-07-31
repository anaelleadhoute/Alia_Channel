import csv
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
               (SELECT COUNT(*) FROM contest_submissions s WHERE s.contest_id = c.id) as submissions
               FROM contests ORDER BY c.created_at DESC LIMIT ?""",
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
async def contest_form(slug: str):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, title, description FROM contests WHERE slug = ?", (slug,)
        )
        contest = await cursor.fetchone()
    if not contest:
        raise HTTPException(status_code=404, detail="Concours introuvable")
    contest = dict(contest)

    with open("/app/static/concours.html", "r") as f:
        html = f.read()

    html = html.replace("{{CONTEST_TITLE}}", contest["title"])
    html = html.replace("{{CONTEST_DESCRIPTION}}", contest["description"] or "Remplis ce formulaire pour participer !")
    html = html.replace("{{CONTEST_ID}}", str(contest["id"]))
    return HTMLResponse(html)


# ── Submissions ───────────────────────────────────────────────────────────────

class SubmissionCreate(BaseModel):
    contest_id: int
    full_name: str
    contact: str
    time_in_israel: str
    interests: List[str]
    discovery: str
    best_opinion: Optional[str] = ""


@router.post("/submit")
async def submit_contest(body: SubmissionCreate):
    async with get_db() as db:
        existing = await db.execute("SELECT id FROM contests WHERE id = ?", (body.contest_id,))
        if not await existing.fetchone():
            raise HTTPException(status_code=404, detail="Concours introuvable")
        await db.execute(
            """INSERT INTO contest_submissions
               (contest_id, full_name, contact, time_in_israel, interests, discovery, best_opinion)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (body.contest_id, body.full_name, body.contact, body.time_in_israel,
             ", ".join(body.interests), body.discovery, body.best_opinion),
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
    writer.writerow(["ID", "Prénom & Nom", "Contact", "Temps en Israël",
                     "Centres d'intérêt", "Découverte", "Avis", "Date"])
    for r in rows:
        r = dict(r)
        writer.writerow([r["id"], r["full_name"], r["contact"], r["time_in_israel"],
                         r["interests"], r["discovery"], r["best_opinion"], r["submitted_at"]])

    output.seek(0)
    filename = f"concours-{contest_id}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
