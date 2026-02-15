"""Base scanner interface."""

from __future__ import annotations
from abc import ABC, abstractmethod

from src.models import ScanResult


class BaseScanner(ABC):
    name: str = "base"

    @abstractmethod
    def scan(self, query: str, query_type: str = "") -> list[ScanResult]:
        """Run a scan and return results."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this scanner's dependencies are installed."""
