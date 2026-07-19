import os
import json
import asyncio
import logging
from datetime import datetime

import anthropic
from db.database import get_db

logger = logging.getLogger(__name__)
client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

CITIES_TRANSLATE = {
    "תל אביב": "Tel-Aviv", "ירושלים": "Jérusalem",
    "חיפה": "Haïfa", "באר שבע": "Beer-Sheva",
    "נתניה": "Netanya", "ראשון לציון": "Rishon LeZion",
    "פתח תקווה": "Petah Tikva", "אשדוד": "Ashdod",
    "רחובות": "Rehovot", "הרצליה": "Herzliya",
    "גבעתיים": "Givataïm", "רמת גן": "Ramat Gan",
    "בת ים": "Bat Yam", "רמת השרון": "Ramat HaSharon",
    "כפר סבא": "Kfar Saba", "מודיעין": "Modi'in",
    "אשקלון": "Ashkelon", "חולון": "Holon",
}


def _build_fr_prompt(doctor: dict) -> str:
    city = CITIES_TRANSLATE.get(doctor["city_he"], doctor["city_he"])
    specialties = json.loads(doctor["specialties_he"] or "[]")
    specialty = doctor["specialty_translated"] or (specialties[0] if specialties else "")
    return f"""Tu es rédacteur pour AL.IA Channel, média pour les olim francophones en Israël.

Un médecin francophone recommandé :
- Nom : {doctor['name_he']}
- Spécialité : {specialty}
- Ville : {city}
- Téléphone : {doctor['phone']}

Rédige un message WhatsApp court (80-100 mots) au format EXACT :
🏥 Le Médecin Alia

Sur ces 6 derniers jours, [nombre entre 2 et 6] utilisateurs d'Alia ont recherché un [spécialité en français] francophone.

👨‍⚕️ Nous vous recommandons [nom du médecin], qui parle français et consulte à [ville].

📞 [numéro de téléphone]

🤖 Pour trouver un médecin adapté à votre ville, spécialité ou caisse maladie, demandez à Alia.
https://wa.me/972549675013?text=Aide-moi

📢 Rejoignez la communauté Alia pour d'autres recommandations.

Réponds uniquement avec le texte, sans JSON."""


def _build_ru_prompt(doctor: dict) -> str:
    city = CITIES_TRANSLATE.get(doctor["city_he"], doctor["city_he"])
    specialties = json.loads(doctor["specialties_he"] or "[]")
    specialty = doctor["specialty_translated"] or (specialties[0] if specialties else "")
    return f"""Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Рекомендуемый русскоязычный врач :
- Имя : {doctor['name_he']}
- Специальность : {specialty}
- Город : {city}
- Телефон : {doctor['phone']}

Напиши короткое WhatsApp сообщение (80-100 слов) в точном формате :
🏥 Врач от Alia

За последние 6 дней [число от 2 до 6] пользователей Alia искали [специальность на русском] русскоязычного.

👨‍⚕️ Рекомендуем [имя врача], который говорит по-русски и принимает в [город].

📞 [номер телефона]

🤖 Чтобы найти врача по городу, специальности или больничной кассе, спросите у Alia.
https://wa.me/972549675013?text=Помоги

📢 Присоединяйтесь к сообществу Alia для других рекомендаций.

Отвечай только текстом, без JSON."""


async def _pick_doctor(lang: str, db) -> dict | None:
    cursor = await db.execute(
        """SELECT * FROM doctors WHERE language = ?
           ORDER BY last_featured ASC NULLS FIRST, RANDOM()
           LIMIT 1""",
        (lang,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def generate_weekly_doctor() -> dict:
    week = datetime.utcnow().strftime("%Y-W%U")

    async with get_db() as db:
        existing = await db.execute("SELECT id FROM weekly_doctor WHERE week = ?", (week,))
        if await existing.fetchone():
            return {"status": "skipped", "week": week}

        doctor_fr = await _pick_doctor("fr", db)
        doctor_ru = await _pick_doctor("ru", db)

    if not doctor_fr and not doctor_ru:
        return {"status": "error", "reason": "no doctors in DB"}

    try:
        tasks = []
        if doctor_fr:
            tasks.append(client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=400,
                messages=[{"role": "user", "content": _build_fr_prompt(doctor_fr)}],
            ))
        if doctor_ru:
            tasks.append(client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=400,
                messages=[{"role": "user", "content": _build_ru_prompt(doctor_ru)}],
            ))

        results = await asyncio.gather(*tasks)
        idx = 0
        content_fr = results[idx].content[0].text.strip() if doctor_fr else None
        if doctor_fr:
            idx += 1
        content_ru = results[idx].content[0].text.strip() if doctor_ru else None

        now = datetime.utcnow().isoformat()
        async with get_db() as db:
            cursor = await db.execute(
                "INSERT INTO weekly_doctor (week, doctor_id, content_fr, content_ru) VALUES (?,?,?,?)",
                (week, doctor_fr["id"] if doctor_fr else None, content_fr, content_ru),
            )
            weekly_id = cursor.lastrowid
            if doctor_fr:
                await db.execute("UPDATE doctors SET last_featured = ? WHERE id = ?", (now, doctor_fr["id"]))
            if doctor_ru:
                await db.execute("UPDATE doctors SET last_featured = ? WHERE id = ?", (now, doctor_ru["id"]))
            await db.commit()

        logger.info(f"[doctor_processor] Generated FR={doctor_fr and doctor_fr['id']} RU={doctor_ru and doctor_ru['id']} week={week}")
        return {"status": "generated", "week": week, "weekly_doctor_id": weekly_id}

    except Exception as e:
        logger.error(f"[doctor_processor] Error: {e}")
        return {"status": "error", "reason": str(e)}
