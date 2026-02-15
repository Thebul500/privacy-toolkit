"""Sherlock scanner - username search across 400+ social networks."""

from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from src.models import ScanResult
from src.scanners.base import BaseScanner


class SherlockScanner(BaseScanner):
    name = "sherlock"

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "sherlock_project", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def scan(self, query: str, query_type: str = "username") -> list[ScanResult]:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / f"{query}.json"
            cmd = [
                sys.executable, "-m", "sherlock_project",
                query,
                "--json", str(output_file),
                "--timeout", "20",
                "--print-found",
            ]
            try:
                subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300,
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

                # Sherlock JSON: {username: {site_name: {url_user: ..., status: ...}}}
                user_data = data.get(query, data)
                if isinstance(user_data, dict):
                    for site_name, info in user_data.items():
                        if isinstance(info, dict):
                            url = info.get("url_user", "")
                            status = info.get("status", "")
                            if status and "claimed" in str(status).lower():
                                continue
                            results.append(ScanResult(
                                scanner=self.name,
                                site_name=site_name,
                                site_url=url,
                                data_type="username_match",
                                details={"status": status, "username": query},
                                confidence="high" if url else "medium",
                                found_at=datetime.now(),
                            ))
            return results
