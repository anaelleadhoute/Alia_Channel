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
    "תל אביב": "Tel-Aviv", "ירושלים": "Jérusalem / Иерусалим",
    "חיפה": "Haïfa / Хайфа", "באר שבע": "Beer-Sheva",
    "נתניה": "Netanya / Нетания", "ראשון לציון": "Rishon LeZion",
    "פתח תקווה": "Petah Tikva", "אשדוד": "Ashdod / Ашдод",
    "רחובות": "Rehovot", "הרצליה": "Herzliya / Герцлия",
    "גבעתיים": "Givataïm", "רמת גן": "Ramat Gan",
    "בת ים": "Bat Yam", "רמת השרון": "Ramat HaSharon",
    "כפר סבא": "Kfar Saba", "מודיעין": "Modi'in",
    "אשקלון": "Ashkelon", "חולון": "Holon",
}


async def generate_weekly_doctor() -> dict:
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        # Skip if already generated this week
        existing = await db.execute("SELECT id FROM weekly_doctor WHERE week = ?", (week,))
        if await existing.fetchone():
            return {"status": "skipped", "week": week}

        # Pick least recently featured doctor (both languages)
        cursor = await db.execute(
            """SELECT * FROM doctors
               ORDER BY last_featured ASC NULLS FIRST, RANDOM()
               LIMIT 1"""
        )
        doctor = await cursor.fetchone()

    if not doctor:
        return {"status": "error", "reason": "no doctors in DB"}

    doctor = dict(doctor)
    city_fr = CITIES_TRANSLATE.get(doctor["city_he"], doctor["city_he"])
    specialties = json.loads(doctor["specialties_he"] or "[]")
    specialty_he = specialties[0] if specialties else ""
    specialty = doctor["specialty_translated"] or specialty_he
    lang_label_fr = "français" if doctor["language"] == "fr" else "russe et français"
    lang_label_ru = "французском" if doctor["language"] == "fr" else "русском и французском"

    fr_prompt = f"""Tu es rédacteur pour AL.IA Channel, média pour les olim francophones en Israël.

Un médecin recommandé qui parle {lang_label_fr} :
- Nom : {doctor['name_he']}
- Spécialité : {specialty}
- Ville : {city_fr}
- Téléphone : {doctor['phone']}
- Profil : {doctor['url']}

Rédige un message WhatsApp court (80-100 mots) au format EXACT :
🏥 Le Médecin Alia

Aujourd'hui, beaucoup d'utilisateurs d'Alia nous demandent un [spécialité en français] [francophone/russophone].

👨‍⚕️ Nous vous recommandons [nom du médecin], qui parle [langue] et consulte à [ville].

📞 [numéro de téléphone]

🤖 Pour trouver un médecin adapté à votre ville, spécialité ou caisse maladie, demandez à Alia.
https://wa.me/972549675013?text=Aide-moi

📢 Rejoignez la communauté Alia pour d'autres recommandations.

Réponds uniquement avec le texte, sans JSON."""

    ru_prompt = f"""Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Рекомендуемый врач, говорящий на {lang_label_ru} :
- Имя : {doctor['name_he']}
- Специальность : {specialty}
- Город : {city_fr}
- Телефон : {doctor['phone']}
- Профиль : {doctor['url']}

Напиши короткое WhatsApp сообщение (80-100 слов) в точном формате :
🏥 Врач от Alia

Сегодня многие пользователи Alia ищут [специальность на русском] [говорящего по-русски/по-французски].

👨‍⚕️ Рекомендуем [имя врача], который говорит на [язык] и принимает в [город].

📞 [номер телефона]

🤖 Чтобы найти врача по городу, специальности или больничной кассе, спросите у Alia.
https://wa.me/972549675013?text=Помоги

📢 Присоединяйтесь к сообществу Alia для других рекомендаций.

Отвечай только текстом, без JSON."""

    try:
        fr_resp, ru_resp = await asyncio.gather(
            client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=400, messages=[{"role": "user", "content": fr_prompt}]),
            client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=400, messages=[{"role": "user", "content": ru_prompt}]),
        )
        content_fr = fr_resp.content[0].text.strip()
        content_ru = ru_resp.content[0].text.strip()

        async with get_db() as db:
            cursor = await db.execute(
                "INSERT INTO weekly_doctor (week, doctor_id, content_fr, content_ru) VALUES (?,?,?,?)",
                (week, doctor["id"], content_fr, content_ru),
            )
            weekly_id = cursor.lastrowid
            await db.execute("UPDATE doctors SET last_featured = ? WHERE id = ?", (datetime.utcnow().isoformat(), doctor["id"]))
            await db.commit()

        logger.info(f"[doctor_processor] Generated for doctor {doctor['id']} — week {week}")
        return {"status": "generated", "week": week, "weekly_doctor_id": weekly_id, "doctor_id": doctor["id"]}

    except Exception as e:
        logger.error(f"[doctor_processor] Error: {e}")
        return {"status": "error", "reason": str(e)}
