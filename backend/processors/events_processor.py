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

Voici les événements familles/enfants à inclure obligatoirement :
{kids_text}

Rédige UN message WhatsApp en français avec cette structure EXACTE (ne change pas les titres de sections) :

🎉 Les événements de la semaine — par Alia

[2-3 événements : concerts, culture, gastronomie — avec nom, date si disponible, lien exact]

👨‍👩‍👧 Pour les familles
[reprends les événements familles ci-dessus — avec nom, date si disponible, lien exact]

[1 événement Meetup ou Eventbrite — avec nom, date si disponible, lien exact]

💬 Parle à Alia 👉 https://wa.me/972549675013?text=Avant%20de%20commencer%2C%20pr%C3%A9sente-toi.

Ne modifie pas les URLs. Ton chaleureux. 150-200 mots.
Réponds uniquement avec le texte du message."""

EVENTS_RU_PROMPT = """Ты редактор Alia Channel — медиа для русскоязычных олим в Израиле.

Вот события этой недели в Израиле :
{events_text}

Вот семейные/детские события для обязательного включения :
{kids_text}

Напиши сообщение для WhatsApp на русском с ТОЧНОЙ структурой (не меняй заголовки разделов) :

🎉 События недели — от Alia

[2-3 события: концерты, культура, гастрономия — с названием, датой если есть, точной ссылкой]

👨‍👩‍👧 Для семей
[используй семейные события выше — с названием, датой если есть, точной ссылкой]

[1 событие из Meetup или Eventbrite — с названием, датой если есть, точной ссылкой]

💬 Напиши Alia 👉 https://wa.me/972549675013?text=%D0%9F%D1%80%D0%B5%D0%B4%D1%81%D1%82%D0%B0%D0%B2%D1%8C%D1%81%D1%8F.

Не меняй URL. Тёплый тон. 150-200 слов.
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


KIDS_KEYWORDS = [
    "ילד", "ילדים", "ילדות", "משפח", "נוער", "kids", "children", "family", "famille",
    "enfant", "jeunesse", "בובה", "סיפור", "משחקייה", "קיץ ילד", "קרקס", "יוגה להורים",
    "הצגה לילד", "סדנת התפתח",
]

def _is_kids_event(event: dict) -> bool:
    text = (event.get("name", "") + " " + event.get("date", "")).lower()
    return any(kw in text for kw in KIDS_KEYWORDS)


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
        source = f" [{e['source']}]" if e.get("source") else ""
        lines.append(f"- {e['name']} | {e['city']}{venue} | {start}{free}{source} | {e['url']}")
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

    kids_events = [e for e in events if _is_kids_event(e)]
    # Fallback: pick any Mairie de Tel Aviv event if no kids events detected
    if not kids_events:
        kids_events = [e for e in events if e.get("source") == "Mairie de Tel Aviv"][:2]
    non_kids_events = [e for e in events if e not in kids_events]

    events_text = _format_events_text(non_kids_events)
    kids_text = _format_events_text(kids_events[:2]) if kids_events else "Aucun événement famille trouvé cette semaine."
    logger.info(f"[events] Generating FR+RU messages for {len(events)} events ({len(kids_events)} kids)...")

    import asyncio
    fr_resp, ru_resp = await asyncio.gather(
        claude.messages.create(
            model="claude-sonnet-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": EVENTS_FR_PROMPT.format(events_text=events_text, kids_text=kids_text)}],
        ),
        claude.messages.create(
            model="claude-sonnet-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": EVENTS_RU_PROMPT.format(events_text=events_text, kids_text=kids_text)}],
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
