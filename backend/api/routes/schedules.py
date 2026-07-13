from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from db.database import get_db

router = APIRouter()

DAYS = ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi']


class ScheduleUpdate(BaseModel):
    day_of_week: Optional[int] = None   # 0=Sun … 6=Sat, None=daily
    hour_utc: Optional[int] = None
    minute_utc: Optional[int] = None
    enabled: Optional[int] = None


@router.get("")
async def list_schedules():
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM schedules ORDER BY id")
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.patch("/{job_key}")
async def update_schedule(job_key: str, update: ScheduleUpdate):
    fields = update.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["job_key"] = job_key
    async with get_db() as db:
        await db.execute(f"UPDATE schedules SET {set_clause} WHERE job_key = :job_key", fields)
        await db.commit()
    return {"ok": True}


@router.get("/due")
async def get_due_jobs(location: str = "server"):
    """Return jobs due within the current 15-minute window."""
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    current_minute = now.minute
    current_dow = now.weekday()
    current_dow_js = (current_dow + 1) % 7

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM schedules WHERE enabled = 1 AND location = ? AND hour_utc = ?",
            (location, current_hour),
        )
        rows = await cursor.fetchall()

    due = []
    for r in rows:
        r = dict(r)
        dow = r["day_of_week"]
        minute = r.get("minute_utc", 0) or 0

        # Skip if already ran today (daily jobs) or this week (weekly jobs)
        if r.get("last_run"):
            last = datetime.fromisoformat(r["last_run"].replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (now - last).total_seconds()
            cooldown = 23 * 3600 if r["day_of_week"] is None else 6 * 24 * 3600
            if elapsed < cooldown:
                continue

        # Due if within current 15-min window
        if abs(current_minute - minute) <= 14:
            if dow is None or dow == current_dow_js:
                due.append(r)

    return {"due": due, "now_utc": now.isoformat(), "hour": current_hour, "minute": current_minute, "dow": current_dow_js}


@router.post("/{job_key}/run")
async def mark_ran(job_key: str):
    """Mark a job as just ran (called by dispatcher after execution)."""
    async with get_db() as db:
        await db.execute(
            "UPDATE schedules SET last_run = ? WHERE job_key = ?",
            (datetime.utcnow().isoformat(), job_key),
        )
        await db.commit()
    return {"ok": True}
