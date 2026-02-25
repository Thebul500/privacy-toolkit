"""Weekly/monthly digest of privacy activity."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Config
    from src.db import Database

logger = logging.getLogger(__name__)


def generate_digest(db: "Database", config: "Config", period: str = "weekly") -> dict:
    """Generate a privacy activity digest for the given period.

    Returns a dict with summary data, a text message, and a JSON payload.
    Skips (has_activity=False) when nothing happened in the period.
    """
    from src.scoring import calculate_score, get_trend
    from src.config import list_profiles

    days = 7 if period == "weekly" else 30
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    profiles = list_profiles()
    profile = profiles[0] if profiles else None

    # New findings in period
    all_findings = db.get_findings()
    new_findings = [f for f in all_findings if (f.get("found_at") or "") >= cutoff]

    # Removal activity in period
    all_removals = db.get_removals()
    recent_removals = [r for r in all_removals if (r.get("updated_at") or "") >= cutoff]
    removals_by_status: dict[str, int] = {}
    for r in recent_removals:
        s = r.get("status", "unknown")
        removals_by_status[s] = removals_by_status.get(s, 0) + 1

    # Score info
    score_current = None
    score_previous = None
    score_change = 0
    if profile:
        try:
            ps = calculate_score(db, profile)
            score_current = ps.score
            trend = get_trend(db, profile)
            key = "7d_change" if period == "weekly" else "30d_change"
            score_change = trend.get(key, 0)
            score_previous = score_current - score_change if score_change else score_current
        except Exception as e:
            logger.warning("Failed to get score for digest: %s", e)

    # Top risk factors
    top_risk_factors: list[str] = []
    if profile:
        try:
            ps = calculate_score(db, profile)
            top_risk_factors = ps.risk_factors[:5]
        except Exception:
            pass

    # Overdue removals
    overdue = db.get_overdue_removals()
    overdue_count = len(overdue)

    has_activity = bool(new_findings or recent_removals or score_change)

    # Build text message
    lines = [f"Privacy Toolkit — {period.title()} Digest"]
    lines.append(f"Period: last {days} days")
    lines.append("")
    if new_findings:
        lines.append(f"New exposures found: {len(new_findings)}")
    if removals_by_status:
        parts = [f"{v} {k}" for k, v in sorted(removals_by_status.items())]
        lines.append(f"Removal activity: {', '.join(parts)}")
    if score_current is not None:
        direction = "+" if score_change > 0 else ""
        lines.append(f"Privacy score: {score_current} ({direction}{score_change})")
    if overdue_count:
        lines.append(f"Overdue removals: {overdue_count}")
    if top_risk_factors:
        lines.append(f"Top risks: {'; '.join(top_risk_factors[:3])}")
    if not has_activity:
        lines.append("No activity this period.")

    text_message = "\n".join(lines)

    return {
        "period": period,
        "days": days,
        "new_findings_count": len(new_findings),
        "removals_confirmed": removals_by_status.get("confirmed", 0),
        "removals_submitted": removals_by_status.get("submitted", 0),
        "removals_reappeared": removals_by_status.get("reappeared", 0),
        "score_current": score_current,
        "score_previous": score_previous,
        "score_change": score_change,
        "top_risk_factors": top_risk_factors,
        "overdue_removals_count": overdue_count,
        "has_activity": has_activity,
        "text_message": text_message,
        "json_payload": {
            "period": period,
            "new_findings": len(new_findings),
            "removals": removals_by_status,
            "score": score_current,
            "score_change": score_change,
            "overdue": overdue_count,
        },
    }


def send_digest(db: "Database", config: "Config", period: str = "weekly") -> bool:
    """Generate and send a digest. Skips if no activity. Returns True if sent."""
    from src.notifications import notify

    digest = generate_digest(db, config, period)
    if not digest["has_activity"]:
        logger.info("No activity for %s digest, skipping send", period)
        return False

    notify("digest", digest["text_message"], config, details=digest["json_payload"])
    db.log("digest_sent", details={"period": period, "findings": digest["new_findings_count"]})
    return True
