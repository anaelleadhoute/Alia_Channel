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
    print("[rami_levy] Loading sales page (intercepting API calls)...")
    api_data = []

    def handle_response(response):
        url = response.url
        # Rami Levy's React app calls their product API — capture it
        if "rami-levy.co.il" in url and any(k in url for k in ["/api/", "catalog", "items", "sale", "product"]):
            try:
                body = response.json()
                api_data.append({"url": url, "body": body})
                print(f"  [rami_levy] Captured API: {url[:80]}")
            except Exception:
                pass

    page.on("response", handle_response)
    page.goto("https://www.rami-levy.co.il/he/online/sales", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)

    # Try to extract from intercepted API responses
    items = []
    for capture in api_data:
        body = capture["body"]
        # Common patterns in Israeli supermarket APIs
        products = (
            body.get("data") or body.get("items") or body.get("products") or
            body.get("result") or (body if isinstance(body, list) else [])
        )
        if isinstance(products, list):
            for p in products[:30]:
                if isinstance(p, dict):
                    name = p.get("name") or p.get("Name") or p.get("title") or ""
                    price = p.get("price") or p.get("Price") or p.get("salePrice") or ""
                    if name:
                        items.append({"text": f"{name} - {price}₪".strip(" -₪") + ("₪" if price else "")})

    # Fallback: parse the rendered DOM
    if not items:
        items = page.evaluate("""() => {
            const results = [];
            // Rami Levy uses data-testid or specific class patterns
            const selectors = [
                '[data-testid*="product"]',
                '[class*="ProductCard"]',
                '[class*="product-card"]',
                '[class*="ProductItem"]',
                '.product',
            ];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(card => {
                    const text = card.innerText.replace(/\\s+/g, ' ').trim();
                    if (text.length > 10 && text.length < 300 && (text.includes('₪') || text.includes('%'))) {
                        results.push({ text });
                    }
                });
                if (results.length > 0) break;
            }
            // Last resort: all text nodes with prices
            if (results.length === 0) {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                const seen = new Set();
                while ((node = walker.nextNode()) && results.length < 30) {
                    const t = node.textContent.trim();
                    if (t.length > 5 && t.length < 150 && t.includes('₪') && !seen.has(t)) {
                        seen.add(t);
                        results.push({ text: t });
                    }
                }
            }
            return results.slice(0, 30);
        }""")

    # Debug: dump page title and URL if still empty
    if not items:
        title = page.title()
        print(f"  [rami_levy] Page title: {title} | URL: {page.url}")
        print(f"  [rami_levy] API calls captured: {len(api_data)}")
        for c in api_data[:3]:
            print(f"    → {c['url'][:100]}")

    print(f"[rami_levy] Found {len(items)} items")
    return items


def scrape_hazi_hinam(page) -> list[dict]:
    print("[hazi_hinam] Loading campaign page...")
    api_data = []

    def handle_response(response):
        url = response.url
        if "hazi-hinam.co.il" in url and "/proxy/api/" in url:
            try:
                body = response.json()
                api_data.append({"url": url, "body": body})
                print(f"  [hazi_hinam] Captured API: {url[:100]}")
            except Exception:
                pass

    page.on("response", handle_response)
    # Homepage already fires getItemsPromoted — no need for campaign URL
    page.goto("https://shop.hazi-hinam.co.il/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)

    items = []
    for capture in api_data:
        url = capture["url"]
        body = capture["body"]
        if "getItemsPromoted" not in url and "GetItemsPromoted" not in url:
            continue

        results = body.get("Results") or body
        raw = results.get("PromotedItems") or results.get("Items") or results.get("items") or []
        print(f"  [hazi_hinam] PromotedItems type: {type(raw)}, value preview: {str(raw)[:200]}")
        # Flatten: if it's a dict of lists, merge them
        if isinstance(raw, dict):
            products = []
            for v in raw.values():
                if isinstance(v, list):
                    products.extend(v)
        elif isinstance(raw, list):
            products = raw
        else:
            products = []
        for p in products[:30]:
            if not isinstance(p, dict):
                continue
            name = p.get("Name") or p.get("name") or p.get("ShortName") or ""
            price = p.get("SalePrice") or p.get("Price") or p.get("price") or ""
            discount = p.get("DiscountPercent") or p.get("Discount") or ""
            if name:
                suffix = f" - {price}₪" if price else ""
                if discount:
                    suffix += f" (-{discount}%)"
                items.append({"text": f"{name}{suffix}"})
        if items:
            break

    if not items:
        print(f"  [hazi_hinam] Could not parse items. API calls: {[c['url'] for c in api_data]}")

    print(f"[hazi_hinam] Found {len(items)} items")
    return items


def scrape_carrefour(page) -> list[dict]:
    print("[carrefour] Loading specials page (intercepting API calls)...")
    api_data = []

    def handle_response(response):
        url = response.url
        if "carrefour.co.il" in url and any(k in url for k in ["/api/", "catalog", "special", "product", "promo"]):
            try:
                body = response.json()
                api_data.append({"url": url, "body": body})
                print(f"  [carrefour] Captured API: {url[:80]}")
            except Exception:
                pass

    page.on("response", handle_response)
    page.goto("https://www.carrefour.co.il/specials", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)

    items = []
    for capture in api_data:
        body = capture["body"]
        products = (
            body.get("data") or body.get("items") or body.get("products") or
            body.get("result") or (body if isinstance(body, list) else [])
        )
        if isinstance(products, list):
            for p in products[:30]:
                if isinstance(p, dict):
                    name = p.get("name") or p.get("title") or ""
                    price = p.get("price") or p.get("salePrice") or p.get("specialPrice") or ""
                    if name:
                        items.append({"text": f"{name} - {price}₪".strip(" -₪") + ("₪" if price else "")})

    if not items:
        items = page.evaluate("""() => {
            const results = [];
            const selectors = [
                '[data-testid*="product"]',
                '[class*="ProductCard"]',
                '[class*="product-card"]',
                '[class*="ProductItem"]',
                '[class*="SpecialItem"]',
                '.product', '.special',
            ];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(card => {
                    const text = card.innerText.replace(/\\s+/g, ' ').trim();
                    if (text.length > 10 && text.length < 300 && (text.includes('₪') || text.includes('%'))) {
                        results.push({ text });
                    }
                });
                if (results.length > 0) break;
            }
            if (results.length === 0) {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                const seen = new Set();
                while ((node = walker.nextNode()) && results.length < 30) {
                    const t = node.textContent.trim();
                    if (t.length > 5 && t.length < 150 && (t.includes('₪') || t.includes('%')) && !seen.has(t)) {
                        seen.add(t);
                        results.push({ text: t });
                    }
                }
            }
            return results.slice(0, 30);
        }""")

    if not items:
        title = page.title()
        print(f"  [carrefour] Page title: {title} | URL: {page.url}")
        print(f"  [carrefour] API calls captured: {len(api_data)}")
        for c in api_data[:3]:
            print(f"    → {c['url'][:100]}")

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
    import sys
    debug = "--debug" in sys.argv
    force = "--force" in sys.argv
    print("=== AL.IA Supermarket Deal Scraper ===")

    # Shufersal via httpx (no browser needed)
    shufersal_items = scrape_shufersal_telegram()

    # Rami Levy + Carrefour via Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="he-IL",
            extra_http_headers={"Accept-Language": "he-IL,he;q=0.9"},
        )
        page = context.new_page()

        try:
            rami_levy_items = scrape_rami_levy(page)
            if debug and not rami_levy_items:
                page.screenshot(path="/tmp/rami_levy_debug.png")
                print("  [debug] Screenshot saved to /tmp/rami_levy_debug.png")
        except Exception as e:
            print(f"[rami_levy] Failed: {e}")
            rami_levy_items = []

        try:
            hazi_hinam_items = scrape_hazi_hinam(page)
            if debug and not hazi_hinam_items:
                page.screenshot(path="/tmp/hazi_hinam_debug.png")
                print("  [debug] Screenshot saved to /tmp/hazi_hinam_debug.png")
        except Exception as e:
            print(f"[hazi_hinam] Failed: {e}")
            hazi_hinam_items = []

        browser.close()

    payload = {
        "shufersal": shufersal_items,
        "rami_levy": rami_levy_items,
        "carrefour": hazi_hinam_items,  # reuses carrefour slot in API
        "force": force,
    }

    print(f"\n[send] Shufersal: {len(shufersal_items)} | Rami Levy: {len(rami_levy_items)} | Hazi Hinam: {len(hazi_hinam_items)}")
    print("[send] Sending to server...")

    with httpx.Client(timeout=60) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        result = resp.json()

    print(f"[done] Server response: {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    run()
