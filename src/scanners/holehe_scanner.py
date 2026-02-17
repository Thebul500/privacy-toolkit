"""Holehe scanner - check if email is registered on 120+ sites."""

from __future__ import annotations
import asyncio
import importlib
import logging
import pkgutil
from datetime import datetime

logger = logging.getLogger(__name__)

from src.models import ScanResult
from src.scanners.base import BaseScanner


class HoleheScanner(BaseScanner):
    name = "holehe"

    def is_available(self) -> bool:
        try:
            import holehe  # noqa: F401
            return True
        except ImportError:
            logger.debug("Holehe not available: package not installed")
            return False

    def scan(self, query: str, query_type: str = "email") -> list[ScanResult]:
        try:
            return asyncio.get_event_loop().run_until_complete(self._async_scan(query))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._async_scan(query))
            finally:
                loop.close()

    async def _async_scan(self, email: str) -> list[ScanResult]:
        try:
            import httpx
            from holehe import modules as holehe_modules
        except ImportError:
            logger.warning("Holehe or httpx not installed, skipping scan for email=%r", email)
            return []

        # Discover all holehe modules
        modules = []
        for importer, modname, ispkg in pkgutil.walk_packages(
            holehe_modules.__path__, holehe_modules.__name__ + "."
        ):
            if not ispkg:
                try:
                    mod = importlib.import_module(modname)
                    # Each module has a function with the same name as the module
                    func_name = modname.split(".")[-1]
                    if hasattr(mod, func_name):
                        modules.append(getattr(mod, func_name))
                except (ImportError, AttributeError) as e:
                    logger.warning("Failed to load holehe module %s: %s", modname, e)
                    continue

        out: list[dict] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            tasks = []
            for module_func in modules:
                try:
                    tasks.append(module_func(email, client, out))
                except Exception as e:
                    logger.warning("Failed to create task for holehe module %s: %s", module_func.__name__, e)
                    continue
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for entry in out:
            if isinstance(entry, dict) and entry.get("exists") is True:
                results.append(ScanResult(
                    scanner=self.name,
                    site_name=entry.get("name", "unknown"),
                    site_url=entry.get("domain", ""),
                    data_type="email_registered",
                    details={
                        "email": email,
                        "rateLimit": entry.get("rateLimit", False),
                        "emailrecovery": entry.get("emailrecovery"),
                        "phoneNumber": entry.get("phoneNumber"),
                    },
                    confidence="high",
                    found_at=datetime.now(),
                ))
        return results
