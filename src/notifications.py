"""Signal and email notifications."""

from __future__ import annotations
import logging

import requests

from src.config import SignalConfig

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
