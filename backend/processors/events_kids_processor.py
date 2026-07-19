import json
import logging
import os
from datetime import datetime

import anthropic

from db.database import get_db

logger = logging.getLogger(__name__)
claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

FR_PROMPT = """Tu es rédacteur pour AL.IA Channel, média pour les olim francophones en Israël.

Une attraction familiale recommandée cette semaine (depuis Karamel.co.il) :
- Nom (en hébreu) : {name}
- Description : {description}

Rédige un message WhatsApp court (80-100 mots) au format EXACT :
👨‍👩‍👧 Sortie famille — Alia

Sur ces 7 derniers jours, [nombre entre 2 et 6] familles d'Alia ont demandé une idée de sortie avec les enfants.

🎡 Cette semaine, on vous recommande [nom traduit en français], [description courte en français, 1 phrase].

📞 Pour plus d'infos, cherchez [nom traduit en français] sur Google ou demandez à Alia.

🤖 Pour plus d'informations, demandez à Alia.
https://wa.me/972549675013?text=Aide-moi

📢 Rejoignez la communauté Alia pour d'autres idées sorties.

Réponds uniquement avec le texte, sans JSON."""

RU_PROMPT = """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Рекомендуемое семейное место на этой неделе (от Karamel.co.il) :
- Название (на иврите) : {name}
- Описание : {description}

Напиши короткое WhatsApp сообщение (80-100 слов) в точном формате :
👨‍👩‍👧 Семейный досуг — от Alia

За последние 7 дней [число от 2 до 6] семей из Alia спрашивали об идее для прогулки с детьми.

🎡 На этой неделе рекомендуем [название на русском], [краткое описание на русском, 1 предложение].

📞 Для получения информации найдите [название на русском] в Google или спросите у Alia.

🤖 Для получения дополнительной информации спросите у Alia.
https://wa.me/972549675013?text=Помоги

📢 Присоединяйтесь к сообществу Alia для других идей на выходные.

Отвечай только текстом, без JSON."""


async def generate_weekly_kids_events(force: bool = False, raw_events: list[dict] | None = None) -> dict:
    import asyncio
    week = datetime.utcnow().strftime("%Y-W%U")

    async with get_db() as db:
        cursor = await db.execute("SELECT id, content_fr, raw_payload FROM weekly_events_kids WHERE week = ?", (week,))
        existing = await cursor.fetchone()

    if existing and existing["content_fr"] and not force:
        return {"status": "skipped", "week": week, "weekly_event_kids_id": existing["id"]}

    if not raw_events:
        if existing and existing["raw_payload"]:
            raw_events = json.loads(existing["raw_payload"])
        else:
            return {"status": "error", "reason": "no events stored for this week"}

    # Pick the Karamel attraction
    karamel = next((e for e in raw_events if e.get("source") == "Karamel"), None)
    if not karamel:
        return {"status": "error", "reason": "no Karamel attraction in stored data"}

    name = karamel.get("name", "")
    description = karamel.get("description", "")

    try:
        fr_resp, ru_resp = await asyncio.gather(
            claude.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=400,
                messages=[{"role": "user", "content": FR_PROMPT.format(name=name, description=description)}],
            ),
            claude.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=400,
                messages=[{"role": "user", "content": RU_PROMPT.format(name=name, description=description)}],
            ),
        )
        content_fr = fr_resp.content[0].text.strip()
        content_ru = ru_resp.content[0].text.strip()

        async with get_db() as db:
            if existing:
                await db.execute(
                    "UPDATE weekly_events_kids SET content_fr=?, content_ru=? WHERE week=?",
                    (content_fr, content_ru, week),
                )
                await db.commit()
                event_id = existing["id"]
            else:
                cursor = await db.execute(
                    "INSERT INTO weekly_events_kids (week, raw_payload, content_fr, content_ru) VALUES (?,?,?,?)",
                    (week, json.dumps(raw_events, ensure_ascii=False), content_fr, content_ru),
                )
                await db.commit()
                event_id = cursor.lastrowid

        logger.info(f"[events_kids] Generated attraction '{name}' for week {week}")
        return {"status": "generated", "week": week, "weekly_event_kids_id": event_id}

    except Exception as e:
        logger.error(f"[events_kids] Error: {e}")
        return {"status": "error", "reason": str(e)}
