import aiosqlite
import os
from contextlib import asynccontextmanager

DB_PATH = os.getenv("DB_PATH", "/data/alia.db")


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guid        TEXT UNIQUE NOT NULL,
                source      TEXT NOT NULL,
                language    TEXT NOT NULL,
                url         TEXT NOT NULL,
                title_raw   TEXT,
                content_raw TEXT,
                scraped_at  DATETIME DEFAULT CURRENT_TIMESTAMP,

                title_fr    TEXT,
                summary_fr  TEXT,
                cta_fr      TEXT,
                caption_ig_fr TEXT,

                title_ru    TEXT,
                summary_ru  TEXT,
                cta_ru      TEXT,
                caption_ig_ru TEXT,

                published_at DATETIME,
                score       REAL,
                category    TEXT,
                ai_processed_at DATETIME,

                status      TEXT DEFAULT 'pending',
                edited_at   DATETIME,

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
                week        TEXT NOT NULL,

                content_fr  TEXT,
                content_ru  TEXT,
                ai_processed_at DATETIME,

                status      TEXT DEFAULT 'pending',
                send_at     DATETIME,
                sent_wa_fr  INTEGER DEFAULT 0,
                sent_wa_ru  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS deals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id      TEXT NOT NULL,
                channel         TEXT NOT NULL,
                category        TEXT NOT NULL,
                relevance_score REAL,
                is_relevant     INTEGER DEFAULT 0,
                deal_product    TEXT,
                deal_price      TEXT,
                deal_summary_he TEXT,
                content_fr      TEXT,
                content_ru      TEXT,
                raw_text        TEXT,
                images_json     TEXT,
                audience        TEXT DEFAULT 'both',
                scraped_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                ai_processed_at DATETIME,
                status          TEXT DEFAULT 'pending',
                sent_wa_fr      INTEGER DEFAULT 0,
                sent_wa_ru      INTEGER DEFAULT 0,
                UNIQUE(message_id, channel)
            );

            CREATE TABLE IF NOT EXISTS digests (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_date   TEXT UNIQUE NOT NULL,
                content_fr    TEXT,
                content_ru    TEXT,
                article_count INTEGER DEFAULT 0,
                generated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                status        TEXT DEFAULT 'pending',
                sent_wa_fr    INTEGER DEFAULT 0,
                sent_wa_ru    INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS faqs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                week         TEXT UNIQUE NOT NULL,
                content_fr   TEXT,
                content_ru   TEXT,
                generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status       TEXT DEFAULT 'pending',
                sent_wa_fr   INTEGER DEFAULT 0,
                sent_wa_ru   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                level       TEXT NOT NULL,
                service     TEXT NOT NULL,
                message     TEXT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contests (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT NOT NULL,
                content_fr   TEXT,
                content_ru   TEXT,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                status       TEXT DEFAULT 'pending',
                sent_wa_fr   INTEGER DEFAULT 0,
                sent_wa_ru   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_publish', 'true');

            CREATE TABLE IF NOT EXISTS weekly_deals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                week            TEXT UNIQUE NOT NULL,
                shufersal_json  TEXT,
                rami_levy_json  TEXT,
                carrefour_json  TEXT,
                content_fr      TEXT,
                content_ru      TEXT,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                status          TEXT DEFAULT 'pending',
                sent_wa_fr      INTEGER DEFAULT 0,
                sent_wa_ru      INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS weekly_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                week            TEXT UNIQUE NOT NULL,
                events_json     TEXT,
                content_fr      TEXT,
                content_ru      TEXT,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                status          TEXT DEFAULT 'pending',
                sent_wa_fr      INTEGER DEFAULT 0,
                sent_wa_ru      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS weekly_prestataire (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                week            TEXT UNIQUE NOT NULL,
                data_json       TEXT,
                content_fr      TEXT,
                content_ru      TEXT,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                status          TEXT DEFAULT 'pending',
                sent_wa_fr      INTEGER DEFAULT 0,
                sent_wa_ru      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS weekly_events_kids (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                week            TEXT UNIQUE NOT NULL,
                events_json     TEXT,
                activity_idea_json TEXT,
                content_fr      TEXT,
                content_ru      TEXT,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                status          TEXT DEFAULT 'pending',
                sent_wa_fr      INTEGER DEFAULT 0,
                sent_wa_ru      INTEGER DEFAULT 0
            );
        """)
        await db.commit()

        # Migrations for existing DBs
        for migration in [
            "ALTER TABLE articles ADD COLUMN published_at DATETIME",
            "ALTER TABLE weekly_events_kids ADD COLUMN activity_idea_json TEXT",
        ]:
            try:
                await db.execute(migration)
                await db.commit()
            except Exception:
                pass  # column already exists
