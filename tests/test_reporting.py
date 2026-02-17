"""Tests for CSV and HTML report export modules."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.reporting.csv_export import export_findings_csv, export_removals_csv
from src.reporting.html_export import export_findings_html, export_removals_html


# ---------------------------------------------------------------------------
# Sample data factories
# ---------------------------------------------------------------------------

def _sample_findings() -> list[dict]:
    """Return a list of finding dicts matching Database.get_findings() output."""
    return [
        {
            "id": 1,
            "scan_id": 1,
            "profile": "testuser",
            "source": "sherlock",
            "site_name": "GitHub",
            "site_url": "https://github.com/janedoe",
            "data_type": "username",
            "details": {"response_code": 200},
            "confidence": "high",
            "found_at": "2026-02-10T12:00:00",
        },
        {
            "id": 2,
            "scan_id": 2,
            "profile": "testuser",
            "source": "hibp",
            "site_name": "Adobe",
            "site_url": "",
            "data_type": "breach",
            "details": {"breach_date": "2013-10-04", "data_classes": ["Emails", "Passwords"]},
            "confidence": "medium",
            "found_at": "2026-02-10T12:05:00",
        },
        {
            "id": 3,
            "scan_id": 3,
            "profile": "testuser",
            "source": "holehe",
            "site_name": "Twitter",
            "site_url": "https://twitter.com",
            "data_type": "email_registered",
            "details": {},
            "confidence": "low",
            "found_at": "2026-02-10T12:10:00",
        },
    ]


def _sample_removals() -> list[dict]:
    """Return a list of removal dicts matching Database.get_removals() output."""
    return [
        {
            "id": 1,
            "profile": "testuser",
            "broker_slug": "spokeo",
            "broker_name": "Spokeo",
            "method": "email",
            "status": "submitted",
            "submitted_at": "2026-02-01T09:00:00",
            "confirmed_at": None,
            "recheck_at": "2026-03-01T09:00:00",
            "notes": "Sent CCPA request",
        },
        {
            "id": 2,
            "profile": "testuser",
            "broker_slug": "whitepages",
            "broker_name": "WhitePages",
            "method": "form",
            "status": "confirmed",
            "submitted_at": "2026-01-15T10:00:00",
            "confirmed_at": "2026-02-05T14:00:00",
            "recheck_at": "2026-04-15T10:00:00",
            "notes": None,
        },
    ]


# ===========================================================================
# CSV Export Tests
# ===========================================================================

class TestCSVExportFindings:
    def test_csv_export_findings(self, tmp_path: Path):
        """Verify CSV export writes correct headers and row data."""
        findings = _sample_findings()
        out = tmp_path / "findings.csv"

        result = export_findings_csv(findings, str(out))

        assert result == str(out)
        assert out.exists()

        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Header row
        assert rows[0] == ["Date", "Scanner", "Site", "URL", "Data Type", "Confidence", "Details"]
        # Data rows
        assert len(rows) == 4  # header + 3 findings

        # Check first data row content
        assert rows[1][0] == "2026-02-10"  # Date truncated to date
        assert rows[1][1] == "sherlock"     # Scanner/Source
        assert rows[1][2] == "GitHub"       # Site
        assert rows[1][3] == "https://github.com/janedoe"  # URL
        assert rows[1][4] == "username"     # Data Type
        assert rows[1][5] == "high"         # Confidence

        # Check that details column contains parseable JSON
        details = json.loads(rows[1][6])
        assert details["response_code"] == 200

    def test_csv_empty_data(self, tmp_path: Path):
        """Empty findings list produces a CSV with only the header row."""
        out = tmp_path / "empty.csv"

        result = export_findings_csv([], str(out))

        assert result == str(out)
        assert out.exists()

        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0] == ["Date", "Scanner", "Site", "URL", "Data Type", "Confidence", "Details"]

    def test_csv_findings_string_details(self, tmp_path: Path):
        """Findings with string details (not dict) are handled gracefully."""
        findings = [{
            "id": 1, "scan_id": 1, "profile": "x",
            "source": "test", "site_name": "Test",
            "site_url": "", "data_type": "other",
            "details": "plain text details",
            "confidence": "low", "found_at": "2026-01-01T00:00:00",
        }]
        out = tmp_path / "string_details.csv"
        export_findings_csv(findings, str(out))

        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[1][6] == "plain text details"


class TestCSVExportRemovals:
    def test_csv_export_removals(self, tmp_path: Path):
        """Verify CSV export writes correct headers and row data for removals."""
        removals = _sample_removals()
        out = tmp_path / "removals.csv"

        result = export_removals_csv(removals, str(out))

        assert result == str(out)
        assert out.exists()

        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert rows[0] == ["Broker", "Method", "Status", "Submitted", "Confirmed", "Notes"]
        assert len(rows) == 3  # header + 2 removals

        # First removal row
        assert rows[1][0] == "Spokeo"
        assert rows[1][1] == "email"
        assert rows[1][2] == "submitted"
        assert rows[1][3] == "2026-02-01"
        assert rows[1][4] == ""  # confirmed_at is None
        assert rows[1][5] == "Sent CCPA request"

        # Second removal row
        assert rows[2][0] == "WhitePages"
        assert rows[2][2] == "confirmed"
        assert rows[2][4] == "2026-02-05"

    def test_csv_removals_empty(self, tmp_path: Path):
        """Empty removals list produces a CSV with only the header row."""
        out = tmp_path / "empty_removals.csv"
        export_removals_csv([], str(out))

        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0] == ["Broker", "Method", "Status", "Submitted", "Confirmed", "Notes"]


# ===========================================================================
# HTML Export Tests
# ===========================================================================

class TestHTMLExportFindings:
    def test_html_export_findings(self, tmp_path: Path):
        """Verify HTML export produces valid HTML with expected elements."""
        findings = _sample_findings()
        out = tmp_path / "report.html"

        result = export_findings_html(findings, str(out), profile_name="testuser")

        assert result == str(out)
        assert out.exists()

        content = out.read_text(encoding="utf-8")

        # Check HTML structure
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content

        # Check title and profile name
        assert "Privacy Toolkit" in content
        assert "Findings Report" in content
        assert "testuser" in content

        # Check summary stats are present
        assert "Total Findings" in content
        assert "Unique Sites" in content
        assert "Scanners Used" in content
        assert "High Confidence" in content

        # Check table headers
        assert "<th>Date</th>" in content
        assert "<th>Scanner</th>" in content
        assert "<th>Site</th>" in content
        assert "<th>URL</th>" in content
        assert "<th>Data Type</th>" in content
        assert "<th>Confidence</th>" in content
        assert "<th>Details</th>" in content

        # Check data rows are present
        assert "GitHub" in content
        assert "Adobe" in content
        assert "sherlock" in content
        assert "hibp" in content
        assert "holehe" in content
        assert "https://github.com/janedoe" in content

        # Check confidence styling classes
        assert "confidence-high" in content
        assert "confidence-medium" in content
        assert "confidence-low" in content

    def test_html_empty_data(self, tmp_path: Path):
        """Empty findings list produces valid HTML with a 'no data' message."""
        out = tmp_path / "empty_report.html"

        result = export_findings_html([], str(out), profile_name="empty")

        assert result == str(out)
        assert out.exists()

        content = out.read_text(encoding="utf-8")

        assert "<!DOCTYPE html>" in content
        assert "No findings to display" in content
        # Summary should show zero counts
        assert ">0<" in content

    def test_html_no_profile(self, tmp_path: Path):
        """HTML export without a profile name still generates valid output."""
        out = tmp_path / "no_profile.html"
        export_findings_html(_sample_findings(), str(out))

        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Findings Report" in content


class TestHTMLExportRemovals:
    def test_html_export_removals(self, tmp_path: Path):
        """Verify HTML export for removal requests contains expected elements."""
        removals = _sample_removals()
        out = tmp_path / "removals.html"

        result = export_removals_html(removals, str(out), profile_name="testuser")

        assert result == str(out)
        assert out.exists()

        content = out.read_text(encoding="utf-8")

        # Check structure
        assert "<!DOCTYPE html>" in content
        assert "Removal Status Report" in content
        assert "testuser" in content

        # Check table headers
        assert "<th>Broker</th>" in content
        assert "<th>Method</th>" in content
        assert "<th>Status</th>" in content

        # Check data
        assert "Spokeo" in content
        assert "WhitePages" in content

        # Check status styling
        assert "status-submitted" in content
        assert "status-confirmed" in content

    def test_html_removals_empty(self, tmp_path: Path):
        """Empty removals list produces valid HTML with a 'no data' message."""
        out = tmp_path / "empty_removals.html"
        export_removals_html([], str(out))

        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "No removal requests to display" in content
