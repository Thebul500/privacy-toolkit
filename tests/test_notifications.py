"""Tests for src.notifications — Signal notification sending."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.config import SignalConfig
from src.notifications import send_signal


class TestSendNotificationSuccess:
    """Test successful notification delivery."""

    @patch("src.notifications.requests.post")
    def test_send_notification_success(self, mock_post):
        """Mock requests.post returning 200 and verify send_signal returns True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        config = SignalConfig(
            enabled=True,
            api_url="http://localhost:9999",
            sender="+15550000000",
            recipients=["+15551111111"],
        )

        result = send_signal("Test notification message", config)
        assert result is True

        # Verify requests.post was called with correct args
        mock_post.assert_called_once_with(
            "http://localhost:9999/v2/send",
            json={
                "message": "Test notification message",
                "number": "+15550000000",
                "recipients": ["+15551111111"],
            },
            timeout=10,
        )

    @patch("src.notifications.requests.post")
    def test_send_notification_multiple_recipients(self, mock_post):
        """Verify that send_signal calls post once per recipient."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        config = SignalConfig(
            enabled=True,
            api_url="http://localhost:9999",
            sender="+15550000000",
            recipients=["+15551111111", "+15552222222", "+15553333333"],
        )

        result = send_signal("Multi-recipient test", config)
        assert result is True
        assert mock_post.call_count == 3

        # Verify each recipient got a separate call
        calls = mock_post.call_args_list
        recipients_sent = [c.kwargs["json"]["recipients"][0] for c in calls]
        assert "+15551111111" in recipients_sent
        assert "+15552222222" in recipients_sent
        assert "+15553333333" in recipients_sent


class TestSendNotificationFailure:
    """Test notification failure handling."""

    @patch("src.notifications.requests.post")
    def test_send_notification_connection_error(self, mock_post):
        """Mock a connection error and verify send_signal returns False."""
        mock_post.side_effect = requests.ConnectionError("Connection refused")

        config = SignalConfig(
            enabled=True,
            api_url="http://localhost:9999",
            sender="+15550000000",
            recipients=["+15551111111"],
        )

        result = send_signal("This should fail", config)
        assert result is False

    @patch("src.notifications.requests.post")
    def test_send_notification_timeout(self, mock_post):
        """Mock a timeout and verify send_signal returns False."""
        mock_post.side_effect = requests.Timeout("Request timed out")

        config = SignalConfig(
            enabled=True,
            api_url="http://localhost:9999",
            sender="+15550000000",
            recipients=["+15551111111"],
        )

        result = send_signal("This should timeout", config)
        assert result is False

    @patch("src.notifications.requests.post")
    def test_send_notification_generic_exception(self, mock_post):
        """Mock a generic exception and verify graceful handling."""
        mock_post.side_effect = Exception("Unexpected error")

        config = SignalConfig(
            enabled=True,
            api_url="http://localhost:9999",
            sender="+15550000000",
            recipients=["+15551111111"],
        )

        result = send_signal("This should fail gracefully", config)
        assert result is False


class TestNotificationsDisabled:
    """Test behavior when notifications are disabled in config."""

    def test_notifications_disabled(self):
        """Config with signal disabled should return False without making requests."""
        config = SignalConfig(
            enabled=False,
            api_url="http://localhost:9999",
            sender="+15550000000",
            recipients=["+15551111111"],
        )

        # No mocking needed -- should short-circuit before any HTTP call
        result = send_signal("Should not send", config)
        assert result is False

    def test_notifications_no_sender(self):
        """Config with empty sender should return False."""
        config = SignalConfig(
            enabled=True,
            api_url="http://localhost:9999",
            sender="",
            recipients=["+15551111111"],
        )

        result = send_signal("Should not send", config)
        assert result is False

    def test_notifications_no_recipients(self):
        """Config with empty recipients should return False."""
        config = SignalConfig(
            enabled=True,
            api_url="http://localhost:9999",
            sender="+15550000000",
            recipients=[],
        )

        result = send_signal("Should not send", config)
        assert result is False

    def test_notifications_all_missing(self):
        """Config with everything empty/disabled should return False."""
        config = SignalConfig(
            enabled=False,
            api_url="",
            sender="",
            recipients=[],
        )

        result = send_signal("Should not send", config)
        assert result is False
