"""
HeyGen video publishing to Instagram Reels.

Mirrors the Canva-carousel flow: videos are created manually in HeyGen
(avatar, script, everything) — the dashboard just lists them and automates
picking + publishing to Instagram as a Reel. HeyGen's video_url is a
presigned/expiring URL, so we always fetch a fresh one at publish time
and re-host the file on our own static server before handing it to
Instagram, same as the Canva-exported carousel images.

HeyGen API: https://developers.heygen.com (x-api-key header)
Instagram side (graph.instagram.com):
  1. POST /{ig-id}/media (video_url, media_type=REELS, caption) -> creation_id
  2. poll status_code == FINISHED
  3. POST /{ig-id}/media_publish (creation_id) -> published media id
"""
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import anthropic
import httpx
from fastapi import APIRouter, Form

from api.routes.instagram import GRAPH_BASE, META_ACCESS_TOKEN, META_IG_ACCOUNT_ID, IL_TZ, _wait_until_finished, _parse_il_datetime
from api.routes.settings import get_setting, set_setting
from db.database import get_db

router = APIRouter()

HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY", "")
HEYGEN_API_BASE = "https://api.heygen.com"
HEYGEN_FOLDER_ID = "a019fbcd82ad420d92599f0da54ca1ab"  # "ALIA" folder on app.heygen.com/projects
PUBLIC_BASE_URL = "https://alia-channel.com"

anthropic_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

HEYGEN_CAPTION_PROMPT = """Tu es rédacteur pour AL.IA Channel, un média Instagram pour les olim francophones en Israël.

Voici le titre d'une vidéo (avatar qui parle) déjà créée sur HeyGen : {title}

Rédige une légende Instagram en français pour ce Reel :
- Commence par un hook accrocheur en une phrase, qui donne envie de regarder la vidéo jusqu'au bout
- 2-3 phrases qui donnent un aperçu utile du contenu, sans tout dévoiler
- Une phrase d'appel à l'action (regarder jusqu'au bout, enregistrer le post, le partager avec quelqu'un que ça peut aider)
- Termine par 5 à 8 hashtags pertinents (mélange de hashtags sur l'alya, Israël, olim, et le sujet précis)

Ton : chaleureux, utile, communautaire — jamais commercial ou "vendeur". Émojis avec modération (2 à 4 max).

Réponds uniquement avec le texte de la légende, sans JSON, sans commentaire."""

STATIC_DIR = Path("/app/static/heygen")
STATIC_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_AGE_SECONDS = 24 * 3600
VIDEO_WAIT_TRIES = 60  # Reels processing takes longer than image containers


def _cleanup_old_uploads():
    cutoff = time.time() - MAX_UPLOAD_AGE_SECONDS
    for f in STATIC_DIR.glob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def _save_video(content: bytes) -> str:
    filename = f"{uuid.uuid4().hex}.mp4"
    (STATIC_DIR / filename).write_bytes(content)
    return f"{PUBLIC_BASE_URL}/heygen/{filename}"


async def _get_published_video_ids() -> list[str]:
    raw = await get_setting("heygen_published_videos")
    return json.loads(raw) if raw else []


async def _mark_video_published(video_id: str):
    ids = await _get_published_video_ids()
    if video_id not in ids:
        ids.append(video_id)
        await set_setting("heygen_published_videos", json.dumps(ids))


async def _publish_reel_from_url(client: httpx.AsyncClient, video_url: str, caption: str) -> dict:
    resp = await client.post(
        f"{GRAPH_BASE}/{META_IG_ACCOUNT_ID}/media",
        data={"video_url": video_url, "media_type": "REELS", "caption": caption, "access_token": META_ACCESS_TOKEN},
    )
    data = resp.json()
    if "id" not in data:
        return {"ok": False, "error": f"Failed to create media container: {data}"}
    creation_id = data["id"]

    await _wait_until_finished(client, creation_id, max_tries=VIDEO_WAIT_TRIES)

    resp = await client.post(
        f"{GRAPH_BASE}/{META_IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": META_ACCESS_TOKEN},
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


@router.get("/videos")
async def list_heygen_videos():
    """List completed videos from the HeyGen account for the dashboard picker."""
    if not HEYGEN_API_KEY:
        return {"ok": False, "error": "HeyGen isn't configured (HEYGEN_API_KEY missing)"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{HEYGEN_API_BASE}/v3/videos",
            headers={"x-api-key": HEYGEN_API_KEY},
            params={"limit": 50, "folder_id": HEYGEN_FOLDER_ID},
        )
    if resp.status_code != 200:
        return {"ok": False, "error": f"HeyGen video list failed: {resp.text}"}

    body = resp.json()
    rows = body.get("data", body if isinstance(body, list) else [])

    published = set(await _get_published_video_ids())
    items = []
    for v in rows:
        if v.get("status") != "completed":
            continue
        items.append(
            {
                "video_id": v["id"],
                "title": v.get("title") or v["id"],
                "thumbnail_url": v.get("thumbnail_url"),
                "duration": v.get("duration"),
                "created_at": v.get("created_at"),
                "already_published": v["id"] in published,
            }
        )
    items.sort(key=lambda x: x["created_at"] or 0, reverse=True)
    return {"ok": True, "items": items}


async def _fetch_and_publish_heygen(video_id: str, caption: str) -> dict:
    if not HEYGEN_API_KEY:
        return {"ok": False, "error": "HeyGen isn't configured (HEYGEN_API_KEY missing)"}
    if not META_ACCESS_TOKEN or not META_IG_ACCOUNT_ID:
        return {"ok": False, "error": "Instagram isn't configured (META_ACCESS_TOKEN / META_IG_ACCOUNT_ID missing)"}

    _cleanup_old_uploads()

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.get(
            f"{HEYGEN_API_BASE}/v3/videos/{video_id}",
            headers={"x-api-key": HEYGEN_API_KEY},
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"HeyGen video fetch failed: {resp.text}"}

        body = resp.json()
        detail = body.get("data", body) if isinstance(body, dict) else {}
        video_url = detail.get("video_url")
        if not video_url:
            return {"ok": False, "error": f"HeyGen video has no video_url yet (status: {detail.get('status')})"}

        video_resp = await client.get(video_url)
        local_url = _save_video(video_resp.content)

        result = await _publish_reel_from_url(client, local_url, caption)

    if result.get("ok"):
        await _mark_video_published(video_id)
    return result


@router.post("/generate-caption")
async def generate_caption(video_title: str = Form(...)):
    """AI-generated Instagram caption from the video's HeyGen title.

    Unlike the Canva carousels (which had 40+ drafts sharing the same
    generic title, so we read the actual slide instead), these HeyGen
    titles come from a curated folder and are genuinely descriptive
    ("5 Erreurs des Olim en Israël"), so the title itself is a reliable
    signal — no need to fetch/analyze a video frame.
    """
    response = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": HEYGEN_CAPTION_PROMPT.format(title=video_title)}],
    )
    caption = response.content[0].text.strip()
    return {"ok": True, "caption": caption}


@router.post("/publish")
async def publish_heygen_video(
    video_id: str = Form(...),
    caption: str = Form(""),
    video_title: str = Form(""),
    thumbnail_url: str = Form(""),
    scheduled_at: str = Form(None),
):
    """Publish a HeyGen video to Instagram as a Reel — or queue it for later.

    If scheduled_at is a future datetime, the post is queued instead of
    published immediately — /fire-scheduled (cron dispatcher) fetches a
    fresh video_url from HeyGen at send time.
    """
    if scheduled_at:
        send_time = _parse_il_datetime(scheduled_at)
        if (send_time - datetime.now(IL_TZ)).total_seconds() > 0:
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO scheduled_heygen_posts (video_id, video_title, caption, send_at, sent, thumbnail_url) VALUES (?,?,?,?,0,?)",
                    (video_id, video_title, caption, send_time.isoformat(), thumbnail_url),
                )
                await db.commit()
            return {"ok": True, "scheduled": True, "send_at": send_time.isoformat()}

    return await _fetch_and_publish_heygen(video_id, caption)


@router.get("/scheduled")
async def list_scheduled_heygen():
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM scheduled_heygen_posts WHERE sent = 0 ORDER BY send_at ASC")
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.delete("/scheduled/{post_id}")
async def delete_scheduled_heygen(post_id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM scheduled_heygen_posts WHERE id = ? AND sent = 0", (post_id,))
        await db.commit()
    return {"ok": True}


@router.post("/fire-scheduled")
async def fire_scheduled_heygen():
    """Called every 15 min by the cron dispatcher, mirrors Instagram's fire-scheduled."""
    now = datetime.now(IL_TZ)
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM scheduled_heygen_posts WHERE sent = 0 AND send_at <= ?", (now.isoformat(),)
        )
        due_ids = [r["id"] for r in await cursor.fetchall()]

    fired = 0
    checked = 0
    for post_id in due_ids:
        # Atomically claim the row so an overlapping call can't publish it twice.
        async with get_db() as db:
            cursor = await db.execute(
                "UPDATE scheduled_heygen_posts SET sent = -1 WHERE id = ? AND sent = 0", (post_id,)
            )
            await db.commit()
            claimed = cursor.rowcount == 1

        if not claimed:
            continue
        checked += 1

        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM scheduled_heygen_posts WHERE id = ?", (post_id,))
            row = dict(await cursor.fetchone())

        result = await _fetch_and_publish_heygen(row["video_id"], row["caption"] or "")
        async with get_db() as db:
            if result.get("ok"):
                await db.execute(
                    "UPDATE scheduled_heygen_posts SET sent = 1, media_id = ?, permalink = ? WHERE id = ?",
                    (result.get("media_id"), result.get("permalink"), post_id),
                )
                fired += 1
            else:
                await db.execute(
                    "UPDATE scheduled_heygen_posts SET sent = 0, error = ? WHERE id = ?",
                    (result.get("error"), post_id),
                )
            await db.commit()

    return {"ok": True, "fired": fired, "checked": checked}
