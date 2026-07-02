from fastapi import APIRouter

router = APIRouter()


@router.post("/article/{article_id}")
async def publish_article(article_id: int, channels: list[str]):
    """Placeholder — implemented in Phase 6 (WhatsApp) and Phase 7 (Instagram)."""
    return {"ok": True, "article_id": article_id, "channels": channels, "status": "pending"}
