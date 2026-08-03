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

Rédige un résumé des infos du jour en français destiné aux olim. Traite les articles dans l'ordre donné ci-dessus (sécurité/politique en premier, société ensuite). Suis EXACTEMENT ce format :

📰 Le Brief Alia

👇

[3 à 5 news résumées, chacune sur une nouvelle ligne, avec un emoji pertinent au début]

📢 Rejoignez la communauté Alia:
https://tinyurl.com/Alia-community

Aucun astérisque, aucun markdown, aucun gras. Réponds uniquement avec le texte du message."""

PROMPT_RU = """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот новости сегодняшнего дня ({today}) :

{articles}

Напиши сводку новостей дня на русском для олим. Излагай новости в указанном выше порядке (сначала безопасность/политика, затем общество). Следуй ТОЧНО этому формату:

📰 Бриф Alia

👇

[3-5 новостей, каждая с новой строки, с подходящим эмодзи в начале]

Присоединяйтесь к сообществу Alia и получайте всё это каждую неделю :
https://tinyurl.com/Alia-community-RU

Никаких звёздочек, никакого markdown, никакого жирного текста. Отвечай только текстом сообщения.

Отвечай только текстом сообщения."""


async def generate_daily_digest(force: bool = False) -> dict:
    """Generate a daily news digest from today's scraped articles."""
    today = date.today().strftime("%d/%m/%Y")
    week_day = datetime.utcnow().strftime("%Y-%m-%d")

    async with get_db() as db:
        existing = await db.execute(
            "SELECT id, sent_wa_fr, sent_wa_ru FROM digests WHERE digest_date = ?", (week_day,)
        )
        row = await existing.fetchone()
        if row:
            if not force and not row["sent_wa_fr"] and not row["sent_wa_ru"]:
                # Skip only if digest is unsent — if already sent (or force=True), regenerate below
                logger.info(f"[digest] Unsent digest for {today} already exists, skipping.")
                return {"status": "skipped", "date": today}
            # Regenerating: free the articles this digest had claimed so they're eligible again
            async with get_db() as db2:
                await db2.execute(
                    "UPDATE articles SET used_in_digest_id = NULL WHERE used_in_digest_id = ?", (row["id"],)
                )
                await db2.execute("DELETE FROM digests WHERE digest_date = ?", (week_day,))
                await db2.commit()

        # Fetch today's articles not yet used in a digest
        cursor = await db.execute(
            """
            SELECT id, title_raw, summary_fr, summary_ru, source, language, score,
                   COALESCE(published_at, scraped_at) AS article_date
            FROM articles
            WHERE DATE(scraped_at) = DATE('now')
            AND (published_at IS NULL OR DATE(published_at) >= DATE('now', '-1 days'))
            AND ai_processed_at IS NOT NULL
            AND score >= 0.6
            AND category IN ('Sécurité', 'Politique', 'Société')
            AND used_in_digest_id IS NULL
            ORDER BY CASE category WHEN 'Société' THEN 1 ELSE 0 END, score DESC, article_date DESC
            LIMIT 20
            """
        )
        articles = await cursor.fetchall()

    if not articles:
        logger.info("[digest] No articles found for today.")
        return {"status": "no_articles"}

    # Build article list for prompt — use each article's already-generated summary
    # (written from the full article text) instead of the bare headline, which loses
    # nuance and can read backwards (e.g. who supports/opposes whom in a story).
    articles_text_fr = "\n".join([
        f"- {row['summary_fr'] or row['title_raw']} ({row['source']})"
        for row in articles
    ])
    articles_text_ru = "\n".join([
        f"- {row['summary_ru'] or row['title_raw']} ({row['source']})"
        for row in articles
    ])

    try:
        fr_response, ru_response = await asyncio.gather(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": PROMPT_FR.format(
                    today=today,
                    articles=articles_text_fr,
                )}],
            ),
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": PROMPT_RU.format(
                    today=today,
                    articles=articles_text_ru,
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
            # Mark articles as used so they won't appear in future digests
            article_ids = [row['id'] for row in articles]
            await db.execute(
                f"UPDATE articles SET used_in_digest_id = ? WHERE id IN ({','.join('?'*len(article_ids))})",
                [digest_id] + article_ids,
            )
            await db.commit()

        logger.info(f"[digest] Generated digest for {today} from {len(articles)} articles (id={digest_id})")
        return {"status": "ok", "date": today, "digest_id": digest_id, "articles_used": len(articles)}

    except Exception as e:
        logger.error(f"[digest] Failed: {e}")
        return {"status": "error", "error": str(e)}
