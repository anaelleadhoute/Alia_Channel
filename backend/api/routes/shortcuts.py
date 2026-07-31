import urllib.parse
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

short_router = APIRouter()

ALIA_BOT_BASE = "https://wa.me/972549675013"

SHORT_ROUTES = {
    "faq":         "FAQ Alia",
    "guide":       "Guide Alia",
    "droits":      "Droits Alia",
    "kids":        "Kids Alia",
    "medecin":     "Medecin Alia",
    "deals":       "Deals Alia",
    "news":        "News Alia",
    "prestataire": "Prestataire Alia",
}


@short_router.get("/go/{slug}")
async def short_link(slug: str):
    text = SHORT_ROUTES.get(slug, "Aide-moi")
    dest = f"{ALIA_BOT_BASE}?text={urllib.parse.quote(text)}"
    return RedirectResponse(url=dest, status_code=302)
