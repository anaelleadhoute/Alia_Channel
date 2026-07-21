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

            CREATE TABLE IF NOT EXISTS schedules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key     TEXT UNIQUE NOT NULL,
                label       TEXT NOT NULL,
                day_of_week INTEGER,
                hour_utc    INTEGER NOT NULL DEFAULT 12,
                enabled     INTEGER NOT NULL DEFAULT 1,
                location    TEXT NOT NULL DEFAULT 'server',
                last_run    DATETIME
            );

            INSERT OR IGNORE INTO schedules (job_key, label, day_of_week, hour_utc, enabled, location) VALUES
                ('news_digest',   '📰 News + Digest',     NULL, 16, 1, 'server'),
                ('telegram_deals','⚡ Telegram Deals',    1,    12, 1, 'server'),
                ('faq',           '❓ FAQ',               2,    12, 1, 'server'),
                ('prestataire',   '🏅 Prestataire',      4,    12, 1, 'mac'),
                ('kids_events',   '👧 Kids Events',      0,    12, 1, 'mac');

            CREATE TABLE IF NOT EXISTS cleanup_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ran_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                articles_deleted INTEGER DEFAULT 0,
                deals_deleted    INTEGER DEFAULT 0,
                triggered_by TEXT DEFAULT 'auto'
            );

            CREATE TABLE IF NOT EXISTS doctors (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                name_he             TEXT NOT NULL,
                phone               TEXT,
                city_he             TEXT,
                url                 TEXT UNIQUE NOT NULL,
                specialties_he      TEXT,
                specialty_translated TEXT,
                language            TEXT NOT NULL,
                source              TEXT DEFAULT 'medreviews',
                imported_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_featured       DATETIME
            );

            CREATE TABLE IF NOT EXISTS weekly_doctor (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                week        TEXT UNIQUE NOT NULL,
                doctor_id   INTEGER,
                content_fr  TEXT,
                content_ru  TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                status      TEXT DEFAULT 'pending',
                sent_wa_fr  INTEGER DEFAULT 0,
                sent_wa_ru  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS weekly_rights (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                week        TEXT UNIQUE NOT NULL,
                source_url  TEXT,
                raw_payload TEXT,
                content_fr  TEXT,
                content_ru  TEXT,
                ai_processed_at DATETIME,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                status      TEXT DEFAULT 'pending',
                sent_wa_fr  INTEGER DEFAULT 0,
                sent_wa_ru  INTEGER DEFAULT 0
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
            "ALTER TABLE weekly_events_kids ADD COLUMN raw_payload TEXT",
            "ALTER TABLE weekly_prestataire ADD COLUMN raw_payload TEXT",
            "ALTER TABLE tips ADD COLUMN raw_payload TEXT",
            "ALTER TABLE schedules ADD COLUMN minute_utc INTEGER NOT NULL DEFAULT 0",
            # Scrape jobs (mac) — separate from generate jobs (server)
            """INSERT OR IGNORE INTO schedules (job_key, label, day_of_week, hour_utc, minute_utc, enabled, location) VALUES
                ('scrape_kids_events',   '👧 Scrape Kids Events',   0, 9,  0, 1, 'mac'),
                ('scrape_prestataire',   '🏅 Scrape Prestataire',   0, 9,  0, 1, 'mac'),
                ('scrape_kol_zchut',     '📄 Scrape Guide',         0, 9,  0, 1, 'mac'),
                ('generate_kids_events', '👧 Generate Kids Events', 1, 9,  0, 1, 'server'),
                ('generate_prestataire', '🏅 Generate Prestataire', 4, 9,  0, 1, 'server'),
                ('generate_kol_zchut',   '📄 Generate Guide',       3, 9,  0, 1, 'server'),
                ('generate_doctor',      '🏥 Generate Médecin',     5, 10, 0, 1, 'server'),
                ('scrape_rights',        '💰 Scrape Droits',        2, 9,  0, 1, 'mac'),
                ('generate_rights',      '💰 Generate Droits',      4, 11, 0, 1, 'server')""",
            # Send jobs — separate from generate, configurable per category
            """INSERT OR IGNORE INTO schedules (job_key, label, day_of_week, hour_utc, minute_utc, enabled, location) VALUES
                ('send_tip',         '📄 Envoyer Guide',         3,    11, 0, 1, 'server'),
                ('send_faq',         '❓ Envoyer FAQ',           2,    11, 0, 1, 'server'),
                ('send_rights',      '💰 Envoyer Droits',        4,    12, 0, 1, 'server'),
                ('send_doctor',      '🏥 Envoyer Médecin',       5,    11, 0, 1, 'server'),
                ('send_kids',        '👧 Envoyer Kids',          1,    10, 0, 1, 'server'),
                ('send_prestataire', '🏅 Envoyer Prestataire',   4,    10, 0, 1, 'server'),
                ('send_deal',        '⚡ Envoyer Deal',          null, 10, 0, 1, 'server')""",
            "DELETE FROM schedules WHERE job_key = 'send_all_pending'",
            "DELETE FROM schedules WHERE job_key = 'send_digest'",
            "DELETE FROM schedules WHERE job_key = 'send_faq'",
        ]:
            try:
                await db.execute(migration)
                await db.commit()
            except Exception:
                pass  # column already exists
