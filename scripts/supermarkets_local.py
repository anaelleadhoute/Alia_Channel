#!/usr/bin/env python3
"""
Supermarket deals local scraper — runs on your Mac (weekly).
Uses Playwright to render JS-heavy sites, extracts deals, sends to server.

Setup:
  pip3 install playwright httpx
  playwright install chromium

Run manually:
  python3 scripts/supermarkets_local.py

Or add to crontab (every Monday at 8am):
  0 8 * * 1 /usr/bin/python3 /Users/anaelleadhoute/Desktop/Alia_Community/scripts/supermarkets_local.py
"""

import httpx
import json
import re
from playwright.sync_api import sync_playwright

SERVER_URL = "https://alia-channel.com/api/scrape/supermarkets/manual"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}


def scrape_rami_levy(page) -> list[dict]:
    print("[rami_levy] Loading sales page...")
    page.goto("https://www.rami-levy.co.il/he/online/sales", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    items = page.evaluate("""() => {
        const results = [];
        // Try product cards
        const cards = document.querySelectorAll('[class*="product"], [class*="item"], [class*="card"]');
        cards.forEach(card => {
            const name = card.querySelector('[class*="name"], [class*="title"], h2, h3, h4');
            const price = card.querySelector('[class*="price"], [class*="cost"]');
            if (name && price) {
                results.push({
                    text: (name.innerText + ' - ' + price.innerText).replace(/\\s+/g, ' ').trim()
                });
            }
        });
        // Fallback: any element with ₪ sign
        if (results.length === 0) {
            document.querySelectorAll('*').forEach(el => {
                if (el.children.length === 0 && el.innerText && el.innerText.includes('₪')) {
                    const t = el.innerText.trim();
                    if (t.length > 5 && t.length < 200) results.push({ text: t });
                }
            });
        }
        return results.slice(0, 30);
    }""")

    print(f"[rami_levy] Found {len(items)} items")
    return items


def scrape_carrefour(page) -> list[dict]:
    print("[carrefour] Loading specials page...")
    page.goto("https://www.carrefour.co.il/specials", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    items = page.evaluate("""() => {
        const results = [];
        const cards = document.querySelectorAll('[class*="product"], [class*="item"], [class*="card"], [class*="deal"]');
        cards.forEach(card => {
            const name = card.querySelector('[class*="name"], [class*="title"], h2, h3, h4');
            const price = card.querySelector('[class*="price"], [class*="cost"]');
            if (name && price) {
                results.push({
                    text: (name.innerText + ' - ' + price.innerText).replace(/\\s+/g, ' ').trim()
                });
            }
        });
        if (results.length === 0) {
            document.querySelectorAll('*').forEach(el => {
                if (el.children.length === 0 && el.innerText && (el.innerText.includes('₪') || el.innerText.includes('%'))) {
                    const t = el.innerText.trim();
                    if (t.length > 5 && t.length < 200) results.push({ text: t });
                }
            });
        }
        return results.slice(0, 30);
    }""")

    print(f"[carrefour] Found {len(items)} items")
    return items


def scrape_shufersal_telegram() -> list[dict]:
    """Shufersal: use plain httpx (Telegram doesn't need JS)."""
    print("[shufersal] Fetching Telegram channel...")
    try:
        resp = httpx.get("https://t.me/s/shufersaloffocial", headers=HEADERS, timeout=15, follow_redirects=True)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []
        for msg in soup.find_all("div", attrs={"data-post": True}):
            text_el = msg.select_one(".tgme_widget_message_text")
            if text_el:
                text = text_el.get_text(separator=" ", strip=True)
                if text:
                    items.append({"text": text[:300]})
        items = items[-10:]
        print(f"[shufersal] Found {len(items)} messages")
        return items
    except Exception as e:
        print(f"[shufersal] Error: {e}")
        return []


def run():
    print("=== AL.IA Supermarket Deal Scraper ===")

    # Shufersal via httpx (no browser needed)
    shufersal_items = scrape_shufersal_telegram()

    # Rami Levy + Carrefour via Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="he-IL",
            extra_http_headers={"Accept-Language": "he-IL,he;q=0.9"},
        )
        page = context.new_page()

        try:
            rami_levy_items = scrape_rami_levy(page)
        except Exception as e:
            print(f"[rami_levy] Failed: {e}")
            rami_levy_items = []

        try:
            carrefour_items = scrape_carrefour(page)
        except Exception as e:
            print(f"[carrefour] Failed: {e}")
            carrefour_items = []

        browser.close()

    payload = {
        "shufersal": shufersal_items,
        "rami_levy": rami_levy_items,
        "carrefour": carrefour_items,
    }

    print(f"\n[send] Shufersal: {len(shufersal_items)} | Rami Levy: {len(rami_levy_items)} | Carrefour: {len(carrefour_items)}")
    print("[send] Sending to server...")

    with httpx.Client(timeout=60) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        result = resp.json()

    print(f"[done] Server response: {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    run()
