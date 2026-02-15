"""JSON export for scan results and tracking data."""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.db import Database


def export_findings(db: Database, profile: Optional[str] = None, output: Optional[str] = None) -> str:
    findings = db.get_findings(profile=profile)
    data = {
        "exported_at": datetime.now().isoformat(),
        "profile": profile,
        "total_findings": len(findings),
        "findings": findings,
    }
    if output:
        path = Path(output)
    else:
        path = DATA_DIR / "scans" / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return str(path)


def export_removals(db: Database, profile: Optional[str] = None, output: Optional[str] = None) -> str:
    removals = db.get_removals(profile=profile)
    data = {
        "exported_at": datetime.now().isoformat(),
        "profile": profile,
        "total_requests": len(removals),
        "removal_requests": removals,
    }
    if output:
        path = Path(output)
    else:
        path = DATA_DIR / "scans" / f"removals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return str(path)
