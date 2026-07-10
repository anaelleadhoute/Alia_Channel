import asyncio
import logging
import os
from datetime import datetime, date

import anthropic

from db.database import get_db

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PROMPT_FR = """Tu es rédacteur pour AL.IA Channel, un média pour les olim francophones en Israël.

Voici les articles d'actualité d'aujourd'hui ({today}) :

{articles}

Rédige un résumé des infos du jour en français destiné aux olim.
- Commence par : 📰 Les infos du jour — {today}
- Liste les 3-5 points les plus importants, chacun sur une nouvelle ligne
- Commence chaque point par un emoji pertinent selon le sujet (🚨 sécurité, 💼 économie, 🏛️ politique, 🔥 urgent, 🌍 international, 🏥 santé, etc.)
- Écris le titre du point en clair, puis une courte phrase d'explication
- Aucun astérisque, aucun markdown, aucun gras
- Termine par : AL.IA Community 👉 wa.me/972549675013

Réponds uniquement avec le texte du message."""

PROMPT_RU = """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот новости сегодняшнего дня ({today}) :

{articles}

Напиши сводку новостей дня на русском для олим.
- Начни с : 📰 Новости дня — {today}
- Перечисли 3-5 самых важных пунктов, каждый с новой строки
- Начинай каждый пункт с подходящего эмодзи (🚨 безопасность, 💼 экономика, 🏛️ политика, 🔥 срочно, 🌍 международное, 🏥 здоровье и т.д.)
- Пиши заголовок пункта, затем короткое пояснение
- Никаких звёздочек, никакого markdown, никакого жирного текста
- Заверши : AL.IA Community 👉 wa.me/972549675013

Отвечай только текстом сообщения."""


async def generate_daily_digest(force: bool = False) -> dict:
    """Generate a daily news digest from today's scraped articles."""
    today = date.today().strftime("%d/%m/%Y")
    week_day = datetime.utcnow().strftime("%Y-%m-%d")

    async with get_db() as db:
        existing = await db.execute(
            "SELECT id FROM digests WHERE digest_date = ?", (week_day,)
        )
        row = await existing.fetchone()
        if row and not force:
            logger.info(f"[digest] Digest for {today} already exists, skipping.")
            return {"status": "skipped", "date": today}
        if row and force:
            async with get_db() as db2:
                await db2.execute("DELETE FROM digests WHERE digest_date = ?", (week_day,))
                await db2.commit()

        # Fetch today's articles — prefer published_at when available, fall back to scraped_at
        cursor = await db.execute(
            """
            SELECT title_raw, summary_fr, summary_ru, source, language, score,
                   COALESCE(published_at, scraped_at) AS article_date
            FROM articles
            WHERE DATE(COALESCE(published_at, scraped_at)) >= DATE('now', '-3 days')
            AND ai_processed_at IS NOT NULL
            AND score >= 0.6
            ORDER BY score DESC, article_date DESC
            LIMIT 20
            """
        )
        articles = await cursor.fetchall()

    if not articles:
        logger.info("[digest] No articles found for today.")
        return {"status": "no_articles"}

    # Build article list for prompt
    articles_text = "\n".join([
        f"- {row['title_raw']} ({row['source']})"
        for row in articles
    ])

    try:
        fr_response, ru_response = await asyncio.gather(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": PROMPT_FR.format(
                    today=today,
                    articles=articles_text,
                )}],
            ),
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": PROMPT_RU.format(
                    today=today,
                    articles=articles_text,
                )}],
            ),
        )

        content_fr = fr_response.content[0].text.strip()
        content_ru = ru_response.content[0].text.strip()

        async with get_db() as db:
            cursor = await db.execute(
                """
                INSERT INTO digests (digest_date, content_fr, content_ru, article_count, generated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (week_day, content_fr, content_ru, len(articles), datetime.utcnow().isoformat()),
            )
            await db.commit()
            digest_id = cursor.lastrowid

        logger.info(f"[digest] Generated digest for {today} from {len(articles)} articles (id={digest_id})")
        return {"status": "ok", "date": today, "digest_id": digest_id, "articles_used": len(articles)}

    except Exception as e:
        logger.error(f"[digest] Failed: {e}")
        return {"status": "error", "error": str(e)}
