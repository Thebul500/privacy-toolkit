"""Tests for src.config — Configuration loading."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.config import (
    BROKERS_DIR,
    Config,
    load_all_brokers,
    load_broker,
    load_profile,
)


class TestLoadConfigExample:
    """Test loading config.yaml.example and verifying defaults."""

    def test_load_config_example(self):
        """Load config.yaml.example and verify it parses with expected defaults."""
        example_path = Path(__file__).parent.parent / "config" / "config.yaml.example"
        assert example_path.exists(), f"config.yaml.example not found at {example_path}"

        config = Config.load(example_path)

        # SMTP defaults from the example file
        assert config.smtp.host == "smtp.gmail.com"
        assert config.smtp.port == 587
        assert config.smtp.use_tls is True
        assert config.smtp.username == ""
        assert config.smtp.rate_limit == 10
        assert config.smtp.delay_seconds == 30

        # Signal disabled in example
        assert config.signal.enabled is False
        assert config.signal.sender == ""
        assert config.signal.recipients == []

        # Schedule defaults
        assert config.schedule.rescan_interval_days == 90
        assert config.schedule.cron_time == "0 3 * * 0"

        # Browser defaults
        assert config.browser.headless is True
        assert config.browser.timeout == 30000

        # Database
        assert config.db_path == "data/privacy_toolkit.db"
        assert config.log_level == "INFO"
        assert config.hibp_api_key == ""

    def test_load_config_returns_all_sections(self):
        """Verify every Config section is populated, not None."""
        example_path = Path(__file__).parent.parent / "config" / "config.yaml.example"
        config = Config.load(example_path)

        assert config.smtp is not None
        assert config.signal is not None
        assert config.schedule is not None
        assert config.browser is not None
        assert config.web is not None


class TestLoadBrokerYaml:
    """Test loading individual broker YAML files."""

    def test_load_broker_yaml(self):
        """Load a real broker YAML from the brokers/ directory."""
        broker = load_broker("whitepages")

        assert broker.slug == "whitepages"
        assert broker.name == "Whitepages"
        assert broker.url == "https://www.whitepages.com"
        assert broker.category == "people_search"
        assert broker.priority.value == "critical"
        assert len(broker.data_types) > 0
        assert len(broker.methods) > 0

    def test_broker_has_email_method(self):
        """Verify the whitepages broker has an email opt-out method."""
        broker = load_broker("whitepages")
        email_method = broker.email_method
        assert email_method is not None
        assert email_method.address == "suppression@whitepages.com"

    def test_broker_has_form_method(self):
        """Verify the whitepages broker has a form opt-out method."""
        broker = load_broker("whitepages")
        form_method = broker.form_method
        assert form_method is not None
        assert "suppression" in form_method.url

    def test_broker_from_fixture(self, broker_yaml_path):
        """Load a broker from a temporary YAML fixture."""
        from src.models import Broker

        broker = Broker.from_yaml(broker_yaml_path)
        assert broker.slug == "tempbroker"
        assert broker.name == "Temp Broker"
        assert len(broker.methods) == 1
        assert broker.methods[0].type.value == "email"
        assert broker.reappearance_days == 60


class TestLoadAllBrokers:
    """Test loading all broker YAML files."""

    def test_load_all_brokers(self):
        """Load all 78 brokers from the brokers/ directory and verify count."""
        brokers = load_all_brokers()
        assert len(brokers) == 78, (
            f"Expected 78 brokers but got {len(brokers)}. "
            f"Check that no broker YAML files were added or removed."
        )

    def test_all_brokers_have_slug(self):
        """Every loaded broker should have a non-empty slug."""
        brokers = load_all_brokers()
        for broker in brokers:
            assert broker.slug, f"Broker with name '{broker.name}' has empty slug"

    def test_all_brokers_have_name(self):
        """Every loaded broker should have a non-empty name."""
        brokers = load_all_brokers()
        for broker in brokers:
            assert broker.name, f"Broker with slug '{broker.slug}' has empty name"

    def test_all_brokers_have_at_least_one_method(self):
        """Every loaded broker should define at least one opt-out method."""
        brokers = load_all_brokers()
        for broker in brokers:
            assert len(broker.methods) > 0, (
                f"Broker '{broker.slug}' has no opt-out methods"
            )


class TestMissingConfigFile:
    """Test graceful handling of missing or invalid config files."""

    def test_missing_config_file(self):
        """Loading a non-existent config file should return defaults."""
        config = Config.load(Path("/tmp/nonexistent_config_file_xyz.yaml"))

        # Should return a default Config (all defaults)
        assert config.smtp.host == "smtp.gmail.com"
        assert config.signal.enabled is True  # dataclass default is True
        assert config.db_path == "data/privacy_toolkit.db"

    def test_missing_profile_raises(self):
        """Loading a non-existent profile should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_profile("this_profile_does_not_exist_xyz")

    def test_missing_broker_raises(self):
        """Loading a non-existent broker should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_broker("this_broker_does_not_exist_xyz")

    def test_empty_yaml_returns_defaults(self, tmp_path):
        """An empty YAML file should parse to default Config values."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")

        config = Config.load(empty_file)
        assert config.smtp.host == "smtp.gmail.com"
        assert config.db_path == "data/privacy_toolkit.db"
