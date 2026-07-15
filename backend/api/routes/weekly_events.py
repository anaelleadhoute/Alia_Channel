from fastapi import APIRouter, HTTPException
from db.database import get_db

router = APIRouter()


@router.get("")
async def list_weekly_events(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, week, content_fr, content_ru, status, sent_wa_fr, sent_wa_ru, created_at FROM weekly_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.get("/prestataire")
async def list_weekly_prestataire(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, week, data_json, content_fr, content_ru, status, sent_wa_fr, sent_wa_ru, created_at FROM weekly_prestataire ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.get("/kids")
async def list_weekly_events_kids(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, week, content_fr, content_ru, status, sent_wa_fr, sent_wa_ru, created_at FROM weekly_events_kids ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.get("/rights")
async def list_weekly_rights(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, week, content_fr, content_ru, sent_wa_fr, sent_wa_ru, created_at FROM weekly_rights ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.get("/doctors")
async def list_weekly_doctors(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, week, content_fr, content_ru, sent_wa_fr, sent_wa_ru, created_at FROM weekly_doctor ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]
