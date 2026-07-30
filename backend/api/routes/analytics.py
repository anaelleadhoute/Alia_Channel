from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from db.database import get_db

router = APIRouter()

ALIA_BOT_URL = "https://wa.me/972549675013?text=Aide-moi"

VALID_CATEGORIES = {"guide", "droits", "prestataire", "kids", "news", "faq", "doctor", "deal", "recommendation"}

short_router = APIRouter()

SHORT_ROUTES = {
    "faq":          "faq",
    "guide":        "guide",
    "droits":       "droits",
    "kids":         "kids",
    "medecin":      "doctor",
    "deals":        "deal",
    "news":         "news",
    "prestataire":  "prestataire",
}


@short_router.get("/go/{slug}")
async def short_link(slug: str):
    category = SHORT_ROUTES.get(slug)
    if category:
        async with get_db() as db:
            await db.execute("INSERT INTO link_clicks (category) VALUES (?)", (category,))
            await db.commit()
    return RedirectResponse(url=ALIA_BOT_URL, status_code=302)


@router.get("/track/{category}")
async def track_click(category: str):
    if category in VALID_CATEGORIES:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO link_clicks (category) VALUES (?)", (category,)
            )
            await db.commit()
    return RedirectResponse(url=ALIA_BOT_URL)


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
