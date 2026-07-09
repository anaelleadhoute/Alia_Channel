import json
import logging
import os
from datetime import datetime, timedelta

import anthropic
import httpx

from db.database import get_db

logger = logging.getLogger(__name__)
claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

EVENTBRITE_TOKEN = os.getenv("EVENTBRITE_TOKEN")
EVENTBRITE_URL = "https://www.eventbriteapi.com/v3/events/search/"

CITIES = [
    {"name": "Tel Aviv", "q": "Tel Aviv"},
    {"name": "Jerusalem", "q": "Jerusalem"},
    {"name": "Netanya", "q": "Netanya"},
]

EVENTS_FR_PROMPT = """Tu es rédacteur pour Alia Channel, média pour les olim francophones en Israël.

Voici des événements cette semaine en Israël :
{events_text}

Rédige UN message WhatsApp en français (150-200 mots) présentant les meilleurs événements.
- Titre : "🎉 Les événements de la semaine — par Alia"
- Sélectionne 4-6 événements variés et intéressants pour des olim (culture, musique, sport, famille...)
- Pour chaque événement : nom, ville, date/heure, et lien
- Termine par : "💬 Parle à Alia 👉 https://wa.me/972549675013?text=Avant%20de%20commencer%2C%20pr%C3%A9sente-toi."
- Ton chaleureux, pas publicitaire

Réponds uniquement avec le texte du message."""

EVENTS_RU_PROMPT = """Ты редактор Alia Channel — медиа для русскоязычных олим в Израиле.

Вот события этой недели в Израиле :
{events_text}

Напиши ОДНО сообщение для WhatsApp на русском (150-200 слов) с лучшими событиями.
- Заголовок : "🎉 События недели — от Alia"
- Выбери 4-6 разнообразных интересных событий для олим (культура, музыка, спорт, семья...)
- Для каждого события : название, город, дата/время и ссылка
- Заверши : "💬 Напиши Alia 👉 https://wa.me/972549675013?text=%D0%9F%D1%80%D0%B5%D0%B4%D1%81%D1%82%D0%B0%D0%B2%D1%8C%D1%81%D1%8F."
- Тёплый тон, без рекламного пафоса

Отвечай только текстом сообщения."""


async def fetch_events() -> list[dict]:
    """Fetch upcoming week's events from Eventbrite for IL cities."""
    if not EVENTBRITE_TOKEN:
        logger.error("[events] EVENTBRITE_TOKEN not set")
        return []

    now = datetime.utcnow()
    week_start = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    week_end = (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_events = []
    headers = {"Authorization": f"Bearer {EVENTBRITE_TOKEN}"}

    async with httpx.AsyncClient(timeout=15) as client:
        for city in CITIES:
            try:
                resp = await client.get(EVENTBRITE_URL, headers=headers, params={
                    "q": city["q"],
                    "location.address": city["q"] + ", Israel",
                    "location.within": "15km",
                    "start_date.range_start": week_start,
                    "start_date.range_end": week_end,
                    "expand": "venue",
                    "sort_by": "date",
                    "page_size": 20,
                })
                resp.raise_for_status()
                data = resp.json()
                events = data.get("events", [])
                logger.info(f"[events] {city['name']}: {len(events)} events found")
                for e in events:
                    venue = e.get("venue") or {}
                    all_events.append({
                        "name": (e.get("name") or {}).get("text", ""),
                        "city": city["name"],
                        "start": e.get("start", {}).get("local", ""),
                        "url": e.get("url", ""),
                        "is_free": e.get("is_free", False),
                        "venue": venue.get("name", ""),
                    })
            except Exception as ex:
                logger.error(f"[events] Failed for {city['name']}: {ex}")

    return all_events


def _format_events_text(events: list[dict]) -> str:
    lines = []
    for e in events:
        start = e.get("start", "")
        try:
            dt = datetime.fromisoformat(start)
            start = dt.strftime("%A %d/%m %H:%M")
        except Exception:
            pass
        free = " (gratuit)" if e.get("is_free") else ""
        venue = f" — {e['venue']}" if e.get("venue") else ""
        lines.append(f"- {e['name']} | {e['city']}{venue} | {start}{free} | {e['url']}")
    return "\n".join(lines)


async def generate_weekly_events(force: bool = False, raw_events: list[dict] | None = None) -> dict:
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM weekly_events WHERE week = ?", (week,))
        existing = await cursor.fetchone()
    if existing and not force:
        return {"status": "skipped", "week": week, "weekly_event_id": existing["id"]}

    if raw_events is not None:
        events = raw_events
    else:
        events = await fetch_events()
    if not events:
        return {"status": "error", "reason": "no events found"}

    events_text = _format_events_text(events)
    logger.info(f"[events] Generating FR+RU messages for {len(events)} events...")

    import asyncio
    fr_resp, ru_resp = await asyncio.gather(
        claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": EVENTS_FR_PROMPT.format(events_text=events_text)}],
        ),
        claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": EVENTS_RU_PROMPT.format(events_text=events_text)}],
        ),
    )

    content_fr = fr_resp.content[0].text.strip()
    content_ru = ru_resp.content[0].text.strip()

    async with get_db() as db:
        if force:
            await db.execute("DELETE FROM weekly_events WHERE week = ?", (week,))
        cursor = await db.execute(
            """INSERT INTO weekly_events (week, events_json, content_fr, content_ru, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (week, json.dumps(events, ensure_ascii=False), content_fr, content_ru, datetime.utcnow().isoformat()),
        )
        await db.commit()
        event_id = cursor.lastrowid

    logger.info(f"[events] Generated weekly_events #{event_id} for {week}")
    return {
        "status": "generated",
        "week": week,
        "weekly_event_id": event_id,
        "event_count": len(events),
    }
