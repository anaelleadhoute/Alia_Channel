import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.database import init_db
from api.routes import articles, tips, publish, scrape, deals, faqs, digests, settings, contests, weekly_deals, weekly_events, maintenance, schedules

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(title="AL.IA Channel API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await init_db()


app.include_router(scrape.router,   prefix="/api/scrape",   tags=["scrape"])
app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(tips.router,     prefix="/api/tips",     tags=["tips"])
app.include_router(publish.router,  prefix="/api/publish",  tags=["publish"])
app.include_router(deals.router,    prefix="/api/deals",    tags=["deals"])
app.include_router(faqs.router,     prefix="/api/faqs",     tags=["faqs"])
app.include_router(digests.router,  prefix="/api/digests",  tags=["digests"])
app.include_router(settings.router,  prefix="/api/settings",  tags=["settings"])
app.include_router(contests.router,      prefix="/api/contests",      tags=["contests"])
app.include_router(weekly_deals.router,   prefix="/api/weekly-deals",   tags=["weekly-deals"])
app.include_router(weekly_events.router,    prefix="/api/weekly-events",    tags=["weekly-events"])
app.include_router(maintenance.router,     prefix="/api/maintenance",      tags=["maintenance"])
app.include_router(schedules.router,       prefix="/api/schedules",        tags=["schedules"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
