from fastapi import APIRouter
from datetime import datetime
from db.database import get_db

router = APIRouter()


@router.post("/cleanup")
async def run_cleanup(triggered_by: str = "manual"):
    """Delete articles and deals older than 30 days, log the result."""
    async with get_db() as db:
        cur = await db.execute(
            "DELETE FROM articles WHERE status = 'pending' AND scraped_at < DATETIME('now', '-14 days')"
        )
        articles_deleted = cur.rowcount
        cur2 = await db.execute(
            "DELETE FROM articles WHERE status IN ('approved','rejected') AND scraped_at < DATETIME('now', '-30 days')"
        )
        articles_deleted += cur2.rowcount

        cur = await db.execute(
            "DELETE FROM deals WHERE scraped_at < DATETIME('now', '-30 days')"
        )
        deals_deleted = cur.rowcount

        await db.execute(
            "INSERT INTO cleanup_logs (ran_at, articles_deleted, deals_deleted, triggered_by) VALUES (?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), articles_deleted, deals_deleted, triggered_by),
        )
        await db.commit()

    return {
        "status": "ok",
        "ran_at": datetime.utcnow().isoformat(),
        "articles_deleted": articles_deleted,
        "deals_deleted": deals_deleted,
        "triggered_by": triggered_by,
    }


@router.get("/cleanup/logs")
async def get_cleanup_logs():
    """Return cleanup history and next scheduled run."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM cleanup_logs ORDER BY ran_at DESC LIMIT 20"
        )
        rows = await cursor.fetchall()
    logs = [dict(r) for r in rows]

    # Next run: first day of next month at 03:00 UTC
    now = datetime.utcnow()
    if now.month == 12:
        next_run = datetime(now.year + 1, 1, 1, 3, 0, 0)
    else:
        next_run = datetime(now.year, now.month + 1, 1, 3, 0, 0)

    return {"logs": logs, "next_run": next_run.isoformat()}
