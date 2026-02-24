"""Tests for src.csrf — CSRF double-submit cookie middleware."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch, PropertyMock

from fastapi.testclient import TestClient


def _make_client():
    """Create a TestClient with module-level globals patched out."""
    import src.app as app_module

    mock_db = MagicMock()
    mock_db.get_findings_count.return_value = 0
    mock_db.get_removals.return_value = []
    mock_db.get_audit_log.return_value = []
    mock_db.get_scans.return_value = []

    mock_tm = MagicMock()
    mock_tm.list_tasks.return_value = []
    type(mock_tm).active_count = PropertyMock(return_value=0)

    mock_config = MagicMock()
    mock_config.db_path = ":memory:"

    # Set module-level globals directly (they're type-annotated, not assigned)
    app_module.config = mock_config
    app_module.db = mock_db
    app_module.task_manager = mock_tm

    os.environ.pop("PRIVACY_TOOLKIT_API_KEY", None)

    with patch.object(app_module, "list_profiles", return_value=[]), \
         patch.object(app_module, "load_profile", side_effect=FileNotFoundError), \
         patch.object(app_module, "load_all_brokers", return_value=[]), \
         patch.object(app_module, "calculate_score", return_value=None):
        client = TestClient(app_module.app, raise_server_exceptions=False)

    return client


class TestCSRFGetSetsCookie:
    """GET requests should receive a _csrf_token cookie."""

    def test_get_sets_csrf_cookie(self):
        client = _make_client()
        resp = client.get("/")
        assert "_csrf_token" in resp.cookies
        assert len(resp.cookies["_csrf_token"]) > 10


class TestCSRFPostWithoutToken:
    """POST without a CSRF token should return 403."""

    def test_post_without_token_rejected(self):
        client = _make_client()
        resp = client.post("/profiles", data={"name": "test"})
        assert resp.status_code == 403


class TestCSRFPostWithFormField:
    """POST with matching cookie + form field should pass CSRF check."""

    def test_post_with_form_field_passes(self):
        client = _make_client()
        # First GET to obtain a token
        get_resp = client.get("/profiles")
        token = get_resp.cookies["_csrf_token"]
        # POST with the token as form field
        resp = client.post(
            "/profiles",
            data={"name": "testprofile", "_csrf_token": token},
            cookies={"_csrf_token": token},
        )
        # Should not be 403 (may be redirect 303 or error, but not CSRF rejection)
        assert resp.status_code != 403


class TestCSRFPostWithHeader:
    """POST with matching cookie + X-CSRF-Token header should pass (HTMX path)."""

    def test_post_with_header_passes(self):
        client = _make_client()
        get_resp = client.get("/accounts")
        token = get_resp.cookies["_csrf_token"]
        resp = client.post(
            "/accounts/search",
            data={"query": "test@example.com", "search_type": "email", "_csrf_token": token},
            headers={"X-CSRF-Token": token},
            cookies={"_csrf_token": token},
        )
        assert resp.status_code != 403


class TestCSRFPostMismatch:
    """POST with mismatched cookie and form token should return 403."""

    def test_post_with_mismatched_token_rejected(self):
        client = _make_client()
        get_resp = client.get("/")
        token = get_resp.cookies["_csrf_token"]
        resp = client.post(
            "/profiles",
            data={"name": "test", "_csrf_token": "wrong-token"},
            cookies={"_csrf_token": token},
        )
        assert resp.status_code == 403


class TestCSRFAPIExempt:
    """API routes should be exempt from CSRF checks."""

    def test_api_health_exempt(self):
        client = _make_client()
        resp = client.get("/api/health")
        assert resp.status_code != 403

    def test_api_stats_exempt(self):
        client = _make_client()
        resp = client.get("/api/stats")
        assert resp.status_code != 403
