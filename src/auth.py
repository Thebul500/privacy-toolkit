"""Authentication middleware for Privacy Toolkit.

**API Key auth** — activated by ``PRIVACY_TOOLKIT_API_KEY`` env var.
Every request (except exempted paths) must include a matching key via either:
  - ``Authorization: Bearer <key>`` header, or
  - ``?api_key=<key>`` query parameter.
When the env var is **not** set, all requests pass through (local dev mode).

**Password auth** — activated by ``PRIVACY_TOOLKIT_PASSWORD`` env var.
Sets a session cookie on successful login.  Simpler alternative to
OAuth2 Proxy for self-hosted deployments.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

EXEMPT_PREFIXES = ("/api/health", "/static/", "/docs", "/openapi.json")
PASSWORD_EXEMPT = ("/api/health", "/static/", "/login", "/setup")


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = os.environ.get("PRIVACY_TOOLKIT_API_KEY", "")
        if not api_key:
            return await call_next(request)

        path = request.url.path
        if any(path == p or path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and auth_header[7:] == api_key:
            return await call_next(request)

        # Check query parameter
        if request.query_params.get("api_key") == api_key:
            return await call_next(request)

        return JSONResponse({"detail": "Unauthorized"}, status_code=401)


def _password_hash(password: str) -> str:
    """Derive a deterministic session token from the password."""
    return hashlib.sha256(password.encode()).hexdigest()[:32]


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """Simple password gate activated by PRIVACY_TOOLKIT_PASSWORD env var."""

    async def dispatch(self, request: Request, call_next):
        password = os.environ.get("PRIVACY_TOOLKIT_PASSWORD", "")
        if not password:
            return await call_next(request)

        path = request.url.path
        if any(path == p or path.startswith(p) for p in PASSWORD_EXEMPT):
            return await call_next(request)

        expected = _password_hash(password)
        cookie = request.cookies.get("_ptk_session", "")
        if hmac.compare_digest(cookie, expected):
            return await call_next(request)

        return RedirectResponse("/login", status_code=303)
