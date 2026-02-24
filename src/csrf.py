"""Double-submit cookie CSRF protection middleware."""

from __future__ import annotations

import secrets
from urllib.parse import parse_qs

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Protect POST/PUT/PATCH/DELETE routes with a double-submit cookie.

    On safe methods (GET/HEAD/OPTIONS) a random ``_csrf_token`` cookie is set
    and stashed in ``request.state.csrf_token`` for template rendering.

    On state-changing methods the cookie value must match either:
      - a ``_csrf_token`` form field, **or**
      - an ``X-CSRF-Token`` header (used by HTMX).

    Paths starting with ``/api/`` are exempt (they use API key auth instead).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # API routes are exempt — they rely on API key auth
        if request.url.path.startswith("/api/"):
            return await call_next(request)

        cookie_token = request.cookies.get("_csrf_token", "")

        if request.method in ("GET", "HEAD", "OPTIONS"):
            # Issue a new token if one doesn't exist yet
            if not cookie_token:
                cookie_token = secrets.token_urlsafe(32)
            request.state.csrf_token = cookie_token
            response = await call_next(request)
            response.set_cookie(
                "_csrf_token",
                cookie_token,
                httponly=False,  # JS needs to read it for HTMX headers
                samesite="strict",
                path="/",
            )
            return response

        # State-changing method — validate the token
        submitted = ""

        # Check header first (HTMX path)
        submitted = request.headers.get("X-CSRF-Token", "")

        # Fall back to form field — read raw body to avoid consuming the
        # stream that FastAPI needs for Form() parameter parsing.
        if not submitted:
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                body = await request.body()
                parsed = parse_qs(body.decode("utf-8", errors="replace"))
                values = parsed.get("_csrf_token", [])
                submitted = values[0] if values else ""
            elif "multipart/form-data" in content_type:
                # For multipart, read raw body and search for the token field.
                # We use request.body() which is cached by Starlette.
                body = await request.body()
                body_str = body.decode("utf-8", errors="replace")
                # Simple extraction: look for the _csrf_token field value
                marker = 'name="_csrf_token"'
                idx = body_str.find(marker)
                if idx != -1:
                    # Value follows after two CRLFs
                    rest = body_str[idx + len(marker):]
                    parts = rest.split("\r\n\r\n", 1)
                    if len(parts) > 1:
                        value_part = parts[1].split("\r\n", 1)[0]
                        submitted = value_part.strip()

        if not cookie_token or not submitted or cookie_token != submitted:
            return JSONResponse(
                {"detail": "CSRF token missing or invalid"},
                status_code=403,
            )

        request.state.csrf_token = cookie_token
        response = await call_next(request)
        return response
