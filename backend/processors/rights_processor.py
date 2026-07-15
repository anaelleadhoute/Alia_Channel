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

Rédige un message "Les Droits Alia" en français (80-100 mots) centré sur l'ÉLIGIBILITÉ — est-ce que l'olim y a droit ?

Format EXACT :
💰 Les Droits Alia

Beaucoup d'utilisateurs d'Alia nous demandent :

"[Question d'éligibilité fréquente entre guillemets, ex: Ai-je droit à... ? Puis-je bénéficier de... ?]"

✅ [Réponse courte : dans quels cas oui]

[1-2 phrases sur les conditions principales : ancienneté, situation familiale, revenus, etc.]

🤖 Pour vérifier votre éligibilité personnelle, demandez à Alia.
https://wa.me/972549675013?text=Aide-moi

📢 Rejoignez la communauté Alia pour découvrir toutes les aides disponibles.

Réponds uniquement avec le texte, sans JSON."""

RU_PROMPT = """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот страница Kol Zchut о правах и льготах в Израиле :
Источник : {url}
Содержание : {content}

Напиши сообщение "Права Alia" на русском (80-100 слов), сфокусированное на ПРАВЕ НА ПОЛУЧЕНИЕ льготы.

ТОЧНЫЙ формат :
💰 Права Alia

Многие пользователи Alia спрашивают :

"[Частый вопрос о праве на льготу в кавычках, например: Имею ли я право на... ? Могу ли я получить... ?]"

✅ [Краткий ответ: в каких случаях да]

[1-2 предложения об основных условиях: стаж, семейное положение, доход и т.д.]

🤖 Чтобы проверить своё личное право на льготу, спросите у Alia.
https://wa.me/972549675013?text=Помоги

📢 Присоединяйтесь к сообществу Alia, чтобы узнать о всех доступных льготах.

Отвечай только текстом, без JSON."""


async def generate_weekly_rights() -> dict:
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM weekly_rights WHERE week = ?", (week,))
        existing = await cursor.fetchone()

    if existing and existing["content_fr"]:
        return {"status": "skipped", "week": week, "weekly_rights_id": existing["id"]}

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
