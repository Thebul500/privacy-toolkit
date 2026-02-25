"""Data models for Privacy Toolkit."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml


DATA_SENSITIVITY = {
    "financial": 5, "ssn": 5, "health": 4, "phone": 3,
    "email": 3, "address": 3, "name": 2, "demographic": 1,
}


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class OptOutMethodType(str, Enum):
    EMAIL = "email"
    FORM = "form"
    PHONE = "phone"
    MANUAL = "manual"


class ScanStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class RemovalStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    REAPPEARED = "reappeared"
    PENDING_CAPTCHA = "pending_captcha"


@dataclass
class Address:
    street: str = ""
    city: str = ""
    state: str = ""
    state_abbr: str = ""
    zip_code: str = ""

    @property
    def formatted(self) -> str:
        parts = [p for p in [self.street, self.city, self.state, self.zip_code] if p]
        return ", ".join(parts)


@dataclass
class Profile:
    name: str
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    email_addresses: list[str] = field(default_factory=list)
    phone_numbers: list[str] = field(default_factory=list)
    usernames: list[str] = field(default_factory=list)
    addresses: list[Address] = field(default_factory=list)
    date_of_birth: str = ""
    region: str = "US"  # "US" or "EU"
    jurisdiction: str = "US"  # US state code (IL, CA) or EU country code (DE, FR)
    applicable_laws: list[str] = field(default_factory=lambda: ["CCPA"])

    @property
    def primary_email(self) -> str:
        return self.email_addresses[0] if self.email_addresses else ""

    @property
    def primary_phone(self) -> str:
        return self.phone_numbers[0] if self.phone_numbers else ""

    @property
    def primary_address(self) -> str:
        return self.addresses[0].formatted if self.addresses else ""

    @classmethod
    def from_yaml(cls, path: Path) -> Profile:
        with open(path) as f:
            data = yaml.safe_load(f)
        idents = data.get("identifiers", {})
        addresses = []
        for addr in idents.get("addresses", []):
            addresses.append(Address(
                street=addr.get("street", ""),
                city=addr.get("city", ""),
                state=addr.get("state", ""),
                state_abbr=addr.get("state_abbr", ""),
                zip_code=addr.get("zip", ""),
            ))
        return cls(
            name=data.get("name", ""),
            first_name=idents.get("first_name", ""),
            last_name=idents.get("last_name", ""),
            full_name=idents.get("full_name", ""),
            email_addresses=idents.get("email_addresses", []),
            phone_numbers=idents.get("phone_numbers", []),
            usernames=idents.get("usernames", []),
            addresses=addresses,
            date_of_birth=idents.get("date_of_birth", ""),
            region=data.get("legal", {}).get("region", "US"),
            jurisdiction=data.get("legal", {}).get("jurisdiction", "US"),
            applicable_laws=data.get("legal", {}).get("applicable_laws", ["CCPA"]),
        )

    def to_yaml(self, path: Path) -> None:
        data = {
            "name": self.name,
            "identifiers": {
                "first_name": self.first_name,
                "last_name": self.last_name,
                "full_name": self.full_name,
                "email_addresses": self.email_addresses,
                "phone_numbers": self.phone_numbers,
                "usernames": self.usernames,
                "addresses": [
                    {"street": a.street, "city": a.city, "state": a.state,
                     "state_abbr": a.state_abbr, "zip": a.zip_code}
                    for a in self.addresses
                ],
                "date_of_birth": self.date_of_birth,
            },
            "legal": {
                "region": self.region,
                "jurisdiction": self.jurisdiction,
                "applicable_laws": self.applicable_laws,
            },
            "created": datetime.now().strftime("%Y-%m-%d"),
            "last_scan": None,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


@dataclass
class FormStep:
    action: str  # goto, fill, click, wait, screenshot, select
    url: str = ""
    selector: str = ""
    field: str = ""  # maps to profile field
    value: str = ""  # static value
    duration: int = 0
    name: str = ""
    format: str = ""


@dataclass
class OptOutMethod:
    type: OptOutMethodType
    # email fields
    address: str = ""
    template: str = "ccpa_deletion_request"
    subject: str = ""
    # form fields
    url: str = ""
    steps: list[FormStep] = field(default_factory=list)
    # phone fields
    number: str = ""
    instructions: str = ""


@dataclass
class Verification:
    type: str = "manual"
    check_url: str = ""
    expected_days: int = 30


@dataclass
class Broker:
    slug: str
    name: str
    url: str = ""
    category: str = "people_search"
    priority: Priority = Priority.MEDIUM
    data_types: list[str] = field(default_factory=list)
    methods: list[OptOutMethod] = field(default_factory=list)
    verification: Verification = field(default_factory=Verification)
    reappearance_days: int = 90
    privacy_policy_url: str = ""
    notes: str = ""

    @classmethod
    def from_yaml(cls, path: Path) -> Broker:
        with open(path) as f:
            data = yaml.safe_load(f)
        opt_out = data.get("opt_out", {})
        methods = []
        for m in opt_out.get("methods", []):
            steps = []
            for s in m.get("steps", []):
                steps.append(FormStep(
                    action=s.get("action", ""),
                    url=s.get("url", ""),
                    selector=s.get("selector", ""),
                    field=s.get("field", ""),
                    value=s.get("value", ""),
                    duration=s.get("duration", 0),
                    name=s.get("name", ""),
                    format=s.get("format", ""),
                ))
            methods.append(OptOutMethod(
                type=OptOutMethodType(m["type"]),
                address=m.get("address", ""),
                template=m.get("template", "ccpa_deletion_request"),
                subject=m.get("subject", ""),
                url=m.get("url", ""),
                steps=steps,
                number=m.get("number", ""),
                instructions=m.get("instructions", ""),
            ))
        ver = opt_out.get("verification", {})
        return cls(
            slug=data["slug"],
            name=data["name"],
            url=data.get("url", ""),
            category=data.get("category", "people_search"),
            priority=Priority(data.get("priority", "medium")),
            data_types=data.get("data_types", []),
            methods=methods,
            verification=Verification(
                type=ver.get("type", "manual"),
                check_url=ver.get("check_url", ""),
                expected_days=ver.get("expected_days", 30),
            ),
            reappearance_days=opt_out.get("reappearance", {}).get("frequency_days", 90),
            privacy_policy_url=data.get("privacy_policy_url", ""),
            notes=data.get("notes", ""),
        )

    @property
    def email_method(self) -> Optional[OptOutMethod]:
        for m in self.methods:
            if m.type == OptOutMethodType.EMAIL:
                return m
        return None

    @property
    def form_method(self) -> Optional[OptOutMethod]:
        for m in self.methods:
            if m.type == OptOutMethodType.FORM:
                return m
        return None


@dataclass
class ScanResult:
    scanner: str
    site_name: str
    site_url: str = ""
    data_type: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    confidence: str = "medium"
    found_at: datetime = field(default_factory=datetime.now)
