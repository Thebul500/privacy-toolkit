"""CSV export for scan findings and removal request data."""

from __future__ import annotations
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.db import Database

logger = logging.getLogger(__name__)

FINDINGS_COLUMNS = ["Date", "Scanner", "Site", "URL", "Data Type", "Confidence", "Details"]
REMOVALS_COLUMNS = ["Broker", "Method", "Status", "Submitted", "Confirmed", "Notes"]


def export_findings_csv(
    findings: list[dict],
    output_path: Optional[str] = None,
) -> str:
    """Export findings to a CSV file.

    Args:
        findings: List of finding dicts from Database.get_findings().
        output_path: Destination file path. Auto-generated if not provided.

    Returns:
        The path the CSV was written to.
    """
    if output_path:
        path = Path(output_path)
    else:
        path = DATA_DIR / "scans" / f"findings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting %d findings to CSV: %s", len(findings), path)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(FINDINGS_COLUMNS)
        for finding in findings:
            details = finding.get("details", {})
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except (json.JSONDecodeError, TypeError):
                    pass
            details_str = json.dumps(details, default=str) if isinstance(details, dict) else str(details)

            writer.writerow([
                (finding.get("found_at") or "")[:10],
                finding.get("source", ""),
                finding.get("site_name", ""),
                finding.get("site_url", ""),
                finding.get("data_type", ""),
                finding.get("confidence", ""),
                details_str,
            ])

    logger.info("CSV export complete: %s (%d rows)", path, len(findings))
    return str(path)


def export_removals_csv(
    removals: list[dict],
    output_path: Optional[str] = None,
) -> str:
    """Export removal requests to a CSV file.

    Args:
        removals: List of removal dicts from Database.get_removals().
        output_path: Destination file path. Auto-generated if not provided.

    Returns:
        The path the CSV was written to.
    """
    if output_path:
        path = Path(output_path)
    else:
        path = DATA_DIR / "scans" / f"removals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting %d removals to CSV: %s", len(removals), path)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(REMOVALS_COLUMNS)
        for removal in removals:
            writer.writerow([
                removal.get("broker_name", ""),
                removal.get("method", ""),
                removal.get("status", ""),
                (removal.get("submitted_at") or "")[:10],
                (removal.get("confirmed_at") or "")[:10],
                removal.get("notes", "") or "",
            ])

    logger.info("CSV export complete: %s (%d rows)", path, len(removals))
    return str(path)


def export_findings(db: Database, profile: Optional[str] = None, output: Optional[str] = None) -> str:
    """High-level export: query findings from DB and write CSV.

    Mirrors the interface of json_export.export_findings for CLI integration.
    """
    findings = db.get_findings(profile=profile)
    return export_findings_csv(findings, output)


def export_removals(db: Database, profile: Optional[str] = None, output: Optional[str] = None) -> str:
    """High-level export: query removals from DB and write CSV.

    Mirrors the interface of json_export.export_removals for CLI integration.
    """
    removals = db.get_removals(profile=profile)
    return export_removals_csv(removals, output)
