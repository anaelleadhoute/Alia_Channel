import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db
from api.routes import articles, tips, publish, scrape

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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
