import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

# Routes that must stay reachable without the admin key (public forms / redirects).
PUBLIC_EXACT = {
    ("GET", "/api/health"),
    ("POST", "/api/contests/submit"),
    ("POST", "/api/recommendations"),
}
PUBLIC_PREFIXES = [
    ("GET", "/api/contests/form/"),
    ("GET", "/go/"),
]


def _is_public(method: str, path: str) -> bool:
    if (method, path) in PUBLIC_EXACT:
        return True
    return any(method == m and path.startswith(prefix) for m, prefix in PUBLIC_PREFIXES)


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """Requires X-Admin-Key on every /api/* and /go/* route except the public ones above."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        if not (path.startswith("/api/") or path.startswith("/go/")):
            return await call_next(request)

        if _is_public(request.method, path):
            return await call_next(request)

        if not ADMIN_API_KEY:
            return JSONResponse({"detail": "Server misconfigured: ADMIN_API_KEY not set"}, status_code=500)

        supplied = request.headers.get("x-admin-key", "")
        if not hmac.compare_digest(supplied, ADMIN_API_KEY):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        return await call_next(request)
