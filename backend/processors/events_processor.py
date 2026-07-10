import json
import logging
import os
from datetime import datetime

import anthropic

from db.database import get_db

logger = logging.getLogger(__name__)
claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

EVENTS_FR_PROMPT = """Tu es rédacteur pour Alia Channel, média pour les olim francophones en Israël.

Voici des événements cette semaine en Israël :
{events_text}

Rédige UN message WhatsApp en français avec ce format :

🎉 Les événements de la semaine — par Alia

[3-4 événements : concerts, culture, gastronomie, sorties — avec nom, date si disponible, lien exact]
[inclus au moins 1 événement Meetup ou Eventbrite]

💬 Parle à Alia 👉 https://wa.me/972549675013?text=Avant%20de%20commencer%2C%20pr%C3%A9sente-toi.

Ne modifie pas les URLs. Ton chaleureux. 120-160 mots.
Réponds uniquement avec le texte du message."""

EVENTS_RU_PROMPT = """Ты редактор Alia Channel — медиа для русскоязычных олим в Израиле.

Вот события этой недели в Израиле :
{events_text}

Напиши сообщение для WhatsApp на русском :

🎉 События недели — от Alia

[3-4 события: концерты, культура, гастрономия, прогулки — с названием, датой если есть, точной ссылкой]
[включи минимум 1 событие из Meetup или Eventbrite]

💬 Напиши Alia 👉 https://wa.me/972549675013?text=%D0%9F%D1%80%D0%B5%D0%B4%D1%81%D1%82%D0%B0%D0%B2%D1%8C%D1%81%D1%8F.

Не меняй URL. Тёплый тон. 120-160 слов.
Отвечай только текстом сообщения."""


def _format_events_text(events: list[dict]) -> str:
    lines = []
    for e in events:
        date = e.get("date", "") or e.get("start", "")
        venue = f" — {e['venue']}" if e.get("venue") else ""
        source = f" [{e['source']}]" if e.get("source") else ""
        lines.append(f"- {e['name']} | {e.get('city', '')}{venue} | {date}{source} | {e.get('url', '')}")
    return "\n".join(lines)


async def generate_weekly_events(force: bool = False, raw_events: list[dict] | None = None) -> dict:
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM weekly_events WHERE week = ?", (week,))
        existing = await cursor.fetchone()
    if existing and not force:
        return {"status": "skipped", "week": week, "weekly_event_id": existing["id"]}

    if not raw_events:
        return {"status": "error", "reason": "no events provided"}

    events_text = _format_events_text(raw_events)
    logger.info(f"[events] Generating FR+RU for {len(raw_events)} events...")

    import asyncio
    fr_resp, ru_resp = await asyncio.gather(
        claude.messages.create(model="claude-sonnet-4-5-20251001", max_tokens=600,
            messages=[{"role": "user", "content": EVENTS_FR_PROMPT.format(events_text=events_text)}]),
        claude.messages.create(model="claude-sonnet-4-5-20251001", max_tokens=600,
            messages=[{"role": "user", "content": EVENTS_RU_PROMPT.format(events_text=events_text)}]),
    )

    content_fr = fr_resp.content[0].text.strip()
    content_ru = ru_resp.content[0].text.strip()

    async with get_db() as db:
        if force:
            await db.execute("DELETE FROM weekly_events WHERE week = ?", (week,))
        cursor = await db.execute(
            """INSERT INTO weekly_events (week, events_json, content_fr, content_ru, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (week, json.dumps(raw_events, ensure_ascii=False), content_fr, content_ru, datetime.utcnow().isoformat()),
        )
        await db.commit()
        event_id = cursor.lastrowid

    logger.info(f"[events] Generated weekly_events #{event_id} for {week}")
    return {"status": "generated", "week": week, "weekly_event_id": event_id, "event_count": len(raw_events)}
