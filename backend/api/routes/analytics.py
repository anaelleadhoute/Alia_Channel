from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from db.database import get_db

router = APIRouter()

ALIA_BOT_BASE = "https://wa.me/972549675013"

VALID_CATEGORIES = {"guide", "droits", "prestataire", "kids", "news", "faq", "doctor", "deal", "recommendation"}

short_router = APIRouter()

SHORT_ROUTES = {
    "faq":          ("faq",          "FAQ Alia"),
    "guide":        ("guide",        "Guide Alia"),
    "droits":       ("droits",       "Droits Alia"),
    "kids":         ("kids",         "Kids Alia"),
    "medecin":      ("doctor",       "Medecin Alia"),
    "deals":        ("deal",         "Deals Alia"),
    "news":         ("news",         "News Alia"),
    "prestataire":  ("prestataire",  "Prestataire Alia"),
}


@short_router.get("/go/{slug}")
async def short_link(slug: str):
    route = SHORT_ROUTES.get(slug)
    if route:
        category, text = route
        async with get_db() as db:
            await db.execute("INSERT INTO link_clicks (category) VALUES (?)", (category,))
            await db.commit()
        import urllib.parse
        dest = f"{ALIA_BOT_BASE}?text={urllib.parse.quote(text)}"
    else:
        dest = f"{ALIA_BOT_BASE}?text=Aide-moi"
    return RedirectResponse(url=dest, status_code=302)


@router.get("/track/{category}")
async def track_click(category: str):
    import urllib.parse
    text = "Aide-moi"
    if category in VALID_CATEGORIES:
        async with get_db() as db:
            await db.execute("INSERT INTO link_clicks (category) VALUES (?)", (category,))
            await db.commit()
        text = next((v[1] for v in SHORT_ROUTES.values() if v[0] == category), "Aide-moi")
    return RedirectResponse(url=f"{ALIA_BOT_BASE}?text={urllib.parse.quote(text)}")


@router.get("/clicks")
async def get_click_stats():
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT category, COUNT(*) as total,
               SUM(CASE WHEN clicked_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as last_7d,
               SUM(CASE WHEN clicked_at >= datetime('now', '-30 days') THEN 1 ELSE 0 END) as last_30d
               FROM link_clicks GROUP BY category ORDER BY total DESC"""
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.get("/clicks/daily")
async def get_daily_clicks():
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT date(clicked_at) as day, category, COUNT(*) as clicks
               FROM link_clicks
               WHERE clicked_at >= datetime('now', '-30 days')
               GROUP BY day, category ORDER BY day DESC"""
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]
