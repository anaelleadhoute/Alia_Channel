"""
Instagram carousel publishing.

Two entry points, both ending in the same Instagram Graph API carousel
publish sequence:

  A) Manual upload — admin exports images from Canva by hand and uploads
     them via the dashboard.
  B) Direct from Canva — admin picks an already-designed carousel from the
     "ALIA carrousels" Canva folder; we export its pages via the Canva
     Export API, download them, and publish straight to Instagram. No
     Canva Autofill/dynamic fields involved — the design itself is always
     made by hand in Canva, only the *publishing* is automated.

Instagram side ("API setup with Instagram login" flow, i.e. graph.instagram.com):
  1. POST /{ig-id}/media  (per image, is_carousel_item=true) -> creation_id
  2. POST /{ig-id}/media  (media_type=CAROUSEL, children=[...], caption)   -> carousel creation_id
  3. POST /{ig-id}/media_publish (creation_id=carousel id)                -> published media id
"""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import pytz
from fastapi import APIRouter, File, Form, UploadFile

from api.routes.canva import get_valid_access_token
from api.routes.settings import get_setting, set_setting
from db.database import get_db

router = APIRouter()

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_IG_ACCOUNT_ID = os.getenv("META_IG_ACCOUNT_ID", "")
GRAPH_BASE = "https://graph.instagram.com/v21.0"
PUBLIC_BASE_URL = "https://alia-channel.com"
IL_TZ = pytz.timezone("Asia/Jerusalem")

CANVA_API_BASE = "https://api.canva.com/rest/v1"
CANVA_CAROUSEL_FOLDER_ID = "FAHSc8sf3pA"  # "ALIA carrousels" folder on Canva

STATIC_DIR = Path("/app/static/instagram")
STATIC_DIR.mkdir(parents=True, exist_ok=True)

MIN_IMAGES = 2
MAX_IMAGES = 10
MAX_UPLOAD_AGE_SECONDS = 24 * 3600  # housekeeping: drop stale uploads on each publish


def _cleanup_old_uploads():
    cutoff = time.time() - MAX_UPLOAD_AGE_SECONDS
    for f in STATIC_DIR.glob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def _save_bytes(content: bytes, ext: str = ".jpg") -> str:
    filename = f"{uuid.uuid4().hex}{ext}"
    (STATIC_DIR / filename).write_bytes(content)
    return f"{PUBLIC_BASE_URL}/instagram/{filename}"


def _parse_il_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = IL_TZ.localize(parsed)
    return parsed


async def _get_published_design_ids() -> list[str]:
    raw = await get_setting("instagram_published_canva_designs")
    return json.loads(raw) if raw else []


async def _mark_design_published(design_id: str):
    ids = await _get_published_design_ids()
    if design_id not in ids:
        ids.append(design_id)
        await set_setting("instagram_published_canva_designs", json.dumps(ids))


async def _wait_until_finished(client: httpx.AsyncClient, creation_id: str, max_tries: int = 15):
    """Poll an Instagram media container until it's finished processing."""
    for _ in range(max_tries):
        resp = await client.get(
            f"{GRAPH_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": META_ACCESS_TOKEN},
        )
        data = resp.json()
        status = data.get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Instagram failed to process container {creation_id}: {data}")
        await asyncio.sleep(2)
    raise RuntimeError(f"Timed out waiting for container {creation_id} to finish processing")


async def _publish_carousel_from_urls(client: httpx.AsyncClient, image_urls: list[str], caption: str) -> dict:
    child_ids = []
    for url in image_urls:
        resp = await client.post(
            f"{GRAPH_BASE}/{META_IG_ACCOUNT_ID}/media",
            data={"image_url": url, "is_carousel_item": "true", "access_token": META_ACCESS_TOKEN},
        )
        data = resp.json()
        if "id" not in data:
            return {"ok": False, "error": f"Failed to create item container: {data}"}
        child_ids.append(data["id"])

    for cid in child_ids:
        await _wait_until_finished(client, cid)

    resp = await client.post(
        f"{GRAPH_BASE}/{META_IG_ACCOUNT_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": META_ACCESS_TOKEN,
        },
    )
    data = resp.json()
    if "id" not in data:
        return {"ok": False, "error": f"Failed to create carousel container: {data}"}
    carousel_id = data["id"]

    await _wait_until_finished(client, carousel_id)

    resp = await client.post(
        f"{GRAPH_BASE}/{META_IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": carousel_id, "access_token": META_ACCESS_TOKEN},
    )
    data = resp.json()
    if "id" not in data:
        return {"ok": False, "error": f"Failed to publish: {data}"}

    media_id = data["id"]
    permalink = None
    try:
        resp = await client.get(
            f"{GRAPH_BASE}/{media_id}", params={"fields": "permalink", "access_token": META_ACCESS_TOKEN}
        )
        permalink = resp.json().get("permalink")
    except Exception:
        pass

    return {"ok": True, "media_id": media_id, "permalink": permalink}


@router.post("/publish")
async def publish_carousel(images: list[UploadFile] = File(...), caption: str = Form("")):
    """Manual flow: admin uploads already-exported images from Canva."""
    if not META_ACCESS_TOKEN or not META_IG_ACCOUNT_ID:
        return {"ok": False, "error": "Instagram isn't configured (META_ACCESS_TOKEN / META_IG_ACCOUNT_ID missing)"}

    if len(images) < MIN_IMAGES or len(images) > MAX_IMAGES:
        return {"ok": False, "error": f"A carousel needs between {MIN_IMAGES} and {MAX_IMAGES} images (got {len(images)})"}

    _cleanup_old_uploads()

    saved_urls = []
    for img in images:
        ext = Path(img.filename or "image.jpg").suffix or ".jpg"
        saved_urls.append(_save_bytes(await img.read(), ext))

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            return await _publish_carousel_from_urls(client, saved_urls, caption)
        except RuntimeError as e:
            return {"ok": False, "error": str(e)}


@router.get("/canva-carousels")
async def list_canva_carousels():
    """List designs in the 'ALIA carrousels' Canva folder for the dashboard picker."""
    try:
        token = await get_valid_access_token()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{CANVA_API_BASE}/folders/{CANVA_CAROUSEL_FOLDER_ID}/items",
            headers={"Authorization": f"Bearer {token}"},
            params={"item_types": "design"},
        )
    if resp.status_code != 200:
        return {"ok": False, "error": f"Canva folder list failed: {resp.text}"}

    published = set(await _get_published_design_ids())
    items = []
    for entry in resp.json().get("items", []):
        d = entry.get("design")
        if not d:
            continue
        items.append(
            {
                "design_id": d["id"],
                "title": d.get("title", ""),
                "thumbnail_url": (d.get("thumbnail") or {}).get("url"),
                "page_count": d.get("page_count"),
                "updated_at": d.get("updated_at"),
                "already_published": d["id"] in published,
            }
        )
    items.sort(key=lambda x: x["updated_at"] or 0, reverse=True)
    return {"ok": True, "items": items}


async def _export_design_images(client: httpx.AsyncClient, token: str, design_id: str) -> list[str]:
    resp = await client.post(
        f"{CANVA_API_BASE}/exports",
        headers={"Authorization": f"Bearer {token}"},
        json={"design_id": design_id, "format": {"type": "jpg", "quality": 85}},
    )
    data = resp.json()
    job = data.get("job")
    if not job:
        raise RuntimeError(f"Canva export failed to start: {data}")
    job_id = job["id"]

    for _ in range(30):
        resp = await client.get(f"{CANVA_API_BASE}/exports/{job_id}", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        status = data["job"]["status"]
        if status == "success":
            return data["job"]["urls"]
        if status == "failed":
            raise RuntimeError(f"Canva export failed: {data}")
        await asyncio.sleep(2)
    raise RuntimeError("Timed out waiting for Canva export to finish")


async def _export_and_publish(design_id: str, caption: str) -> dict:
    """Export the design's current pages from Canva right now, then publish them."""
    try:
        canva_token = await get_valid_access_token()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

    _cleanup_old_uploads()

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            export_urls = await _export_design_images(client, canva_token, design_id)
        except RuntimeError as e:
            return {"ok": False, "error": str(e)}

        if len(export_urls) < MIN_IMAGES or len(export_urls) > MAX_IMAGES:
            return {
                "ok": False,
                "error": f"Ce carrousel a {len(export_urls)} pages — Instagram accepte entre {MIN_IMAGES} et {MAX_IMAGES}.",
            }

        saved_urls = []
        for url in export_urls:
            resp = await client.get(url)
            saved_urls.append(_save_bytes(resp.content, ".jpg"))

        try:
            result = await _publish_carousel_from_urls(client, saved_urls, caption)
        except RuntimeError as e:
            return {"ok": False, "error": str(e)}

    if result.get("ok"):
        await _mark_design_published(design_id)
    return result


@router.post("/publish-from-canva")
async def publish_from_canva(
    design_id: str = Form(...),
    caption: str = Form(""),
    design_title: str = Form(""),
    thumbnail_url: str = Form(""),
    scheduled_at: str = Form(None),
):
    """Direct flow: export a design already sitting in the Canva folder, then publish it.

    If scheduled_at is a future datetime, the post is queued instead of published
    immediately — /fire-scheduled (called by the cron dispatcher) re-exports the
    design fresh at send time, so any edits made in Canva after scheduling are
    picked up automatically.
    """
    if not META_ACCESS_TOKEN or not META_IG_ACCOUNT_ID:
        return {"ok": False, "error": "Instagram isn't configured (META_ACCESS_TOKEN / META_IG_ACCOUNT_ID missing)"}

    if scheduled_at:
        send_time = _parse_il_datetime(scheduled_at)
        if (send_time - datetime.now(IL_TZ)).total_seconds() > 0:
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO scheduled_instagram_posts (design_id, design_title, caption, send_at, sent, thumbnail_url) VALUES (?,?,?,?,0,?)",
                    (design_id, design_title, caption, send_time.isoformat(), thumbnail_url),
                )
                await db.commit()
            return {"ok": True, "scheduled": True, "send_at": send_time.isoformat()}

    return await _export_and_publish(design_id, caption)


@router.get("/scheduled")
async def list_scheduled_instagram():
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM scheduled_instagram_posts WHERE sent = 0 ORDER BY send_at ASC")
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.delete("/scheduled/{post_id}")
async def delete_scheduled_instagram(post_id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM scheduled_instagram_posts WHERE id = ? AND sent = 0", (post_id,))
        await db.commit()
    return {"ok": True}


@router.post("/fire-scheduled")
async def fire_scheduled_instagram():
    """Called every 15 min by the cron dispatcher, mirrors fire-scheduled-manual."""
    now = datetime.now(IL_TZ)
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM scheduled_instagram_posts WHERE sent = 0 AND send_at <= ?", (now.isoformat(),)
        )
        rows = await cursor.fetchall()

    fired = 0
    for row in rows:
        row = dict(row)
        result = await _export_and_publish(row["design_id"], row["caption"] or "")
        async with get_db() as db:
            if result.get("ok"):
                await db.execute(
                    "UPDATE scheduled_instagram_posts SET sent = 1, media_id = ?, permalink = ? WHERE id = ?",
                    (result.get("media_id"), result.get("permalink"), row["id"]),
                )
                fired += 1
            else:
                await db.execute(
                    "UPDATE scheduled_instagram_posts SET error = ? WHERE id = ?",
                    (result.get("error"), row["id"]),
                )
            await db.commit()

    return {"ok": True, "fired": fired, "checked": len(rows)}
