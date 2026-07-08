from fastapi import APIRouter
from pydantic import BaseModel
from db.database import get_db

router = APIRouter()


async def get_setting(key: str) -> str:
    async with get_db() as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
    return row["value"] if row else None


async def set_setting(key: str, value: str):
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        await db.commit()


@router.get("")
async def get_all_settings():
    async with get_db() as db:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
    return {row["key"]: row["value"] for row in rows}


class SettingUpdate(BaseModel):
    value: str


@router.patch("/{key}")
async def update_setting(key: str, update: SettingUpdate):
    await set_setting(key, update.value)
    return {"ok": True, "key": key, "value": update.value}
