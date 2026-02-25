"""Tests for Phase 1 features: compliance scoring, digest, auto-resubmission, REST API."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi.testclient import TestClient


# ============================================================================
# 1. BROKER COMPLIANCE SCORING
# ============================================================================

class TestBrokerCompliance:
    """Test get_broker_compliance() in db.py."""

    def test_empty_db_returns_empty(self, tmp_db):
        result = tmp_db.get_broker_compliance()
        assert result == []

    def test_single_broker_pending(self, tmp_db):
        tmp_db.create_removal("user1", "acme", "Acme Inc", "email")
        result = tmp_db.get_broker_compliance()
        assert len(result) == 1
        assert result[0]["broker_slug"] == "acme"
        assert result[0]["total_requests"] == 1
        assert result[0]["confirmed_count"] == 0
        assert result[0]["compliance_label"] == "undetermined"

    def test_compliant_broker(self, tmp_db):
        """Broker with >80% confirmed is labeled compliant."""
        for i in range(5):
            rid = tmp_db.create_removal("user1", "good-broker", "Good Broker", "email")
            tmp_db.update_removal_status(rid, "submitted")
            tmp_db.update_removal_status(rid, "confirmed")
        result = tmp_db.get_broker_compliance(broker_slug="good-broker")
        assert len(result) == 1
        assert result[0]["compliance_label"] == "compliant"
        assert result[0]["compliance_rate"] == 100.0
        assert result[0]["confirmed_count"] == 5

    def test_resistant_broker(self, tmp_db):
        """Broker with <50% confirmed is labeled resistant."""
        for i in range(4):
            rid = tmp_db.create_removal("user1", "bad-broker", "Bad Broker", "email")
            tmp_db.update_removal_status(rid, "submitted")
            if i == 0:
                tmp_db.update_removal_status(rid, "confirmed")
            else:
                tmp_db.update_removal_status(rid, "rejected")
        result = tmp_db.get_broker_compliance(broker_slug="bad-broker")
        assert len(result) == 1
        assert result[0]["compliance_label"] == "resistant"
        assert result[0]["rejected_count"] == 3

    def test_inconsistent_broker(self, tmp_db):
        """Broker with 50-80% confirmed is labeled inconsistent."""
        for i in range(4):
            rid = tmp_db.create_removal("user1", "mid-broker", "Mid Broker", "email")
            tmp_db.update_removal_status(rid, "submitted")
            if i < 3:
                tmp_db.update_removal_status(rid, "confirmed")
            else:
                tmp_db.update_removal_status(rid, "rejected")
        result = tmp_db.get_broker_compliance(broker_slug="mid-broker")
        assert len(result) == 1
        assert result[0]["compliance_label"] == "inconsistent"

    def test_undetermined_with_few_samples(self, tmp_db):
        """Less than 3 samples → undetermined."""
        rid = tmp_db.create_removal("user1", "new-broker", "New Broker", "email")
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")
        result = tmp_db.get_broker_compliance(broker_slug="new-broker")
        assert result[0]["compliance_label"] == "undetermined"

    def test_avg_days_to_confirm(self, tmp_db):
        rid = tmp_db.create_removal("user1", "fast-broker", "Fast Broker", "email")
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")
        result = tmp_db.get_broker_compliance(broker_slug="fast-broker")
        # avg_days should be a number (could be 0.0 since submitted/confirmed same moment)
        assert result[0]["avg_days_to_confirm"] is not None

    def test_filter_by_slug(self, tmp_db):
        tmp_db.create_removal("user1", "broker-a", "Broker A", "email")
        tmp_db.create_removal("user1", "broker-b", "Broker B", "email")
        result = tmp_db.get_broker_compliance(broker_slug="broker-a")
        assert len(result) == 1
        assert result[0]["broker_slug"] == "broker-a"

    def test_bounce_count(self, tmp_db):
        rid = tmp_db.create_removal("user1", "bounce-broker", "Bounce Broker", "email")
        tmp_db.update_removal_status(rid, "submitted", notes="email bounce detected")
        result = tmp_db.get_broker_compliance(broker_slug="bounce-broker")
        assert result[0]["bounce_count"] == 1

    def test_reappearance_rate(self, tmp_db):
        rid = tmp_db.create_removal("user1", "relapse-broker", "Relapse Broker", "email")
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")
        tmp_db.update_removal_status(rid, "reappeared")
        result = tmp_db.get_broker_compliance(broker_slug="relapse-broker")
        assert result[0]["reappeared_count"] == 1
        assert result[0]["reappearance_rate"] == 100.0


class TestDataSensitivity:
    def test_constant_exists(self):
        from src.models import DATA_SENSITIVITY
        assert DATA_SENSITIVITY["financial"] == 5
        assert DATA_SENSITIVITY["ssn"] == 5
        assert DATA_SENSITIVITY["name"] == 2
        assert DATA_SENSITIVITY["demographic"] == 1


class TestComplianceWeightedScoring:
    def test_resistant_broker_costs_more(self, tmp_db):
        """A resistant broker listing should deduct 5 points instead of 3."""
        # Create resistant broker compliance data
        for i in range(4):
            rid = tmp_db.create_removal("testuser", "resistant-site", "Resistant Site", "email")
            tmp_db.update_removal_status(rid, "submitted")
            tmp_db.update_removal_status(rid, "rejected")

        # Add a listing finding for that broker
        scan_id = tmp_db.create_scan("testuser", "test", "people", "test")
        tmp_db.add_finding(scan_id, "testuser", "people_search", "resistant-site",
                           "http://example.com", "listing_phone")

        from src.scoring import calculate_score
        ps = calculate_score(tmp_db, "testuser")
        # 100 - 5 (resistant penalty) = 95
        assert ps.score == 95

    def test_default_penalty_without_compliance(self, tmp_db):
        """Without compliance data, default -3 penalty applies."""
        scan_id = tmp_db.create_scan("testuser", "test", "people", "test")
        tmp_db.add_finding(scan_id, "testuser", "people_search", "Unknown Broker",
                           "http://example.com", "listing_phone")

        from src.scoring import calculate_score
        ps = calculate_score(tmp_db, "testuser")
        assert ps.score == 97  # 100 - 3


# ============================================================================
# 2. NOTIFICATION DIGEST
# ============================================================================

class TestDigest:
    def test_generate_empty_digest(self, tmp_db, sample_config):
        from src.digest import generate_digest
        with patch("src.config.list_profiles", return_value=[]):
            result = generate_digest(tmp_db, sample_config, "weekly")
        assert result["has_activity"] is False
        assert result["new_findings_count"] == 0
        assert "No activity" in result["text_message"]

    def test_generate_digest_with_findings(self, tmp_db, sample_config):
        from src.digest import generate_digest
        # Add a recent finding
        scan_id = tmp_db.create_scan("testuser", "test", "email", "test@example.com")
        tmp_db.add_finding(scan_id, "testuser", "holehe", "twitter.com",
                           "https://twitter.com", "email_registered")

        with patch("src.config.list_profiles", return_value=["testuser"]):
            result = generate_digest(tmp_db, sample_config, "weekly")
        assert result["has_activity"] is True
        assert result["new_findings_count"] >= 1

    def test_send_digest_skips_no_activity(self, tmp_db, sample_config):
        from src.digest import send_digest
        with patch("src.config.list_profiles", return_value=[]), \
             patch("src.notifications.notify") as mock_notify:
            sent = send_digest(tmp_db, sample_config, "weekly")
        assert sent is False
        mock_notify.assert_not_called()

    def test_send_digest_sends_on_activity(self, tmp_db, sample_config):
        from src.digest import send_digest
        scan_id = tmp_db.create_scan("testuser", "test", "email", "test@example.com")
        tmp_db.add_finding(scan_id, "testuser", "holehe", "twitter.com",
                           "https://twitter.com", "email_registered")

        with patch("src.config.list_profiles", return_value=["testuser"]), \
             patch("src.notifications.notify") as mock_notify:
            sent = send_digest(tmp_db, sample_config, "weekly")
        assert sent is True
        mock_notify.assert_called_once()

    def test_monthly_period(self, tmp_db, sample_config):
        from src.digest import generate_digest
        with patch("src.config.list_profiles", return_value=[]):
            result = generate_digest(tmp_db, sample_config, "monthly")
        assert result["period"] == "monthly"
        assert result["days"] == 30


# ============================================================================
# 3. RE-LISTING AUTO-RESUBMISSION
# ============================================================================

class TestRescanMethods:
    def test_rescan_count_column_exists(self, tmp_db):
        """The migration should add rescan_count column."""
        rid = tmp_db.create_removal("user1", "broker1", "Broker 1", "email")
        removals = tmp_db.get_removals()
        assert removals[0].get("rescan_count") is not None

    def test_increment_rescan_count(self, tmp_db):
        rid = tmp_db.create_removal("user1", "broker1", "Broker 1", "email")
        tmp_db.increment_rescan_count(rid)
        tmp_db.increment_rescan_count(rid)
        removals = tmp_db.get_removals()
        assert removals[0]["rescan_count"] == 2

    def test_get_confirmed_for_rescan_empty(self, tmp_db):
        result = tmp_db.get_confirmed_for_rescan()
        assert result == []

    def test_get_confirmed_for_rescan_returns_due(self, tmp_db):
        rid = tmp_db.create_removal("user1", "broker1", "Broker 1", "email",
                                    rescan_days=0)  # Immediately due
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")
        result = tmp_db.get_confirmed_for_rescan()
        assert len(result) == 1

    def test_get_confirmed_for_rescan_skips_future(self, tmp_db):
        rid = tmp_db.create_removal("user1", "broker1", "Broker 1", "email",
                                    rescan_days=365)  # Far in the future
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")
        result = tmp_db.get_confirmed_for_rescan()
        assert len(result) == 0

    def test_reset_for_resubmission(self, tmp_db):
        rid = tmp_db.create_removal("user1", "broker1", "Broker 1", "email")
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")
        tmp_db.update_removal_status(rid, "reappeared")
        tmp_db.reset_for_resubmission(rid)
        removals = tmp_db.get_removals()
        assert removals[0]["status"] == "pending"
        assert removals[0]["submitted_at"] is None
        assert removals[0]["confirmed_at"] is None

    def test_reset_for_resubmission_rejects_non_reappeared(self, tmp_db):
        rid = tmp_db.create_removal("user1", "broker1", "Broker 1", "email")
        with pytest.raises(ValueError, match="Can only reset reappeared"):
            tmp_db.reset_for_resubmission(rid)

    def test_push_next_rescan(self, tmp_db):
        rid = tmp_db.create_removal("user1", "broker1", "Broker 1", "email",
                                    rescan_days=0)
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")
        tmp_db.push_next_rescan(rid, days=90)
        removals = tmp_db.get_removals()
        rescan_at = removals[0]["next_rescan_at"]
        assert rescan_at is not None
        # Should be ~90 days from now
        rescan_date = datetime.fromisoformat(rescan_at)
        assert rescan_date > datetime.now() + timedelta(days=80)

    def test_auto_resubmission_in_verification(self, tmp_db, sample_config):
        """When verification finds reappeared listing, it should auto-reset to pending."""
        from src.tasks import run_verification_scans

        rid = tmp_db.create_removal("testuser", "testbroker", "Test Broker", "email",
                                    recheck_days=0)
        tmp_db.update_removal_status(rid, "submitted")

        mock_findings = [MagicMock(scanner="test", site_name="Test", site_url="http://example.com",
                                   data_type="listing_phone", details={}, confidence="high")]

        with patch("src.config.load_profile") as mock_lp, \
             patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True), \
             patch("src.scanners.people_search_scanner.scan_single", return_value=mock_findings), \
             patch("src.notifications.notify"):
            mock_lp.return_value = MagicMock()
            result = run_verification_scans("testuser", sample_config, tmp_db)

        assert result["reappeared"] == 1
        # The removal should now be pending (auto-resubmitted)
        removals = tmp_db.get_removals()
        assert removals[0]["status"] == "pending"
        assert removals[0]["rescan_count"] == 1


class TestConfirmedRescan:
    def test_no_due_rescans(self, tmp_db, sample_config):
        from src.tasks import run_confirmed_rescan
        with patch("src.config.load_profile"):
            result = run_confirmed_rescan("testuser", sample_config, tmp_db)
        assert result == {"checked": 0, "still_clear": 0, "relisted": 0}

    def test_still_clear_pushes_rescan(self, tmp_db, sample_config):
        from src.tasks import run_confirmed_rescan

        rid = tmp_db.create_removal("testuser", "testbroker", "Test Broker", "email",
                                    rescan_days=0)
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")

        with patch("src.config.load_profile") as mock_lp, \
             patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True), \
             patch("src.scanners.people_search_scanner.scan_single", return_value=[]):
            mock_lp.return_value = MagicMock()
            result = run_confirmed_rescan("testuser", sample_config, tmp_db)

        assert result["still_clear"] == 1
        # Rescan date should be pushed forward
        removals = tmp_db.get_removals()
        assert removals[0]["status"] == "confirmed"

    def test_relisted_resets_to_pending(self, tmp_db, sample_config):
        from src.tasks import run_confirmed_rescan

        rid = tmp_db.create_removal("testuser", "testbroker", "Test Broker", "email",
                                    rescan_days=0)
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")

        mock_findings = [MagicMock(scanner="test", site_name="Test", site_url="http://example.com",
                                   data_type="listing_phone", details={}, confidence="high")]

        with patch("src.config.load_profile") as mock_lp, \
             patch("src.scanners.people_search_scanner.has_scanner_config", return_value=True), \
             patch("src.scanners.people_search_scanner.scan_single", return_value=mock_findings), \
             patch("src.notifications.notify"):
            mock_lp.return_value = MagicMock()
            result = run_confirmed_rescan("testuser", sample_config, tmp_db)

        assert result["relisted"] == 1
        removals = tmp_db.get_removals()
        assert removals[0]["status"] == "pending"


# ============================================================================
# 4. REST API
# ============================================================================

@pytest.fixture
def api_client():
    """Create a TestClient with mocked module-level globals for API testing."""
    import src.app as app_module

    mock_db = MagicMock()
    mock_db.get_findings_count.return_value = 5
    mock_db.get_findings.return_value = [{"id": 1, "profile": "alice", "source": "test"}]
    mock_db.get_removals.return_value = [
        {"id": 1, "profile": "alice", "broker_slug": "broker1", "status": "pending"},
    ]
    mock_db.get_scans.return_value = [{"id": 1, "profile": "alice", "scanner": "test"}]
    mock_db.get_audit_log.return_value = []
    mock_db.get_broker_compliance.return_value = [
        {"broker_slug": "broker1", "broker_name": "Broker 1",
         "total_requests": 5, "confirmed_count": 4, "rejected_count": 0,
         "reappeared_count": 0, "bounce_count": 0, "avg_days_to_confirm": 7.0,
         "compliance_rate": 80.0, "reappearance_rate": 0.0, "compliance_label": "compliant"},
    ]
    mock_db.get_score_history.return_value = [
        {"id": 1, "profile": "alice", "score": 85, "grade": "B", "calculated_at": datetime.now().isoformat()},
    ]

    mock_tm = MagicMock()
    mock_tm.list_tasks.return_value = []
    type(mock_tm).active_count = PropertyMock(return_value=0)
    mock_tm.submit.return_value = "test-task-123"
    mock_tm.get.return_value = None

    mock_config = MagicMock()
    mock_config.db_path = ":memory:"

    app_module.config = mock_config
    app_module.db = mock_db
    app_module.task_manager = mock_tm

    os.environ.pop("PRIVACY_TOOLKIT_API_KEY", None)
    os.environ.pop("PRIVACY_TOOLKIT_PASSWORD", None)

    mock_profile = MagicMock()
    mock_profile.name = "alice"
    mock_profile.first_name = "Alice"
    mock_profile.last_name = "Smith"
    mock_profile.full_name = "Alice Smith"
    mock_profile.email_addresses = ["alice@example.com"]
    mock_profile.phone_numbers = []
    mock_profile.usernames = []

    mock_score = MagicMock()
    mock_score.score = 85
    mock_score.grade = "B"
    mock_score.findings_count = 5
    mock_score.breaches_count = 1
    mock_score.broker_listings = 2
    mock_score.accounts_found = 3
    mock_score.removals_confirmed = 1
    mock_score.removals_pending = 1
    mock_score.risk_factors = ["Test risk"]
    mock_score.recommendations = ["Test rec"]

    with patch("src.config.list_profiles", return_value=["alice"]), \
         patch("src.config.load_profile", return_value=mock_profile), \
         patch("src.config.load_all_brokers", return_value=[]), \
         patch("src.app.list_profiles", return_value=["alice"]), \
         patch("src.app.load_profile", return_value=mock_profile), \
         patch("src.app.load_all_brokers", return_value=[]), \
         patch("src.app.is_setup_complete", return_value={
             "config_exists": True, "has_profiles": True,
             "smtp_configured": True, "all_complete": True,
         }), \
         patch("src.app.calculate_score", return_value=mock_score), \
         patch("src.scoring.calculate_score", return_value=mock_score), \
         patch("src.scoring.get_trend", return_value={"7d_change": 2, "30d_change": 5, "direction": "up"}):
        client = TestClient(app_module.app, raise_server_exceptions=False)
        client._mock_db = mock_db
        client._mock_tm = mock_tm
        yield client


class TestAPIHealth:
    def test_health_endpoint(self, api_client):
        resp = api_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "tasks_active" in data


class TestAPIStats:
    def test_stats_endpoint(self, api_client):
        resp = api_client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data
        assert "findings" in data


class TestAPIProfiles:
    def test_list_profiles(self, api_client):
        resp = api_client.get("/api/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_profile_detail(self, api_client):
        resp = api_client.get("/api/profiles/alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "alice"


class TestAPIScans:
    def test_list_scans(self, api_client):
        resp = api_client.get("/api/scans")
        assert resp.status_code == 200

    def test_trigger_scan(self, api_client):
        resp = api_client.post("/api/scans", json={"profile": "alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data

    def test_trigger_scan_missing_profile(self, api_client):
        resp = api_client.post("/api/scans", json={})
        assert resp.status_code == 400


class TestAPIFindings:
    def test_list_findings(self, api_client):
        resp = api_client.get("/api/findings")
        assert resp.status_code == 200


class TestAPIRemovals:
    def test_list_removals(self, api_client):
        resp = api_client.get("/api/removals")
        assert resp.status_code == 200

    def test_trigger_removals(self, api_client):
        resp = api_client.post("/api/removals",
                               json={"profile": "alice", "broker_slugs": ["broker1"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data


class TestAPIBrokers:
    def test_list_brokers(self, api_client):
        resp = api_client.get("/api/brokers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_broker_compliance(self, api_client):
        resp = api_client.get("/api/brokers/broker1/compliance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["broker_slug"] == "broker1"


class TestAPITasks:
    def test_list_tasks(self, api_client):
        resp = api_client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestAPIPasswordExempt:
    def test_api_routes_exempt_from_password(self):
        """API routes should bypass password auth (they use API key auth)."""
        from src.auth import PASSWORD_EXEMPT
        assert "/api/" in PASSWORD_EXEMPT
