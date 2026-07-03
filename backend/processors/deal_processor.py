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

CATEGORY_LABELS = {
    "supermarket": {"fr": "🛒 Promo supermarché", "ru": "🛒 Акция в супермаркете"},
    "electronics": {"fr": "📱 Bon plan électronique", "ru": "📱 Скидка на электронику"},
    "flights":     {"fr": "✈️ Bon plan vol",         "ru": "✈️ Дешёвые авиабилеты"},
    "hotels":      {"fr": "🏨 Bon plan hôtel",        "ru": "🏨 Скидка на отель"},
}

PROMPT_FR = """Tu es rédacteur pour AL.IA Channel, un média pour les olim francophones en Israël.

Voici un bon plan trouvé en Israël :
Catégorie : {category_label}
Produit/Service : {product}
Prix : {price}
Résumé : {summary}
Texte original : {raw_text}

Rédige un message WhatsApp en français (80-120 mots) pour présenter ce bon plan aux olim.
- Commence par l'emoji de catégorie et un titre accrocheur
- Explique le bon plan clairement (produit, prix, économie réalisée)
- Ajoute une phrase d'appel à l'action
- Termine par : "AL.IA Community 👉 wa.me/972549675013"

Réponds uniquement avec le texte du message, sans JSON."""

PROMPT_RU = """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот акция найденная в Израиле :
Категория : {category_label}
Товар/Услуга : {product}
Цена : {price}
Описание : {summary}
Оригинальный текст : {raw_text}

Напиши сообщение для WhatsApp на русском (80-120 слов) об этой акции для олим.
- Начни с эмодзи категории и привлекательного заголовка
- Объясни акцию чётко (товар, цена, экономия)
- Добавь призыв к действию
- Заверши : "AL.IA Community 👉 wa.me/972549675013"

Отвечай только текстом сообщения, без JSON."""


async def _generate_fr(deal: dict) -> str:
    category = deal.get("category", "")
    label = CATEGORY_LABELS.get(category, {}).get("fr", category)
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": PROMPT_FR.format(
            category_label=label,
            product=deal.get("deal_product") or "N/A",
            price=deal.get("deal_price") or "N/A",
            summary=deal.get("deal_summary_he") or "",
            raw_text=deal.get("raw_text") or "",
        )}],
    )
    return response.content[0].text.strip()


async def _generate_ru(deal: dict) -> str:
    category = deal.get("category", "")
    label = CATEGORY_LABELS.get(category, {}).get("ru", category)
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": PROMPT_RU.format(
            category_label=label,
            product=deal.get("deal_product") or "N/A",
            price=deal.get("deal_price") or "N/A",
            summary=deal.get("deal_summary_he") or "",
            raw_text=deal.get("raw_text") or "",
        )}],
    )
    return response.content[0].text.strip()


async def process_deal(deal_id: int, deal: dict) -> bool:
    try:
        audience = deal.get("audience", "both")
        tasks = []
        if audience in ("fr", "both"):
            tasks.append(_generate_fr(deal))
        else:
            tasks.append(None)
        if audience in ("ru", "both"):
            tasks.append(_generate_ru(deal))
        else:
            tasks.append(None)

        results = await asyncio.gather(*[t for t in tasks if t is not None], return_exceptions=True)

        idx = 0
        content_fr = None
        content_ru = None
        if tasks[0] is not None:
            if isinstance(results[idx], Exception):
                raise results[idx]
            content_fr = results[idx]
            idx += 1
        if tasks[1] is not None:
            if isinstance(results[idx], Exception):
                raise results[idx]
            content_ru = results[idx]

        async with get_db() as db:
            await db.execute(
                """
                UPDATE deals SET
                    content_fr = ?,
                    content_ru = ?,
                    ai_processed_at = ?
                WHERE id = ?
                """,
                (content_fr, content_ru, datetime.utcnow().isoformat(), deal_id),
            )
            await db.commit()

        logger.info(f"[deal_processor] Deal {deal_id} processed in FR + RU")
        return True

    except Exception as e:
        logger.error(f"[deal_processor] Failed to process deal {deal_id}: {e}")
        return False


async def process_pending_deals() -> dict:
    """Process all deals that haven't been through AI yet."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, category, deal_product, deal_price,
                   deal_summary_he, raw_text
            FROM deals
            WHERE is_relevant = 1 AND ai_processed_at IS NULL
            ORDER BY relevance_score DESC
            """
        )
        pending = await cursor.fetchall()

    if not pending:
        logger.info("[deal_processor] No pending deals.")
        return {"processed": 0}

    success = 0
    for row in pending:
        result = await process_deal(row["id"], dict(row))
        if result:
            success += 1

    return {"processed": len(pending), "success": success}
