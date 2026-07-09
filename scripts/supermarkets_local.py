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
        if "rami-levy.co.il" in url and any(k in url for k in ["/api/", "catalog", "items", "sale", "product", "www-api"]):
            try:
                body = response.json()
                api_data.append({"url": url, "body": body})
                print(f"  [rami_levy] Captured API: {url[:80]}")
            except Exception:
                pass

    page.on("response", handle_response)
    try:
        page.goto("https://www.rami-levy.co.il/he/online/sales", wait_until="commit", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(8000)

    # If no API calls yet, scroll to trigger lazy load and wait more
    if not any("/api/sales" in c["url"] for c in api_data):
        page.evaluate("window.scrollBy(0, 600)")
        page.wait_for_timeout(5000)
        page.evaluate("window.scrollBy(0, 600)")
        page.wait_for_timeout(3000)

    items = []
    for capture in api_data:
        url = capture["url"]
        body = capture["body"]
        if "/api/sales" not in url:
            continue

        # Rami Levy sales API: {"data": [...products...]}
        products = body.get("data") or (body if isinstance(body, list) else [])
        if isinstance(products, list):
            for p in products[:30]:
                if not isinstance(p, dict):
                    continue
                name = p.get("name") or p.get("Name") or ""
                price = (p.get("price") or {})
                price_val = price.get("price") or price.get("sale_price") or price if not isinstance(price, dict) else ""
                if name:
                    items.append({"text": f"{name} - {price_val}₪" if price_val else name})
        if items:
            break

    if not items:
        print(f"  [rami_levy] API calls: {[c['url'] for c in api_data]}")

    print(f"[rami_levy] Found {len(items)} items")
    return items


def scrape_hazi_hinam(page) -> list[dict]:
    print("[hazi_hinam] Loading campaign page...")
    api_data = []

    def handle_response(response):
        url = response.url
        if "hazi-hinam.co.il" in url:
            try:
                body = response.json()
                api_data.append({"url": url, "body": body})
                print(f"  [hazi_hinam] Captured API: {url[:100]}")
            except Exception:
                pass

    page.on("response", handle_response)
    # Homepage fires getItemsPromoted — navigate there
    try:
        page.goto("https://shop.hazi-hinam.co.il/", wait_until="commit", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(12000)

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
            product_id = p.get("Id") or p.get("id") or ""
            barcode = p.get("BarKod") or p.get("Barcode") or ""
            if name:
                suffix = f" - {price}₪" if price else ""
                if discount:
                    suffix += f" (-{discount}%)"
                item = {"text": f"{name}{suffix}"}
                if product_id and barcode:
                    from urllib.parse import quote
                    name_slug = name.replace(" - ", "-").replace(" ", "-")
                    item["url"] = f"https://shop.hazi-hinam.co.il/catalog/products/{product_id}/{barcode}/{quote(name_slug, safe='-')}"
                items.append(item)
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


def scrape_shufersal(page) -> list[dict]:
    """Shufersal: scrape promo page via Playwright, intercept API calls."""
    print("[shufersal] Loading promo page...")
    api_data = []

    def handle_response(response):
        url = response.url
        if "shufersal.co.il" in url and ("json" in response.headers.get("content-type", "") or any(k in url for k in ["/api/", "product", "promo", "sale", "catalog", "search", "online"])):
            try:
                body = response.json()
                api_data.append({"url": url, "body": body})
                print(f"  [shufersal] Captured API: {url[:100]}")
            except Exception:
                pass

    page.on("response", handle_response)
    try:
        page.goto("https://www.shufersal.co.il/online/he/promo/A", wait_until="commit", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(4000)
    # Scroll to trigger lazy-loaded product catalog
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 800)")
        page.wait_for_timeout(800)

    items = []
    for capture in api_data:
        url = capture["url"]
        body = capture["body"]
        # Try to find product lists in common response shapes
        products = None
        if isinstance(body, dict):
            products = (
                body.get("products") or body.get("items") or body.get("results") or
                body.get("Products") or body.get("Items") or
                body.get("data", {}).get("products") if isinstance(body.get("data"), dict) else None
            )
        elif isinstance(body, list):
            products = body
        if isinstance(products, list):
            for p in products[:30]:
                if not isinstance(p, dict):
                    continue
                name = p.get("name") or p.get("Name") or p.get("title") or ""
                price = p.get("price") or p.get("Price") or p.get("salePrice") or ""
                if name and (price or "₪" in str(p)):
                    items.append({"text": f"{name} - {price}₪" if price else name})
            if items:
                break

    # DOM fallback
    if not items:
        items = page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('[class*="product"], [class*="item"], [data-product]').forEach(card => {
                const text = card.innerText.replace(/\\s+/g, ' ').trim();
                if (text.length > 10 && text.length < 300 && text.includes('₪')) {
                    results.push({ text });
                }
            });
            return results.slice(0, 30);
        }""")

    if not items:
        # Shufersal renders products in HTML — parse DOM directly
        items = page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // Strategy 1: named product card selectors
            const cardSelectors = [
                '.product_box', '.miglog-prod', 'li.item', 'li.product',
                '[class*="productBox"]', '[class*="product-box"]',
                '[class*="ProductCard"]', '[class*="product-card"]',
                '[class*="ProductItem"]', '[class*="product-item"]',
                '[data-product]', 'article',
            ];
            const getUrl = (el) => {
                const a = el.closest('a') || el.querySelector('a');
                if (a && a.href && a.href.includes('shufersal.co.il')) return a.href;
                return null;
            };

            for (const sel of cardSelectors) {
                document.querySelectorAll(sel).forEach(card => {
                    const text = card.innerText.replace(/\\s+/g, ' ').trim();
                    if (text.length > 15 && text.length < 400 && text.includes('₪') && !seen.has(text)) {
                        seen.add(text);
                        const item = { text };
                        const url = getUrl(card);
                        if (url) item.url = url;
                        results.push(item);
                    }
                });
                if (results.length >= 5) break;
            }

            // Strategy 2: find price leaf nodes, walk UP the DOM to capture name+price together
            if (results.length === 0) {
                document.querySelectorAll('*').forEach(el => {
                    if (el.children.length > 0) return;
                    const t = el.innerText ? el.innerText.trim() : '';
                    if (!t.includes('₪')) return;
                    let parent = el.parentElement;
                    for (let i = 0; i < 6; i++) {
                        if (!parent || parent === document.body) break;
                        const pt = parent.innerText ? parent.innerText.replace(/\\s+/g, ' ').trim() : '';
                        if (pt.length > t.length + 3 && pt.length < 400 && !seen.has(pt)) {
                            seen.add(pt);
                            const item = { text: pt };
                            const url = getUrl(parent);
                            if (url) item.url = url;
                            results.push(item);
                            break;
                        }
                        parent = parent.parentElement;
                    }
                });
            }

            return results.slice(0, 30);
        }""")
        if not items:
            print(f"  [shufersal] 0 items. APIs: {[c['url'] for c in api_data]}")

    # Filter noise then deduplicate by removing longer variants that contain shorter ones
    import re as _re
    filtered = []
    for it in items:
        t = it["text"].strip()
        if "שקלים חדשים" in t and len(t) < 50:
            continue
        if _re.match(r'^[\s\d₪.,\'\"\-–—ב-ל"ק]+$', t) and len(t) < 40:
            continue
        filtered.append(t)

    # Keep shortest unique representation: drop text B if it contains text A (A is shorter)
    deduped = []
    filtered.sort(key=len)
    for t in filtered:
        if not any(t != s and s in t for s in deduped):
            deduped.append(t)

    items = [{"text": t} for t in deduped[:30]]

    print(f"[shufersal] Found {len(items)} items")
    for i in items[:8]:
        print(f"  → {i['text'][:150]}")
    return items


def run():
    import sys
    debug = "--debug" in sys.argv
    force = "--force" in sys.argv
    print("=== AL.IA Supermarket Deal Scraper ===")

    def new_page(context):
        """Fresh page with no leftover listeners."""
        return context.new_page()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        ctx_opts = dict(
            user_agent=HEADERS["User-Agent"],
            locale="he-IL",
            extra_http_headers={"Accept-Language": "he-IL,he;q=0.9"},
        )

        try:
            context = browser.new_context(**ctx_opts)
            shufersal_items = scrape_shufersal(context.new_page())
            context.close()
        except Exception as e:
            print(f"[shufersal] Failed: {e}")
            shufersal_items = []

        try:
            context = browser.new_context(**ctx_opts)
            rami_levy_items = scrape_rami_levy(context.new_page())
            context.close()
        except Exception as e:
            print(f"[rami_levy] Failed: {e}")
            rami_levy_items = []

        try:
            context = browser.new_context(**ctx_opts)
            hazi_hinam_items = scrape_hazi_hinam(context.new_page())
            context.close()
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
