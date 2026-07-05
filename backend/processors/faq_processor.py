import asyncio
import logging
import os
from datetime import datetime

import anthropic

from db.database import get_db

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

WHATSAPP_BOT_LINK = "wa.me/972549675013"  # TODO: replace with actual bot link
COMMUNITY_FR_LINK = "wa.me/972549675013"  # TODO: replace with FR group invite link
COMMUNITY_RU_LINK = "wa.me/972549675013"  # TODO: replace with RU group invite link

PROMPT_FR = """Tu es expert en immigration et droits des olim en Israël.

La question la plus fréquemment posée cette semaine par les olim est :
"{question}"

Rédige une réponse complète et pratique pour les olim francophones en Israël.

Format :
❓ {question}

💡 [Réponse complète en 150-200 mots, avec des étapes concrètes si possible]

🤖 Des questions ? Notre bot WhatsApp est là pour vous aider 👉 {bot_link}
👥 Rejoignez la communauté AL.IA 👉 {community_link}

Réponds uniquement avec le texte du message, sans JSON, sans titre supplémentaire."""

PROMPT_RU = """Ты эксперт по иммиграции и правам олим в Израиле.

Самый частый вопрос этой недели среди олим:
"{question}"

Напиши полный и практический ответ для русскоязычных олим в Израиле.

Формат :
❓ {question}

💡 [Полный ответ 150-200 слов, с конкретными шагами если возможно]

🤖 Есть вопросы? Наш WhatsApp бот готов помочь 👉 {bot_link}
👥 Присоединяйтесь к сообществу AL.IA 👉 {community_link}

Отвечай только текстом сообщения, без JSON, без дополнительных заголовков."""


async def generate_weekly_faq(question: str) -> dict:
    """Generate a weekly FAQ for olim in FR + RU and save to DB."""
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        existing = await db.execute(
            "SELECT id FROM faqs WHERE week = ?", (week,)
        )
        if await existing.fetchone():
            logger.info(f"[faq] FAQ for {week} already exists, skipping.")
            return {"status": "skipped", "week": week}

    try:
        fr_response, ru_response = await asyncio.gather(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": PROMPT_FR.format(
                    question=question,
                    bot_link=WHATSAPP_BOT_LINK,
                    community_link=COMMUNITY_FR_LINK,
                )}],
            ),
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": PROMPT_RU.format(
                    question=question,
                    bot_link=WHATSAPP_BOT_LINK,
                    community_link=COMMUNITY_RU_LINK,
                )}],
            ),
        )

        content_fr = fr_response.content[0].text.strip()
        content_ru = ru_response.content[0].text.strip()

        async with get_db() as db:
            cursor = await db.execute(
                """
                INSERT INTO faqs (week, content_fr, content_ru, generated_at)
                VALUES (?, ?, ?, ?)
                """,
                (week, content_fr, content_ru, datetime.utcnow().isoformat()),
            )
            await db.commit()
            faq_id = cursor.lastrowid

        logger.info(f"[faq] Generated FAQ for {week} (id={faq_id})")
        return {"status": "ok", "week": week, "faq_id": faq_id}

    except Exception as e:
        logger.error(f"[faq] Failed: {e}")
        return {"status": "error", "error": str(e)}
