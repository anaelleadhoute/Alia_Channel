import logging
from db.database import get_db

logger = logging.getLogger(__name__)


async def cleanup_old_articles(days: int = 30) -> dict:
    """Delete articles that were sent more than `days` days ago."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            DELETE FROM articles
            WHERE status = 'approved'
            AND (sent_wa_fr = 1 OR sent_wa_ru = 1 OR sent_ig_fr = 1 OR sent_ig_ru = 1)
            AND scraped_at < datetime('now', ? )
            """,
            (f"-{days} days",),
        )
        deleted = db.total_changes
        await db.commit()

    logger.info(f"[cleanup] Deleted {deleted} articles older than {days} days.")
    return {"deleted": deleted, "older_than_days": days}


async def cleanup_rejected_articles(days: int = 7) -> dict:
    """Delete rejected articles older than `days` days."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            DELETE FROM articles
            WHERE status = 'rejected'
            AND scraped_at < datetime('now', ?)
            """,
            (f"-{days} days",),
        )
        deleted = db.total_changes
        await db.commit()

    logger.info(f"[cleanup] Deleted {deleted} rejected articles older than {days} days.")
    return {"deleted_rejected": deleted}


async def run_cleanup() -> dict:
    sent = await cleanup_old_articles(days=30)
    rejected = await cleanup_rejected_articles(days=7)
    return {**sent, **rejected}
