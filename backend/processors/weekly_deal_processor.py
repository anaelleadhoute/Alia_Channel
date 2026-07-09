import json
import logging
import os
from datetime import datetime

import anthropic

from db.database import get_db
from scrapers.supermarket_scraper import fetch_all_supermarket_data

logger = logging.getLogger(__name__)
client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SUPERMARKET_LINKS = {
    "shufersal": "https://www.shufersal.co.il/online/he/specials",
    "rami_levy": "https://www.rami-levy.co.il/he/online/sales",
    "carrefour": "https://www.carrefour.co.il/specials",
}

PICK_DEAL_PROMPT = """Tu es expert en promotions supermarché en Israël pour des olim (immigrés).

Voici les dernières promotions disponibles chez {supermarket_name} :
{items_text}

Sélectionne le MEILLEUR deal de la semaine pour des familles d'olim.
Critères : réduction significative, produit courant (nourriture, hygiène, etc.), pas trop niche.

Réponds UNIQUEMENT en JSON :
{{
  "product": "nom du produit en hébreu ou français",
  "price": "prix ou réduction (ex: 9.90₪, -30%)",
  "description": "une phrase décrivant l'offre"
}}

Si aucune promotion claire n'est trouvée, réponds : {{"product": null, "price": null, "description": null}}"""

COMBINED_FR_PROMPT = """Tu es rédacteur pour AL.IA Channel, média pour les olim francophones en Israël.

Voici les meilleurs deals de la semaine dans les supermarchés :

🔵 Shufersal : {shufersal}
🟢 Rami Levy : {rami_levy}
🔴 Carrefour : {carrefour}

Rédige UN message WhatsApp en français (120-150 mots) présentant ces 3 deals.
- Titre : "🛒 Deals de la semaine — AL.IA a trouvé pour vous !"
- Présente chaque supermarché avec son emoji et le deal clairement
- Inclus les liens :
  • Shufersal : {link_shufersal}
  • Rami Levy : {link_rami}
  • Carrefour : {link_carrefour}
- Termine par : "AL.IA Community 👉 wa.me/972549675013"
- Ton chaleureux, pas publicitaire

Réponds uniquement avec le texte du message."""

COMBINED_RU_PROMPT = """Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот лучшие акции недели в супермаркетах :

🔵 Shufersal : {shufersal}
🟢 Rami Levy : {rami_levy}
🔴 Carrefour : {carrefour}

Напиши ОДНО сообщение для WhatsApp на русском (120-150 слов) с этими 3 акциями.
- Заголовок : "🛒 Акции недели — AL.IA нашла для вас !"
- Представь каждый супермаркет с эмодзи и акцией чётко
- Включи ссылки :
  • Shufersal : {link_shufersal}
  • Rami Levy : {link_rami}
  • Carrefour : {link_carrefour}
- Заверши : "AL.IA Community 👉 wa.me/972549675013"
- Тёплый тон, без рекламного пафоса

Отвечай только текстом сообщения."""


async def _pick_best_deal(supermarket_name: str, items: list[dict]) -> dict:
    """Ask Claude to pick the best deal from a list of scraped items."""
    if not items:
        return {"product": None, "price": None, "description": f"Aucune promo trouvée"}

    items_text = "\n".join(f"- {item['text']}" for item in items[:15])

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": PICK_DEAL_PROMPT.format(
                supermarket_name=supermarket_name,
                items_text=items_text,
            )}],
        )
        import re
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        logger.error(f"[weekly_deal] Pick deal failed for {supermarket_name}: {e}")
        return {"product": None, "price": None, "description": None}


def _format_deal(deal: dict) -> str:
    if not deal.get("product"):
        return "Aucune promo disponible cette semaine"
    parts = [deal["product"]]
    if deal.get("price"):
        parts.append(f"à {deal['price']}")
    if deal.get("description"):
        parts.append(f"— {deal['description']}")
    return " ".join(parts)


async def generate_weekly_deals(raw_data: dict | None = None) -> dict:
    """Full pipeline: scrape → pick best deal per super → generate combined FR+RU message.

    raw_data: pre-scraped items dict (from local Mac scraper). If None, scrapes automatically.
    """
    week = datetime.utcnow().strftime("%Y-W%W")

    # Check if already generated this week
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM weekly_deals WHERE week = ?", (week,))
        existing = await cursor.fetchone()
    if existing:
        return {"status": "skipped", "week": week, "weekly_deal_id": existing["id"]}

    if raw_data is None:
        logger.info("[weekly_deal] Scraping supermarkets automatically...")
        raw_data = await fetch_all_supermarket_data()

    # Pick best deal per supermarket (in parallel)
    import asyncio
    shufersal_deal, rami_deal, carrefour_deal = await asyncio.gather(
        _pick_best_deal("Shufersal", raw_data["shufersal"]),
        _pick_best_deal("Rami Levy", raw_data["rami_levy"]),
        _pick_best_deal("Carrefour", raw_data["carrefour"]),
    )

    shufersal_str = _format_deal(shufersal_deal)
    rami_str = _format_deal(rami_deal)
    carrefour_str = _format_deal(carrefour_deal)

    # Generate combined messages
    logger.info("[weekly_deal] Generating FR + RU messages...")
    fr_response, ru_response = await asyncio.gather(
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": COMBINED_FR_PROMPT.format(
                shufersal=shufersal_str,
                rami_levy=rami_str,
                carrefour=carrefour_str,
                link_shufersal=SUPERMARKET_LINKS["shufersal"],
                link_rami=SUPERMARKET_LINKS["rami_levy"],
                link_carrefour=SUPERMARKET_LINKS["carrefour"],
            )}],
        ),
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": COMBINED_RU_PROMPT.format(
                shufersal=shufersal_str,
                rami_levy=rami_str,
                carrefour=carrefour_str,
                link_shufersal=SUPERMARKET_LINKS["shufersal"],
                link_rami=SUPERMARKET_LINKS["rami_levy"],
                link_carrefour=SUPERMARKET_LINKS["carrefour"],
            )}],
        ),
    )

    content_fr = fr_response.content[0].text.strip()
    content_ru = ru_response.content[0].text.strip()

    # Save to DB
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO weekly_deals
               (week, shufersal_json, rami_levy_json, carrefour_json, content_fr, content_ru, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                week,
                json.dumps(shufersal_deal, ensure_ascii=False),
                json.dumps(rami_deal, ensure_ascii=False),
                json.dumps(carrefour_deal, ensure_ascii=False),
                content_fr,
                content_ru,
                datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()
        weekly_deal_id = cursor.lastrowid

    logger.info(f"[weekly_deal] Generated weekly deal #{weekly_deal_id} for {week}")
    return {
        "status": "generated",
        "week": week,
        "weekly_deal_id": weekly_deal_id,
        "deals": {
            "shufersal": shufersal_str,
            "rami_levy": rami_str,
            "carrefour": carrefour_str,
        },
    }
