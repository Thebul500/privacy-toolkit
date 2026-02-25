"""Authentication middleware for Privacy Toolkit.

**API Key auth** — activated by ``PRIVACY_TOOLKIT_API_KEY`` env var.
Every request (except exempted paths) must include a matching key via either:
  - ``Authorization: Bearer <key>`` header, or
  - ``?api_key=<key>`` query parameter.
When the env var is **not** set, all requests pass through (local dev mode).

**Password auth** — activated by ``PRIVACY_TOOLKIT_PASSWORD`` env var.
Uses bcrypt for password hashing, random session tokens with 24h expiry.
"""

from __future__ import annotations

import hmac
import os
import secrets
import time

import bcrypt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

EXEMPT_PREFIXES = ("/api/health", "/static/", "/docs", "/openapi.json")
PASSWORD_EXEMPT = ("/api/", "/static/", "/login", "/logout", "/setup")

# In-memory session store: token -> {"created_at": float, "password_hash": bytes}
_sessions: dict[str, dict] = {}

SESSION_MAX_AGE = 86400  # 24 hours


def _hash_password(password: str) -> bytes:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())


def _verify_password(password: str, hashed: bytes) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed)


def create_session(password: str) -> str:
    """Create a new session, return the session token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "created_at": time.time(),
        "password_hash": _hash_password(password),
    }
    return token


def validate_session(token: str) -> bool:
    """Check if a session token is valid and not expired."""
    session = _sessions.get(token)
    if not session:
        return False
    if time.time() - session["created_at"] > SESSION_MAX_AGE:
        _sessions.pop(token, None)
        return False
    return True


def destroy_session(token: str) -> None:
    """Remove a session from the store."""
    _sessions.pop(token, None)


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
        if auth_header.startswith("Bearer ") and hmac.compare_digest(auth_header[7:], api_key):
            return await call_next(request)

        # Check query parameter
        if hmac.compare_digest(request.query_params.get("api_key", ""), api_key):
            return await call_next(request)

        return JSONResponse({"detail": "Unauthorized"}, status_code=401)


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """Simple password gate activated by PRIVACY_TOOLKIT_PASSWORD env var."""

    async def dispatch(self, request: Request, call_next):
        password = os.environ.get("PRIVACY_TOOLKIT_PASSWORD", "")
        if not password:
            return await call_next(request)

        path = request.url.path
        if any(path == p or path.startswith(p) for p in PASSWORD_EXEMPT):
            return await call_next(request)

        cookie = request.cookies.get("_ptk_session", "")
        if cookie and validate_session(cookie):
            return await call_next(request)

        return RedirectResponse("/login", status_code=303)
