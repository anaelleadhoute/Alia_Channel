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

Voici un bon plan à présenter :
Produit/Service : {product}
Prix : {price}
Résumé : {summary}
Texte original : {raw_text}
Lien direct : {deal_link}

Rédige un message WhatsApp en français en suivant EXACTEMENT ce format :

💙 Le Bon Plan Alia

La vie en Israël est chère, surtout quand on est olé.

C'est pourquoi Alia partage régulièrement des bons plans qui valent vraiment le coup.

🚫 Ce post n'est pas sponsorisé.

👇

[Présente le produit clairement : nom, prix, réduction si applicable. 2-3 lignes max. Inclus le lien : {deal_link}]

📢 Rejoignez la communauté Alia pour découvrir chaque semaine de nouveaux bons plans.

🤖 Des questions ? Parlez à Alia :
https://wa.me/972549675013?text=Aide-moi

Réponds uniquement avec le texte du message, sans JSON, sans commentaire."""

PROMPT_RU = """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот акция для публикации :
Товар/Услуга : {product}
Цена : {price}
Описание : {summary}
Оригинальный текст : {raw_text}
Прямая ссылка : {deal_link}

Напиши сообщение для WhatsApp на русском, строго следуя этому формату :

💙 Выгодное предложение от Alia

Жизнь в Израиле дорогая, особенно для олим.

Поэтому Alia регулярно делится предложениями, которые действительно стоят внимания.

🚫 Этот пост не спонсируется.

👇

[Представь товар чётко: название, цена, скидка если есть. Максимум 2-3 строки. Включи ссылку: {deal_link}]

📢 Присоединяйтесь к сообществу Alia, чтобы каждую неделю узнавать о новых выгодных предложениях.

🤖 Есть вопросы? Напишите Alia :
https://wa.me/972549675013?text=Помоги

Отвечай только текстом сообщения, без JSON, без комментариев."""


CHANNEL_WEBSITES = {
    "shufersaloffocial": "https://www.shufersal.co.il",
    "payngoil":          "https://www.payngo.co.il",
    "SecretFlights":     "https://www.secretflights.co.il",
    "hotelscoil":        "https://www.hotels.co.il",
}


def _deal_link(deal: dict) -> str:
    """Extract direct URL from raw text, fall back to channel website."""
    raw = deal.get("raw_text") or ""
    # Full URL with protocol
    match = re.search(r'https?://[^\s\)\]"\']+', raw)
    if match:
        return match.group(0)
    # Short URL without protocol (e.g. shufersal.club/xxx)
    match = re.search(r'\b[\w-]+\.\w{2,6}/\S+', raw)
    if match:
        return "https://" + match.group(0)
    # Fall back to channel website
    channel = deal.get("channel", "")
    return CHANNEL_WEBSITES.get(channel, f"https://t.me/{channel}")


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
            deal_link=_deal_link(deal),
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
            deal_link=_deal_link(deal),
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
            SELECT id, message_id, channel, category, deal_product, deal_price,
                   deal_summary_he, raw_text, audience
            FROM deals
            WHERE is_relevant = 1 AND ai_processed_at IS NULL
            AND scraped_at >= datetime('now', '-2 hours')
            ORDER BY relevance_score DESC
            """
        )
        pending = await cursor.fetchall()

    if not pending:
        logger.info("[deal_processor] No pending deals.")
        return {"processed": 0}

    success = 0
    deal_ids = []
    for row in pending:
        result = await process_deal(row["id"], dict(row))
        if result:
            success += 1
            deal_ids.append(row["id"])

    return {"processed": len(pending), "success": success, "deal_ids": deal_ids}


async def pick_best_deal(deal_ids: list[int]) -> int | None:
    """Ask Claude to pick the single best deal from a list of processed deals. Flights are low priority."""
    if not deal_ids:
        return None
    if len(deal_ids) == 1:
        return deal_ids[0]

    async with get_db() as db:
        placeholders = ",".join("?" * len(deal_ids))
        cursor = await db.execute(
            f"SELECT id, category, deal_product, deal_price, relevance_score FROM deals WHERE id IN ({placeholders})",
            deal_ids,
        )
        rows = await cursor.fetchall()

    candidates = "\n".join(
        f"{i+1}. [id={r['id']}] {r['category']} | {r['deal_product']} | {r['deal_price']} | score={r['relevance_score']}"
        for i, r in enumerate(rows)
    )

    prompt = f"""Tu es éditeur pour AL.IA Channel, une communauté WhatsApp pour les olim en Israël.

Voici les deals disponibles cette semaine :
{candidates}

Choisis UN SEUL deal à envoyer à la communauté. Critères :
- Pertinence maximale pour les olim (produits du quotidien, bons pour familles)
- Les vols (flights) sont basse priorité — ne les choisis que s'il n'y a rien de mieux
- Le meilleur rapport qualité/prix et utilité

Réponds UNIQUEMENT avec le chiffre de l'id du deal choisi. Exemple : 42"""

    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        chosen_id = int(resp.content[0].text.strip())
        if chosen_id in deal_ids:
            return chosen_id
    except Exception:
        pass
    # Fallback: first non-flight deal, or first deal
    for r in rows:
        if r["category"] != "flights":
            return r["id"]
    return rows[0]["id"]
