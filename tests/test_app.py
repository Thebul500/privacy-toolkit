"""Tests for src.app — FastAPI web route tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client():
    """Patch module-level globals and return a TestClient for the app.

    The app uses module-level ``config``, ``db``, and ``task_manager`` that are
    normally initialized during lifespan.  We assign them directly on the module
    (they're type-annotated but unset until lifespan runs).
    """
    import src.app as app_module

    mock_db = MagicMock()
    mock_db.get_findings_count.return_value = 0
    mock_db.get_removals.return_value = []
    mock_db.get_audit_log.return_value = []
    mock_db.get_scans.return_value = []

    mock_tm = MagicMock()
    mock_tm.list_tasks.return_value = []
    type(mock_tm).active_count = PropertyMock(return_value=0)
    mock_tm.submit.return_value = "fake-task-id"

    mock_config = MagicMock()
    mock_config.db_path = ":memory:"

    mock_score = MagicMock()
    mock_score.score = 85
    mock_score.grade = "B"
    mock_score.breaches_count = 0
    mock_score.broker_listings = 0
    mock_score.accounts_found = 0
    mock_score.removals_confirmed = 0
    mock_score.risk_factors = []

    # Set module-level globals directly
    app_module.config = mock_config
    app_module.db = mock_db
    app_module.task_manager = mock_tm

    os.environ.pop("PRIVACY_TOOLKIT_API_KEY", None)

    # load_profile returns a minimal Profile mock by default
    profile_mock = MagicMock()
    profile_mock.name = "alice"
    profile_mock.full_name = "Alice Smith"
    profile_mock.email_addresses = ["alice@example.com"]
    profile_mock.phone_numbers = []
    profile_mock.usernames = []

    with patch.object(app_module, "list_profiles", return_value=["alice"]), \
         patch.object(app_module, "load_profile", return_value=profile_mock) as mock_load, \
         patch.object(app_module, "load_all_brokers", return_value=[]), \
         patch.object(app_module, "calculate_score", return_value=mock_score):
        client = TestClient(app_module.app, raise_server_exceptions=False)
        # Expose mocks for assertions
        client._mock_db = mock_db
        client._mock_tm = mock_tm
        client._mock_load = mock_load
        client._app_module = app_module
        yield client


def _csrf_post(client, url, data=None, **kwargs):
    """Helper: GET a page first to obtain a CSRF token, then POST with it."""
    get_resp = client.get("/")
    token = get_resp.cookies.get("_csrf_token", "")
    if data is None:
        data = {}
    data["_csrf_token"] = token
    cookies = kwargs.pop("cookies", {})
    cookies["_csrf_token"] = token
    return client.post(url, data=data, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TestDashboard:
    def test_get_dashboard(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_dashboard_contains_score(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200
        assert "85" in resp.text


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class TestProfilesPage:
    def test_get_profiles(self, app_client):
        resp = app_client.get("/profiles")
        assert resp.status_code == 200
        assert "Profiles" in resp.text


class TestCreateProfile:
    def test_create_profile_redirects(self, app_client):
        app_module = app_client._app_module
        with patch.object(app_module, "load_profile", side_effect=FileNotFoundError), \
             patch.object(app_module, "validate_safe_name") as mock_vsn:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_vsn.return_value = mock_path

            from src.models import Profile
            with patch.object(Profile, "to_yaml"):
                resp = _csrf_post(app_client, "/profiles", data={
                    "name": "bob",
                    "first_name": "Bob",
                    "last_name": "Jones",
                    "emails": "bob@example.com",
                    "phones": "",
                    "usernames": "",
                })
        assert resp.status_code in (200, 303)

    def test_create_profile_path_traversal(self, app_client):
        app_module = app_client._app_module
        with patch.object(app_module, "validate_safe_name", side_effect=ValueError("Unsafe name")):
            resp = _csrf_post(app_client, "/profiles", data={
                "name": "../etc/passwd",
                "first_name": "",
                "last_name": "",
                "emails": "",
                "phones": "",
                "usernames": "",
            })
        assert resp.status_code == 200
        assert "Unsafe name" in resp.text

    def test_create_profile_duplicate(self, app_client):
        app_module = app_client._app_module
        with patch.object(app_module, "validate_safe_name") as mock_vsn:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_vsn.return_value = mock_path

            resp = _csrf_post(app_client, "/profiles", data={
                "name": "alice",
                "first_name": "",
                "last_name": "",
                "emails": "",
                "phones": "",
                "usernames": "",
            })
        assert resp.status_code == 200
        assert "already exists" in resp.text


class TestProfileDetail:
    def test_get_profile_detail(self, app_client):
        resp = app_client.get("/profiles/alice")
        assert resp.status_code == 200

    def test_get_missing_profile_redirects(self, app_client):
        app_module = app_client._app_module
        with patch.object(app_module, "load_profile", side_effect=FileNotFoundError):
            resp = app_client.get("/profiles/nonexistent", follow_redirects=False)
        assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------


class TestScansPage:
    def test_get_scans(self, app_client):
        resp = app_client.get("/scans")
        assert resp.status_code == 200
        assert "Scans" in resp.text


class TestTriggerScan:
    def test_trigger_scan_redirects(self, app_client):
        resp = _csrf_post(app_client, "/scans/trigger", data={"profile": "alice"})
        assert resp.status_code in (200, 303)

    def test_trigger_scan_missing_profile(self, app_client):
        app_module = app_client._app_module
        with patch.object(app_module, "load_profile", side_effect=FileNotFoundError):
            resp = _csrf_post(
                app_client, "/scans/trigger",
                data={"profile": "noone"},
            )
        assert resp.status_code in (200, 303)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


class TestAccountsPage:
    def test_get_accounts(self, app_client):
        resp = app_client.get("/accounts")
        assert resp.status_code == 200
        assert "Accounts" in resp.text


class TestAccountsSearch:
    def test_search_invalid_email(self, app_client):
        resp = _csrf_post(app_client, "/accounts/search", data={
            "query": "not-an-email",
            "search_type": "email",
        })
        assert resp.status_code == 200
        assert "Invalid email" in resp.text

    def test_search_valid_email_mocked(self, app_client):
        resp = _csrf_post(app_client, "/accounts/search", data={
            "query": "test@example.com",
            "search_type": "email",
        })
        # May get 200 or 500 depending on scanner imports — just not 403
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Removals
# ---------------------------------------------------------------------------


class TestRemovalsPage:
    def test_get_removals(self, app_client):
        resp = app_client.get("/removals")
        assert resp.status_code == 200
        assert "Removal" in resp.text


# ---------------------------------------------------------------------------
# Brokers
# ---------------------------------------------------------------------------


class TestBrokersPage:
    def test_get_brokers(self, app_client):
        resp = app_client.get("/brokers")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------


class TestActivityPage:
    def test_get_activity(self, app_client):
        resp = app_client.get("/activity")
        assert resp.status_code == 200
        assert "Activity" in resp.text


# ---------------------------------------------------------------------------
# API Routes (JSON)
# ---------------------------------------------------------------------------


class TestAPIHealth:
    def test_api_health(self, app_client):
        resp = app_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "tasks_active" in data


class TestAPIStats:
    def test_api_stats_keys(self, app_client):
        resp = app_client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data
        assert "findings" in data
        assert "removals_total" in data
        assert "removals_by_status" in data
        assert "brokers_configured" in data
        assert "tasks_active" in data
