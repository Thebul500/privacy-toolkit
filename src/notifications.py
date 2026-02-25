"""Signal, webhook, and multi-channel notifications."""

from __future__ import annotations
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import requests

from src.config import SignalConfig, WebhookConfig

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)


def send_signal(message: str, config: SignalConfig) -> bool:
    if not config.enabled or not config.sender or not config.recipients:
        return False
    try:
        for recipient in config.recipients:
            resp = requests.post(
                f"{config.api_url}/v2/send",
                json={
                    "message": message,
                    "number": config.sender,
                    "recipients": [recipient],
                },
                timeout=10,
            )
            if resp.status_code >= 400:
                logger.error("Signal API returned status %d for recipient=%s: %s", resp.status_code, recipient, resp.text[:200])
        return True
    except Exception as e:
        logger.error("Signal API call failed: %s", e)
        return False


def send_webhook(event: str, message: str, details: dict, config: WebhookConfig) -> bool:
    """Send a notification to a webhook endpoint."""
    if not config.enabled or not config.url:
        return False
    try:
        payload = {
            "event": event,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }
        resp = requests.post(
            config.url,
            json=payload,
            headers=config.headers,
            timeout=10,
        )
        if resp.status_code >= 400:
            logger.error("Webhook returned status %d: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as e:
        logger.error("Webhook call failed: %s", e)
        return False


def notify(event: str, message: str, config: "Config", details: dict | None = None) -> None:
    """Dispatch notification to all enabled channels (Signal + webhook)."""
    if config.signal.enabled:
        send_signal(message, config.signal)
    if config.webhook.enabled:
        send_webhook(event, message, details or {}, config.webhook)
