import asyncio
import logging
import os
from datetime import datetime

import anthropic
import httpx
from bs4 import BeautifulSoup

from db.database import get_db

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


async def _fetch_content(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        resp = await client.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["nav", "header", "footer", "script", "style"]):
            tag.decompose()
        main = soup.find("div", class_="mw-parser-output") or soup.body
        return main.get_text(separator="\n", strip=True)[:4000] if main else ""


async def _get_past_tips(limit: int = 8) -> str:
    """Return a summary of recently sent tips to avoid repetition."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT source_url, content_fr FROM tips WHERE ai_processed_at IS NOT NULL ORDER BY scraped_at DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
    if not rows:
        return ""
    lines = "\n".join(f"- {row['source_url']} : {row['content_fr'][:120]}..." for row in rows)
    return f"\nÉvite ces sujets déjà envoyés ces 8 dernières semaines :\n{lines}\n"


async def process_tip(tip_id: int, source_url: str, raw_content: str) -> bool:
    """Generate FR + RU versions of a Kol Zchut tip."""
    try:
        if not raw_content:
            raw_content = await _fetch_content(source_url)

        past_tips = await _get_past_tips()
        past_tips_ru = past_tips.replace("Évite ces sujets déjà envoyés", "Избегай этих тем, уже отправленных")

        fr_prompt = f"""Tu es rédacteur pour AL.IA Channel, un média pour les olim francophones en Israël.

Voici du contenu issu d'une source officielle israélienne :
Source : {source_url}
Contenu : {raw_content[:3000]}
{past_tips}
Rédige un "Guide Alia" en français pour les nouveaux olim. Choisis UNE question concrète et fréquente liée à ce contenu.

Format EXACT à respecter :
📄 Le Guide Alia

Beaucoup d'utilisateurs d'Alia nous demandent :

"[La question fréquente entre guillemets]"

✅ [Réponse claire et concrète en 2-3 phrases]

⚠️ [Une mise en garde ou nuance importante, si pertinente]

🤖 Pour connaître la procédure adaptée à votre situation, demandez à Alia.
https://wa.me/972549675013?text=Aide-moi

📢 Rejoignez la communauté Alia pour recevoir d'autres guides pratiques :
https://tinyurl.com/Alia-community

Réponds uniquement avec le texte du guide, sans JSON, sans commentaire."""

        ru_prompt = f"""Ты редактор AL.IA Channel — медиа для русскоязычных олим в Израиле.

Вот контент из официального израильского источника :
Источник : {source_url}
Содержание : {raw_content[:3000]}
{past_tips_ru}
Напиши "Гид Alia" на русском для новых олим. Выбери ОДИН конкретный и частый вопрос по этой теме.

ТОЧНЫЙ формат :
📄 Гид Alia

Многие пользователи Alia спрашивают :

"[Частый вопрос в кавычках]"

✅ [Чёткий и конкретный ответ в 2-3 предложениях]

⚠️ [Важная оговорка или нюанс, если есть]

🤖 Чтобы узнать процедуру для вашей ситуации, спросите у Alia.
https://wa.me/972549675013?text=Помоги

📢 Присоединяйтесь к сообществу Alia, чтобы получать другие практические гиды :
https://tinyurl.com/Alia-community-RU

Отвечай только текстом гида, без JSON, без комментариев."""

        fr_response, ru_response = await asyncio.gather(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": fr_prompt}],
            ),
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": ru_prompt}],
            ),
        )

        content_fr = fr_response.content[0].text.strip()
        content_ru = ru_response.content[0].text.strip()

        async with get_db() as db:
            await db.execute(
                """
                UPDATE tips SET
                    content_fr = ?,
                    content_ru = ?,
                    ai_processed_at = ?
                WHERE id = ?
                """,
                (content_fr, content_ru, datetime.utcnow().isoformat(), tip_id),
            )
            await db.commit()

        logger.info(f"[tip_processor] Tip {tip_id} processed in FR + RU")
        return True

    except Exception as e:
        logger.error(f"[tip_processor] Failed to process tip {tip_id}: {e}")
        return False


async def process_pending_tips() -> dict:
    """Process all tips that haven't been through AI yet."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, source_url FROM tips
            WHERE ai_processed_at IS NULL
            ORDER BY scraped_at DESC
            """
        )
        pending = await cursor.fetchall()

    if not pending:
        logger.info("[tip_processor] No pending tips.")
        return {"processed": 0}

    results = []
    for row in pending:
        result = await process_tip(row["id"], row["source_url"], "")
        results.append(result)

    success = sum(1 for r in results if r)
    return {"processed": len(pending), "success": success}
