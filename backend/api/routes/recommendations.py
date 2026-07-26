from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, Literal
from db.database import get_db

router = APIRouter()


class RecommendationSubmit(BaseModel):
    type: Literal["prestataire", "medecin"]
    name: str
    specialty: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    language: Literal["fr", "ru", "both"]
    notes: Optional[str] = None
    submitted_by: Optional[str] = None


@router.post("")
async def submit_recommendation(body: RecommendationSubmit):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO recommendations (type, name, specialty, city, phone, language, notes, submitted_by)
               VALUES (?,?,?,?,?,?,?,?)""",
            (body.type, body.name, body.specialty, body.city, body.phone,
             body.language, body.notes, body.submitted_by)
        )
        await db.commit()
    return {"ok": True}


@router.get("")
async def list_recommendations(status: Optional[str] = None):
    async with get_db() as db:
        if status:
            cursor = await db.execute(
                "SELECT * FROM recommendations WHERE status = ? ORDER BY created_at DESC", (status,)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM recommendations ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.patch("/{id}/status")
async def update_recommendation_status(id: int, status: str):
    if status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid status")
    async with get_db() as db:
        await db.execute("UPDATE recommendations SET status = ? WHERE id = ?", (status, id))
        await db.commit()
    return {"ok": True}


@router.delete("/{id}")
async def delete_recommendation(id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM recommendations WHERE id = ?", (id,))
        await db.commit()
    return {"ok": True}
