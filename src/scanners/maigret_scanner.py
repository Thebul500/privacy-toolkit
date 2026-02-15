"""Maigret scanner - username search across 1300+ sites."""

from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from src.models import ScanResult
from src.scanners.base import BaseScanner


class MaigretScanner(BaseScanner):
    name = "maigret"

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "maigret", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def scan(self, query: str, query_type: str = "username") -> list[ScanResult]:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "report.json"
            cmd = [
                sys.executable, "-m", "maigret",
                query,
                "--json", "notype",
                "-o", str(output_file),
                "--timeout", "30",
                "--no-color",
            ]
            try:
                subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600,
                )
            except subprocess.TimeoutExpired:
                pass

            results = []
            if output_file.exists():
                try:
                    with open(output_file) as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    return results

                # Maigret JSON format varies, handle common structures
                sites = data if isinstance(data, list) else data.get("sites", [])
                if isinstance(data, dict) and not sites:
                    # Try flat dict format: {site_name: {url: ..., status: ...}}
                    for site_name, info in data.items():
                        if isinstance(info, dict) and info.get("status"):
                            status = str(info["status"]).lower()
                            if "claimed" in status or "found" in status:
                                results.append(ScanResult(
                                    scanner=self.name,
                                    site_name=site_name,
                                    site_url=info.get("url", ""),
                                    data_type="username_match",
                                    details={"username": query, "tags": info.get("tags", [])},
                                    confidence="high",
                                    found_at=datetime.now(),
                                ))
                else:
                    for site in sites:
                        if isinstance(site, dict):
                            status = str(site.get("status", "")).lower()
                            if "claimed" in status or "found" in status:
                                results.append(ScanResult(
                                    scanner=self.name,
                                    site_name=site.get("site_name", site.get("name", "unknown")),
                                    site_url=site.get("url_user", site.get("url", "")),
                                    data_type="username_match",
                                    details={"username": query, "tags": site.get("tags", [])},
                                    confidence="high",
                                    found_at=datetime.now(),
                                ))
            return results
