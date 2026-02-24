"""Tests for src.db — Database operations."""

from __future__ import annotations

import pytest


class TestCreateScan:
    """Test scan creation and retrieval."""

    def test_create_scan(self, tmp_db):
        """Insert a scan and verify it exists in the database."""
        scan_id = tmp_db.create_scan(
            profile="testuser",
            scanner="hibp",
            scan_type="email",
            query="test@example.com",
        )
        assert scan_id is not None
        assert isinstance(scan_id, int)
        assert scan_id > 0

        scans = tmp_db.get_scans(profile="testuser")
        assert len(scans) == 1
        assert scans[0]["profile"] == "testuser"
        assert scans[0]["scanner"] == "hibp"
        assert scans[0]["scan_type"] == "email"
        assert scans[0]["query"] == "test@example.com"
        assert scans[0]["status"] == "running"

    def test_complete_scan(self, tmp_db):
        """Complete a scan and verify status transitions."""
        scan_id = tmp_db.create_scan("user1", "sherlock", "username", "jdoe")
        tmp_db.complete_scan(scan_id, result_count=5, output_path="/tmp/out.json")

        scans = tmp_db.get_scans(profile="user1")
        assert scans[0]["status"] == "completed"
        assert scans[0]["result_count"] == 5
        assert scans[0]["completed_at"] is not None

    def test_fail_scan(self, tmp_db):
        """Fail a scan and verify error is stored."""
        scan_id = tmp_db.create_scan("user1", "maigret", "username", "jdoe")
        tmp_db.fail_scan(scan_id, "Connection timeout")

        scans = tmp_db.get_scans(profile="user1")
        assert scans[0]["status"] == "failed"
        assert scans[0]["error_message"] == "Connection timeout"

    def test_get_scans_all(self, tmp_db):
        """Get all scans without profile filter."""
        tmp_db.create_scan("user1", "hibp", "email", "a@b.com")
        tmp_db.create_scan("user2", "hibp", "email", "c@d.com")

        scans = tmp_db.get_scans()
        assert len(scans) == 2

    def test_get_scans_limit(self, tmp_db):
        """Verify the limit parameter works."""
        for i in range(5):
            tmp_db.create_scan("user1", "hibp", "email", f"u{i}@b.com")

        scans = tmp_db.get_scans(profile="user1", limit=3)
        assert len(scans) == 3


class TestCreateFinding:
    """Test finding creation and retrieval."""

    def test_create_finding(self, tmp_db):
        """Insert a finding linked to a scan and verify it exists."""
        scan_id = tmp_db.create_scan("testuser", "hibp", "email", "test@example.com")
        finding_id = tmp_db.add_finding(
            scan_id=scan_id,
            profile="testuser",
            source="hibp",
            site_name="Adobe",
            site_url="https://adobe.com",
            data_type="breach",
            details={"breach_date": "2013-10-04", "pwn_count": 152445165},
            confidence="high",
        )
        assert finding_id is not None
        assert isinstance(finding_id, int)
        assert finding_id > 0

    def test_finding_details_json(self, tmp_db):
        """Verify that details dict is stored as JSON and parsed back."""
        scan_id = tmp_db.create_scan("testuser", "hibp", "email", "test@example.com")
        details = {"breach_date": "2020-01-01", "data_classes": ["email", "password"]}
        tmp_db.add_finding(
            scan_id=scan_id,
            profile="testuser",
            source="hibp",
            site_name="TestBreach",
            details=details,
        )
        findings = tmp_db.get_findings(profile="testuser")
        assert len(findings) == 1
        assert findings[0]["details"] == details
        assert isinstance(findings[0]["details"], dict)

    def test_finding_defaults(self, tmp_db):
        """Verify default values for optional fields."""
        scan_id = tmp_db.create_scan("testuser", "hibp", "email", "a@b.com")
        tmp_db.add_finding(
            scan_id=scan_id,
            profile="testuser",
            source="hibp",
            site_name="SomeBreak",
        )
        findings = tmp_db.get_findings(profile="testuser")
        assert findings[0]["confidence"] == "medium"
        assert findings[0]["site_url"] == ""


class TestCreateRemovalRequest:
    """Test removal request CRUD."""

    def test_create_removal_request(self, tmp_db):
        """Insert a removal request and verify defaults."""
        removal_id = tmp_db.create_removal(
            profile="testuser",
            broker_slug="whitepages",
            broker_name="Whitepages",
            method="email",
        )
        assert removal_id is not None
        assert isinstance(removal_id, int)
        assert removal_id > 0

        removals = tmp_db.get_removals(profile="testuser")
        assert len(removals) == 1
        assert removals[0]["status"] == "pending"
        assert removals[0]["broker_slug"] == "whitepages"
        assert removals[0]["method"] == "email"
        assert removals[0]["recheck_at"] is not None
        assert removals[0]["next_rescan_at"] is not None


class TestGetFindingsByProfile:
    """Test querying findings by profile and source."""

    def test_get_findings_by_profile(self, tmp_db):
        """Query findings filtered by profile name."""
        scan1 = tmp_db.create_scan("alice", "hibp", "email", "alice@test.com")
        scan2 = tmp_db.create_scan("bob", "hibp", "email", "bob@test.com")

        tmp_db.add_finding(scan1, "alice", "hibp", "Breach1")
        tmp_db.add_finding(scan1, "alice", "hibp", "Breach2")
        tmp_db.add_finding(scan2, "bob", "hibp", "Breach3")

        alice_findings = tmp_db.get_findings(profile="alice")
        assert len(alice_findings) == 2
        assert all(f["profile"] == "alice" for f in alice_findings)

        bob_findings = tmp_db.get_findings(profile="bob")
        assert len(bob_findings) == 1

    def test_get_findings_by_source(self, tmp_db):
        """Query findings filtered by source scanner."""
        scan_id = tmp_db.create_scan("user1", "multi", "full", "user1")
        tmp_db.add_finding(scan_id, "user1", "hibp", "Site1")
        tmp_db.add_finding(scan_id, "user1", "sherlock", "Site2")
        tmp_db.add_finding(scan_id, "user1", "hibp", "Site3")

        hibp_only = tmp_db.get_findings(source="hibp")
        assert len(hibp_only) == 2

    def test_get_findings_count(self, tmp_db):
        """Verify the count method returns correct totals."""
        scan_id = tmp_db.create_scan("user1", "hibp", "email", "a@b.com")
        tmp_db.add_finding(scan_id, "user1", "hibp", "Breach1")
        tmp_db.add_finding(scan_id, "user1", "hibp", "Breach2")

        assert tmp_db.get_findings_count(profile="user1") == 2
        assert tmp_db.get_findings_count() == 2


class TestGetRemovalRequests:
    """Test querying removal requests."""

    def test_get_removal_requests(self, tmp_db):
        """Query removal requests with filters."""
        tmp_db.create_removal("alice", "whitepages", "Whitepages", "email")
        tmp_db.create_removal("alice", "spokeo", "Spokeo", "form")
        tmp_db.create_removal("bob", "radaris", "Radaris", "email")

        alice_removals = tmp_db.get_removals(profile="alice")
        assert len(alice_removals) == 2

        all_removals = tmp_db.get_removals()
        assert len(all_removals) == 3

    def test_get_removal_requests_by_status(self, tmp_db):
        """Filter removal requests by status."""
        rid1 = tmp_db.create_removal("user1", "broker1", "Broker 1", "email")
        tmp_db.create_removal("user1", "broker2", "Broker 2", "email")
        tmp_db.update_removal_status(rid1, "submitted")

        pending = tmp_db.get_removals(status="pending")
        assert len(pending) == 1
        assert pending[0]["broker_slug"] == "broker2"

        submitted = tmp_db.get_removals(status="submitted")
        assert len(submitted) == 1
        assert submitted[0]["broker_slug"] == "broker1"


class TestUpdateRemovalStatus:
    """Test updating removal request status."""

    def test_update_removal_status(self, tmp_db):
        """Update status and verify the change persists."""
        rid = tmp_db.create_removal("user1", "whitepages", "Whitepages", "email")

        tmp_db.update_removal_status(rid, "submitted")
        removals = tmp_db.get_removals(profile="user1")
        assert removals[0]["status"] == "submitted"
        assert removals[0]["submitted_at"] is not None

    def test_update_to_confirmed(self, tmp_db):
        """Confirm a removal and verify confirmed_at is set."""
        rid = tmp_db.create_removal("user1", "spokeo", "Spokeo", "email")
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")

        removals = tmp_db.get_removals(profile="user1")
        assert removals[0]["status"] == "confirmed"
        assert removals[0]["confirmed_at"] is not None

    def test_update_with_kwargs(self, tmp_db):
        """Update status with extra keyword arguments (notes, message_id)."""
        rid = tmp_db.create_removal("user1", "radaris", "Radaris", "email")
        tmp_db.update_removal_status(
            rid,
            "submitted",
            email_message_id="<abc123@privacy-toolkit>",
            notes="Sent via test",
        )
        removals = tmp_db.get_removals(profile="user1")
        assert removals[0]["email_message_id"] == "<abc123@privacy-toolkit>"
        assert removals[0]["notes"] == "Sent via test"


class TestStateTransitionValidation:
    """Test that invalid status transitions are rejected."""

    def test_pending_to_confirmed_rejected(self, tmp_db):
        """Cannot go directly from pending to confirmed."""
        rid = tmp_db.create_removal("user1", "broker1", "Broker", "email")
        with pytest.raises(ValueError, match="Invalid status transition"):
            tmp_db.update_removal_status(rid, "confirmed")

    def test_pending_to_reappeared_rejected(self, tmp_db):
        """Cannot go directly from pending to reappeared."""
        rid = tmp_db.create_removal("user1", "broker1", "Broker", "email")
        with pytest.raises(ValueError, match="Invalid status transition"):
            tmp_db.update_removal_status(rid, "reappeared")

    def test_submitted_to_reappeared_rejected(self, tmp_db):
        """Cannot go directly from submitted to reappeared."""
        rid = tmp_db.create_removal("user1", "broker1", "Broker", "email")
        tmp_db.update_removal_status(rid, "submitted")
        with pytest.raises(ValueError, match="Invalid status transition"):
            tmp_db.update_removal_status(rid, "reappeared")

    def test_valid_full_lifecycle(self, tmp_db):
        """Full valid lifecycle: pending -> submitted -> confirmed -> reappeared."""
        rid = tmp_db.create_removal("user1", "broker1", "Broker", "email")
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "confirmed")
        tmp_db.update_removal_status(rid, "reappeared")
        removals = tmp_db.get_removals(profile="user1")
        assert removals[0]["status"] == "reappeared"

    def test_nonexistent_removal_raises(self, tmp_db):
        """Updating a non-existent removal should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            tmp_db.update_removal_status(99999, "submitted")

    def test_pending_captcha_to_pending_valid(self, tmp_db):
        """pending_captcha -> pending is a valid transition."""
        rid = tmp_db.create_removal("user1", "broker1", "Broker", "email")
        # Manually set to pending_captcha
        conn = tmp_db._connect()
        conn.execute("UPDATE removal_requests SET status='pending_captcha' WHERE id=?", (rid,))
        conn.commit()
        conn.close()
        tmp_db.update_removal_status(rid, "pending")
        removals = tmp_db.get_removals(profile="user1")
        assert removals[0]["status"] == "pending"

    def test_rejected_to_submitted_valid(self, tmp_db):
        """rejected -> submitted is a valid transition."""
        rid = tmp_db.create_removal("user1", "broker1", "Broker", "email")
        tmp_db.update_removal_status(rid, "submitted")
        tmp_db.update_removal_status(rid, "rejected")
        tmp_db.update_removal_status(rid, "submitted")
        removals = tmp_db.get_removals(profile="user1")
        assert removals[0]["status"] == "submitted"


class TestAuditLog:
    """Test audit log insertion and querying."""

    def test_audit_log(self, tmp_db):
        """Insert and query audit log entries."""
        tmp_db.log("test_action", profile="testuser", details={"key": "value"})
        tmp_db.log("another_action", profile="testuser", success=False)

        entries = tmp_db.get_audit_log()
        assert len(entries) >= 2

        # Most recent first (ORDER BY id DESC)
        latest = entries[0]
        assert latest["action"] == "another_action"
        assert latest["success"] == 0  # stored as integer

        previous = entries[1]
        assert previous["action"] == "test_action"
        assert previous["success"] == 1

    def test_audit_log_auto_created_on_scan(self, tmp_db):
        """Verify that creating a scan automatically writes an audit entry."""
        tmp_db.create_scan("user1", "hibp", "email", "a@b.com")

        entries = tmp_db.get_audit_log()
        scan_entries = [e for e in entries if e["action"] == "scan_started"]
        assert len(scan_entries) == 1
        assert scan_entries[0]["profile"] == "user1"

    def test_audit_log_limit(self, tmp_db):
        """Verify the limit parameter on audit log queries."""
        for i in range(10):
            tmp_db.log(f"action_{i}")

        entries = tmp_db.get_audit_log(limit=5)
        assert len(entries) == 5
