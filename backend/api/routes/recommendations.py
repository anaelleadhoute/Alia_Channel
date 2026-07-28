import os
import anthropic
from fastapi import APIRouter, HTTPException
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


@router.post("/{id}/generate")
async def generate_recommendation_message(id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM recommendations WHERE id = ?", (id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    r = dict(row)

    lang = r.get("language", "both")
    type_label = "médecin" if r["type"] == "medecin" else "prestataire"
    details = f"Nom: {r['name']}"
    if r.get("specialty"): details += f"\nSpécialité: {r['specialty']}"
    if r.get("city"): details += f"\nVille: {r['city']}"
    if r.get("phone"): details += f"\nTél: {r['phone']}"
    if r.get("notes"): details += f"\nNotes: {r['notes']}"

    claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    result = {"content_fr": None, "content_ru": None, "audience": lang}

    async def gen(prompt):
        resp = await claude.messages.create(model="claude-haiku-4-5-20251001", max_tokens=512,
                                            messages=[{"role":"user","content":prompt}])
        return resp.content[0].text.strip()

    if lang in ("fr", "both"):
        prompt_fr = f"""Tu es rédacteur pour AL.IA Channel, un média WhatsApp pour les olim francophones en Israël.
Un membre de la communauté recommande un(e) {type_label}. Écris un message WhatsApp chaleureux et utile pour partager cette recommandation avec la communauté.
Format: commence par un emoji accrocheur, présente le/la {type_label}, donne les infos pratiques, et encourage les membres à contacter.
Ton: chaleureux, communautaire, concis (max 200 mots). Ne mentionne pas qui a fait la recommandation.

Informations:
{details}

Termine TOUJOURS le message par ces deux lignes exactes (sans les modifier) :
💡 Vous aussi, partagez vos bonnes adresses : https://tinyurl.com/Alia-community
👥 Rejoindre la communauté AL.IA : https://tinyurl.com/Alia-community

Réponds UNIQUEMENT avec le message WhatsApp, sans explication."""
        result["content_fr"] = await gen(prompt_fr)

    if lang in ("ru", "both"):
        prompt_ru = f"""Ты редактор AL.IA Channel — WhatsApp-медиа для русскоязычных олим в Израиле.
Участник сообщества рекомендует {type_label}. Напиши тёплое и полезное WhatsApp-сообщение для сообщества с этой рекомендацией.
Формат: начни с подходящего эмодзи, представь специалиста, дай практическую информацию, призови обращаться.
Тон: тёплый, общественный, краткий (макс 200 слов). Не упоминай, кто сделал рекомендацию.

Информация:
{details}

Завершай сообщение ВСЕГДА этими двумя строками (без изменений) :
💡 Поделитесь своими рекомендациями : https://tinyurl.com/Alia-community
👥 Присоединиться к сообществу AL.IA : https://tinyurl.com/Alia-community-RU

Отвечай ТОЛЬКО текстом WhatsApp-сообщения, без пояснений."""
        result["content_ru"] = await gen(prompt_ru)

    return result
