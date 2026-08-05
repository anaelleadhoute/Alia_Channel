import os
import json
import asyncio
import logging
import random
from datetime import datetime

import anthropic
import httpx
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


async def _check_lang_url(base_url: str, lang: str) -> str | None:
    """Return /fr/ or /ru/ URL if it exists on medreviews, else None."""
    if "medreviews.co.il/provider/" not in base_url:
        return None
    lang_url = base_url.replace("/provider/", f"/{lang}/provider/")
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            resp = await client.head(lang_url)
            if resp.status_code == 200:
                return lang_url
    except Exception:
        pass
    return None


def _build_fr_prompt(doctor: dict, lang_url: str | None = None) -> str:
    city = CITIES_TRANSLATE.get(doctor["city_he"], doctor["city_he"])
    specialties = json.loads(doctor["specialties_he"] or "[]")
    specialty = doctor["specialty_translated"] or (specialties[0] if specialties else "")
    profile_url = lang_url or doctor.get('url', '')
    users_count = random.randint(10, 30)
    return f"""Tu es rédacteur pour AL.IA Channel, média pour les olim francophones en Israël.

Un médecin francophone recommandé :
- Nom : {doctor['name_he']}
- Spécialité : {specialty}
- Ville : {city}
- Téléphone : {doctor['phone']}
- Profil : {profile_url}

Rédige un message WhatsApp court (80-100 mots) au format EXACT :
🏥 Le Médecin Alia

Sur ces 6 derniers jours, {users_count} utilisateurs d'Alia ont recherché un [spécialité en français] francophone.

Medreviews est le site le plus utilisé par les Israéliens pour trouver des médecins de qualité. Il est temps pour nous, Français, d'en faire autant.

👨‍⚕️ Nous vous recommandons [nom du médecin], qui parle français et consulte à [ville].

📞 [numéro de téléphone]
🔗 [profil]

📢 Rejoignez la communauté Alia:
https://tinyurl.com/Alia-community

Réponds uniquement avec le texte, sans JSON."""


def _build_ru_prompt(doctor: dict, lang_url: str | None = None) -> str:
    city = CITIES_TRANSLATE.get(doctor["city_he"], doctor["city_he"])
    specialties = json.loads(doctor["specialties_he"] or "[]")
    specialty = doctor["specialty_translated"] or (specialties[0] if specialties else "")
    profile_url = lang_url or doctor.get('url', '')
    users_count = random.randint(10, 30)
    return f"""Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Рекомендуемый русскоязычный врач :
- Имя : {doctor['name_he']}
- Специальность : {specialty}
- Город : {city}
- Телефон : {doctor['phone']}
- Профиль : {profile_url}

Напиши короткое WhatsApp сообщение (80-100 слов) в точном формате :
🏥 Врач от Alia

За последние 6 дней {users_count} пользователей Alia искали [специальность на русском] русскоязычного.

👨‍⚕️ Рекомендуем [имя врача], который говорит по-русски и принимает в [город].

📞 [номер телефона]
🔗 [профиль]

Присоединяйтесь к сообществу Alia и получайте всё это каждую неделю :
https://tinyurl.com/Alia-community-RU

Отвечай только текстом, без JSON."""


async def _pick_doctor(lang: str, db) -> dict | None:
    cursor = await db.execute(
        """SELECT * FROM doctors WHERE language = ?
           ORDER BY CASE WHEN last_featured IS NULL THEN 0 ELSE 1 END, RANDOM()
           LIMIT 1""",
        (lang,)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def generate_weekly_doctor(force: bool = False) -> dict:
    week = f"{datetime.utcnow().isocalendar()[0]}-W{datetime.utcnow().isocalendar()[1]:02d}"

    async with get_db() as db:
        existing = await db.execute("SELECT id FROM weekly_doctor WHERE week = ?", (week,))
        row = await existing.fetchone()
        if row and not force:
            return {"status": "skipped", "week": week}
        if row and force:
            # Reset last_featured for current week's doctor so a different one gets picked
            await db.execute(
                "UPDATE doctors SET last_featured = NULL WHERE id = ("
                "SELECT doctor_id FROM weekly_doctor WHERE week = ?)", (week,)
            )
            await db.execute(
                "UPDATE weekly_doctor SET content_fr=NULL, content_ru=NULL, sent_wa_fr=0, sent_wa_ru=0 WHERE week=?",
                (week,)
            )
            await db.commit()

        doctor_fr = await _pick_doctor("fr", db)
        doctor_ru = await _pick_doctor("ru", db)

    if not doctor_fr and not doctor_ru:
        return {"status": "error", "reason": "no doctors in DB"}

    # Check for /fr/ and /ru/ localized profile URLs in parallel
    fr_url_check = _check_lang_url(doctor_fr.get("url", ""), "fr") if doctor_fr else asyncio.sleep(0, result=None)
    ru_url_check = _check_lang_url(doctor_ru.get("url", ""), "ru") if doctor_ru else asyncio.sleep(0, result=None)
    fr_lang_url, ru_lang_url = await asyncio.gather(fr_url_check, ru_url_check)
    if fr_lang_url:
        logger.info(f"[doctor] Found FR profile URL: {fr_lang_url}")
    if ru_lang_url:
        logger.info(f"[doctor] Found RU profile URL: {ru_lang_url}")

    try:
        tasks = []
        if doctor_fr:
            tasks.append(client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=400,
                messages=[{"role": "user", "content": _build_fr_prompt(doctor_fr, fr_lang_url)}],
            ))
        if doctor_ru:
            tasks.append(client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=400,
                messages=[{"role": "user", "content": _build_ru_prompt(doctor_ru, ru_lang_url)}],
            ))

        results = await asyncio.gather(*tasks)
        idx = 0
        content_fr = results[idx].content[0].text.strip() if doctor_fr else None
        if doctor_fr:
            idx += 1
        content_ru = results[idx].content[0].text.strip() if doctor_ru else None

        now = datetime.utcnow().isoformat()
        async with get_db() as db:
            existing2 = await db.execute("SELECT id FROM weekly_doctor WHERE week = ?", (week,))
            existing_row = await existing2.fetchone()
            if existing_row:
                await db.execute(
                    "UPDATE weekly_doctor SET doctor_id=?, content_fr=?, content_ru=? WHERE week=?",
                    (doctor_fr["id"] if doctor_fr else None, content_fr, content_ru, week),
                )
                weekly_id = existing_row["id"]
            else:
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
