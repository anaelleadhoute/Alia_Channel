import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "/data/alia.db")


def get_db() -> aiosqlite.Connection:
    db = aiosqlite.connect(DB_PATH)
    return db


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guid        TEXT UNIQUE NOT NULL,
                source      TEXT NOT NULL,
                language    TEXT NOT NULL,       -- 'fr', 'ru', 'both'
                url         TEXT NOT NULL,
                title_raw   TEXT,
                content_raw TEXT,
                scraped_at  DATETIME DEFAULT CURRENT_TIMESTAMP,

                -- AI generated
                title_fr    TEXT,
                summary_fr  TEXT,
                cta_fr      TEXT,
                caption_ig_fr TEXT,

                title_ru    TEXT,
                summary_ru  TEXT,
                cta_ru      TEXT,
                caption_ig_ru TEXT,

                score       REAL,
                category    TEXT,
                ai_processed_at DATETIME,

                -- Validation
                status      TEXT DEFAULT 'pending',  -- pending/approved/rejected
                edited_at   DATETIME,

                -- Publication
                send_at     DATETIME,
                sent_wa_fr  INTEGER DEFAULT 0,
                sent_wa_ru  INTEGER DEFAULT 0,
                sent_ig_fr  INTEGER DEFAULT 0,
                sent_ig_ru  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS tips (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url  TEXT NOT NULL,
                scraped_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                week        TEXT NOT NULL,          -- e.g. '2024-W42'

                content_fr  TEXT,
                content_ru  TEXT,
                ai_processed_at DATETIME,

                status      TEXT DEFAULT 'pending',
                send_at     DATETIME,
                sent_wa_fr  INTEGER DEFAULT 0,
                sent_wa_ru  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                level       TEXT NOT NULL,          -- INFO/WARNING/ERROR
                service     TEXT NOT NULL,          -- scraper/ai/publisher/etc
                message     TEXT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.commit()
