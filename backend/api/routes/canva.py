"""
Canva Connect API — OAuth (PKCE) so we can call the Autofill API against a
Brand Template and pull the rendered carousel images back out.

Flow (one-time bootstrap, then auto-refreshed):
  1. Admin opens /api/canva/oauth/start in a browser -> redirected to Canva to log in + approve.
  2. Canva redirects back to /api/canva/oauth/callback?code=... -> we exchange the code
     for an access_token + refresh_token and store both in the settings table.
  3. get_valid_access_token() is used by the rest of the app; it refreshes automatically
     once the access token is close to expiring.

Both endpoints are public (see api/auth.py) because Canva's own redirect can't carry our
X-Admin-Key header. That's safe: /start only redirects to Canva's own login/consent screen,
and /callback can only succeed with a real `code`, which Canva only issues after the actual
Canva account owner approves access on Canva's site — nothing here works without that.
"""
import base64
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from api.routes.settings import get_setting, set_setting

router = APIRouter()

CANVA_CLIENT_ID = os.getenv("CANVA_CLIENT_ID", "")
CANVA_CLIENT_SECRET = os.getenv("CANVA_CLIENT_SECRET", "")
CANVA_REDIRECT_URI = "https://alia-channel.com/api/canva/oauth/callback"
CANVA_AUTHORIZE_URL = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"

# Must exactly match what's enabled on the Integration's "Scopes" tab at
# canva.com/developers, or the authorize request fails with invalid_scope.
# asset:write is intentionally excluded — only asset:read is enabled there.
# folder:read is required to list the "ALIA carrousels" folder contents.
CANVA_SCOPES = "design:content:read design:content:write brandtemplate:content:read brandtemplate:content:write brandtemplate:meta:read asset:read folder:read"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@router.get("/oauth/start")
async def canva_oauth_start():
    """Kick off the PKCE flow — open this URL in a browser."""
    verifier = _b64url(secrets.token_bytes(64))[:128]
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    await set_setting("canva_pkce_verifier", verifier)

    params = {
        "code_challenge_method": "s256",
        "response_type": "code",
        "client_id": CANVA_CLIENT_ID,
        "redirect_uri": CANVA_REDIRECT_URI,
        "code_challenge": challenge,
        "scope": CANVA_SCOPES,
    }
    return RedirectResponse(f"{CANVA_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/oauth/callback")
async def canva_oauth_callback(code: str = None, error: str = None):
    if error:
        return {"ok": False, "error": error}
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    verifier = await get_setting("canva_pkce_verifier")
    if not verifier:
        raise HTTPException(status_code=400, detail="No PKCE verifier on file — restart via /oauth/start")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            CANVA_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": CANVA_REDIRECT_URI,
            },
            auth=(CANVA_CLIENT_ID, CANVA_CLIENT_SECRET),
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Canva token exchange failed: {resp.text}")

    data = resp.json()
    await _store_tokens(data)
    return {"ok": True, "message": "Canva connected — you can close this tab."}


async def _store_tokens(data: dict):
    await set_setting("canva_access_token", data["access_token"])
    await set_setting("canva_refresh_token", data["refresh_token"])
    expires_at = int(time.time()) + int(data.get("expires_in", 14400))
    await set_setting("canva_access_token_expires_at", str(expires_at))


async def get_valid_access_token() -> str:
    """Return a live access token, refreshing it first if it's expired/near-expiry."""
    expires_at = await get_setting("canva_access_token_expires_at")
    access_token = await get_setting("canva_access_token")
    refresh_token = await get_setting("canva_refresh_token")

    if not refresh_token:
        raise RuntimeError("Canva isn't connected yet — visit /api/canva/oauth/start first")

    if access_token and expires_at and int(expires_at) - 60 > int(time.time()):
        return access_token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            CANVA_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(CANVA_CLIENT_ID, CANVA_CLIENT_SECRET),
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Canva token refresh failed: {resp.text}")

    data = resp.json()
    await _store_tokens(data)
    return data["access_token"]
