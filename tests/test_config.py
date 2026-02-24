"""Tests for src.config — Configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config import (
    BROKERS_DIR,
    Config,
    load_all_brokers,
    load_broker,
    load_profile,
    validate_broker,
    validate_safe_name,
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


class TestEnvVarResolution:
    """Test environment variable fallback support in config loading."""

    def test_env_var_resolution(self, tmp_path, monkeypatch):
        """Empty YAML values should fall back to environment variables."""
        monkeypatch.setenv("SMTP_PASSWORD", "env-pass-123")
        monkeypatch.setenv("SMTP_USERNAME", "env-user@example.com")
        monkeypatch.setenv("HIBP_API_KEY", "env-hibp-key")
        monkeypatch.setenv("SIGNAL_SENDER", "+15551234567")
        monkeypatch.setenv("SIGNAL_API_URL", "http://env-signal:9999")

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "smtp": {"username": "", "password": ""},
            "hibp": {"api_key": ""},
            "notifications": {"signal": {"sender": "", "api_url": ""}},
        }))

        config = Config.load(config_file)

        assert config.smtp.password == "env-pass-123"
        assert config.smtp.username == "env-user@example.com"
        assert config.hibp_api_key == "env-hibp-key"
        assert config.signal.sender == "+15551234567"
        assert config.signal.api_url == "http://env-signal:9999"

    def test_env_var_syntax(self, tmp_path, monkeypatch):
        """Values like ${SMTP_PASSWORD} should resolve from the environment."""
        monkeypatch.setenv("SMTP_PASSWORD", "dollar-brace-pass")
        monkeypatch.setenv("HIBP_API_KEY", "dollar-brace-hibp")

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "smtp": {"password": "${SMTP_PASSWORD}"},
            "hibp": {"api_key": "${HIBP_API_KEY}"},
        }))

        config = Config.load(config_file)

        assert config.smtp.password == "dollar-brace-pass"
        assert config.hibp_api_key == "dollar-brace-hibp"

    def test_literal_value_unchanged(self, tmp_path, monkeypatch):
        """Non-empty literal values should pass through without env lookup."""
        monkeypatch.setenv("SMTP_PASSWORD", "should-be-ignored")
        monkeypatch.setenv("HIBP_API_KEY", "should-be-ignored")

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "smtp": {"password": "my-literal-password", "username": "literal@test.com"},
            "hibp": {"api_key": "literal-hibp-key"},
            "notifications": {"signal": {"sender": "+10000000000", "api_url": "http://literal:8080"}},
        }))

        config = Config.load(config_file)

        assert config.smtp.password == "my-literal-password"
        assert config.smtp.username == "literal@test.com"
        assert config.hibp_api_key == "literal-hibp-key"
        assert config.signal.sender == "+10000000000"
        assert config.signal.api_url == "http://literal:8080"


class TestValidateBroker:
    """Test the validate_broker() function."""

    def _valid_broker_dict(self) -> dict:
        """Return a minimal valid broker dict for testing."""
        return {
            "slug": "testbroker",
            "name": "Test Broker",
            "url": "https://testbroker.example.com",
            "category": "people_search",
            "priority": "high",
            "data_types": ["name", "email"],
            "opt_out": {
                "methods": [
                    {
                        "type": "email",
                        "address": "remove@testbroker.example.com",
                        "template": "ccpa_deletion_request",
                        "subject": "",
                    }
                ],
                "verification": {"type": "manual"},
            },
        }

    def test_validate_broker_valid(self):
        """A complete broker dict passes with no errors."""
        data = self._valid_broker_dict()
        errors = validate_broker(data, "testbroker.yaml")
        assert errors == []

    def test_validate_broker_missing_slug(self):
        """Missing slug returns an error."""
        data = self._valid_broker_dict()
        del data["slug"]
        errors = validate_broker(data, "testbroker.yaml")
        assert any("slug" in e for e in errors)

    def test_validate_broker_bad_priority(self):
        """Invalid priority returns an error."""
        data = self._valid_broker_dict()
        data["priority"] = "urgent"
        errors = validate_broker(data, "testbroker.yaml")
        assert any("priority" in e.lower() for e in errors)

    def test_validate_broker_no_methods(self):
        """Missing opt_out.methods returns an error."""
        data = self._valid_broker_dict()
        del data["opt_out"]["methods"]
        errors = validate_broker(data, "testbroker.yaml")
        assert any("methods" in e for e in errors)

    def test_validate_broker_bad_method_type(self):
        """Invalid method type returns an error."""
        data = self._valid_broker_dict()
        data["opt_out"]["methods"] = [{"type": "fax"}]
        errors = validate_broker(data, "testbroker.yaml")
        assert any("fax" in e for e in errors)

    def test_validate_all_real_brokers(self):
        """Load all 78 real broker YAMLs and assert all pass validation."""
        for path in sorted(BROKERS_DIR.glob("*.yaml")):
            if path.stem.startswith("_"):
                continue
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            errors = validate_broker(data, path.name)
            assert errors == [], (
                f"Broker {path.name} has validation errors: {errors}"
            )


class TestPathTraversalPrevention:
    """Test that path traversal attacks are blocked."""

    def test_dotdot_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="illegal characters"):
            validate_safe_name("../etc/passwd", tmp_path, "test")

    def test_forward_slash_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="illegal characters"):
            validate_safe_name("foo/bar", tmp_path, "test")

    def test_backslash_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="illegal characters"):
            validate_safe_name("foo\\bar", tmp_path, "test")

    def test_null_byte_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="null bytes"):
            validate_safe_name("foo\x00bar", tmp_path, "test")

    def test_empty_name_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            validate_safe_name("", tmp_path, "test")

    def test_whitespace_only_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            validate_safe_name("   ", tmp_path, "test")

    def test_valid_name_returns_path(self, tmp_path):
        result = validate_safe_name("my-profile", tmp_path, "test")
        assert result == (tmp_path / "my-profile.yaml").resolve()

    def test_load_profile_traversal(self):
        with pytest.raises(ValueError):
            load_profile("../../etc/passwd")

    def test_load_broker_traversal(self):
        with pytest.raises(ValueError):
            load_broker("../../etc/passwd")
