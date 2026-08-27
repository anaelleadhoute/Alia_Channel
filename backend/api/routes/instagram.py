"""
Instagram carousel publishing — manual-content flow.

The carousel design itself is made by hand in Canva (no Autofill/dynamic
fields). This endpoint just takes the exported images + a caption, hosts the
images at a public HTTPS URL (reusing the static file server every other
part of the app already relies on), and drives the Instagram Graph API
("API setup with Instagram login" flow, i.e. graph.instagram.com) through
the three-step carousel publish sequence:

  1. POST /{ig-id}/media  (per image, is_carousel_item=true) -> creation_id
  2. POST /{ig-id}/media  (media_type=CAROUSEL, children=[...], caption)   -> carousel creation_id
  3. POST /{ig-id}/media_publish (creation_id=carousel id)                -> published media id
"""
import asyncio
import os
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, File, Form, UploadFile

router = APIRouter()

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_IG_ACCOUNT_ID = os.getenv("META_IG_ACCOUNT_ID", "")
GRAPH_BASE = "https://graph.instagram.com/v21.0"
PUBLIC_BASE_URL = "https://alia-channel.com"

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


async def _wait_until_finished(client: httpx.AsyncClient, creation_id: str, max_tries: int = 15):
    """Poll a media container until Instagram finishes processing it."""
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


@router.post("/publish")
async def publish_carousel(images: list[UploadFile] = File(...), caption: str = Form("")):
    if not META_ACCESS_TOKEN or not META_IG_ACCOUNT_ID:
        return {"ok": False, "error": "Instagram isn't configured (META_ACCESS_TOKEN / META_IG_ACCOUNT_ID missing)"}

    if len(images) < MIN_IMAGES or len(images) > MAX_IMAGES:
        return {"ok": False, "error": f"A carousel needs between {MIN_IMAGES} and {MAX_IMAGES} images (got {len(images)})"}

    _cleanup_old_uploads()

    # 1. Save uploads to the public static dir, in the order they were sent.
    saved_urls = []
    for img in images:
        ext = Path(img.filename or "image.jpg").suffix or ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = STATIC_DIR / filename
        dest.write_bytes(await img.read())
        saved_urls.append(f"{PUBLIC_BASE_URL}/instagram/{filename}")

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            # 2. One container per image.
            child_ids = []
            for url in saved_urls:
                resp = await client.post(
                    f"{GRAPH_BASE}/{META_IG_ACCOUNT_ID}/media",
                    data={
                        "image_url": url,
                        "is_carousel_item": "true",
                        "access_token": META_ACCESS_TOKEN,
                    },
                )
                data = resp.json()
                if "id" not in data:
                    return {"ok": False, "error": f"Failed to create item container: {data}"}
                child_ids.append(data["id"])

            for cid in child_ids:
                await _wait_until_finished(client, cid)

            # 3. Bundle into a carousel container.
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

            # 4. Publish.
            resp = await client.post(
                f"{GRAPH_BASE}/{META_IG_ACCOUNT_ID}/media_publish",
                data={"creation_id": carousel_id, "access_token": META_ACCESS_TOKEN},
            )
            data = resp.json()
            if "id" not in data:
                return {"ok": False, "error": f"Failed to publish: {data}"}

            media_id = data["id"]

            # Best-effort permalink lookup — not critical if it fails.
            permalink = None
            try:
                resp = await client.get(
                    f"{GRAPH_BASE}/{media_id}",
                    params={"fields": "permalink", "access_token": META_ACCESS_TOKEN},
                )
                permalink = resp.json().get("permalink")
            except Exception:
                pass

            return {"ok": True, "media_id": media_id, "permalink": permalink}

        except RuntimeError as e:
            return {"ok": False, "error": str(e)}
