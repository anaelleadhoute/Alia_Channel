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

ALIA_LINK_FR = "https://wa.me/972549675013?text=Avant%20de%20commencer%2C%20pr%C3%A9sente-toi"
ALIA_LINK_RU = "https://wa.me/972549675013?text=%D0%9F%D1%80%D0%B5%D0%B4%D1%81%D1%82%D0%B0%D0%B2%D1%8C%D1%81%D1%8F"

PROMPT_FR = """Tu es expert en immigration et droits des olim en Israël.

Génère les 3 questions les plus posées cette semaine par les olim francophones (logement, santé, travail, Bituach Leumi, banque, école, Misrad Haklita, fiscalité, etc.).
{past_topics}

Format EXACT à respecter (sans rien ajouter avant ou après) :
🔥 Questions les plus posées cette semaine :

❓ [question 1]
💡 [Réponse concise, 2-3 phrases max]

❓ [question 2]
💡 [Réponse concise, 2-3 phrases max]

❓ [question 3]
💡 [Réponse concise, 2-3 phrases max]

Pour plus d'informations ou savoir comment faire, parle à Alia 👉 {alia_link}

Réponds uniquement avec le texte du message."""

PROMPT_RU = """Ты эксперт по иммиграции и правам олим в Израиле.

Составь 3 наиболее часто задаваемых вопроса этой недели от русскоязычных олим (жильё, здоровье, работа, Битуах Леуми, банк, школа, Мисрад Аклита, налоги и т.д.).
{past_topics}

ТОЧНЫЙ формат (ничего не добавлять до или после) :
🔥 Самые частые вопросы этой недели:

❓ [вопрос 1]
💡 [Краткий ответ, 2-3 предложения]

❓ [вопрос 2]
💡 [Краткий ответ, 2-3 предложения]

❓ [вопрос 3]
💡 [Краткий ответ, 2-3 предложения]

Для получения дополнительной информации или помощи — напиши Alia 👉 {alia_link}

Отвечай только текстом сообщения."""


async def generate_weekly_faq() -> dict:
    """Generate a weekly FAQ for olim in FR + RU and save to DB."""
    week = datetime.utcnow().strftime("%Y-W%W")

    async with get_db() as db:
        existing = await db.execute(
            "SELECT id FROM faqs WHERE week = ?", (week,)
        )
        if await existing.fetchone():
            logger.info(f"[faq] FAQ for {week} already exists, skipping.")
            return {"status": "skipped", "week": week}

        # Fetch last 8 weeks of questions to avoid repetition
        cursor = await db.execute(
            "SELECT content_fr FROM faqs ORDER BY generated_at DESC LIMIT 8"
        )
        past_faqs = await cursor.fetchall()

    past_topics = ""
    if past_faqs:
        past_topics = "\nÉvite absolument ces sujets déjà traités ces 8 dernières semaines :\n" + "\n".join(
            f"- {row[0][:150]}..." for row in past_faqs
        )

    try:
        fr_response, ru_response = await asyncio.gather(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                messages=[{"role": "user", "content": PROMPT_FR.format(
                    past_topics=past_topics,
                    alia_link=ALIA_LINK_FR,
                )}],
            ),
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                messages=[{"role": "user", "content": PROMPT_RU.format(
                    past_topics=past_topics.replace("Évite absolument ces sujets", "Избегай этих тем"),
                    alia_link=ALIA_LINK_RU,
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
