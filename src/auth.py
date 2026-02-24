"""Optional API key authentication middleware for Privacy Toolkit.

If the ``PRIVACY_TOOLKIT_API_KEY`` environment variable is set, every
request (except exempted paths) must include a matching key via either:
  - ``Authorization: Bearer <key>`` header, or
  - ``?api_key=<key>`` query parameter.

When the env var is **not** set, all requests pass through (local dev mode).
"""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

EXEMPT_PREFIXES = ("/api/health", "/static/", "/docs", "/openapi.json")


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
