"""PhoneInfoga scanner - phone number OSINT."""

from __future__ import annotations
import json
import subprocess
from datetime import datetime
from pathlib import Path

from src.config import BIN_DIR
from src.models import ScanResult
from src.scanners.base import BaseScanner


class PhoneInfogaScanner(BaseScanner):
    name = "phoneinfoga"

    def __init__(self, binary_path: str = ""):
        self.binary = Path(binary_path) if binary_path else BIN_DIR / "phoneinfoga"

    def is_available(self) -> bool:
        if not self.binary.exists():
            return False
        try:
            result = subprocess.run(
                [str(self.binary), "version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def scan(self, query: str, query_type: str = "phone") -> list[ScanResult]:
        cmd = [str(self.binary), "scan", "-n", query]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            return []

        results = []
        output = proc.stdout

        # PhoneInfoga outputs structured text, parse it
        # Try JSON output first
        try:
            data = json.loads(output)
            if isinstance(data, dict):
                results.append(ScanResult(
                    scanner=self.name,
                    site_name="PhoneInfoga",
                    site_url="",
                    data_type="phone_info",
                    details=data,
                    confidence="high",
                    found_at=datetime.now(),
                ))
                return results
        except (json.JSONDecodeError, ValueError):
            pass

        # Parse text output
        if output.strip():
            info = {}
            for line in output.splitlines():
                line = line.strip()
                if ":" in line:
                    key, _, val = line.partition(":")
                    info[key.strip().lower()] = val.strip()

            if info:
                results.append(ScanResult(
                    scanner=self.name,
                    site_name="PhoneInfoga",
                    site_url="",
                    data_type="phone_info",
                    details={"phone": query, "raw": info},
                    confidence="medium",
                    found_at=datetime.now(),
                ))

        return results
