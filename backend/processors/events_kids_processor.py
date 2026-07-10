import json
import logging
import os
from datetime import datetime

import anthropic

from db.database import get_db

logger = logging.getLogger(__name__)
claude = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

KIDS_PICK_PROMPT = """Voici une liste d'activités et événements pour enfants et familles (titres en hébreu). Chaque ligne a un numéro.

{events_text}

Choisis EXACTEMENT 2 activités (pas plus, pas moins) pour des familles avec enfants.
Traduis leur titre en français et en russe.

Réponds UNIQUEMENT avec ce JSON (exactement 2 indexes, 2 titres fr, 2 titres ru) :
{{"indexes": [n, n], "titles_fr": ["titre fr", "titre fr"], "titles_ru": ["titre ru", "titre ru"]}}"""

KIDS_INTRO_FR_PROMPT = """Tu es rédacteur pour Alia Channel. Écris 1 seule phrase d'introduction chaleureuse pour un message WhatsApp parents olim sur ces activités : {summary}. Pas de titre, pas de liste, pas de hashtag, pas de # au début."""

KIDS_INTRO_RU_PROMPT = """Ты редактор Alia Channel. Напиши 1 тёплое вступительное предложение для WhatsApp-сообщения для родителей-олим об этих мероприятиях: {summary}. Без заголовка, без списка, без решётки в начале."""


def _build_message_fr(events: list[dict], intro: str) -> str:
    lines = ["👨‍👩‍👧 Sorties familles de la semaine — par Alia", "", intro, ""]
    karamel = None
    ipo = None
    for e in events:
        if e.get("source") == "Karamel":
            karamel = e
            continue
        if e.get("upcoming_highlight"):
            ipo = e
            continue
        name = e.get("name_fr") or e["name"]
        date = e.get("date", "")
        date_str = f" — {date}" if date else ""
        lines.append(f"🎈 {name}{date_str}")
        if e.get("url"):
            lines.append(e["url"])
        lines.append("")
    if karamel:
        name = karamel.get("name_fr") or karamel["name"]
        desc = karamel.get("desc_fr") or ""
        lines.append(f"💡 Idée activité : {name}")
        if desc:
            lines.append(desc)
        if karamel.get("url"):
            lines.append(karamel["url"])
        lines.append("")
    if ipo:
        name = ipo.get("name_fr") or ipo["name"]
        lines.append(f"🎻 À venir — {name} | {ipo.get('date', '')}")
        if ipo.get("url"):
            lines.append(ipo["url"])
        lines.append("")
    lines.append("💬 Parle à Alia 👉 https://wa.me/972549675013?text=Avant%20de%20commencer%2C%20pr%C3%A9sente-toi.")
    return "\n".join(lines)


def _build_message_ru(events: list[dict], intro: str) -> str:
    lines = ["👨‍👩‍👧 Семейный досуг недели — от Alia", "", intro, ""]
    karamel = None
    ipo = None
    for e in events:
        if e.get("source") == "Karamel":
            karamel = e
            continue
        if e.get("upcoming_highlight"):
            ipo = e
            continue
        name = e.get("name_ru") or e["name"]
        date = e.get("date", "")
        date_str = f" — {date}" if date else ""
        lines.append(f"🎈 {name}{date_str}")
        if e.get("url"):
            lines.append(e["url"])
        lines.append("")
    if karamel:
        name = karamel.get("name_ru") or karamel["name"]
        desc = karamel.get("desc_ru") or ""
        lines.append(f"💡 Идея на неделю : {name}")
        if desc:
            lines.append(desc)
        if karamel.get("url"):
            lines.append(karamel["url"])
        lines.append("")
    if ipo:
        name = ipo.get("name_ru") or ipo["name"]
        lines.append(f"🎻 Скоро — {name} | {ipo.get('date', '')}")
        if ipo.get("url"):
            lines.append(ipo["url"])
        lines.append("")
    lines.append("💬 Напиши Alia 👉 https://wa.me/972549675013?text=%D0%9F%D1%80%D0%B5%D0%B4%D1%81%D1%82%D0%B0%D0%B2%D1%8C%D1%81%D1%8F.")
    return "\n".join(lines)


async def generate_weekly_kids_events(force: bool = False, raw_events: list[dict] | None = None) -> dict:
    import asyncio, re
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM weekly_events_kids WHERE week = ?", (week,))
        existing = await cursor.fetchone()
    if existing and not force:
        return {"status": "skipped", "week": week, "weekly_event_kids_id": existing["id"]}

    if not raw_events:
        return {"status": "error", "reason": "no events provided"}

    karamel = next((e for e in raw_events if e.get("source") == "Karamel"), None)
    ipo = next((e for e in raw_events if e.get("upcoming_highlight")), None)
    seen_names = set()
    candidates = []
    for e in raw_events:
        if e.get("source") == "Karamel" or e.get("upcoming_highlight"):
            continue
        if e["name"] in seen_names:
            continue
        seen_names.add(e["name"])
        candidates.append(e)
    candidates = candidates[:20]

    # Step 1: Claude picks the best 3 and translates; also translate IPO title if present
    ipo_line = f"\nIPO: {ipo['name']}" if ipo else ""
    events_text = "\n".join(f"{i}. {e['name']} | {e.get('date','')} " for i, e in enumerate(candidates))
    pick_prompt = KIDS_PICK_PROMPT.format(events_text=events_text)
    extra_titles = {}
    if ipo:
        extra_titles["ipo"] = ipo["name"]
    if karamel:
        extra_titles["karamel"] = karamel["name"]
    if extra_titles:
        extras_str = ", ".join(f'"{k}": "{v}"' for k, v in extra_titles.items())
        pick_prompt += f"\n\nTraduis aussi ces titres en français et russe et ajoute-les au JSON :\n{{{extras_str}}}\nFormat : \"ipo_fr\", \"ipo_ru\", \"karamel_fr\", \"karamel_ru\""
    if karamel and karamel.get("description"):
        pick_prompt += f"\n\nTraduis aussi cette description de l'activité Karamel en français et russe (max 120 caractères chacune) :\n\"{karamel['description'][:300]}\"\nAjoute \"karamel_desc_fr\" et \"karamel_desc_ru\" au JSON."

    pick_resp = await claude.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=500,
        messages=[{"role": "user", "content": pick_prompt}]
    )
    titles_fr = []
    titles_ru = []
    try:
        raw = pick_resp.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw); raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        indexes = parsed.get("indexes", [])[:2]
        titles_fr = parsed.get("titles_fr", [])
        titles_ru = parsed.get("titles_ru", [])
        if ipo:
            ipo["name_fr"] = parsed.get("ipo_fr") or ipo["name"]
            ipo["name_ru"] = parsed.get("ipo_ru") or ipo["name"]
        if karamel:
            karamel["name_fr"] = parsed.get("karamel_fr") or karamel["name"]
            karamel["name_ru"] = parsed.get("karamel_ru") or karamel["name"]
            karamel["desc_fr"] = parsed.get("karamel_desc_fr", "")
            karamel["desc_ru"] = parsed.get("karamel_desc_ru", "")
        selected = [candidates[i] for i in indexes if 0 <= i < len(candidates)]
    except Exception as ex:
        logger.warning(f"[events_kids] Pick parse failed: {ex} — raw: {pick_resp.content[0].text[:200]}")
        selected = candidates[:2]

    # Attach translated names to each selected event
    for i, e in enumerate(selected):
        e["name_fr"] = titles_fr[i] if i < len(titles_fr) else e["name"]
        e["name_ru"] = titles_ru[i] if i < len(titles_ru) else e["name"]

    if karamel:
        selected.append(karamel)
    if ipo:
        selected.append(ipo)

    summary = ", ".join(e["name"] for e in selected if e.get("source") != "Karamel" and not e.get("upcoming_highlight"))
    logger.info(f"[events_kids] Selected {len(selected)} events, generating intros...")

    # Step 2: Claude writes intro text only (URLs come from Python)
    fr_resp, ru_resp = await asyncio.gather(
        claude.messages.create(model="claude-haiku-4-5-20251001", max_tokens=100,
            messages=[{"role": "user", "content": KIDS_INTRO_FR_PROMPT.format(summary=summary)}]),
        claude.messages.create(model="claude-haiku-4-5-20251001", max_tokens=100,
            messages=[{"role": "user", "content": KIDS_INTRO_RU_PROMPT.format(summary=summary)}]),
    )

    def _clean_intro(text: str) -> str:
        lines = [l for l in text.strip().splitlines() if not l.strip().startswith('#')]
        return " ".join(" ".join(lines).split())

    intro_fr = _clean_intro(fr_resp.content[0].text)
    intro_ru = _clean_intro(ru_resp.content[0].text)
    content_fr = _build_message_fr(selected, intro_fr)
    content_ru = _build_message_ru(selected, intro_ru)

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
