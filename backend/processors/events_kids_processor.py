import json
import logging
import os
from datetime import datetime

import anthropic

from db.database import get_db

logger = logging.getLogger(__name__)
claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

KIDS_FR_PROMPT = """Tu es rédacteur pour Alia Channel, média pour les olim francophones en Israël.

Voici des activités pour enfants et familles cette semaine à Tel Aviv :
{events_text}

Rédige UN message WhatsApp en français pour les parents olim :

👨‍👩‍👧 Sorties familles de la semaine — par Alia

[2-3 activités avec nom, date si disponible, lien exact]

💬 Parle à Alia 👉 https://wa.me/972549675013?text=Avant%20de%20commencer%2C%20pr%C3%A9sente-toi.

Ne modifie pas les URLs. Ton chaleureux et enthousiaste. 80-120 mots.
Réponds uniquement avec le texte du message."""

KIDS_RU_PROMPT = """Ты редактор Alia Channel — медиа для русскоязычных олим в Израиле.

Вот детские и семейные мероприятия этой недели в Тель-Авиве :
{events_text}

Напиши сообщение для WhatsApp на русском для родителей-олим :

👨‍👩‍👧 Семейный досуг недели — от Alia

[2-3 мероприятия с названием, датой если есть, точной ссылкой]

💬 Напиши Alia 👉 https://wa.me/972549675013?text=%D0%9F%D1%80%D0%B5%D0%B4%D1%81%D1%82%D0%B0%D0%B2%D1%8C%D1%81%D1%8F.

Не меняй URL. Тёплый и живой тон. 80-120 слов.
Отвечай только текстом сообщения."""


def _format_events_text(events: list[dict]) -> str:
    lines = []
    for e in events:
        date = e.get("date", "") or e.get("start", "")
        lines.append(f"- {e['name']} | {e.get('city', 'Tel Aviv')} | {date} | {e.get('url', '')}")
    return "\n".join(lines)


async def generate_weekly_kids_events(force: bool = False, raw_events: list[dict] | None = None) -> dict:
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM weekly_events_kids WHERE week = ?", (week,))
        existing = await cursor.fetchone()
    if existing and not force:
        return {"status": "skipped", "week": week, "weekly_event_kids_id": existing["id"]}

    if not raw_events:
        return {"status": "error", "reason": "no events provided"}

    events_text = _format_events_text(raw_events)
    logger.info(f"[events_kids] Generating FR+RU for {len(raw_events)} kids events...")

    import asyncio
    fr_resp, ru_resp = await asyncio.gather(
        claude.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=400,
            messages=[{"role": "user", "content": KIDS_FR_PROMPT.format(events_text=events_text)}]),
        claude.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=400,
            messages=[{"role": "user", "content": KIDS_RU_PROMPT.format(events_text=events_text)}]),
    )

    content_fr = fr_resp.content[0].text.strip()
    content_ru = ru_resp.content[0].text.strip()

    async with get_db() as db:
        if force:
            await db.execute("DELETE FROM weekly_events_kids WHERE week = ?", (week,))
        cursor = await db.execute(
            """INSERT INTO weekly_events_kids (week, events_json, content_fr, content_ru, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (week, json.dumps(raw_events, ensure_ascii=False), content_fr, content_ru, datetime.utcnow().isoformat()),
        )
        await db.commit()
        event_id = cursor.lastrowid

    logger.info(f"[events_kids] Generated weekly_events_kids #{event_id} for {week}")
    return {"status": "generated", "week": week, "weekly_event_kids_id": event_id, "event_count": len(raw_events)}
