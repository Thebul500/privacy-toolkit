"""Tests for src.scanners — Scanner classes with mocked HTTP calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from src.scanners.hibp_scanner import HIBPScanner


class TestHIBPScannerFound:
    """Test HIBP scanner when breaches are found."""

    @patch("src.scanners.hibp_scanner.time.sleep")
    def test_hibp_scanner_found(self, mock_sleep):
        """Mock a successful breach response and verify ScanResult objects."""
        breach_data = [
            {
                "Name": "Adobe",
                "Domain": "adobe.com",
                "BreachDate": "2013-10-04",
                "AddedDate": "2013-12-04T00:00:00Z",
                "PwnCount": 152445165,
                "DataClasses": ["Email addresses", "Password hints", "Passwords"],
                "IsVerified": True,
                "IsSensitive": False,
                "Description": "Adobe breach.",
            },
            {
                "Name": "LinkedIn",
                "Domain": "linkedin.com",
                "BreachDate": "2012-05-05",
                "AddedDate": "2016-05-21T00:00:00Z",
                "PwnCount": 164611595,
                "DataClasses": ["Email addresses", "Passwords"],
                "IsVerified": True,
                "IsSensitive": False,
                "Description": "LinkedIn breach.",
            },
        ]

        mock_breach_resp = MagicMock()
        mock_breach_resp.status_code = 200
        mock_breach_resp.json.return_value = breach_data

        # Paste endpoint returns 404 (no pastes)
        mock_paste_resp = MagicMock()
        mock_paste_resp.status_code = 404

        scanner = HIBPScanner(api_key="fake-key")

        with patch.object(scanner.session, "get") as mock_get:
            mock_get.side_effect = [mock_breach_resp, mock_paste_resp]
            results = scanner.scan("test@example.com")

        assert len(results) == 2
        assert results[0].scanner == "hibp"
        assert results[0].site_name == "Adobe"
        assert results[0].data_type == "breach"
        assert results[0].confidence == "high"
        assert results[0].details["pwn_count"] == 152445165
        assert results[0].details["is_verified"] is True

        assert results[1].site_name == "LinkedIn"
        assert results[1].details["breach_date"] == "2012-05-05"

    @patch("src.scanners.hibp_scanner.time.sleep")
    def test_hibp_scanner_with_pastes(self, mock_sleep):
        """Mock breach + paste responses and verify both are returned."""
        mock_breach_resp = MagicMock()
        mock_breach_resp.status_code = 200
        mock_breach_resp.json.return_value = [
            {
                "Name": "TestBreach",
                "Domain": "test.com",
                "BreachDate": "2020-01-01",
                "AddedDate": "2020-02-01T00:00:00Z",
                "PwnCount": 1000,
                "DataClasses": ["Email addresses"],
                "IsVerified": True,
                "IsSensitive": False,
                "Description": "",
            }
        ]

        mock_paste_resp = MagicMock()
        mock_paste_resp.status_code = 200
        mock_paste_resp.json.return_value = [
            {
                "Source": "Pastebin",
                "Id": "abc123",
                "Title": "Leaked Emails",
                "Date": "2020-03-15T00:00:00Z",
                "EmailCount": 500,
            }
        ]

        scanner = HIBPScanner(api_key="fake-key")

        with patch.object(scanner.session, "get") as mock_get:
            mock_get.side_effect = [mock_breach_resp, mock_paste_resp]
            results = scanner.scan("test@example.com")

        assert len(results) == 2
        breaches = [r for r in results if r.data_type == "breach"]
        pastes = [r for r in results if r.data_type == "paste"]
        assert len(breaches) == 1
        assert len(pastes) == 1
        assert pastes[0].site_name == "Pastebin: Leaked Emails"
        assert pastes[0].details["paste_id"] == "abc123"


class TestHIBPScannerNotFound:
    """Test HIBP scanner when no breaches are found."""

    @patch("src.scanners.hibp_scanner.time.sleep")
    def test_hibp_scanner_not_found(self, mock_sleep):
        """Mock 404 responses (no breaches, no pastes) and verify empty results."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        scanner = HIBPScanner(api_key="fake-key")

        with patch.object(scanner.session, "get") as mock_get:
            mock_get.return_value = mock_resp
            results = scanner.scan("clean@example.com")

        assert len(results) == 0

    @patch("src.scanners.hibp_scanner.time.sleep")
    def test_hibp_scanner_no_api_key_401(self, mock_sleep):
        """Mock 401 (no API key) and verify graceful fallback to empty."""
        mock_breach_resp = MagicMock()
        mock_breach_resp.status_code = 401

        # The fallback _check_breaches_free also needs a mock
        mock_breaches_list_resp = MagicMock()
        mock_breaches_list_resp.status_code = 200
        mock_breaches_list_resp.json.return_value = []

        mock_paste_resp = MagicMock()
        mock_paste_resp.status_code = 401

        scanner = HIBPScanner(api_key="")

        with patch.object(scanner.session, "get") as mock_get:
            mock_get.side_effect = [mock_breach_resp, mock_breaches_list_resp, mock_paste_resp]
            results = scanner.scan("nokey@example.com")

        assert len(results) == 0


class TestHIBPScannerRateLimited:
    """Test HIBP scanner rate limiting (429 responses)."""

    @patch("src.scanners.hibp_scanner.time.sleep")
    def test_hibp_scanner_rate_limited(self, mock_sleep):
        """Mock a 429 response, then successful retry."""
        # First call returns 429, second call (retry) returns 200
        mock_rate_limited = MagicMock()
        mock_rate_limited.status_code = 429
        mock_rate_limited.headers = {"Retry-After": "2"}

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = [
            {
                "Name": "DelayedBreach",
                "Domain": "delayed.com",
                "BreachDate": "2021-06-01",
                "AddedDate": "2021-07-01T00:00:00Z",
                "PwnCount": 5000,
                "DataClasses": ["Email addresses"],
                "IsVerified": True,
                "IsSensitive": False,
                "Description": "",
            }
        ]

        # Pastes return 404
        mock_paste_404 = MagicMock()
        mock_paste_404.status_code = 404

        scanner = HIBPScanner(api_key="fake-key")

        with patch.object(scanner.session, "get") as mock_get:
            # Breach: 429 -> retry -> 200, then paste: 404
            mock_get.side_effect = [mock_rate_limited, mock_success, mock_paste_404]
            results = scanner.scan("ratelimited@example.com")

        # Should have retried and found the breach
        assert len(results) == 1
        assert results[0].site_name == "DelayedBreach"

        # Verify sleep was called for rate limiting (Retry-After header)
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert 2 in sleep_calls  # Retry-After: 2

    @patch("src.scanners.hibp_scanner.time.sleep")
    def test_hibp_scanner_rate_limited_retry_fails(self, mock_sleep):
        """Mock 429 on breach, retry also fails (non-200)."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "1"}

        mock_500 = MagicMock()
        mock_500.status_code = 500

        mock_paste_404 = MagicMock()
        mock_paste_404.status_code = 404

        scanner = HIBPScanner(api_key="fake-key")

        with patch.object(scanner.session, "get") as mock_get:
            mock_get.side_effect = [mock_429, mock_500, mock_paste_404]
            results = scanner.scan("fail@example.com")

        assert len(results) == 0


class TestHIBPScannerAvailability:
    """Test scanner metadata."""

    def test_is_available(self):
        """HIBP scanner should always report as available."""
        scanner = HIBPScanner()
        assert scanner.is_available() is True

    def test_scanner_name(self):
        """Verify scanner name is 'hibp'."""
        scanner = HIBPScanner()
        assert scanner.name == "hibp"

    def test_api_key_header_set(self):
        """When an API key is provided, it should be in session headers."""
        scanner = HIBPScanner(api_key="my-secret-key")
        assert scanner.session.headers.get("hibp-api-key") == "my-secret-key"

    def test_no_api_key_header(self):
        """When no API key is provided, hibp-api-key should not be in headers."""
        scanner = HIBPScanner(api_key="")
        assert "hibp-api-key" not in scanner.session.headers
