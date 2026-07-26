from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.database import get_db

router = APIRouter()


class ContentUpdate(BaseModel):
    content_fr: Optional[str] = None
    content_ru: Optional[str] = None


@router.get("/prestataire")
async def list_weekly_prestataire(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, week, data_json, content_fr, content_ru, status, sent_wa_fr, sent_wa_ru, created_at FROM weekly_prestataire ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.patch("/prestataire/{id}")
async def update_prestataire(id: int, body: ContentUpdate):
    async with get_db() as db:
        row = await db.execute("SELECT id FROM weekly_prestataire WHERE id = ?", (id,))
        if not await row.fetchone():
            raise HTTPException(status_code=404, detail="Not found")
        fields = {k: v for k, v in body.dict().items() if v is not None}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            await db.execute(f"UPDATE weekly_prestataire SET {sets} WHERE id = ?", (*fields.values(), id))
            await db.commit()
    return {"ok": True}


@router.get("/kids")
async def list_weekly_events_kids(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, week, content_fr, content_ru, status, sent_wa_fr, sent_wa_ru, created_at FROM weekly_events_kids ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.patch("/kids/{id}")
async def update_kids(id: int, body: ContentUpdate):
    async with get_db() as db:
        row = await db.execute("SELECT id FROM weekly_events_kids WHERE id = ?", (id,))
        if not await row.fetchone():
            raise HTTPException(status_code=404, detail="Not found")
        fields = {k: v for k, v in body.dict().items() if v is not None}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            await db.execute(f"UPDATE weekly_events_kids SET {sets} WHERE id = ?", (*fields.values(), id))
            await db.commit()
    return {"ok": True}


@router.get("/rights")
async def list_weekly_rights(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, week, content_fr, content_ru, sent_wa_fr, sent_wa_ru, created_at FROM weekly_rights ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.patch("/rights/{id}")
async def update_rights(id: int, body: ContentUpdate):
    async with get_db() as db:
        row = await db.execute("SELECT id FROM weekly_rights WHERE id = ?", (id,))
        if not await row.fetchone():
            raise HTTPException(status_code=404, detail="Not found")
        fields = {k: v for k, v in body.dict().items() if v is not None}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            await db.execute(f"UPDATE weekly_rights SET {sets} WHERE id = ?", (*fields.values(), id))
            await db.commit()
    return {"ok": True}


@router.get("/doctors")
async def list_weekly_doctors(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, week, content_fr, content_ru, sent_wa_fr, sent_wa_ru, created_at FROM weekly_doctor ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.patch("/doctors/{id}")
async def update_doctors(id: int, body: ContentUpdate):
    async with get_db() as db:
        row = await db.execute("SELECT id FROM weekly_doctor WHERE id = ?", (id,))
        if not await row.fetchone():
            raise HTTPException(status_code=404, detail="Not found")
        fields = {k: v for k, v in body.dict().items() if v is not None}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            await db.execute(f"UPDATE weekly_doctor SET {sets} WHERE id = ?", (*fields.values(), id))
            await db.commit()
    return {"ok": True}
