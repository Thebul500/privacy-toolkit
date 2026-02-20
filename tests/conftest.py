"""Shared fixtures for Privacy Toolkit tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import yaml

from src.config import Config, SignalConfig, SmtpConfig
from src.db import Database
from src.models import (
    Address,
    Broker,
    OptOutMethod,
    OptOutMethodType,
    Priority,
    Profile,
    Verification,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database for testing.

    Patches TOOLKIT_DIR so the Database constructor writes into tmp_path
    instead of the real project directory.
    """
    with patch("src.db.TOOLKIT_DIR", tmp_path):
        db = Database(db_path="test.db")
        yield db
    # Cleanup is automatic -- tmp_path is removed by pytest after the test.


@pytest.fixture
def sample_profile():
    """Return a Profile object populated with fake test data."""
    return Profile(
        name="testuser",
        first_name="Jane",
        last_name="Doe",
        full_name="Jane Doe",
        email_addresses=["jane.doe@example.com", "jdoe@test.org"],
        phone_numbers=["+15551234567"],
        usernames=["janedoe", "jdoe42"],
        addresses=[
            Address(
                street="123 Main St",
                city="Springfield",
                state="Illinois",
                state_abbr="IL",
                zip_code="62704",
            )
        ],
        date_of_birth="1990-01-15",
        jurisdiction="US",
        applicable_laws=["CCPA", "GDPR"],
    )


@pytest.fixture
def sample_config():
    """Return a Config object with test/dummy values (no real credentials)."""
    return Config(
        smtp=SmtpConfig(
            host="smtp.test.local",
            port=587,
            use_tls=True,
            username="test@example.com",
            password="fake-password",
            from_name="Test Toolkit",
            from_email="test@example.com",
            rate_limit=10,
            delay_seconds=0,
        ),
        signal=SignalConfig(
            enabled=True,
            api_url="http://localhost:9999",
            sender="+15550000000",
            recipients=["+15551111111"],
        ),
        db_path="data/test.db",
        log_level="DEBUG",
        hibp_api_key="test-api-key-fake",
    )


@pytest.fixture
def sample_broker():
    """Return a Broker object matching a typical broker YAML structure."""
    return Broker(
        slug="testbroker",
        name="Test Broker Inc",
        url="https://testbroker.example.com",
        category="people_search",
        priority=Priority.HIGH,
        data_types=["name", "phone", "email", "address"],
        methods=[
            OptOutMethod(
                type=OptOutMethodType.EMAIL,
                address="privacy@testbroker.example.com",
                template="ccpa_deletion_request",
                subject="Data Deletion Request",
            ),
            OptOutMethod(
                type=OptOutMethodType.FORM,
                url="https://testbroker.example.com/optout",
                steps=[],
            ),
        ],
        verification=Verification(
            type="check_listing",
            check_url="https://testbroker.example.com/search",
            expected_days=14,
        ),
        reappearance_days=90,
        privacy_policy_url="https://testbroker.example.com/privacy",
        notes="Test broker for unit tests",
    )


@pytest.fixture
def broker_yaml_path(tmp_path):
    """Create a temporary broker YAML file and return its path."""
    data = {
        "slug": "tempbroker",
        "name": "Temp Broker",
        "url": "https://tempbroker.example.com",
        "category": "people_search",
        "priority": "medium",
        "data_types": ["name", "email"],
        "opt_out": {
            "methods": [
                {
                    "type": "email",
                    "address": "remove@tempbroker.example.com",
                    "template": "ccpa_deletion_request",
                    "subject": "",
                }
            ],
            "verification": {
                "type": "manual",
                "check_url": "",
                "expected_days": 30,
            },
            "reappearance": {
                "frequency_days": 60,
            },
        },
        "privacy_policy_url": "https://tempbroker.example.com/privacy",
        "notes": "",
    }
    path = tmp_path / "tempbroker.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    return path


@pytest.fixture
def profile_yaml_path(tmp_path):
    """Create a temporary profile YAML file and return its path."""
    data = {
        "name": "yamluser",
        "identifiers": {
            "first_name": "John",
            "last_name": "Smith",
            "full_name": "John Smith",
            "email_addresses": ["john@example.com"],
            "phone_numbers": ["+15559876543"],
            "usernames": ["jsmith"],
            "addresses": [
                {
                    "street": "456 Oak Ave",
                    "city": "Portland",
                    "state": "Oregon",
                    "state_abbr": "OR",
                    "zip": "97201",
                }
            ],
            "date_of_birth": "1985-06-20",
        },
        "legal": {
            "jurisdiction": "US",
            "applicable_laws": ["CCPA"],
        },
        "created": "2026-01-01",
        "last_scan": None,
    }
    path = tmp_path / "yamluser.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    return path
