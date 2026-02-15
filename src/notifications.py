"""Signal and email notifications."""

from __future__ import annotations
import requests

from src.config import SignalConfig


def send_signal(message: str, config: SignalConfig) -> bool:
    if not config.enabled or not config.sender or not config.recipients:
        return False
    try:
        for recipient in config.recipients:
            requests.post(
                f"{config.api_url}/v2/send",
                json={
                    "message": message,
                    "number": config.sender,
                    "recipients": [recipient],
                },
                timeout=10,
            )
        return True
    except Exception:
        return False
