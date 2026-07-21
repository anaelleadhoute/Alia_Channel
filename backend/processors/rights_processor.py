import asyncio
import logging
import os
from datetime import datetime

import anthropic
from db.database import get_db

logger = logging.getLogger(__name__)
client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

FR_PROMPT = """Tu es rédacteur pour AL.IA Channel, média pour les olim francophones en Israël.

Voici une page de Kol Zchut sur les droits et aides en Israël :
Source : {url}
Contenu : {content}

Rédige un message "Les Droits Alia" en français (80-100 mots) sur un droit ou une aide disponible pour les olim.

Format EXACT :
💰 Les Droits Alia

💡 Le saviez-vous ?

[1 fait concret et utile sur ce droit/cette aide : qui peut en bénéficier, montant, conditions principales]

✅ [Ce que vous pouvez faire concrètement pour en bénéficier]

🤖 Pour plus d'informations, demandez à Alia.
https://wa.me/972549675013?text=Aide-moi

📢 Rejoignez la communauté Alia pour découvrir toutes les aides disponibles :
https://tinyurl.com/Alia-community

Réponds uniquement avec le texte, sans JSON."""

RU_PROMPT = """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот страница Kol Zchut о правах и льготах в Израиле :
Источник : {url}
Содержание : {content}

Напиши сообщение "Права Alia" на русском (80-100 слов) о праве или льготе, доступной для олим.

ТОЧНЫЙ формат :
💰 Права Alia

💡 Знаете ли вы ?

[1 конкретный и полезный факт об этом праве/льготе: кто может получить, сумма, основные условия]

✅ [Что можно сделать конкретно, чтобы воспользоваться этим правом]

🤖 Для получения дополнительной информации спросите у Alia.
https://wa.me/972549675013?text=Помоги

📢 Присоединяйтесь к сообществу Alia, чтобы узнать о всех доступных льготах.

Отвечай только текстом, без JSON."""


async def generate_weekly_rights(force: bool = False) -> dict:
    week = datetime.utcnow().strftime("%Y-W%U")

    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM weekly_rights WHERE week = ?", (week,))
        existing = await cursor.fetchone()

    if existing and existing["content_fr"] and not force:
        return {"status": "skipped", "week": week, "weekly_rights_id": existing["id"]}

    if existing and force:
        async with get_db() as db:
            await db.execute(
                "UPDATE weekly_rights SET content_fr=NULL, content_ru=NULL, sent_wa_fr=0, sent_wa_ru=0, ai_processed_at=NULL WHERE week=?",
                (week,)
            )
            await db.commit()

    if not existing or not existing["raw_payload"]:
        return {"status": "error", "reason": "no rights data stored for this week"}

    import json
    payload = json.loads(existing["raw_payload"])
    url = payload.get("url", "")
    content = payload.get("content", "")[:3000]

    try:
        fr_resp, ru_resp = await asyncio.gather(
            client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=400,
                messages=[{"role": "user", "content": FR_PROMPT.format(url=url, content=content)}],
            ),
            client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=400,
                messages=[{"role": "user", "content": RU_PROMPT.format(url=url, content=content)}],
            ),
        )
        content_fr = fr_resp.content[0].text.strip()
        content_ru = ru_resp.content[0].text.strip()

        async with get_db() as db:
            await db.execute(
                "UPDATE weekly_rights SET content_fr=?, content_ru=?, ai_processed_at=? WHERE week=?",
                (content_fr, content_ru, datetime.utcnow().isoformat(), week),
            )
            await db.commit()
            cursor = await db.execute("SELECT id FROM weekly_rights WHERE week=?", (week,))
            row = await cursor.fetchone()

        logger.info(f"[rights_processor] Generated for week {week}")
        return {"status": "generated", "week": week, "weekly_rights_id": row["id"]}

    except Exception as e:
        logger.error(f"[rights_processor] Error: {e}")
        return {"status": "error", "reason": str(e)}
