import asyncio
import base64
import logging
import os
from datetime import datetime

import anthropic
import httpx

from db.database import get_db

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

TELEGRAM_CHANNELS = [
    {"username": "shufersaloffocial", "category": "supermarket"},
    {"username": "payngoil",          "category": "electronics"},
    {"username": "SecretFlights",     "category": "flights"},
    {"username": "ivorycoil",         "category": "deals"},
]

RELEVANCE_PROMPT = """You are a content curator for AL.IA Channel, a media platform for French-speaking and Russian-speaking olim (immigrants) in Israel.

Today's date is {today}.

Analyze this deal from a Telegram channel (category: {category}).

{content}

IMPORTANT: If the deal has an expiry date and it has already passed (before today), set is_relevant to false and explain in reason.

Answer in JSON only:
{{
  "is_relevant": true/false,
  "relevance_score": 1-10,
  "audience": "fr" | "ru" | "both",
  "reason": "one sentence why relevant or not for olim in Israel (mention if expired)",
  "deal_summary_he": "short deal summary in Hebrew if extractable, else null",
  "deal_price": "price if visible, else null",
  "deal_product": "product or service name if visible, else null"
}}

audience: "fr" if only relevant to French speakers (e.g. flights to Paris), "ru" if only relevant to Russian speakers (e.g. flights to Moscow), "both" for everything else.

Relevance scoring hierarchy (apply to BOTH FR and RU audiences unless destination is specific):
- Flights to France/French-speaking countries (Paris, etc.) → score 10 for FR audience
- Flights to Russia, Ukraine, or CIS countries → score 10 for RU audience
- Electronics deals (appliances, TV, phone) → score 8
- Supermarket / food deals → score 7
- Hotels in Israel → score 6
- Anything else useful for olim → score 5
- Not useful for olim OR expired → score 1-3, is_relevant: false

Score 7+ = worth publishing. Score below 7 = skip."""


async def _get_last_seen_id(username: str) -> int:
    """Get the last processed message ID for a channel."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT MAX(CAST(message_id AS INTEGER)) FROM deals WHERE channel = ?",
            (username,),
        )
        row = await cursor.fetchone()
        return row[0] or 0


async def _fetch_channel_messages(username: str, limit: int = 30) -> list[dict]:
    """
    Fetch recent posts from a public Telegram channel.
    Uses the Telegram Bot API with the channel joined by the bot.
    """
    async with httpx.AsyncClient() as client:
        # The bot must be added to the channel as admin to read messages
        # Alternative: use Telegram's public preview
        resp = await client.get(
            f"https://t.me/s/{username}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.error(f"[telegram] Failed to fetch @{username}: {resp.status_code}")
            return []

        return _parse_tme_html(resp.text, username)


def _parse_tme_html(html: str, username: str) -> list[dict]:
    """Parse t.me/s/channel HTML to extract messages and image URLs."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    messages = []

    for wrap in soup.find_all("div", class_="tgme_widget_message_wrap"):
        msg = wrap.find("div", attrs={"data-post": True})
        if not msg:
            continue
        msg_id = msg.get("data-post", "").split("/")[-1]
        text_el = msg.select_one(".tgme_widget_message_text")
        text = text_el.get_text(separator="\n", strip=True) if text_el else ""

        # Extract image URLs from background-image style
        images = []
        for img_el in wrap.select(".tgme_widget_message_photo_wrap"):
            style = img_el.get("style", "")
            if "url('" in style:
                img_url = style.split("url('")[1].split("')")[0]
                if img_url:
                    images.append(img_url)

        # Extract all external links from the full wrap (includes inline buttons)
        button_links = []
        for a in wrap.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "t.me" not in href and not href.startswith("https://telegram"):
                button_links.append(href)

        if button_links:
            from html import unescape
            text = text + "\n" + "\n".join(unescape(lnk) for lnk in button_links)

        if text or images:
            messages.append({
                "id": msg_id,
                "username": username,
                "text": text,
                "images": images,
                "scraped_at": datetime.utcnow().isoformat(),
            })

    return messages


async def _analyze_deal(message: dict, category: str) -> dict | None:
    """Send message content to Claude to assess relevance for olim."""
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    content_parts = []

    # Add images if present
    for img_url in message.get("images", [])[:2]:
        try:
            async with httpx.AsyncClient() as http:
                img_resp = await http.get(img_url, timeout=15)
                if img_resp.status_code == 200:
                    img_b64 = base64.standard_b64encode(img_resp.content).decode()
                    content_type = img_resp.headers.get("content-type", "image/jpeg")
                    content_parts.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": content_type,
                            "data": img_b64,
                        },
                    })
        except Exception as e:
            logger.warning(f"[telegram] Could not fetch image {img_url}: {e}")

    # Add text
    content_description = f"Text: {message['text']}" if message["text"] else "No text, image only"
    content_parts.append({
        "type": "text",
        "text": RELEVANCE_PROMPT.format(
            today=datetime.utcnow().strftime("%Y-%m-%d"),
            category=category,
            content=content_description,
        ),
    })

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": content_parts}],
        )
        import json, re
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
        result["message_id"] = message["id"]
        result["channel"] = message["username"]
        result["category"] = category
        result["audience"] = result.get("audience", "both")
        result["raw_text"] = message["text"]
        result["images"] = message["images"]
        return result
    except Exception as e:
        logger.error(f"[telegram] Claude analysis failed: {e}")
        return None


async def _save_deal(deal: dict) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO deals (
                message_id, channel, category,
                relevance_score, is_relevant,
                deal_product, deal_price, deal_summary_he,
                raw_text, images_json, audience, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deal["message_id"],
                deal["channel"],
                deal["category"],
                deal.get("relevance_score", 0),
                1 if deal.get("is_relevant") else 0,
                deal.get("deal_product"),
                deal.get("deal_price"),
                deal.get("deal_summary_he"),
                deal.get("raw_text", ""),
                str(deal.get("images", [])),
                deal.get("audience", "both"),
                datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()


async def run_telegram_scraper(category_filter: str | None = None) -> dict:
    """
    Scrape all Telegram deal channels, analyze with Claude, save relevant deals.
    Optionally filter by category (supermarket, electronics, flights, hotels).
    """
    channels = TELEGRAM_CHANNELS
    if category_filter:
        channels = [c for c in channels if c["category"] == category_filter]

    total_scraped = 0
    total_relevant = 0

    for channel in channels:
        username = channel["username"]
        category = channel["category"]
        logger.info(f"[telegram] Scraping @{username} ({category})...")

        last_seen_id = await _get_last_seen_id(username)
        all_messages = await _fetch_channel_messages(username)

        # Keep only new messages (after last seen), take last 5
        new_messages = [
            m for m in all_messages
            if int(m["id"]) > last_seen_id
        ][-5:]

        logger.info(f"[telegram] {len(new_messages)} new messages from @{username} (last seen: {last_seen_id})")

        if not new_messages:
            continue

        tasks = [_analyze_deal(msg, category) for msg in new_messages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates = [
            r for r in results
            if not isinstance(r, Exception) and r is not None and r.get("is_relevant")
        ]
        total_scraped += len(candidates)

        if candidates:
            best = max(candidates, key=lambda r: r.get("relevance_score", 0))
            total_relevant += 1
            await _save_deal(best)

    return {
        "scraped": total_scraped,
        "relevant": total_relevant,
        "channels": len(channels),
    }
