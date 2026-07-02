import asyncio
import json
import logging
import os
import re
from datetime import datetime

import anthropic

from db.database import get_db

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

CATEGORIES = [
    "Aliya & Absorption",
    "Logement",
    "Emploi",
    "Santé",
    "Education",
    "Aides sociales",
    "Sécurité",
    "Politique",
    "Société",
    "Autre",
]


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


async def _generate_fr(title: str, content: str) -> dict:
    prompt = f"""Tu es rédacteur pour AL.IA Channel, un média destiné aux olim francophones en Israël.

Article source (hébreu ou anglais) :
Titre : {title}
Contenu : {content[:2000]}

Génère exactement ce JSON (sans markdown, sans backticks) :
{{
  "title_fr": "Titre traduit et accrocheur en français (max 80 caractères)",
  "summary_fr": "Résumé clair et utile en français pour des olim (150-200 mots). Mentionne ce qui est concret et actionnable.",
  "cta_fr": "Message WhatsApp court (max 3 lignes) avec emoji, résumé en 1 phrase + lien vers AL.IA Community : wa.me/972549675013",
  "caption_ig_fr": "Caption Instagram en français (max 220 caractères) avec 3-5 hashtags pertinents en français et hébreu",
  "score": 0.0,
  "category": "une des catégories suivantes : {', '.join(CATEGORIES)}"
}}

Pour le score (0.0 à 1.0) : évalue la pertinence pour des olim francophones.
1.0 = très pertinent (aliya, droits, aides, logement, emploi)
0.5 = moyennement pertinent (actualité israélienne générale)
0.0 = non pertinent (sport, people, international sans lien Israël)"""

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(response.content[0].text)


async def _generate_ru(title: str, content: str) -> dict:
    prompt = f"""Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Исходная статья (на иврите или английском) :
Заголовок : {title}
Содержание : {content[:2000]}

Сгенерируй точно этот JSON (без markdown, без backticks) :
{{
  "title_ru": "Переведённый и привлекательный заголовок на русском (макс 80 символов)",
  "summary_ru": "Чёткое и полезное резюме на русском для олим (150-200 слов). Укажи конкретные и практичные моменты.",
  "cta_ru": "Короткое сообщение для WhatsApp (макс 3 строки) с эмодзи, резюме в 1 предложении + ссылка на AL.IA Community : wa.me/972549675013",
  "caption_ig_ru": "Instagram caption на русском (макс 220 символов) с 3-5 релевантными хэштегами на русском и иврите"
}}"""

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(response.content[0].text)


async def process_article(article_id: int, title: str, content: str) -> bool:
    """Generate FR + RU content in parallel for one article."""
    try:
        results = await asyncio.gather(
            _generate_fr(title, content),
            _generate_ru(title, content),
            return_exceptions=True,
        )
        if isinstance(results[0], Exception) or isinstance(results[1], Exception):
            raise results[0] if isinstance(results[0], Exception) else results[1]
        fr_result, ru_result = results

        async with get_db() as db:
            await db.execute(
                """
                UPDATE articles SET
                    title_fr   = :title_fr,
                    summary_fr = :summary_fr,
                    cta_fr     = :cta_fr,
                    caption_ig_fr = :caption_ig_fr,
                    score      = :score,
                    category   = :category,
                    title_ru   = :title_ru,
                    summary_ru = :summary_ru,
                    cta_ru     = :cta_ru,
                    caption_ig_ru = :caption_ig_ru,
                    ai_processed_at = :processed_at
                WHERE id = :id
                """,
                {
                    "id": article_id,
                    **fr_result,
                    **ru_result,
                    "processed_at": datetime.utcnow().isoformat(),
                },
            )
            await db.commit()

        logger.info(f"[ai] Article {article_id} processed — score={fr_result.get('score')}")
        return True

    except Exception as e:
        logger.error(f"[ai] Failed to process article {article_id}: {e}")
        return False


async def process_pending_articles() -> dict:
    """Process all articles that haven't been through AI yet."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, title_raw, content_raw FROM articles
            WHERE ai_processed_at IS NULL
            AND (title_raw IS NOT NULL OR content_raw IS NOT NULL)
            ORDER BY scraped_at DESC
            LIMIT 20
            """
        )
        pending = await cursor.fetchall()

    if not pending:
        logger.info("[ai] No pending articles to process.")
        return {"processed": 0}

    logger.info(f"[ai] Processing {len(pending)} articles...")

    results = []
    for i in range(0, len(pending), 5):
        batch = pending[i:i+5]
        batch_results = await asyncio.gather(*[
            process_article(row["id"], row["title_raw"] or "", row["content_raw"] or "")
            for row in batch
        ])
        results.extend(batch_results)
        if i + 5 < len(pending):
            await asyncio.sleep(2)

    success = sum(1 for r in results if r)
    return {"processed": len(pending), "success": success, "failed": len(pending) - success}
