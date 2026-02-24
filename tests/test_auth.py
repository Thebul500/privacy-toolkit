"""Tests for src.auth — API key middleware."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _get_app():
    """Import app fresh (module-level state depends on lifespan)."""
    from src.app import app
    return app


class TestAPIKeyMiddleware:
    """Test the optional API key authentication middleware."""

    def test_no_key_configured_allows_all(self):
        """When PRIVACY_TOOLKIT_API_KEY is unset, all requests pass (not 401)."""
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("PRIVACY_TOOLKIT_API_KEY", None)
            client = TestClient(_get_app(), raise_server_exceptions=False)
            # /api/stats may 500 if lifespan not run, but must NOT be 401
            resp = client.get("/api/stats")
            assert resp.status_code != 401

    def test_bearer_token_accepted(self):
        """Requests with correct Bearer token should succeed."""
        with patch.dict("os.environ", {"PRIVACY_TOOLKIT_API_KEY": "test-secret-key"}):
            client = TestClient(_get_app(), raise_server_exceptions=False)
            resp = client.get(
                "/api/stats",
                headers={"Authorization": "Bearer test-secret-key"},
            )
            # May get 500 if lifespan not run, but should NOT be 401
            assert resp.status_code != 401

    def test_missing_key_rejected(self):
        """Requests without a key should get 401 when key is configured."""
        with patch.dict("os.environ", {"PRIVACY_TOOLKIT_API_KEY": "test-secret-key"}):
            client = TestClient(_get_app(), raise_server_exceptions=False)
            resp = client.get("/api/stats")
            assert resp.status_code == 401

    def test_health_exempt(self):
        """The /api/health endpoint should be exempt from auth."""
        with patch.dict("os.environ", {"PRIVACY_TOOLKIT_API_KEY": "test-secret-key"}):
            client = TestClient(_get_app(), raise_server_exceptions=False)
            resp = client.get("/api/health")
            # Health endpoint may fail due to lifespan but should NOT be 401
            assert resp.status_code != 401
