"""Tests for profile URL discovery feature across scanner, remover, tasks, app, and CLI."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from src.models import Address, Profile, ScanResult
from src.scanners.people_search_scanner import (
    SITE_BY_SLUG,
    has_scanner_config,
    scan_single,
)


# ---------------------------------------------------------------------------
# has_scanner_config()
# ---------------------------------------------------------------------------


class TestHasScannerConfig:
    def test_known_slug_returns_true(self):
        assert has_scanner_config("radaris") is True

    def test_unknown_slug_returns_false(self):
        assert has_scanner_config("not-a-real-broker") is False

    def test_all_sites_present_in_lookup(self):
        from src.scanners.people_search_scanner import PEOPLE_SEARCH_SITES
        for site in PEOPLE_SEARCH_SITES:
            assert site["slug"] in SITE_BY_SLUG


# ---------------------------------------------------------------------------
# scan_single()
# ---------------------------------------------------------------------------


@pytest.fixture
def profile_for_scan():
    return Profile(
        name="testuser",
        first_name="Jane",
        last_name="Doe",
        full_name="Jane Doe",
        email_addresses=["jane@example.com"],
        phone_numbers=["+15551234567"],
        addresses=[
            Address(street="123 Main St", city="Springfield",
                    state="Illinois", state_abbr="IL", zip_code="62704")
        ],
    )


class TestScanSingle:
    def test_unknown_slug_returns_empty(self, profile_for_scan):
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(scan_single(profile_for_scan, "nonexistent-broker"))
        finally:
            loop.close()
        assert result == []

    @patch("src.scanners.people_search_scanner.PeopleSearchScanner.is_available", return_value=False)
    def test_playwright_unavailable_returns_empty(self, mock_avail, profile_for_scan):
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(scan_single(profile_for_scan, "radaris"))
        finally:
            loop.close()
        assert result == []

    @patch("src.scanners.people_search_scanner.PeopleSearchScanner.is_available", return_value=True)
    def test_scan_single_with_mocked_playwright(self, mock_avail, profile_for_scan):
        """Mock Playwright and _check_site to verify scan_single returns findings."""
        fake_result = ScanResult(
            scanner="people_search",
            site_name="Radaris",
            site_url="https://radaris.com/~Jane-Doe/0123456789",
            data_type="listing_name",
            details={"broker_slug": "radaris"},
            confidence="high",
        )

        mock_context = AsyncMock()
        mock_context.set_default_timeout = MagicMock()
        mock_browser = AsyncMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch.return_value = mock_browser

        mock_pw_cm = AsyncMock()
        mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)
        mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("src.scanners.people_search_scanner.PeopleSearchScanner._check_site",
                    new_callable=AsyncMock, return_value=fake_result), \
             patch("playwright.async_api.async_playwright",
                    return_value=mock_pw_cm):
            loop = asyncio.new_event_loop()
            try:
                results = loop.run_until_complete(scan_single(profile_for_scan, "radaris"))
            finally:
                loop.close()

        assert len(results) == 1
        assert results[0].site_name == "Radaris"
        assert "radaris.com" in results[0].site_url

    def test_scan_single_empty_profile_returns_empty(self):
        """Profile with no name/phone/email should return empty."""
        empty_profile = Profile(name="empty")
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(scan_single(empty_profile, "radaris"))
        finally:
            loop.close()
        assert result == []


# ---------------------------------------------------------------------------
# EmailRemover._discover_listing_url()
# ---------------------------------------------------------------------------


class TestDiscoverListingUrl:
    def test_uses_existing_db_findings(self, tmp_db, sample_profile):
        """If DB already has findings, should return those URLs without scanning."""
        from src.removers.email_remover import EmailRemover
        from src.config import SmtpConfig

        smtp = SmtpConfig(host="localhost", port=587, username="x", password="x")
        remover = EmailRemover(smtp, tmp_db)

        # Insert a finding into DB
        scan_id = tmp_db.create_scan("testuser", "people_search", "name", "Jane Doe")
        tmp_db.add_finding(
            scan_id, "testuser", "people_search", "Radaris",
            "https://radaris.com/~Jane-Doe/123", "listing_name",
            {"broker_slug": "radaris"}, "high",
        )
        tmp_db.complete_scan(scan_id, 1)

        urls = remover._discover_listing_url(sample_profile, "radaris")
        assert len(urls) >= 1
        assert "radaris.com" in urls[0]

    def test_no_scanner_config_returns_empty(self, tmp_db, sample_profile):
        """If broker has no scanner config, should return empty."""
        from src.removers.email_remover import EmailRemover
        from src.config import SmtpConfig

        smtp = SmtpConfig(host="localhost", port=587, username="x", password="x")
        remover = EmailRemover(smtp, tmp_db)
        urls = remover._discover_listing_url(sample_profile, "no-such-broker")
        assert urls == []

    @patch("src.scanners.people_search_scanner.scan_single")
    @patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True)
    def test_runs_scan_when_no_db_findings(self, mock_has, mock_scan, tmp_db, sample_profile):
        """If no DB findings, should call scan_single and persist results."""
        from src.removers.email_remover import EmailRemover
        from src.config import SmtpConfig

        fake_result = ScanResult(
            scanner="people_search",
            site_name="TestBroker",
            site_url="https://testbroker.com/~Jane-Doe/456",
            data_type="listing_name",
            details={"broker_slug": "testbroker"},
            confidence="high",
        )

        async def fake_scan(profile, slug):
            return [fake_result]

        mock_scan.side_effect = fake_scan

        smtp = SmtpConfig(host="localhost", port=587, username="x", password="x")
        remover = EmailRemover(smtp, tmp_db)
        urls = remover._discover_listing_url(sample_profile, "testbroker")

        assert len(urls) == 1
        assert "testbroker.com" in urls[0]

        # Verify finding was persisted to DB
        findings = tmp_db.get_findings(profile="testuser")
        assert len(findings) >= 1


# ---------------------------------------------------------------------------
# run_url_discovery() task
# ---------------------------------------------------------------------------


class TestRunUrlDiscovery:
    @patch("src.scanners.people_search_scanner.has_scanner_config", return_value=False)
    def test_no_scanner_config_returns_error(self, mock_has, tmp_db):
        from src.tasks import run_url_discovery
        result = run_url_discovery("testuser", "fake-broker", None, tmp_db)
        assert result["error"]
        assert result["found"] == 0

    @patch("src.config.load_profile")
    @patch("src.scanners.people_search_scanner.scan_single")
    @patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True)
    def test_discovery_saves_findings(self, mock_has, mock_scan, mock_load, tmp_db, sample_profile):
        from src.tasks import run_url_discovery

        mock_load.return_value = sample_profile
        fake_result = ScanResult(
            scanner="people_search", site_name="Radaris",
            site_url="https://radaris.com/~Jane-Doe/789",
            data_type="listing_name", details={"broker_slug": "radaris"},
        )

        async def fake(profile, slug):
            return [fake_result]

        mock_scan.side_effect = fake

        result = run_url_discovery("testuser", "radaris", None, tmp_db)
        assert result["found"] == 1
        assert "radaris.com" in result["urls"][0]

        # Verify persisted
        findings = tmp_db.get_findings(profile="testuser")
        assert len(findings) >= 1


# ---------------------------------------------------------------------------
# POST /brokers/{slug}/verify route
# ---------------------------------------------------------------------------


class TestVerifyBrokerRoute:
    @pytest.fixture
    def app_client(self):
        import os
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

        profile_mock = MagicMock()
        profile_mock.name = "alice"
        profile_mock.full_name = "Alice Smith"
        profile_mock.first_name = "Alice"
        profile_mock.last_name = "Smith"
        profile_mock.email_addresses = ["alice@example.com"]
        profile_mock.phone_numbers = ["+15551234567"]
        profile_mock.usernames = []
        profile_mock.addresses = [MagicMock(state_abbr="IL", state="Illinois")]

        from fastapi.testclient import TestClient

        with patch.object(app_module, "list_profiles", return_value=["alice"]), \
             patch.object(app_module, "load_profile", return_value=profile_mock), \
             patch.object(app_module, "load_all_brokers", return_value=[]), \
             patch.object(app_module, "calculate_score", return_value=mock_score), \
             patch.object(app_module, "is_setup_complete", return_value={
                 "config_exists": True, "has_profiles": True,
                 "smtp_configured": True, "all_complete": True,
             }):
            client = TestClient(app_module.app, raise_server_exceptions=False)
            client._mock_db = mock_db
            client._app_module = app_module
            yield client

    def _csrf_post(self, client, url, data=None, **kwargs):
        get_resp = client.get("/")
        token = get_resp.cookies.get("_csrf_token", "")
        if data is None:
            data = {}
        data["_csrf_token"] = token
        cookies = kwargs.pop("cookies", {})
        cookies["_csrf_token"] = token
        return client.post(url, data=data, cookies=cookies, **kwargs)

    @patch("src.scanners.people_search_scanner.has_scanner_config", return_value=False)
    def test_verify_no_scanner_config(self, mock_has, app_client):
        resp = self._csrf_post(app_client, "/brokers/fake-broker/verify", data={"profile": "alice"})
        assert resp.status_code == 200
        assert "No scanner config" in resp.text

    @patch("src.scanners.people_search_scanner.scan_single")
    @patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True)
    def test_verify_no_listing_found(self, mock_has, mock_scan, app_client):
        async def fake_scan(profile, slug):
            return []

        mock_scan.side_effect = fake_scan
        resp = self._csrf_post(app_client, "/brokers/radaris/verify", data={"profile": "alice"})
        assert resp.status_code == 200
        assert "No listing found" in resp.text

    @patch("src.scanners.people_search_scanner.scan_single")
    @patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True)
    def test_verify_listing_found(self, mock_has, mock_scan, app_client):
        fake = ScanResult(
            scanner="people_search", site_name="Radaris",
            site_url="https://radaris.com/~Alice-Smith/999",
            data_type="listing_name", details={},
        )

        async def fake_scan(profile, slug):
            return [fake]

        mock_scan.side_effect = fake_scan
        resp = self._csrf_post(app_client, "/brokers/radaris/verify", data={"profile": "alice"})
        assert resp.status_code == 200
        assert "Found 1 listing" in resp.text
        assert "radaris.com" in resp.text


# ---------------------------------------------------------------------------
# CLI scan verify-listing
# ---------------------------------------------------------------------------


class TestCLIVerifyListing:
    @patch("src.scanners.people_search_scanner.scan_single")
    @patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True)
    @patch("src.cli.load_profile")
    def test_verify_listing_found(self, mock_load, mock_has, mock_scan, tmp_db, sample_profile):
        from click.testing import CliRunner
        from src.cli import cli

        mock_load.return_value = sample_profile
        fake = ScanResult(
            scanner="people_search", site_name="Radaris",
            site_url="https://radaris.com/~Jane-Doe/123",
            data_type="listing_name", details={"broker_slug": "radaris"},
        )

        async def fake_scan(profile, slug):
            return [fake]

        mock_scan.side_effect = fake_scan

        runner = CliRunner()
        with patch("src.cli.Config.load") as mock_cfg, \
             patch("src.cli.get_db", return_value=tmp_db):
            mock_cfg.return_value = MagicMock()
            result = runner.invoke(cli, ["-p", "testuser", "scan", "verify-listing", "--broker", "radaris"])

        assert result.exit_code == 0
        assert "Radaris" in result.output

    def test_verify_listing_no_profile(self, tmp_db):
        from click.testing import CliRunner
        from src.cli import cli

        runner = CliRunner()
        with patch("src.cli.Config.load") as mock_cfg, \
             patch("src.cli.get_db", return_value=tmp_db):
            mock_cfg.return_value = MagicMock()
            result = runner.invoke(cli, ["scan", "verify-listing", "--broker", "radaris"])

        assert "Profile required" in result.output

    @patch("src.scanners.people_search_scanner.has_scanner_config", return_value=False)
    def test_verify_listing_no_scanner(self, mock_has, tmp_db):
        from click.testing import CliRunner
        from src.cli import cli

        runner = CliRunner()
        with patch("src.cli.Config.load") as mock_cfg, \
             patch("src.cli.get_db", return_value=tmp_db):
            mock_cfg.return_value = MagicMock()
            result = runner.invoke(cli, ["-p", "testuser", "scan", "verify-listing", "--broker", "fakebro"])

        assert "No scanner config" in result.output
