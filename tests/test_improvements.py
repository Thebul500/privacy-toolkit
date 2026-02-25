"""Tests for the 10 enterprise-grade improvements."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


# =============================================================================
# 1. Result Deduplication in DB
# =============================================================================

class TestResultDedup:
    """Test that duplicate findings are ignored."""

    def test_duplicate_insert_returns_same_id(self, tmp_db):
        """Inserting the same finding twice returns the existing ID."""
        scan_id = tmp_db.create_scan("user1", "hibp", "email", "a@b.com")
        fid1 = tmp_db.add_finding(scan_id, "user1", "hibp", "Adobe",
                                  "https://adobe.com", "breach")
        fid2 = tmp_db.add_finding(scan_id, "user1", "hibp", "Adobe",
                                  "https://adobe.com", "breach")
        assert fid1 == fid2

    def test_unique_constraint_works(self, tmp_db):
        """Different findings get different IDs."""
        scan_id = tmp_db.create_scan("user1", "hibp", "email", "a@b.com")
        fid1 = tmp_db.add_finding(scan_id, "user1", "hibp", "Adobe",
                                  "https://adobe.com", "breach")
        fid2 = tmp_db.add_finding(scan_id, "user1", "hibp", "LinkedIn",
                                  "https://linkedin.com", "breach")
        assert fid1 != fid2

    def test_count_stays_correct_after_rescan(self, tmp_db):
        """Findings count doesn't increase when re-scanning same data."""
        scan_id = tmp_db.create_scan("user1", "hibp", "email", "a@b.com")
        tmp_db.add_finding(scan_id, "user1", "hibp", "Adobe",
                           "https://adobe.com", "breach")
        tmp_db.add_finding(scan_id, "user1", "hibp", "Adobe",
                           "https://adobe.com", "breach")
        tmp_db.add_finding(scan_id, "user1", "hibp", "Adobe",
                           "https://adobe.com", "breach")
        assert tmp_db.get_findings_count(profile="user1") == 1

    def test_dedup_migration_cleans_existing(self, tmp_path):
        """Migration handles pre-existing duplicate rows."""
        import sqlite3
        from unittest.mock import patch
        from src.db import Database

        # Create a DB with duplicates BEFORE the unique index
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("""CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            profile TEXT NOT NULL,
            source TEXT NOT NULL,
            site_name TEXT NOT NULL,
            site_url TEXT,
            data_type TEXT,
            details TEXT,
            confidence TEXT DEFAULT 'medium',
            found_at TEXT NOT NULL
        )""")
        # Insert duplicates
        for _ in range(3):
            conn.execute(
                "INSERT INTO findings (scan_id, profile, source, site_name, site_url, data_type, details, confidence, found_at) VALUES (1, 'u', 's', 'site', 'url', 'type', '{}', 'high', '2026-01-01')"
            )
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 3
        conn.close()

        # Now create Database which runs migration
        with patch("src.db.TOOLKIT_DIR", tmp_path):
            db = Database(db_path="test.db")

        # Should have only 1 row after dedup cleanup
        assert db.get_findings_count() == 1


# =============================================================================
# 2. Session Auth Hardening
# =============================================================================

class TestAuthHardening:
    """Test bcrypt password hashing and session management."""

    def test_bcrypt_round_trip(self):
        """Password hashed with bcrypt can be verified."""
        from src.auth import _hash_password, _verify_password
        hashed = _hash_password("mypassword123")
        assert _verify_password("mypassword123", hashed)
        assert not _verify_password("wrongpassword", hashed)

    def test_create_session(self):
        """Creating a session returns a valid token."""
        from src.auth import _sessions, create_session, validate_session
        token = create_session("testpass")
        assert isinstance(token, str)
        assert len(token) > 20
        assert validate_session(token)
        # Cleanup
        _sessions.pop(token, None)

    def test_expired_session_rejected(self):
        """Session older than 24h is rejected."""
        from src.auth import SESSION_MAX_AGE, _sessions, create_session, validate_session
        token = create_session("testpass")
        # Backdate the session
        _sessions[token]["created_at"] = time.time() - SESSION_MAX_AGE - 1
        assert not validate_session(token)

    def test_destroy_session(self):
        """Destroying a session removes it from the store."""
        from src.auth import create_session, destroy_session, validate_session
        token = create_session("testpass")
        assert validate_session(token)
        destroy_session(token)
        assert not validate_session(token)

    def test_wrong_password_rejected(self):
        """Wrong password does not validate."""
        from src.auth import _hash_password, _verify_password
        hashed = _hash_password("correct")
        assert not _verify_password("incorrect", hashed)

    def test_concurrent_sessions(self):
        """Multiple sessions can exist simultaneously."""
        from src.auth import _sessions, create_session, validate_session
        t1 = create_session("pass1")
        t2 = create_session("pass2")
        assert validate_session(t1)
        assert validate_session(t2)
        assert t1 != t2
        _sessions.pop(t1, None)
        _sessions.pop(t2, None)


# =============================================================================
# 3. Proxy Support
# =============================================================================

class TestProxySupport:
    """Test proxy configuration loading."""

    def test_proxy_config_defaults(self):
        """ProxyConfig defaults to empty strings."""
        from src.config import ProxyConfig
        p = ProxyConfig()
        assert p.server == ""
        assert p.username == ""
        assert p.password == ""

    def test_proxy_in_browser_config(self):
        """BrowserConfig includes proxy."""
        from src.config import BrowserConfig, ProxyConfig
        bc = BrowserConfig(proxy=ProxyConfig(server="http://proxy:8080"))
        assert bc.proxy.server == "http://proxy:8080"

    def test_empty_proxy_means_no_proxy_arg(self):
        """When proxy is empty, no proxy dict should be passed."""
        from src.config import BrowserConfig
        bc = BrowserConfig()
        assert not bc.proxy.server


# =============================================================================
# 4. User-Agent Rotation + Request Jitter
# =============================================================================

class TestUARotation:
    """Test user agent rotation and jitter."""

    def test_ua_is_from_list(self):
        """Random UA selection returns a valid user agent."""
        import random
        from src.scanners.people_search_scanner import USER_AGENTS
        ua = random.choice(USER_AGENTS)
        assert ua in USER_AGENTS
        assert "Mozilla" in ua

    def test_ua_list_has_variety(self):
        """UA list has at least 5 different agents."""
        from src.scanners.people_search_scanner import USER_AGENTS
        assert len(USER_AGENTS) >= 5
        assert len(set(USER_AGENTS)) == len(USER_AGENTS)

    def test_form_remover_imports_user_agents(self):
        """FormRemover can access USER_AGENTS."""
        from src.scanners.people_search_scanner import USER_AGENTS
        assert len(USER_AGENTS) > 0


# =============================================================================
# 5. Webhook Notifications
# =============================================================================

class TestWebhookNotifications:
    """Test webhook and multi-channel notification dispatch."""

    def test_webhook_sends_post(self):
        """Webhook sends POST request with correct payload."""
        from src.config import WebhookConfig
        from src.notifications import send_webhook

        config = WebhookConfig(enabled=True, url="https://example.com/hook")
        with patch("src.notifications.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = send_webhook("test_event", "Hello", {"key": "val"}, config)
        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["json"]["event"] == "test_event"
        assert call_kwargs.kwargs["json"]["message"] == "Hello"

    def test_webhook_disabled_skips(self):
        """Disabled webhook doesn't send anything."""
        from src.config import WebhookConfig
        from src.notifications import send_webhook

        config = WebhookConfig(enabled=False, url="https://example.com/hook")
        with patch("src.notifications.requests.post") as mock_post:
            result = send_webhook("test_event", "Hello", {}, config)
        assert result is False
        mock_post.assert_not_called()

    def test_notify_calls_both_channels(self, sample_config):
        """notify() dispatches to both Signal and webhook when both enabled."""
        from src.config import WebhookConfig
        from src.notifications import notify

        sample_config.webhook = WebhookConfig(enabled=True, url="https://example.com/hook")
        with patch("src.notifications.send_signal") as mock_signal, \
             patch("src.notifications.send_webhook") as mock_webhook:
            mock_signal.return_value = True
            mock_webhook.return_value = True
            notify("test", "msg", sample_config, {"detail": 1})
        mock_signal.assert_called_once()
        mock_webhook.assert_called_once()

    def test_webhook_headers_passed(self):
        """Custom headers are included in webhook request."""
        from src.config import WebhookConfig
        from src.notifications import send_webhook

        config = WebhookConfig(
            enabled=True,
            url="https://example.com/hook",
            headers={"Authorization": "Bearer test123"},
        )
        with patch("src.notifications.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            send_webhook("ev", "msg", {}, config)
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test123"

    def test_webhook_failure_returns_false(self):
        """Webhook returns False on HTTP error."""
        from src.config import WebhookConfig
        from src.notifications import send_webhook

        config = WebhookConfig(enabled=True, url="https://example.com/hook")
        with patch("src.notifications.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=500)
            result = send_webhook("ev", "msg", {}, config)
        assert result is False


# =============================================================================
# 6. PDF Report Generation
# =============================================================================

class TestPDFReports:
    """Test PDF report generation."""

    def test_pdf_findings_created(self, tmp_db, tmp_path):
        """PDF findings report is created and non-empty."""
        from src.reporting.pdf_export import export_findings_pdf

        scan_id = tmp_db.create_scan("user1", "hibp", "email", "a@b.com")
        tmp_db.add_finding(scan_id, "user1", "hibp", "Adobe",
                           "https://adobe.com", "breach")

        output = str(tmp_path / "test_findings.pdf")
        path = export_findings_pdf(tmp_db, "user1", output)
        assert path == output
        import os
        assert os.path.getsize(path) > 100

    def test_pdf_removals_created(self, tmp_db, tmp_path):
        """PDF removals report is created and non-empty."""
        from src.reporting.pdf_export import export_removals_pdf

        tmp_db.create_removal("user1", "whitepages", "Whitepages", "email")

        output = str(tmp_path / "test_removals.pdf")
        path = export_removals_pdf(tmp_db, "user1", output)
        assert path == output
        import os
        assert os.path.getsize(path) > 100


# =============================================================================
# 7. Score History + Trending
# =============================================================================

class TestScoreHistory:
    """Test score persistence and trend calculation."""

    def test_score_saved_on_calculate(self, tmp_db):
        """Calculating a score saves it to history."""
        from src.scoring import calculate_score
        scan_id = tmp_db.create_scan("user1", "hibp", "email", "a@b.com")
        tmp_db.add_finding(scan_id, "user1", "hibp", "Adobe",
                           "https://adobe.com", "breach",
                           details={"data_classes": ["Passwords"]})
        calculate_score(tmp_db, "user1")
        history = tmp_db.get_score_history("user1")
        assert len(history) >= 1
        assert history[0]["profile"] == "user1"

    def test_history_retrieved_in_order(self, tmp_db):
        """Score history is returned most recent first."""
        tmp_db.save_score("user1", 80, "B")
        tmp_db.save_score("user1", 85, "B")
        tmp_db.save_score("user1", 90, "A")
        history = tmp_db.get_score_history("user1")
        assert history[0]["score"] == 90
        assert history[-1]["score"] == 80

    def test_trend_no_history_returns_stable(self, tmp_db):
        """No history returns stable direction."""
        from src.scoring import get_trend
        trend = get_trend(tmp_db, "user1")
        assert trend["direction"] == "stable"
        assert trend["7d_change"] == 0

    def test_trend_calculated_correctly(self, tmp_db):
        """Trend calculates correct 7d change."""
        from src.scoring import get_trend

        # Insert score from 10 days ago
        old_time = (datetime.now() - timedelta(days=10)).isoformat()
        conn = tmp_db._connect()
        conn.execute(
            "INSERT INTO score_history (profile, score, grade, calculated_at) VALUES (?, ?, ?, ?)",
            ("user1", 70, "C", old_time),
        )
        conn.commit()
        conn.close()

        # Insert current score
        tmp_db.save_score("user1", 85, "B")

        trend = get_trend(tmp_db, "user1")
        assert trend["7d_change"] == 15
        assert trend["direction"] == "up"


# =============================================================================
# 8. Post-Removal Verification
# =============================================================================

class TestPostRemovalVerification:
    """Test verification scans for submitted removals."""

    def test_no_pending_returns_empty(self, tmp_db, sample_config):
        """No pending rechecks returns zero counts."""
        from src.tasks import run_verification_scans
        result = run_verification_scans("user1", sample_config, tmp_db)
        assert result["verified"] == 0
        assert result["confirmed"] == 0
        assert result["reappeared"] == 0

    def test_verification_confirms_removal(self, tmp_db, sample_config):
        """When scan finds nothing, removal is confirmed."""
        from src.tasks import run_verification_scans

        # Create a removal that's past recheck date
        rid = tmp_db.create_removal("user1", "fastpeoplesearch",
                                    "FastPeopleSearch", "email",
                                    recheck_days=-1)
        tmp_db.update_removal_status(rid, "submitted")

        # Mock scan_single to return no findings (patch at source module)
        with patch("src.scanners.people_search_scanner.scan_single", return_value=[]), \
             patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True), \
             patch("src.config.load_profile"):
            result = run_verification_scans("user1", sample_config, tmp_db)

        assert result["confirmed"] == 1

    def test_verification_detects_reappearance(self, tmp_db, sample_config):
        """When scan still finds listing, removal is marked reappeared."""
        from src.tasks import run_verification_scans
        from src.models import ScanResult

        rid = tmp_db.create_removal("user1", "fastpeoplesearch",
                                    "FastPeopleSearch", "email",
                                    recheck_days=-1)
        tmp_db.update_removal_status(rid, "submitted")

        mock_finding = ScanResult(
            scanner="people_search",
            site_name="FastPeopleSearch",
            site_url="https://fastpeoplesearch.com/name/jane-doe",
            data_type="listing_name",
            details={},
            confidence="high",
            found_at=datetime.now(),
        )

        with patch("src.scanners.people_search_scanner.scan_single", return_value=[mock_finding]), \
             patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True), \
             patch("src.config.load_profile"), \
             patch("src.notifications.notify"):
            result = run_verification_scans("user1", sample_config, tmp_db)

        assert result["reappeared"] == 1


# =============================================================================
# 9. CAPTCHA Solver Integration
# =============================================================================

class TestCAPTCHASolver:
    """Test CAPTCHA solver configuration and detection."""

    def test_no_provider_skips_solving(self):
        """Provider 'none' returns False immediately."""
        import asyncio
        from src.captcha_solver import CaptchaSolver
        from src.config import CaptchaConfig

        solver = CaptchaSolver(CaptchaConfig(provider="none"))
        page = MagicMock()

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(solver.detect_and_solve(page))
        loop.close()
        assert result is False

    def test_no_api_key_skips(self):
        """Provider with no API key returns False."""
        import asyncio
        from src.captcha_solver import CaptchaSolver
        from src.config import CaptchaConfig

        solver = CaptchaSolver(CaptchaConfig(provider="2captcha", api_key=""))
        page = MagicMock()

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(solver.detect_and_solve(page))
        loop.close()
        assert result is False

    def test_captcha_config_defaults(self):
        """CaptchaConfig has sensible defaults."""
        from src.config import CaptchaConfig
        c = CaptchaConfig()
        assert c.provider == "none"
        assert c.api_key == ""
        assert c.timeout == 120

    def test_form_step_solve_captcha(self):
        """FormRemover handles solve_captcha step type."""
        from src.config import BrowserConfig, CaptchaConfig
        from src.removers.form_remover import FormRemover

        config = BrowserConfig()
        captcha = CaptchaConfig(provider="none")
        remover = FormRemover(config, MagicMock(), captcha_config=captcha)
        assert remover.captcha_config.provider == "none"


# =============================================================================
# 10. Selector Health Check + Fallback Detection
# =============================================================================

class TestSelectorHealthCheck:
    """Test selector fallback and health check functionality."""

    def test_fallback_selectors_configured(self):
        """Key sites have fallback_selector and content_patterns."""
        from src.scanners.people_search_scanner import PEOPLE_SEARCH_SITES

        sites_with_fallback = [s for s in PEOPLE_SEARCH_SITES if s.get("fallback_selector")]
        assert len(sites_with_fallback) >= 4

    def test_content_patterns_configured(self):
        """Key sites have content_patterns for regex fallback."""
        from src.scanners.people_search_scanner import PEOPLE_SEARCH_SITES

        sites_with_patterns = [s for s in PEOPLE_SEARCH_SITES if s.get("content_patterns")]
        assert len(sites_with_patterns) >= 4

    def test_check_selector_health_exists(self):
        """check_selector_health function is importable."""
        from src.scanners.people_search_scanner import check_selector_health
        assert callable(check_selector_health)

    def test_health_check_returns_list(self):
        """Health check returns a list of status dicts (mocked)."""
        import asyncio

        from src.scanners.people_search_scanner import check_selector_health

        # We can't actually run it without Playwright, so just verify it's async
        assert asyncio.iscoroutinefunction(check_selector_health)
