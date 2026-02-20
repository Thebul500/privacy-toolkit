"""Privacy exposure scoring engine."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PrivacyScore:
    score: int  # 0-100 (0 = maximum exposure, 100 = fully private)
    grade: str  # A, B, C, D, F
    findings_count: int
    breaches_count: int
    broker_listings: int
    accounts_found: int
    removals_confirmed: int
    removals_pending: int
    risk_factors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def _parse_details(raw: str | dict | None) -> dict:
    """Safely parse finding details from DB (may be JSON string or dict)."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _compute_grade(score: int) -> str:
    """Map a numeric score to a letter grade."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def calculate_score(db, profile: str) -> PrivacyScore:
    """Calculate the privacy exposure score for a profile.

    Queries findings, breaches, and removals from the database
    and produces a 0-100 score with grade, risk factors, and
    recommendations.

    Args:
        db: Database instance with get_findings / get_removals methods.
        profile: Profile name to score.

    Returns:
        PrivacyScore dataclass with all computed fields.
    """
    findings = db.get_findings(profile=profile)
    removals = db.get_removals(profile=profile)

    # --- Classify findings ---
    breaches: list[dict] = []
    broker_listings: list[dict] = []
    accounts: list[dict] = []

    for f in findings:
        data_type = f.get("data_type", "")
        if data_type == "breach":
            breaches.append(f)
        elif data_type.startswith("listing_"):
            broker_listings.append(f)
        elif data_type in ("email_registered", "username_match"):
            accounts.append(f)
        # paste and phone_info are informational, not directly scored

    # --- Classify removals ---
    confirmed_removals = [r for r in removals if r.get("status") == "confirmed"]
    pending_removals = [r for r in removals if r.get("status") in ("pending", "submitted")]

    # --- Calculate score ---
    score = 100

    # -3 per data broker listing
    score -= 3 * len(broker_listings)

    # Breaches: -5 with password, -2 without
    for b in breaches:
        details = _parse_details(b.get("details"))
        data_classes = details.get("data_classes", [])
        if "Passwords" in data_classes:
            score -= 5
        else:
            score -= 2

    # -1 per account found on tracking services
    score -= 1 * len(accounts)

    # +2 per confirmed removal
    score += 2 * len(confirmed_removals)

    # +1 per pending removal (in progress)
    score += 1 * len(pending_removals)

    # Clamp
    score = max(0, min(100, score))

    grade = _compute_grade(score)

    # --- Build risk factors ---
    risk_factors: list[str] = []

    for b in breaches:
        details = _parse_details(b.get("details"))
        data_classes = details.get("data_classes", [])
        site_name = b.get("site_name", "Unknown")
        if "Passwords" in data_classes:
            risk_factors.append(f"Password exposed in {site_name} breach")
        elif data_classes:
            exposed = ", ".join(data_classes[:3])
            risk_factors.append(f"{site_name} breach exposed: {exposed}")

    for bl in broker_listings:
        site_name = bl.get("site_name", "Unknown")
        risk_factors.append(f"Listed on {site_name}")

    # --- Build recommendations ---
    recommendations: list[str] = []

    # Password-exposed breaches
    pw_breaches = [
        b for b in breaches
        if "Passwords" in _parse_details(b.get("details")).get("data_classes", [])
    ]
    for b in pw_breaches:
        site_name = b.get("site_name", "Unknown")
        recommendations.append(f"Change password for {site_name}")

    if pw_breaches:
        recommendations.append(
            "Enable two-factor authentication on all breached accounts"
        )

    # Broker listing removals
    # Find brokers that don't already have a removal request
    removal_broker_slugs = {r.get("broker_slug", "") for r in removals}
    for bl in broker_listings:
        site_name = bl.get("site_name", "Unknown")
        # Use a normalized slug for comparison
        slug = site_name.lower().replace(" ", "-").replace(".", "-")
        if slug not in removal_broker_slugs:
            recommendations.append(f"Submit removal request to {site_name}")

    # General advice when there are findings but no specific recs yet
    if breaches and not pw_breaches:
        recommendations.append(
            "Monitor breached accounts for suspicious activity"
        )

    if not findings and not recommendations:
        recommendations.append(
            "Continue periodic scans to detect new exposures"
        )

    return PrivacyScore(
        score=score,
        grade=grade,
        findings_count=len(findings),
        breaches_count=len(breaches),
        broker_listings=len(broker_listings),
        accounts_found=len(accounts),
        removals_confirmed=len(confirmed_removals),
        removals_pending=len(pending_removals),
        risk_factors=risk_factors,
        recommendations=recommendations,
    )
