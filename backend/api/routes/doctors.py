from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from db.database import get_db
from datetime import datetime
import json

router = APIRouter()


class DoctorImport(BaseModel):
    doctors: list[dict]


class DoctorUpdate(BaseModel):
    name_he: Optional[str] = None
    phone: Optional[str] = None
    city_he: Optional[str] = None
    specialty_translated: Optional[str] = None
    language: Optional[str] = None


@router.post("/import")
async def import_doctors(body: DoctorImport):
    """Receive scraped doctors from Mac and upsert into DB."""
    inserted = 0
    updated = 0
    async with get_db() as db:
        for doc in body.doctors:
            specialties_json = json.dumps(doc.get("specialties_he", []), ensure_ascii=False)
            existing = await db.execute("SELECT id FROM doctors WHERE url = ?", (doc["url"],))
            row = await existing.fetchone()
            if row:
                await db.execute(
                    "UPDATE doctors SET name_he=?, phone=?, city_he=?, specialties_he=?, specialty_translated=?, language=?, imported_at=? WHERE url=?",
                    (doc["name_he"], doc["phone"], doc["city_he"], specialties_json, doc["specialty_translated"], doc["language"], datetime.utcnow().isoformat(), doc["url"]),
                )
                updated += 1
            else:
                await db.execute(
                    "INSERT INTO doctors (name_he, phone, city_he, url, specialties_he, specialty_translated, language, source) VALUES (?,?,?,?,?,?,?,?)",
                    (doc["name_he"], doc["phone"], doc["city_he"], doc["url"], specialties_json, doc["specialty_translated"], doc["language"], doc.get("source", "medreviews")),
                )
                inserted += 1
        await db.commit()
    return {"inserted": inserted, "updated": updated, "total": len(body.doctors)}


@router.get("")
async def list_doctors(language: Optional[str] = None, limit: int = 50):
    async with get_db() as db:
        if language:
            cursor = await db.execute("SELECT * FROM doctors WHERE language = ? ORDER BY imported_at DESC LIMIT ?", (language, limit))
        else:
            cursor = await db.execute("SELECT * FROM doctors ORDER BY imported_at DESC LIMIT ?", (limit,))
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.post("/generate")
async def generate_doctor():
    """Pick a doctor not recently featured and generate FR+RU message."""
    from processors.doctor_processor import generate_weekly_doctor
    from api.routes.scrape import _is_auto_publish, _auto_publish_item

    result = await generate_weekly_doctor()
    if result.get("status") == "generated" and result.get("weekly_doctor_id"):
        auto = await _is_auto_publish("doctor")
        if auto:
            await _auto_publish_item("weekly_doctor", "id", result["weekly_doctor_id"])
            result["auto_published"] = True
    return result
