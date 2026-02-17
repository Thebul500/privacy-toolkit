"""Tests for src.models — Pydantic/dataclass models."""

from __future__ import annotations

from datetime import datetime

import yaml

from src.models import (
    Address,
    Broker,
    FormStep,
    OptOutMethod,
    OptOutMethodType,
    Priority,
    Profile,
    RemovalStatus,
    ScanResult,
    ScanStatus,
    Verification,
)


class TestProfileCreation:
    """Test creating Profile objects with valid data."""

    def test_profile_creation(self, sample_profile):
        """Create a Profile with valid data and verify all fields."""
        p = sample_profile

        assert p.name == "testuser"
        assert p.first_name == "Jane"
        assert p.last_name == "Doe"
        assert p.full_name == "Jane Doe"
        assert len(p.email_addresses) == 2
        assert p.email_addresses[0] == "jane.doe@example.com"
        assert len(p.phone_numbers) == 1
        assert len(p.usernames) == 2
        assert p.jurisdiction == "US"
        assert "CCPA" in p.applicable_laws
        assert "GDPR" in p.applicable_laws

    def test_profile_primary_email(self, sample_profile):
        """Verify primary_email returns the first email address."""
        assert sample_profile.primary_email == "jane.doe@example.com"

    def test_profile_primary_phone(self, sample_profile):
        """Verify primary_phone returns the first phone number."""
        assert sample_profile.primary_phone == "+15551234567"

    def test_profile_primary_address(self, sample_profile):
        """Verify primary_address returns formatted address string."""
        addr = sample_profile.primary_address
        assert "123 Main St" in addr
        assert "Springfield" in addr
        assert "Illinois" in addr

    def test_profile_empty_defaults(self):
        """A Profile with only a name should have sensible empty defaults."""
        p = Profile(name="minimal")
        assert p.primary_email == ""
        assert p.primary_phone == ""
        assert p.primary_address == ""
        assert p.date_of_birth == ""
        assert p.jurisdiction == "US"
        assert p.applicable_laws == ["CCPA"]

    def test_address_formatted(self):
        """Verify the Address.formatted property joins non-empty parts."""
        a = Address(street="100 Elm St", city="Austin", state="TX", zip_code="78701")
        assert a.formatted == "100 Elm St, Austin, TX, 78701"

    def test_address_partial(self):
        """Address with only some fields should omit blanks."""
        a = Address(city="Denver", state="CO")
        assert a.formatted == "Denver, CO"


class TestProfileFromYaml:
    """Test loading Profile from a YAML file."""

    def test_profile_from_yaml(self, profile_yaml_path):
        """Load a profile from YAML and verify all fields parse correctly."""
        p = Profile.from_yaml(profile_yaml_path)

        assert p.name == "yamluser"
        assert p.first_name == "John"
        assert p.last_name == "Smith"
        assert p.full_name == "John Smith"
        assert "john@example.com" in p.email_addresses
        assert "+15559876543" in p.phone_numbers
        assert "jsmith" in p.usernames
        assert len(p.addresses) == 1
        assert p.addresses[0].city == "Portland"
        assert p.addresses[0].state_abbr == "OR"

    def test_profile_roundtrip(self, sample_profile, tmp_path):
        """Write a Profile to YAML and read it back, verifying fidelity."""
        path = tmp_path / "roundtrip.yaml"
        sample_profile.to_yaml(path)
        assert path.exists()

        loaded = Profile.from_yaml(path)
        assert loaded.name == sample_profile.name
        assert loaded.first_name == sample_profile.first_name
        assert loaded.last_name == sample_profile.last_name
        assert loaded.email_addresses == sample_profile.email_addresses
        assert loaded.phone_numbers == sample_profile.phone_numbers
        assert loaded.usernames == sample_profile.usernames


class TestBrokerFromYaml:
    """Test parsing broker YAML into Broker model."""

    def test_broker_from_yaml(self, broker_yaml_path):
        """Parse a broker YAML fixture into a Broker dataclass."""
        broker = Broker.from_yaml(broker_yaml_path)

        assert broker.slug == "tempbroker"
        assert broker.name == "Temp Broker"
        assert broker.url == "https://tempbroker.example.com"
        assert broker.category == "people_search"
        assert broker.priority == Priority.MEDIUM
        assert "name" in broker.data_types
        assert "email" in broker.data_types

    def test_broker_methods_parsed(self, broker_yaml_path):
        """Verify opt-out methods are correctly parsed from YAML."""
        broker = Broker.from_yaml(broker_yaml_path)

        assert len(broker.methods) == 1
        method = broker.methods[0]
        assert method.type == OptOutMethodType.EMAIL
        assert method.address == "remove@tempbroker.example.com"
        assert method.template == "ccpa_deletion_request"

    def test_broker_verification(self, broker_yaml_path):
        """Verify the verification section is parsed."""
        broker = Broker.from_yaml(broker_yaml_path)

        assert broker.verification.type == "manual"
        assert broker.verification.expected_days == 30

    def test_broker_email_method_property(self, broker_yaml_path):
        """Test the email_method convenience property."""
        broker = Broker.from_yaml(broker_yaml_path)
        assert broker.email_method is not None
        assert broker.email_method.type == OptOutMethodType.EMAIL

    def test_broker_form_method_none(self, broker_yaml_path):
        """Broker with only email method should return None for form_method."""
        broker = Broker.from_yaml(broker_yaml_path)
        assert broker.form_method is None

    def test_broker_real_whitepages(self):
        """Load the real whitepages broker and verify complex structure."""
        from src.config import BROKERS_DIR

        path = BROKERS_DIR / "whitepages.yaml"
        broker = Broker.from_yaml(path)

        assert broker.slug == "whitepages"
        assert broker.priority == Priority.CRITICAL
        assert len(broker.methods) == 2  # form + email

        # Has form steps
        form = broker.form_method
        assert form is not None
        assert len(form.steps) > 0
        assert form.steps[0].action == "goto"


class TestScanResultCreation:
    """Test creating ScanResult objects."""

    def test_scan_result_creation(self):
        """Create a ScanResult with valid data and verify fields."""
        result = ScanResult(
            scanner="hibp",
            site_name="Adobe",
            site_url="https://adobe.com",
            data_type="breach",
            details={
                "breach_date": "2013-10-04",
                "pwn_count": 152445165,
                "data_classes": ["email", "password"],
            },
            confidence="high",
        )
        assert result.scanner == "hibp"
        assert result.site_name == "Adobe"
        assert result.data_type == "breach"
        assert result.details["pwn_count"] == 152445165
        assert result.confidence == "high"
        assert isinstance(result.found_at, datetime)

    def test_scan_result_defaults(self):
        """ScanResult with minimal fields should have sensible defaults."""
        result = ScanResult(scanner="test", site_name="TestSite")
        assert result.site_url == ""
        assert result.data_type == ""
        assert result.details == {}
        assert result.confidence == "medium"
        assert isinstance(result.found_at, datetime)

    def test_scan_result_paste_type(self):
        """Create a paste-type ScanResult."""
        result = ScanResult(
            scanner="hibp",
            site_name="Pastebin: Leaked Emails",
            site_url="https://pastebin.com/abc123",
            data_type="paste",
            details={"email_count": 5000, "source": "Pastebin"},
            confidence="high",
        )
        assert result.data_type == "paste"
        assert result.details["source"] == "Pastebin"


class TestEnums:
    """Test model enumerations."""

    def test_priority_values(self):
        """All Priority levels should be valid."""
        assert Priority.CRITICAL.value == "critical"
        assert Priority.HIGH.value == "high"
        assert Priority.MEDIUM.value == "medium"
        assert Priority.LOW.value == "low"

    def test_scan_status_values(self):
        """All ScanStatus values should be valid."""
        assert ScanStatus.RUNNING.value == "running"
        assert ScanStatus.COMPLETED.value == "completed"
        assert ScanStatus.FAILED.value == "failed"

    def test_removal_status_values(self):
        """All RemovalStatus values should be valid."""
        assert RemovalStatus.PENDING.value == "pending"
        assert RemovalStatus.SUBMITTED.value == "submitted"
        assert RemovalStatus.CONFIRMED.value == "confirmed"
        assert RemovalStatus.REAPPEARED.value == "reappeared"

    def test_opt_out_method_types(self):
        """All OptOutMethodType values should be valid."""
        assert OptOutMethodType.EMAIL.value == "email"
        assert OptOutMethodType.FORM.value == "form"
        assert OptOutMethodType.PHONE.value == "phone"
        assert OptOutMethodType.MANUAL.value == "manual"
