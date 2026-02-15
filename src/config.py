"""Configuration loading for Privacy Toolkit."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from src.models import Broker, Profile

TOOLKIT_DIR = Path(__file__).parent.parent
DEFAULT_CONFIG = TOOLKIT_DIR / "config" / "config.yaml"
PROFILES_DIR = TOOLKIT_DIR / "config" / "profiles"
BROKERS_DIR = TOOLKIT_DIR / "brokers"
TEMPLATES_DIR = TOOLKIT_DIR / "templates"
DATA_DIR = TOOLKIT_DIR / "data"
BIN_DIR = TOOLKIT_DIR / "bin"


@dataclass
class SmtpConfig:
    host: str = "smtp.gmail.com"
    port: int = 587
    use_tls: bool = True
    username: str = ""
    password: str = ""
    from_name: str = ""
    from_email: str = ""
    rate_limit: int = 10
    delay_seconds: int = 30


@dataclass
class SignalConfig:
    enabled: bool = True
    api_url: str = "http://localhost:8082"
    sender: str = ""
    recipients: list[str] = field(default_factory=list)


@dataclass
class ScheduleConfig:
    rescan_interval_days: int = 90
    cron_time: str = "0 3 * * 0"
    notify_on_complete: bool = True
    notification_method: str = "signal"


@dataclass
class BrowserConfig:
    headless: bool = True
    timeout: int = 30000
    screenshot_on_submit: bool = True


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class Config:
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    web: WebConfig = field(default_factory=WebConfig)
    db_path: str = "data/privacy_toolkit.db"
    log_level: str = "INFO"
    hibp_api_key: str = ""

    @classmethod
    def load(cls, path: Optional[Path] = None) -> Config:
        path = path or DEFAULT_CONFIG
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        smtp_data = data.get("smtp", {})
        signal_data = data.get("notifications", {}).get("signal", {})
        sched_data = data.get("scheduling", {})
        browser_data = data.get("browser", {})
        web_data = data.get("web", {})

        return cls(
            smtp=SmtpConfig(
                host=smtp_data.get("host", "smtp.gmail.com"),
                port=smtp_data.get("port", 587),
                use_tls=smtp_data.get("use_tls", True),
                username=smtp_data.get("username", ""),
                password=smtp_data.get("password", ""),
                from_name=smtp_data.get("from_name", ""),
                from_email=smtp_data.get("from_email", ""),
                rate_limit=smtp_data.get("rate_limit", 10),
                delay_seconds=smtp_data.get("delay_seconds", 30),
            ),
            signal=SignalConfig(
                enabled=signal_data.get("enabled", False),
                api_url=signal_data.get("api_url", "http://localhost:8082"),
                sender=signal_data.get("sender", ""),
                recipients=signal_data.get("recipients", []),
            ),
            schedule=ScheduleConfig(
                rescan_interval_days=sched_data.get("rescan_interval_days", 90),
                cron_time=sched_data.get("cron_time", "0 3 * * 0"),
                notify_on_complete=sched_data.get("notify_on_complete", True),
                notification_method=sched_data.get("notification_method", "signal"),
            ),
            browser=BrowserConfig(
                headless=browser_data.get("headless", True),
                timeout=browser_data.get("timeout", 30000),
                screenshot_on_submit=browser_data.get("screenshot_on_submit", True),
            ),
            web=WebConfig(
                host=web_data.get("host", "0.0.0.0"),
                port=web_data.get("port", 8080),
            ),
            db_path=data.get("database", {}).get("path", "data/privacy_toolkit.db"),
            log_level=data.get("logging", {}).get("level", "INFO"),
            hibp_api_key=data.get("hibp", {}).get("api_key", ""),
        )


def load_profile(name: str) -> Profile:
    path = PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")
    return Profile.from_yaml(path)


def list_profiles() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.yaml"))]


def load_broker(slug: str) -> Broker:
    path = BROKERS_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Broker not found: {path}")
    return Broker.from_yaml(path)


def load_all_brokers() -> list[Broker]:
    if not BROKERS_DIR.exists():
        return []
    brokers = []
    for path in sorted(BROKERS_DIR.glob("*.yaml")):
        if path.stem.startswith("_"):
            continue
        try:
            brokers.append(Broker.from_yaml(path))
        except Exception:
            continue
    return brokers
