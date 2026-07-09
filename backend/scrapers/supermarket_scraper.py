import json
import logging
import re
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}


async def scrape_shufersal_telegram() -> list[dict]:
    """Scrape Shufersal deals from their public Telegram channel."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://t.me/s/shufersaloffocial", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            logger.error(f"[supermarket] Shufersal Telegram failed: {resp.status_code}")
            return []
        return _parse_telegram_messages(resp.text)
    except Exception as e:
        logger.error(f"[supermarket] Shufersal scrape error: {e}")
        return []


def _parse_telegram_messages(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for msg in soup.find_all("div", attrs={"data-post": True}):
        text_el = msg.select_one(".tgme_widget_message_text")
        text = text_el.get_text(separator="\n", strip=True) if text_el else ""
        if text:
            items.append({"text": text})
    return items[-10:]  # last 10 messages


async def scrape_rami_levy() -> list[dict]:
    """Scrape Rami Levy weekly sales page."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.rami-levy.co.il/he/online/sales",
                headers=HEADERS, timeout=20, follow_redirects=True
            )
        if resp.status_code != 200:
            logger.error(f"[supermarket] Rami Levy failed: {resp.status_code}")
            return []
        return _extract_items_from_html(resp.text, "rami-levy.co.il")
    except Exception as e:
        logger.error(f"[supermarket] Rami Levy scrape error: {e}")
        return []


async def scrape_carrefour() -> list[dict]:
    """Scrape Carrefour Israel specials page."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.carrefour.co.il/specials",
                headers=HEADERS, timeout=20, follow_redirects=True
            )
        if resp.status_code != 200:
            logger.error(f"[supermarket] Carrefour failed: {resp.status_code}")
            return []
        return _extract_items_from_html(resp.text, "carrefour.co.il")
    except Exception as e:
        logger.error(f"[supermarket] Carrefour scrape error: {e}")
        return []


def _extract_items_from_html(html: str, domain: str) -> list[dict]:
    """Extract product text and prices from HTML. Works with both static and partial SSR pages."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Try JSON-LD structured data first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") in ("Product", "Offer"):
                        items.append({
                            "text": f"{item.get('name', '')} - {item.get('offers', {}).get('price', '')} ₪"
                        })
            elif data.get("@type") == "ItemList":
                for elem in data.get("itemListElement", []):
                    name = elem.get("name") or elem.get("item", {}).get("name", "")
                    if name:
                        items.append({"text": name})
        except Exception:
            pass

    # Try embedded __NEXT_DATA__ or window.__STATE__
    for script in soup.find_all("script"):
        src = script.string or ""
        if "__NEXT_DATA__" in src:
            try:
                match = re.search(r'__NEXT_DATA__\s*=\s*(\{.*?\})\s*;?\s*\n', src, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    # Flatten all strings that look like product names
                    flat = json.dumps(data, ensure_ascii=False)
                    prices = re.findall(r'"name"\s*:\s*"([^"]{5,60})".*?"price"\s*:\s*"?(\d+[\.,]?\d*)"?', flat)
                    for name, price in prices[:20]:
                        items.append({"text": f"{name} - {price} ₪"})
            except Exception:
                pass

    if items:
        return items[:20]

    # Generic fallback: find elements that look like product cards
    for el in soup.select("[class*='product'], [class*='item'], [class*='deal'], [class*='sale'], [class*='promo']"):
        text = el.get_text(separator=" ", strip=True)
        # Filter: must contain a shekel price or discount
        if re.search(r'₪|\d+\s*%|\d+\.\d{2}', text) and 10 < len(text) < 300:
            items.append({"text": text[:300]})

    if not items:
        # Last resort: extract all visible text blocks containing prices
        body_text = soup.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in body_text.splitlines() if re.search(r'₪|\d+\s*%', l) and len(l) > 8]
        items = [{"text": l} for l in lines[:20]]

    logger.info(f"[supermarket] Extracted {len(items)} items from {domain}")
    return items[:20]


async def fetch_all_supermarket_data() -> dict:
    """Fetch raw deal data from all 3 supermarkets."""
    import asyncio
    shufersal_task = scrape_shufersal_telegram()
    rami_task = scrape_rami_levy()
    carrefour_task = scrape_carrefour()

    shufersal, rami_levy, carrefour = await asyncio.gather(
        shufersal_task, rami_task, carrefour_task, return_exceptions=True
    )

    def safe(result, name):
        if isinstance(result, Exception):
            logger.error(f"[supermarket] {name} failed: {result}")
            return []
        return result or []

    return {
        "shufersal": safe(shufersal, "Shufersal"),
        "rami_levy": safe(rami_levy, "Rami Levy"),
        "carrefour": safe(carrefour, "Carrefour"),
    }
