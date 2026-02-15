"""SpiderFoot scanner - comprehensive OSINT via Docker container."""

from __future__ import annotations
import subprocess
from datetime import datetime

from src.models import ScanResult
from src.scanners.base import BaseScanner

DOCKER_IMAGE = "ghcr.io/smicallef/spiderfoot:latest"
CONTAINER_NAME = "privacy-toolkit-spiderfoot"
HOST_PORT = 5001


class SpiderfootScanner(BaseScanner):
    name = "spiderfoot"

    def __init__(self, port: int = HOST_PORT):
        self.port = port

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", DOCKER_IMAGE],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def is_running(self) -> bool:
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() == "true"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def start(self) -> bool:
        if self.is_running():
            return True
        # Remove stopped container if exists
        subprocess.run(
            ["docker", "rm", "-f", CONTAINER_NAME],
            capture_output=True, timeout=10,
        )
        result = subprocess.run(
            [
                "docker", "run", "-d",
                "--name", CONTAINER_NAME,
                "-p", f"{self.port}:5001",
                "--restart", "unless-stopped",
                DOCKER_IMAGE,
            ],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0

    def stop(self) -> bool:
        result = subprocess.run(
            ["docker", "stop", CONTAINER_NAME],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0

    def scan(self, query: str, query_type: str = "") -> list[ScanResult]:
        # SpiderFoot is interactive via web UI - this just ensures it's running
        if not self.is_running():
            self.start()
        return [ScanResult(
            scanner=self.name,
            site_name="SpiderFoot Web UI",
            site_url=f"http://localhost:{self.port}",
            data_type="web_ui",
            details={"message": f"SpiderFoot running at http://localhost:{self.port}"},
            confidence="high",
            found_at=datetime.now(),
        )]
