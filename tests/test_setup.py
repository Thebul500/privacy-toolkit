"""Tests for onboarding: setup detection, wizard routes, and password auth."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client():
    """Patch module-level globals and return a TestClient."""
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
    mock_config.smtp = MagicMock()
    mock_config.smtp.username = "test@example.com"
    mock_config.smtp.password = "fake"

    mock_score = MagicMock()
    mock_score.score = 85
    mock_score.grade = "B"
    mock_score.breaches_count = 0
    mock_score.broker_listings = 0
    mock_score.accounts_found = 0
    mock_score.removals_confirmed = 0
    mock_score.risk_factors = []

    app_module.config = mock_config
    app_module.db = mock_db
    app_module.task_manager = mock_tm

    os.environ.pop("PRIVACY_TOOLKIT_API_KEY", None)
    os.environ.pop("PRIVACY_TOOLKIT_PASSWORD", None)

    profile_mock = MagicMock()
    profile_mock.name = "alice"

    with patch.object(app_module, "list_profiles", return_value=["alice"]), \
         patch.object(app_module, "load_profile", return_value=profile_mock), \
         patch.object(app_module, "load_all_brokers", return_value=[]), \
         patch.object(app_module, "calculate_score", return_value=mock_score):
        client = TestClient(app_module.app, raise_server_exceptions=False)
        client._app_module = app_module
        yield client


def _csrf_post(client, url, data=None, **kwargs):
    """GET a page first to obtain a CSRF token, then POST with it."""
    get_resp = client.get("/setup")
    token = get_resp.cookies.get("_csrf_token", "")
    if data is None:
        data = {}
    data["_csrf_token"] = token
    cookies = kwargs.pop("cookies", {})
    cookies["_csrf_token"] = token
    return client.post(url, data=data, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# is_setup_complete()
# ---------------------------------------------------------------------------


class TestIsSetupComplete:
    def test_returns_dict_keys(self, tmp_path):
        with patch("src.config.DEFAULT_CONFIG", tmp_path / "missing.yaml"), \
             patch("src.config.PROFILES_DIR", tmp_path / "profiles"):
            from src.config import is_setup_complete
            result = is_setup_complete()
        assert "config_exists" in result
        assert "has_profiles" in result
        assert "smtp_configured" in result
        assert "all_complete" in result

    def test_all_missing(self, tmp_path):
        with patch("src.config.DEFAULT_CONFIG", tmp_path / "missing.yaml"), \
             patch("src.config.PROFILES_DIR", tmp_path / "profiles"):
            from src.config import is_setup_complete
            result = is_setup_complete()
        assert result["config_exists"] is False
        assert result["has_profiles"] is False
        assert result["smtp_configured"] is False
        assert result["all_complete"] is False

    def test_config_exists_no_smtp(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("web:\n  port: 8080\n")
        with patch("src.config.DEFAULT_CONFIG", config_path), \
             patch("src.config.PROFILES_DIR", tmp_path / "profiles"):
            from src.config import is_setup_complete
            result = is_setup_complete()
        assert result["config_exists"] is True
        assert result["smtp_configured"] is False
        assert result["all_complete"] is False

    def test_all_complete(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "smtp:\n  username: user@gmail.com\n  password: apppass\n"
        )
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "test.yaml").write_text("name: test\n")
        with patch("src.config.DEFAULT_CONFIG", config_path), \
             patch("src.config.PROFILES_DIR", profiles_dir):
            from src.config import is_setup_complete
            result = is_setup_complete()
        assert result["config_exists"] is True
        assert result["has_profiles"] is True
        assert result["smtp_configured"] is True
        assert result["all_complete"] is True


# ---------------------------------------------------------------------------
# Setup Wizard Routes
# ---------------------------------------------------------------------------


class TestSetupPage:
    def test_get_setup_step_1(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": False, "has_profiles": False,
                                        "smtp_configured": False, "all_complete": False}):
            resp = app_client.get("/setup")
        assert resp.status_code == 200
        assert "Welcome" in resp.text

    def test_get_setup_step_2(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": False, "has_profiles": False,
                                        "smtp_configured": False, "all_complete": False}):
            resp = app_client.get("/setup?step=2")
        assert resp.status_code == 200
        assert "Email Setup" in resp.text

    def test_get_setup_step_4(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": True,
                                        "smtp_configured": True, "all_complete": True}):
            resp = app_client.get("/setup?step=4")
        assert resp.status_code == 200
        assert "All Set" in resp.text


class TestSetupSmtp:
    def test_smtp_save(self, app_client, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("web:\n  port: 8080\n")
        app_module = app_client._app_module
        with patch.object(app_module, "DEFAULT_CONFIG", config_path), \
             patch.object(app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": False,
                                        "smtp_configured": False, "all_complete": False}):
            resp = _csrf_post(app_client, "/setup/smtp", data={
                "smtp_username": "test@gmail.com",
                "smtp_password": "fakepass",
            }, follow_redirects=False)
        assert resp.status_code == 303
        assert "step=3" in resp.headers.get("location", "")

    def test_smtp_test_missing_fields(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": False, "has_profiles": False,
                                        "smtp_configured": False, "all_complete": False}):
            resp = _csrf_post(app_client, "/setup/smtp-test", data={
                "smtp_username": "",
                "smtp_password": "",
            })
        assert resp.status_code == 200
        assert "enter both" in resp.text


class TestSetupSkipSmtp:
    def test_skip_smtp_redirects(self, app_client, tmp_path):
        config_path = tmp_path / "config.yaml"
        example_path = tmp_path / "config.yaml.example"
        example_path.write_text("web:\n  port: 8080\n")
        app_module = app_client._app_module
        with patch.object(app_module, "DEFAULT_CONFIG", config_path), \
             patch.object(app_module, "TOOLKIT_DIR", tmp_path), \
             patch.object(app_module, "is_setup_complete",
                          return_value={"config_exists": False, "has_profiles": False,
                                        "smtp_configured": False, "all_complete": False}):
            resp = _csrf_post(app_client, "/setup/skip-smtp", follow_redirects=False)
        assert resp.status_code == 303
        assert "step=3" in resp.headers.get("location", "")


class TestSetupComplete:
    def test_complete_redirects_to_dashboard(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": True,
                                        "smtp_configured": True, "all_complete": True}):
            resp = _csrf_post(app_client, "/setup/complete", follow_redirects=False)
        assert resp.status_code == 303
        loc = resp.headers.get("location", "")
        assert "message=" in loc or loc == "/"


# ---------------------------------------------------------------------------
# Dashboard Redirect
# ---------------------------------------------------------------------------


class TestDashboardRedirect:
    def test_redirects_to_setup_when_incomplete(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": False, "has_profiles": False,
                                        "smtp_configured": False, "all_complete": False}):
            resp = app_client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert "/setup" in resp.headers.get("location", "")

    def test_shows_dashboard_when_complete(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": True,
                                        "smtp_configured": True, "all_complete": True}):
            resp = app_client.get("/")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text


# ---------------------------------------------------------------------------
# Profile Redirect Support
# ---------------------------------------------------------------------------


class TestProfileRedirect:
    def test_create_profile_with_redirect(self, app_client):
        app_module = app_client._app_module
        with patch.object(app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": False,
                                        "smtp_configured": False, "all_complete": False}), \
             patch.object(app_module, "validate_safe_name") as mock_vsn:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_vsn.return_value = mock_path

            from src.models import Profile
            with patch.object(Profile, "to_yaml"):
                resp = _csrf_post(app_client, "/profiles", data={
                    "name": "bob",
                    "first_name": "Bob",
                    "last_name": "",
                    "emails": "",
                    "phones": "",
                    "usernames": "",
                    "redirect": "/setup?step=4",
                }, follow_redirects=False)
        assert resp.status_code == 303
        assert "/setup" in resp.headers.get("location", "")


# ---------------------------------------------------------------------------
# Password Auth
# ---------------------------------------------------------------------------


class TestPasswordAuth:
    def test_no_password_set_allows_access(self, app_client):
        os.environ.pop("PRIVACY_TOOLKIT_PASSWORD", None)
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": True,
                                        "smtp_configured": True, "all_complete": True}):
            resp = app_client.get("/")
        assert resp.status_code == 200

    def test_password_set_redirects_to_login(self):
        """When PRIVACY_TOOLKIT_PASSWORD is set, unauthenticated requests redirect."""
        with patch.dict("os.environ", {"PRIVACY_TOOLKIT_PASSWORD": "secret123"}):
            import src.app as app_module
            client = TestClient(app_module.app, raise_server_exceptions=False)
            resp = client.get("/profiles", follow_redirects=False)
        assert resp.status_code == 303
        assert "/login" in resp.headers.get("location", "")

    def test_login_page_accessible(self):
        """Login page should not require auth."""
        with patch.dict("os.environ", {"PRIVACY_TOOLKIT_PASSWORD": "secret123"}):
            import src.app as app_module
            client = TestClient(app_module.app, raise_server_exceptions=False)
            resp = client.get("/login")
        # May fail due to lifespan not running, but should NOT be 303 redirect
        assert resp.status_code != 303 or "/login" not in resp.headers.get("location", "")

    def test_setup_exempt_from_password(self):
        """Setup page should not require auth."""
        with patch.dict("os.environ", {"PRIVACY_TOOLKIT_PASSWORD": "secret123"}):
            import src.app as app_module
            client = TestClient(app_module.app, raise_server_exceptions=False)
            resp = client.get("/setup", follow_redirects=False)
        # Should not redirect to login
        assert "/login" not in resp.headers.get("location", "")


class TestLoginRoutes:
    def test_get_login(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": True,
                                        "smtp_configured": True, "all_complete": True}):
            resp = app_client.get("/login")
        assert resp.status_code == 200
        assert "password" in resp.text.lower()

    def test_login_wrong_password(self, app_client):
        with patch.dict("os.environ", {"PRIVACY_TOOLKIT_PASSWORD": "correct"}), \
             patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": True,
                                        "smtp_configured": True, "all_complete": True}):
            resp = _csrf_post(app_client, "/login", data={
                "password": "wrong",
            }, follow_redirects=False)
        assert resp.status_code == 303
        assert "error" in resp.headers.get("location", "").lower()

    def test_login_correct_password(self, app_client):
        with patch.dict("os.environ", {"PRIVACY_TOOLKIT_PASSWORD": "correct"}), \
             patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": True,
                                        "smtp_configured": True, "all_complete": True}):
            resp = _csrf_post(app_client, "/login", data={
                "password": "correct",
            }, follow_redirects=False)
        assert resp.status_code == 303
        loc = resp.headers.get("location", "")
        assert loc == "/" or loc.startswith("/?")
        # Check cookie was set
        assert "_ptk_session" in resp.cookies


# ---------------------------------------------------------------------------
# Nav Link
# ---------------------------------------------------------------------------


class TestNavSetupLink:
    def test_setup_link_shown_when_incomplete(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": False, "has_profiles": False,
                                        "smtp_configured": False, "all_complete": False}):
            resp = app_client.get("/setup")
        assert resp.status_code == 200
        assert "Setup Required" in resp.text

    def test_setup_link_hidden_when_complete(self, app_client):
        with patch.object(app_client._app_module, "is_setup_complete",
                          return_value={"config_exists": True, "has_profiles": True,
                                        "smtp_configured": True, "all_complete": True}):
            resp = app_client.get("/profiles")
        assert resp.status_code == 200
        assert "Setup Required" not in resp.text
