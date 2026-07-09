from fastapi import APIRouter, HTTPException
from db.database import get_db

router = APIRouter()


@router.get("")
async def list_weekly_deals(limit: int = 10):
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, week, shufersal_json, rami_levy_json, carrefour_json,
                      content_fr, content_ru, status, sent_wa_fr, sent_wa_ru, created_at
               FROM weekly_deals ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.patch("/{deal_id}")
async def update_weekly_deal(deal_id: int, body: dict):
    allowed = {"content_fr", "content_ru", "status"}
    fields = {k: v for k, v in body.items() if k in allowed}
    if not fields:
        raise HTTPException(status_code=400, detail="No valid fields")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    async with get_db() as db:
        await db.execute(
            f"UPDATE weekly_deals SET {set_clause} WHERE id = ?",
            (*fields.values(), deal_id),
        )
        await db.commit()
    return {"ok": True}


@router.delete("/{deal_id}")
async def delete_weekly_deal(deal_id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM weekly_deals WHERE id = ?", (deal_id,))
        await db.commit()
    return {"ok": True}
