"""Configuration loading for Privacy Toolkit."""

from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

from src.models import Broker, Profile

TOOLKIT_DIR = Path(__file__).parent.parent
DEFAULT_CONFIG = TOOLKIT_DIR / "config" / "config.yaml"
PROFILES_DIR = TOOLKIT_DIR / "config" / "profiles"
BROKERS_DIR = TOOLKIT_DIR / "brokers"
TEMPLATES_DIR = TOOLKIT_DIR / "templates"
DATA_DIR = TOOLKIT_DIR / "data"
BIN_DIR = TOOLKIT_DIR / "bin"


def _resolve_env(value: str, env_name: str) -> str:
    """Resolve a config value with environment variable fallback.

    - If value is "${VAR_NAME}", look up VAR_NAME in the environment.
    - If value is empty/blank, fall back to the env var ``env_name``.
    - Otherwise return the literal value unchanged.
    """
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_key = value[2:-1]
        return os.environ.get(env_key, "")
    if not value or (isinstance(value, str) and not value.strip()):
        return os.environ.get(env_name, "")
    return value


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
                username=_resolve_env(smtp_data.get("username", ""), "SMTP_USERNAME"),
                password=_resolve_env(smtp_data.get("password", ""), "SMTP_PASSWORD"),
                from_name=smtp_data.get("from_name", ""),
                from_email=smtp_data.get("from_email", ""),
                rate_limit=smtp_data.get("rate_limit", 10),
                delay_seconds=smtp_data.get("delay_seconds", 30),
            ),
            signal=SignalConfig(
                enabled=signal_data.get("enabled", False),
                api_url=_resolve_env(signal_data.get("api_url", "http://localhost:8082"), "SIGNAL_API_URL"),
                sender=_resolve_env(signal_data.get("sender", ""), "SIGNAL_SENDER"),
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
            hibp_api_key=_resolve_env(data.get("hibp", {}).get("api_key", ""), "HIBP_API_KEY"),
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


VALID_PRIORITIES = {"critical", "high", "medium", "low"}
VALID_METHOD_TYPES = {"email", "form", "phone", "manual"}


def validate_broker(data: dict, filename: str) -> list[str]:
    """Validate a broker YAML dict and return a list of error strings.

    Returns an empty list if the broker data is valid.
    """
    errors: list[str] = []

    # Required top-level fields
    for field_name in ("slug", "name", "url", "category", "priority"):
        if field_name not in data or not data[field_name]:
            errors.append(f"Missing required field: {field_name}")

    # Priority validation
    priority = data.get("priority")
    if priority and priority not in VALID_PRIORITIES:
        errors.append(
            f"Invalid priority '{priority}', must be one of: "
            f"{', '.join(sorted(VALID_PRIORITIES))}"
        )

    # Category must be a string
    category = data.get("category")
    if category is not None and not isinstance(category, str):
        errors.append(f"'category' must be a string, got {type(category).__name__}")

    # data_types must be a list if present
    data_types = data.get("data_types")
    if data_types is not None and not isinstance(data_types, list):
        errors.append(f"'data_types' must be a list, got {type(data_types).__name__}")

    # opt_out.methods must exist and be non-empty
    opt_out = data.get("opt_out", {})
    if not isinstance(opt_out, dict):
        errors.append("'opt_out' must be a mapping")
        return errors

    methods = opt_out.get("methods")
    if not methods:
        errors.append("'opt_out.methods' is missing or empty")
        return errors

    if not isinstance(methods, list):
        errors.append(
            f"'opt_out.methods' must be a list, got {type(methods).__name__}"
        )
        return errors

    # Validate each method
    for i, method in enumerate(methods):
        method_type = method.get("type")
        if not method_type:
            errors.append(f"Method {i}: missing 'type'")
            continue

        if method_type not in VALID_METHOD_TYPES:
            errors.append(
                f"Method {i}: invalid type '{method_type}', "
                f"must be one of: {', '.join(sorted(VALID_METHOD_TYPES))}"
            )
            continue

        if method_type == "email" and not method.get("address"):
            errors.append(f"Method {i} (email): missing 'address'")

        if method_type == "form":
            if not method.get("url"):
                errors.append(f"Method {i} (form): missing 'url'")
            if not method.get("steps"):
                errors.append(f"Method {i} (form): missing 'steps'")

    return errors


def load_broker(slug: str) -> Broker:
    path = BROKERS_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Broker not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    errors = validate_broker(data, path.name)
    if errors:
        for err in errors:
            logger.warning("Broker %s: %s", path.name, err)
    return Broker.from_yaml(path)


def load_all_brokers() -> list[Broker]:
    if not BROKERS_DIR.exists():
        return []
    brokers = []
    warned = 0
    for path in sorted(BROKERS_DIR.glob("*.yaml")):
        if path.stem.startswith("_"):
            continue
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            errors = validate_broker(data, path.name)
            if errors:
                warned += 1
                for err in errors:
                    logger.warning("Broker %s: %s", path.name, err)
            brokers.append(Broker.from_yaml(path))
        except Exception as e:
            logger.warning("Failed to load broker YAML %s: %s", path.name, e)
            continue
    logger.info("Loaded %d brokers (%d with warnings)", len(brokers), warned)
    return brokers
